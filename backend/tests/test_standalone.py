"""Standalone integration tests. Official endpoints are mocked; no real publication."""
import asyncio
import json
import time
import uuid
from collections import Counter

import httpx
import pytest
from fastapi.testclient import TestClient
from app import db, main, local_identity as auth, local_store as store, local_publication as pub, selection_pipeline as pipeline
from app.local_routes import router
from test_selection_pipeline import samples

PASSWORD='Only-a-test-password-2026'

@pytest.fixture
def local(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DB_PATH',str(tmp_path/'studio.db'))
    monkeypatch.setattr(main,'STUDIO_MODE','standalone')
    monkeypatch.setenv('STUDIO_SOURCE_SCHEDULER','false')
    monkeypatch.setenv('STUDIO_PIPELINE_WORKER','false')
    monkeypatch.setenv('STUDIO_DRAFT_ENABLED','true')
    monkeypatch.setenv('STUDIO_PUBLISH_ENABLED','true')
    async def idle():await asyncio.Event().wait()
    monkeypatch.setattr(pub,'worker',idle)
    original=list(main.app.router.routes)
    main.app.include_router(router,prefix='/api/v1')
    added=main.app.router.routes[len(original):]
    main.app.router.routes[:]=added+original
    try:
        with TestClient(main.app) as client:
            alice=auth.create_user('alice',PASSWORD,'super_admin')
            bob=auth.create_user('bobby',PASSWORD,'wechat_operator')
            reader=auth.create_user('reader',PASSWORD,'readonly_operator')
            def login(name):
                r=client.post('/api/v1/auth/login',json={'username':name,'password':PASSWORD})
                assert r.status_code==200,r.text
                return r.json()['data']
            a,b,r=login('alice'),login('bobby'),login('reader')
            yield client,alice,bob,a,b,r
    finally:main.app.router.routes[:]=original

def headers(tokens):return {'Authorization':'Bearer '+tokens['accessToken']}

def account(local):
    c,owner,_,tokens,_,_=local;h=headers(tokens);id=str(uuid.uuid4())
    assert c.post('/api/v1/wechat-workspace/accounts',headers=h,json={'requestId':id,'accountName':'Test account','allowPublish':True}).status_code==200
    r=c.put('/api/v1/wechat-workspace/accounts/'+id+'/credential',headers=h,json={'appId':'wx000000000000test','appSecret':'test-only-fake-app-secret'})
    assert r.status_code==200,r.text
    return id

def frozen(local,mode='publish'):
    c,owner,_,tokens,_,_=local;h=headers(tokens);id=account(local)
    assert c.post('/api/v1/research/listings/import',headers=h,json={'items':samples()}).status_code==200
    ids=[x['id'] for x in c.get('/api/v1/research/listings',headers=h).json()['data']]
    r=c.post('/api/v1/research/selection-runs',headers=h,json={'request_id':str(uuid.uuid4()),'account_id':id,'listing_ids':ids,'use_ai':False,'delivery_mode':mode,'acknowledge_automatic_publishing':mode=='publish'})
    assert r.status_code==200,r.text
    run=r.json()['data']
    for _ in range(7):asyncio.run(pipeline.advance(run['id'],owner,h['Authorization']))
    assert pub.get_row(run['id'],owner)['state']=='accepted'
    return run

def official_mock(monkeypatch,fail=None,query=None):
    calls=Counter();real=httpx.AsyncClient
    def handler(request):
        assert request.url.host=='api.weixin.qq.com','Standalone must never contact the shared service'
        path=request.url.path;calls[path]+=1
        if fail and fail in path:raise httpx.ReadTimeout('do not expose secret',request=request)
        data={'stable_token':{'access_token':'test-only-token','expires_in':7200},
              'add_material':{'media_id':'cover-test'},'uploadimg':{'url':'http://mmbiz.qpic.cn/test.png'},
              'add':{'media_id':'draft-test'},'submit':{'publish_id':'publication-test'},
              'get':query if query is not None else {'publish_status':0,'article_id':'article-test','article_detail':{'item':[{'article_url':'http://mp.weixin.qq.com/s/test-final'}]}}}
        return httpx.Response(200,json=data[path.rsplit('/',1)[-1]])
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
    return calls

def test_local_auth_ownership_and_credential_encryption(local):
    c,owner,_,a,b,r=local;id=account(local)
    assert c.get('/api/v1/wechat-workspace/accounts',headers=headers(b)).json()['data']==[]
    assert c.get('/api/v1/wechat-workspace/accounts/'+id+'/credential',headers=headers(b)).status_code==404
    assert c.post('/api/v1/wechat-workspace/accounts',headers=headers(r),json={'requestId':str(uuid.uuid4()),'accountName':'forbidden'}).status_code==403
    assert b'test-only-fake-app-secret' not in c.get('/api/v1/wechat-workspace/accounts',headers=headers(a)).content
    with db.connect() as conn:
        assert PASSWORD not in conn.execute('SELECT password_hash FROM local_user WHERE id=?',(owner,)).fetchone()[0]
        assert a['accessToken'] not in [x[0] for x in conn.execute('SELECT hash FROM local_session')]
        cipher=conn.execute('SELECT credential FROM local_account WHERE id=?',(id,)).fetchone()[0]
        assert 'app-secret' not in cipher
    renewed=c.post('/api/v1/auth/refresh',json={'refreshToken':a['refreshToken']})
    assert renewed.status_code==200
    assert c.post('/api/v1/auth/refresh',json={'refreshToken':a['refreshToken']}).status_code==401
    assert c.post('/api/v1/auth/change-password',headers=headers(a),json={'currentPassword':PASSWORD,'newPassword':'Another-test-password-2026'}).status_code==200
    assert c.get('/api/v1/auth/me',headers=headers(a)).status_code==401

def test_complete_local_pipeline_never_uses_shared_service(local,monkeypatch):
    run=frozen(local);owner=local[1];calls=official_mock(monkeypatch)
    for _ in range(7):
        with db.connect() as c:c.execute('UPDATE local_publication SET next_at=0 WHERE id=?',(run['id'],))
        asyncio.run(pub.advance(run['id']))
    assert pub.receipt(pub.get_row(run['id'],owner))['publishedUrl']=='https://mp.weixin.qq.com/s/test-final'
    assert calls['/cgi-bin/draft/add']==calls['/cgi-bin/freepublish/submit']==1
    pipeline.resume(run['id'],owner)
    asyncio.run(pipeline.advance(run['id'],owner,headers(local[3])['Authorization']))
    with db.connect() as c:assert pipeline.row_for(c,run['id'],owner)['status']=='published'
    asyncio.run(pub.advance(run['id']))
    assert calls['/cgi-bin/freepublish/submit']==1

def test_unknown_write_and_restart_intent_are_never_resent(local,monkeypatch):
    run=frozen(local);calls=official_mock(monkeypatch,'add_material')
    asyncio.run(pub.advance(run['id']))
    assert pub.get_row(run['id'],local[1])['state']=='reconciling'
    asyncio.run(pub.advance(run['id']))
    with pytest.raises(auth.LocalError):pub.resume(local[1],run['id'])
    assert calls['/cgi-bin/material/add_material']==1
    with db.connect() as c:
        c.execute("UPDATE local_publication SET state='accepted',next_at=0 WHERE id=?",(run['id'],))
        c.execute("UPDATE local_publication_step SET state='intent' WHERE publication_id=?",(run['id'],))
    asyncio.run(pub.advance(run['id']))
    assert pub.get_row(run['id'],local[1])['state']=='reconciling'
    assert calls['/cgi-bin/material/add_material']==1

def test_switch_and_actor_revocation_block_before_write(local,monkeypatch):
    run=frozen(local);calls=official_mock(monkeypatch)
    monkeypatch.setenv('STUDIO_PUBLISH_ENABLED','false')
    asyncio.run(pub.advance(run['id']))
    assert pub.get_row(run['id'],local[1])['state']=='blocked' and not calls
    monkeypatch.setenv('STUDIO_PUBLISH_ENABLED','true')
    pub.resume(local[1],run['id'])
    with db.connect() as c:c.execute('UPDATE local_user SET version=version+1 WHERE id=?',(local[1],))
    asyncio.run(pub.advance(run['id']))
    assert pub.get_row(run['id'],local[1])['error_code']=='PUBLICATION_AUTH_CHANGED' and not calls

def test_missing_encryption_key_never_discards_credentials(local):
    account(local)
    from pathlib import Path
    Path(db.DB_PATH).with_name('credential.key').unlink()
    with pytest.raises(auth.LocalError) as e:store.key()
    assert e.value.code=='ENCRYPTION_KEY_MISSING'

def test_generated_news_article_can_use_same_native_publisher(local,monkeypatch):
    from app.domain import now,article_draft
    c,owner,_,tokens,_,_=local;h=headers(tokens);id=account(local)
    rid,aid=str(uuid.uuid4()),str(uuid.uuid4())
    report={'kind':'news','sources':[{'title':'测试新品资讯','url':'https://example.com/news','summary':'这是一条仅用于测试的资讯摘要。'*22,'published_at':now()}]}
    body=article_draft(report,'测试资讯解读')
    with db.connect() as conn:
        conn.execute('INSERT INTO research VALUES(?,?,?,?,?)',(rid,owner,'测试资讯解读',db.dump(report),now()))
        conn.execute('INSERT INTO article(id,owner,research_id,request_id,status,title,body,mode,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(aid,owner,rid,str(uuid.uuid4()),'needs_review','测试资讯解读',body,'ai',now()))
    response=c.post('/api/v1/research/selection-runs',headers=h,json={'request_id':str(uuid.uuid4()),'account_id':id,'article_id':aid,'delivery_mode':'draft_only'})
    assert response.status_code==200,response.text
    run=response.json()['data']
    async def forbidden(*a,**kw):raise AssertionError('Existing articles must not call the model again')
    monkeypatch.setattr(main,'article_create',forbidden)
    for _ in range(7):asyncio.run(pipeline.advance(run['id'],owner,h['Authorization']))
    calls=official_mock(monkeypatch)
    for _ in range(4):asyncio.run(pub.advance(run['id']))
    assert pub.get_row(run['id'],owner)['state']=='draft_delivered'
    assert calls['/cgi-bin/draft/add']==1 and calls['/cgi-bin/freepublish/submit']==0

@pytest.mark.parametrize('query,expected',[
    ({'publish_status':1},'publishing'),
    ({'publish_status':0,'article_id':'confirmed-but-no-url'},'publishing'),
    ({'publish_status':2},'rejected'),
])
def test_processing_missing_link_and_rejection_are_not_success(local,monkeypatch,query,expected):
    run=frozen(local);calls=official_mock(monkeypatch,query=query)
    for _ in range(7):
        with db.connect() as c:c.execute('UPDATE local_publication SET next_at=0 WHERE id=?',(run['id'],))
        asyncio.run(pub.advance(run['id']))
    receipt=pub.receipt(pub.get_row(run['id'],local[1]))
    assert receipt['status']==expected and not receipt['publishedUrl']
    assert calls['/cgi-bin/draft/add']==calls['/cgi-bin/freepublish/submit']==1

def test_query_failure_retries_only_query(local,monkeypatch):
    run=frozen(local)
    with monkeypatch.context() as network:
        calls=official_mock(network,'freepublish/get')
        for _ in range(6):
            with db.connect() as c:c.execute('UPDATE local_publication SET next_at=0 WHERE id=?',(run['id'],))
            asyncio.run(pub.advance(run['id']))
        assert pub.get_row(run['id'],local[1])['state']=='publishing'
        assert calls['/cgi-bin/freepublish/submit']==calls['/cgi-bin/freepublish/get']==1
    with monkeypatch.context() as network:
        calls=official_mock(network)
        with db.connect() as c:c.execute('UPDATE local_publication SET next_at=0 WHERE id=?',(run['id'],))
        asyncio.run(pub.advance(run['id']))
        assert pub.get_row(run['id'],local[1])['state']=='published'
        assert list(calls)==['/cgi-bin/freepublish/get']
