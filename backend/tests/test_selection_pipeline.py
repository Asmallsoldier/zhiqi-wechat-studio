"""Isolated contracts: no real model, provider or WeChat traffic."""
import asyncio
from datetime import datetime, timezone, timedelta
import json
import time
import uuid
import httpx
import pytest
from fastapi.testclient import TestClient
from app import db, main, selection_pipeline as p
from app.domain import Listing, article_draft
from app.editorial import select_report, validate_article, EditorialBlock, wechat_html
from app.publication_bridge import BridgeError, PublicationBridge, CONTRACT, checked_receipt, official_url

ACCOUNT = '00000000-0000-4000-8000-000000000002'

def samples():
    return [Listing(external_id=str(n), title=f'测试手机样本{n}', model='测试型号', variant='256GB',
        condition='good', price=price, category='phone', seller_ref=f'seller-{n}', battery_health=90,
        inspection_available=True, repair_status='verified_original',
        url=f'https://www.goofish.com/item?id={n}', observed_at=datetime.now(timezone.utc)).public()
        for n, price in enumerate([1000,1000,1000,1000,1000,900])]

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DB_PATH',str(tmp_path/'isolated.db'))
    monkeypatch.setenv('STUDIO_SOURCE_SCHEDULER','false')
    monkeypatch.setenv('STUDIO_PIPELINE_WORKER','false')
    async def grant_account(*args):pass
    monkeypatch.setattr(main,'require_account_access',grant_account)
    main.app.dependency_overrides[main.identity]=lambda:'alice'
    with TestClient(main.app) as c:yield c
    main.app.dependency_overrides.clear()

def create_run(client,**changes):
    client.post('/api/v1/research/listings/import',json={'items':samples()})
    ids=[x['id'] for x in client.get('/api/v1/research/listings').json()['data']]
    req={'request_id':str(uuid.uuid4()),'account_id':ACCOUNT,'listing_ids':ids,'use_ai':False,
         'title':'二手数码选购核验指南',**changes}
    response=client.post('/api/v1/research/selection-runs',json=req)
    assert response.status_code==200,response.text
    return response.json()['data'],req

def get_run(run):
    with db.connect() as c:return p.row_for(c,run['id'],'alice')

class FakeBridge:
    def __init__(self,mode='draft_only',ambiguous=False):
        self.mode,self.ambiguous=mode,ambiguous
        self.submits=self.queries=self.probes=0
    async def capabilities(self,account,mode):
        self.probes+=1
        return {'contractVersion':CONTRACT,'accountId':account,'deliveryModes':[mode],'idempotentSubmission':True}
    async def submit(self,run,payload):
        self.submits+=1
        assert {x['key'] for x in payload['images']}=={'cover','comparison','risks'}
        assert '{{image:comparison}}' in payload['html']
        assert payload['contentHash']==run['content_hash']
        if self.ambiguous:raise BridgeError('NETWORK_UNKNOWN','网络结果未确认',True,True)
        return {'status':'draft_delivered','draftMediaId':'test-draft-id'} if self.mode=='draft_only' else {'status':'publishing','publishId':'test-publish-id'}
    async def query(self,run):
        self.queries+=1
        return {'status':'published','articleId':'test-article','publishedUrl':'https://mp.weixin.qq.com/s/test-article'} if self.mode=='publish' else {'status':'draft_delivered','draftMediaId':'test-draft-id'}

def drain(run,bridge,count=8):
    for _ in range(count):asyncio.run(p.advance(run['id'],'alice','Bearer unit-test',bridge))

def test_draft_pipeline_freezes_data_and_embeds_two_original_images(client):
    run,_=create_run(client);bridge=FakeBridge();drain(run,bridge)
    stored=get_run(run)
    assert stored['status']=='draft_delivered' and stored['submit_intent']==1 and bridge.submits==1
    snapshot=json.loads(stored['snapshot_json'])
    assert snapshot['review']['passed'] and len(snapshot['items'])==6
    visible=client.get('/api/v1/research/selection-runs').json()['data'][0]
    assert 'base64' not in json.dumps(visible) and 'Bearer' not in json.dumps(visible)
    drain(run,bridge);assert bridge.submits==1

def test_publish_processing_is_not_success_until_final_receipt(client):
    run,_=create_run(client,delivery_mode='publish',acknowledge_automatic_publishing=True)
    bridge=FakeBridge(mode='publish');drain(run,bridge,7)
    assert get_run(run)['status']=='publishing'
    assert not json.loads(get_run(run)['receipt_json']).get('publishedUrl')
    p.resume(run['id'],'alice');drain(run,bridge,1)
    assert get_run(run)['status']=='published' and bridge.submits==bridge.queries==1

def test_ambiguous_submission_after_restart_queries_only(client):
    run,_=create_run(client);bridge=FakeBridge(ambiguous=True);drain(run,bridge,7)
    assert get_run(run)['stage']=='reconcile'
    p.recover_after_restart();assert get_run(run)['error_code']=='SESSION_REQUIRED'
    p.resume(run['id'],'alice');drain(run,bridge,2)
    assert get_run(run)['status']=='draft_delivered' and bridge.submits==bridge.queries==1

def test_idempotency_account_lock_and_owner_isolation(client):
    run,req=create_run(client)
    assert client.post('/api/v1/research/selection-runs',json=req).json()['data']['id']==run['id']
    assert client.post('/api/v1/research/selection-runs',json={**req,'title':'另一篇文章'}).status_code==409
    assert client.post('/api/v1/research/selection-runs',json={**req,'request_id':str(uuid.uuid4())}).json()['code']=='ACCOUNT_RUN_ACTIVE'
    main.app.dependency_overrides[main.identity]=lambda:'bob'
    assert client.get('/api/v1/research/selection-runs').json()['data']==[]
    assert client.get('/api/v1/research/selection-runs/'+run['id']).status_code==404
    for action in ('resume','cancel'):
        assert client.post(f"/api/v1/research/selection-runs/{run['id']}/{action}").status_code==404
    assert client.post('/api/v1/research/selection-runs',json={**req,'request_id':str(uuid.uuid4())}).status_code==404

def test_missing_source_and_unacknowledged_publish_rejected(client):
    for data in ({'query':'手机','delivery_mode':'publish'},{},{'query':'x'}):
        assert client.post('/api/v1/research/selection-runs',json={'request_id':str(uuid.uuid4()),'account_id':ACCOUNT,**data}).status_code==422

def test_no_selection_does_not_write_or_submit(client):
    run,_=create_run(client)
    snapshot=json.loads(get_run(run)['snapshot_json']);snapshot['items']=snapshot['items'][:2]
    with db.connect() as c:c.execute('UPDATE selection_run SET snapshot_json=? WHERE id=?',(db.dump(snapshot),run['id']))
    bridge=FakeBridge();drain(run,bridge)
    assert get_run(run)['status']=='no_selection' and bridge.submits==0
    with db.connect() as c:assert c.execute('SELECT count(*) FROM article').fetchone()[0]==0

def test_same_frozen_samples_blocked_before_second_article(client):
    run,req=create_run(client);bridge=FakeBridge();drain(run,bridge)
    second=client.post('/api/v1/research/selection-runs',json={**req,'request_id':str(uuid.uuid4())}).json()['data']
    drain(second,bridge)
    assert get_run(second)['error_code']=='DUPLICATE_SELECTION' and bridge.submits==1

def test_lease_fencing_and_irrevocable_submit_intent(client):
    run,_=create_run(client);claim=p.claim(run['id'],'alice')
    assert p.claim(run['id'],'alice') is None
    with pytest.raises(p.PipelineError):p.cancel(run['id'],'alice')
    with db.connect() as c:c.execute('UPDATE selection_run SET lease_until=? WHERE id=?',(time.time()-1,run['id']))
    with pytest.raises(p.PipelineError):p.save(claim,stage='collect')
    with db.connect() as c:c.execute('UPDATE selection_run SET submit_intent=1,lease_until=0 WHERE id=?',(run['id'],))
    with pytest.raises(p.PipelineError):p.cancel(run['id'],'alice')
    assert p.resume(run['id'],'alice')['stage']=='reconcile'

def test_stale_blocks_new_submit_but_allows_reconciliation(client):
    run,_=create_run(client);bridge=FakeBridge();drain(run,bridge,6)
    snapshot=json.loads(get_run(run)['snapshot_json'])
    for group in snapshot['report']['groups']:
        for item in group['candidates']:item['observed_at']=(datetime.now(timezone.utc)-timedelta(days=4)).isoformat()
    with db.connect() as c:c.execute('UPDATE selection_run SET snapshot_json=? WHERE id=?',(db.dump(snapshot),run['id']))
    drain(run,bridge,1)
    assert get_run(run)['error_code']=='SELECTION_STALE' and bridge.submits==0
    with db.connect() as c:c.execute('UPDATE selection_run SET submit_intent=1 WHERE id=?',(run['id'],))
    p.resume(run['id'],'alice');drain(run,bridge,1)
    assert get_run(run)['status']=='draft_delivered' and bridge.queries==1

def test_unknown_model_is_never_called_again(client,monkeypatch):
    run,_=create_run(client,use_ai=True)
    monkeypatch.setattr(main,'AI_KEY','test');monkeypatch.setattr(main,'AI_BASE','https://model.example/v1');monkeypatch.setattr(main,'AI_MODEL','test')
    bridge=FakeBridge();drain(run,bridge,3)
    aid=str(uuid.uuid4());rid=str(uuid.uuid5(uuid.UUID(run['id']),'selection-article-v1'))
    with db.connect() as c:
        c.execute('INSERT INTO article(id,owner,research_id,request_id,status,title,body,mode,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                  (aid,'alice',run['id'],rid,'uncertain','保留稿','保留内容','ai',datetime.now(timezone.utc).isoformat()))
    async def forbidden(*a,**kw):raise AssertionError('must not call again')
    monkeypatch.setattr(main,'article_create',forbidden);drain(run,bridge,2)
    assert get_run(run)['error_code']=='ARTICLE_RESULT_UNCONFIRMED'
    with db.connect() as c:c.execute("UPDATE article SET status='needs_review',body=? WHERE id=?",(article_draft(select_report(samples()),'选购文章'),aid))
    p.resume(run['id'],'alice');drain(run,bridge,1)
    assert get_run(run)['stage']=='validate'

def test_provider_unknown_does_not_recollect(client,monkeypatch):
    run,_=create_run(client,listing_ids=[],query='测试手机');bridge=FakeBridge();drain(run,bridge,1)
    calls=[]
    async def unavailable(query):
        calls.append(query);raise main.SourceError('XIANYU_PROVIDER_UNAVAILABLE')
    monkeypatch.setattr(p.xianyu,'search',unavailable);drain(run,bridge,1)
    p.resume(run['id'],'alice');drain(run,bridge,1)
    assert get_run(run)['error_code']=='COLLECTION_OUTCOME_UNKNOWN' and len(calls)==1

def test_quality_gate_blocks_invented_prices_claims_urls():
    report=select_report(samples());article={'title':'选购文章','body':article_draft(report,'选购文章')}
    assert validate_article(article,report)['passed']
    for extra in ('最低只要1元。','本人亲测，保证升值。','https://unknown.example/item','折扣99%'):
        with pytest.raises(EditorialBlock):validate_article({**article,'body':article['body']+'\n'+extra},report)

@pytest.mark.parametrize('value',['http://mp.weixin.qq.com/s/abc','https://evil.example/s/abc','https://mp.weixin.qq.com.evil.example/s/abc','https://mp.weixin.qq.com/s/abc?access_token=secret','https://u:p@mp.weixin.qq.com/s/abc','javascript:alert(1)','https://mp.weixin.qq.com/s'])
def test_final_urls(value):assert official_url(value)==''

def test_receipt_binding_and_required_final_link():
    run={'id':'run','account_id':ACCOUNT,'content_hash':'hash','delivery_mode':'publish'}
    data={'contractVersion':CONTRACT,'requestId':'run','accountId':ACCOUNT,'contentHash':'hash','deliveryMode':'publish','status':'published','articleId':'article','publishedUrl':'https://mp.weixin.qq.com/s/abc'}
    assert checked_receipt(data,run)['status']=='published'
    for key in ('accountId','contentHash','requestId','deliveryMode','contractVersion'):
        with pytest.raises(BridgeError):checked_receipt({**data,key:'other'},run)
    assert checked_receipt({**data,'publishedUrl':''},run)['status']=='reconciling'
    assert checked_receipt({**data,'articleId':''},run)['status']=='reconciling'

def test_html_does_not_execute_source_markup():
    rendered=wechat_html('# 标题\n\n<script>alert(1)</script> ![bad](https://evil.example/x) [坏链接](javascript:alert(1))')
    assert '<script>' not in rendered and 'src="https://evil' not in rendered and '<a href="javascript' not in rendered
    assert rendered.count('<img')==2

def test_transport_error_redaction_and_no_put_retry(monkeypatch):
    calls=[]
    async def handler(request):
        calls.append(request.method);raise httpx.ReadTimeout('secret token in endpoint',request=request)
    real=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
    with pytest.raises(BridgeError) as exc:asyncio.run(PublicationBridge('https://shared.example','Bearer test').submit({'id':'test'},{}))
    assert exc.value.unknown and 'secret' not in exc.value.message and calls==['PUT']

def test_session_permissions_and_emergency_stop(monkeypatch):
    data={'userId':'alice','status':'active','permissions':['wechat.read','wechat.write'],'role':'wechat_operator'}
    real=httpx.AsyncClient
    async def handler(request):return httpx.Response(200,json={'data':data})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
    with pytest.raises(main.HTTPException) as exc:asyncio.run(main.validate_session('Bearer unit',execute=True))
    assert exc.value.status_code==403
    data['permissions'].append('wechat.execute')
    assert asyncio.run(main.validate_session('Bearer unit',execute=True))=='alice'
    monkeypatch.setattr(main,'STOP',True)
    with pytest.raises(main.HTTPException) as exc:asyncio.run(main.validate_session('Bearer unit',execute=True))
    assert exc.value.detail['code']=='EMERGENCY_STOP'

@pytest.mark.parametrize('phrase',['租赁','月租','首付','补差价','仅配件','仅主板'])
def test_installments_rentals_and_parts_not_selected(phrase):
    rows=samples();rows[-1]['title']=phrase+'测试手机'
    with pytest.raises(EditorialBlock) as exc:select_report(rows)
    assert exc.value.code=='NO_QUALIFIED_SELECTION'

def test_real_bridge_transport_contract_through_processing_to_final(client,monkeypatch):
    run,_=create_run(client,delivery_mode='publish',acknowledge_automatic_publishing=True)
    drain(run,FakeBridge(),6)
    stored=get_run(run);calls=[]
    async def handler(request):
        assert request.headers['Authorization']=='Bearer fixture'
        calls.append((request.method,request.url.path))
        if request.url.path.endswith('/capabilities'):
            assert request.url.params['accountId']==ACCOUNT
            return httpx.Response(200,json={'success':True,'data':{'contractVersion':CONTRACT,'accountId':ACCOUNT,'idempotentSubmission':True,'deliveryModes':['publish']}})
        data={'contractVersion':CONTRACT,'requestId':run['id'],'accountId':ACCOUNT,'contentHash':stored['content_hash'],'deliveryMode':'publish'}
        if request.method=='PUT':
            body=json.loads(request.content);assert body['requestId']==run['id'] and body['contentHash']==stored['content_hash']
            assert len(body['images'])==3
            data.update(status='publishing',publishId='publish-fixture')
        else:data.update(status='published',publishId='publish-fixture',articleId='article-fixture',publishedUrl='https://mp.weixin.qq.com/s/fixture')
        return httpx.Response(200,json={'success':True,'data':data})
    real=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
    bridge=PublicationBridge('https://shared.example','Bearer fixture')
    drain(run,bridge,1);assert get_run(run)['status']=='publishing'
    p.resume(run['id'],'alice');drain(run,bridge,1)
    assert get_run(run)['status']=='published'
    assert [x[0] for x in calls]==['GET','PUT','GET']

def test_unavailable_contract_stops_before_paid_work(client,monkeypatch):
    run,_=create_run(client,use_ai=True)
    async def handler(request):return httpx.Response(404,json={'success':False})
    real=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
    drain(run,PublicationBridge('https://shared.example','Bearer fixture'))
    assert get_run(run)['error_code']=='PUBLICATION_CONTRACT_UNAVAILABLE'
    with db.connect() as c:assert c.execute('SELECT count(*) FROM article').fetchone()[0]==0

def test_wrong_account_receipt_can_only_reconcile_same_request(client,monkeypatch):
    run,_=create_run(client);drain(run,FakeBridge(),6)
    stored=get_run(run);calls=[]
    async def handler(request):
        calls.append(request.method)
        if request.url.path.endswith('/capabilities'):
            return httpx.Response(200,json={'success':True,'data':{'contractVersion':CONTRACT,'accountId':ACCOUNT,'idempotentSubmission':True,'deliveryModes':['draft_only']}})
        data={'contractVersion':CONTRACT,'requestId':run['id'],'accountId':'wrong-account' if request.method=='PUT' else ACCOUNT,
              'contentHash':stored['content_hash'],'deliveryMode':'draft_only','status':'draft_delivered','draftMediaId':'draft-fixture'}
        return httpx.Response(200,json={'success':True,'data':data})
    real=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
    bridge=PublicationBridge('https://shared.example','Bearer fixture');drain(run,bridge,1)
    assert get_run(run)['error_code']=='PUBLICATION_RECEIPT_MISMATCH' and get_run(run)['submit_intent']==1
    p.resume(run['id'],'alice');drain(run,bridge,1)
    assert get_run(run)['status']=='draft_delivered' and calls==['GET','PUT','GET']

def test_confirmed_collection_snapshot_survives_restart_without_recollect(client,monkeypatch):
    run,_=create_run(client,listing_ids=[],query='测试手机')
    bridge=FakeBridge();drain(run,bridge,1)
    with db.connect() as c:
        c.execute('UPDATE selection_run SET snapshot_json=? WHERE id=?',(db.dump({'collect_intent':True,'items':samples()}),run['id']))
    async def forbidden(query):raise AssertionError('confirmed provider receipt must not be requested twice')
    monkeypatch.setattr(p.xianyu,'search',forbidden)
    p.recover_after_restart();p.resume(run['id'],'alice');drain(run,bridge,1)
    assert get_run(run)['stage']=='analyze'

def test_remote_blocked_permission_is_not_displayed_as_processing(client):
    run,_=create_run(client);drain(run,FakeBridge(),6)
    claim=p.claim(run['id'],'alice');p.freeze_intent(claim)
    p.apply_receipt(claim,{'status':'blocked','errorCode':'WECHAT_48001'})
    stored=get_run(run)
    assert stored['status']=='blocked' and '接口权限' in stored['message']
    assert stored['submit_intent']==1


@pytest.mark.parametrize('blocker',['PUBLICATION_PERMISSION_REQUIRED','PUBLICATION_BRIDGE_DISABLED','PUBLICATION_EXTERNAL_DISABLED','PUBLICATION_DAILY_LIMIT'])
def test_capability_returns_precise_safe_blocker(monkeypatch,blocker):
    real=httpx.AsyncClient
    async def handler(request):
        return httpx.Response(200,json={'success':True,'data':{'contractVersion':CONTRACT,'accountId':ACCOUNT,'idempotentSubmission':True,'deliveryModes':[],'blockedReason':blocker}})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
    with pytest.raises(BridgeError) as exc:asyncio.run(PublicationBridge('https://shared.example','Bearer fixture').capabilities(ACCOUNT,'publish'))
    assert exc.value.code==blocker

def test_background_worker_revalidates_each_stage_and_completes_one_draft(client,monkeypatch):
    run,_=create_run(client);bridge=FakeBridge();checks=[]
    async def session(token,execute=False):
        checks.append(execute);return 'alice'
    monkeypatch.setattr(main,'validate_session',session)
    monkeypatch.setattr(p,'PublicationBridge',lambda *args:bridge)
    async def exercise():
        worker=p.PipelineWorker();worker.authorize(run['id'],'alice','Bearer private-test-token')
        task=asyncio.create_task(worker.serve(interval=0.001))
        try:
            async def until_done():
                while get_run(run)['status']!='draft_delivered':await asyncio.sleep(0.01)
            await asyncio.wait_for(until_done(),timeout=3)
            assert not worker.sessions
        finally:
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass
    asyncio.run(exercise())
    assert len(checks)>=7 and all(checks) and bridge.submits==1
    with db.connect() as c:
        saved=c.execute('SELECT snapshot_json,payload_json,receipt_json,request_json FROM selection_run').fetchone()
    assert 'private-test-token' not in str(tuple(saved))

def test_background_worker_permission_revoked_between_stages_blocks_submission(client,monkeypatch):
    run,_=create_run(client);bridge=FakeBridge();checks=[]
    async def session(token,execute=False):
        checks.append(execute)
        if len(checks)>1:raise main.fail('FORBIDDEN','没有发表执行权限',403)
        return 'alice'
    monkeypatch.setattr(main,'validate_session',session)
    monkeypatch.setattr(p,'PublicationBridge',lambda *args:bridge)
    async def exercise():
        worker=p.PipelineWorker();worker.authorize(run['id'],'alice','Bearer test')
        task=asyncio.create_task(worker.serve(interval=0.001))
        try:
            async def until_blocked():
                while get_run(run)['status']!='blocked':await asyncio.sleep(0.01)
            await asyncio.wait_for(until_blocked(),timeout=3)
        finally:
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass
    asyncio.run(exercise())
    assert get_run(run)['error_code']=='FORBIDDEN' and bridge.submits==0

def test_refresh_time_alone_does_not_reopen_duplicate_deal():
    from app.editorial import selection_hash
    original=samples()
    refreshed=[{**x,'observed_at':(datetime.fromisoformat(x['observed_at'])+timedelta(seconds=5)).isoformat()} for x in original]
    assert selection_hash(original)==selection_hash(refreshed)
    refreshed[-1]['price']='850'
    assert selection_hash(original)!=selection_hash(refreshed)

def test_provider_aliases_do_not_inflate_same_goofish_items():
    from app.domain import analyze
    from app.editorial import selection_hash
    original=samples()[:3]
    duplicates=[{**x,'source_id':'authorized_provider','external_id':'provider-'+x['external_id']} for x in original]
    report=analyze(original+duplicates)
    assert report['sample_count']==3 and report['groups'][0]['sample_count']==3
    assert selection_hash(original)==selection_hash(original+duplicates)
    with pytest.raises(EditorialBlock):select_report(original+duplicates)

def test_duplicate_item_keeps_latest_observation_not_list_order():
    from app.domain import analyze
    original=samples()[:1]
    old={**original[0],'observed_at':(datetime.now(timezone.utc)-timedelta(days=4)).isoformat(),'price':'200'}
    for rows in ([old,*original],[*original,old]):
        report=analyze(rows)
        assert report['groups'][0]['sample_count']==1
        assert report['groups'][0]['median_asking_price']==1000

def test_conflicting_same_timestamp_prices_do_not_become_a_bargain():
    from app.domain import analyze
    rows=samples(); conflicting={**rows[-1],'price':'10','source_id':'authorized_provider'}
    report=analyze(rows+[conflicting])
    group=report['groups'][0]
    assert group['sample_count']==5
    assert all(c['verdict']!='值得核验' for c in group['candidates'])
    assert any('资料不一致' in risk for c in group['candidates'] for risk in c['risks'])

def test_price_formatting_does_not_create_conflicts_or_new_selection():
    from app.domain import analyze
    from app.editorial import selection_hash
    rows=samples()
    formatted=[{**x,'price':str(x['price'])+'.00' if '.' not in str(x['price']) else x['price']} for x in rows]
    assert selection_hash(rows)==selection_hash(formatted)
    report=analyze(rows+formatted)
    assert report['sample_count']==6 and not any(c['risks'] for c in report['groups'][0]['candidates'])

def test_unauthorized_account_cannot_reserve_other_owners_activity_slot(client,monkeypatch):
    async def denied(*args):raise main.fail('ACCOUNT_ACCESS_REQUIRED','无权操作该公众号',403)
    monkeypatch.setattr(main,'require_account_access',denied)
    response=client.post('/api/v1/research/selection-runs',json={'request_id':str(uuid.uuid4()),'account_id':ACCOUNT,'query':'测试手机'})
    assert response.status_code==403
    with db.connect() as c:assert c.execute('SELECT count(*) FROM selection_run').fetchone()[0]==0

def test_account_check_fails_closed_on_malformed_or_foreign_account_response(monkeypatch):
    real=httpx.AsyncClient
    for data in (None,[],[{'accountId':ACCOUNT,'platform':'douyin'}],[{'accountId':'other','platform':'wechat_official'}]):
        async def handler(request):return httpx.Response(200,json={'success':True,'data':data})
        monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
        with pytest.raises(main.HTTPException):asyncio.run(main.require_account_access(ACCOUNT,'Bearer test'))
