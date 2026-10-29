from datetime import datetime,timezone,timedelta
import json,uuid
import pytest
from fastapi.testclient import TestClient
from app.domain import Listing,analyze,article_draft
from app import db,main

AT=datetime.now(timezone.utc)
def item(n=0,price=1000,**kw):
    return Listing(external_id=str(n),title='手机商品',model='型号 A',variant='256GB',category='phone',condition='good',price=price,
      url=f'https://www.goofish.com/item?id={n}',observed_at=AT,seller_ref=f'seller-{n}',battery_health=90,
      inspection_available=True,repair_status='verified_original',**kw).public()

def test_comparable_groups_and_price_not_transaction():
    rows=[item(n,1000+n*10) for n in range(5)]+[item(6,900)]
    rows[0]['shipping']='20'; rows.append({**item(7,200),'variant':'128GB'})
    report=analyze(rows,AT)
    group=report['groups'][0]
    assert group['sample_count']==6
    assert group['candidates'][0]['verdict']=='值得核验'
    assert report['groups'][1]['confidence']=='低'
    assert '挂牌价不是成交价。' in report['limits']

def test_duplicate_and_old_samples_do_not_inflate_confidence():
    a=item();report=analyze([a,a,{**item(1),'observed_at':(AT-timedelta(days=4)).isoformat()}],AT)
    assert report['sample_count']==2
    assert report['groups'][0]['sample_count']==1
    assert all(x['verdict']!='值得核验' for x in report['groups'][0]['candidates'])

def test_low_price_and_deposit_are_not_recommendations():
    rows=[item(n,1000) for n in range(5)]+[item(6,10),{**item(7,50),'title':'仅定金 锁机'}]
    report=analyze(rows,AT)
    assert all(c['verdict']!='值得核验' for c in report['groups'][0]['candidates'])
    assert any('显著低于' in r for c in report['groups'][0]['candidates'] for r in c['risks'])
    assert '成交价' in article_draft(report,'测试选题')

def test_input_requires_evidence_not_future_or_private_scheme():
    with pytest.raises(ValueError):Listing.model_validate({**item(),'url':'javascript:alert(1)'})
    with pytest.raises(ValueError):Listing.model_validate({**item(),'price':'NaN'})
    with pytest.raises(ValueError):Listing.model_validate({**item(),'observed_at':(AT+timedelta(days=1)).isoformat()})

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DB_PATH',str(tmp_path/'test.db'))
    monkeypatch.setenv('STUDIO_SOURCE_SCHEDULER','false')
    monkeypatch.setenv('STUDIO_PIPELINE_WORKER','false')
    main.app.dependency_overrides[main.identity]=lambda:'alice'
    with TestClient(main.app) as client:yield client
    main.app.dependency_overrides.clear()

def test_import_analyze_export_and_request_idempotency(client):
    imported=client.post('/api/v1/research/listings/import',json={'items':[item(n,1000+n*10) for n in range(6)]})
    assert imported.status_code==200
    assert client.post('/api/v1/research/listings/import',json={'items':[item()]}).status_code==200
    assert len(client.get('/api/v1/research/listings').json()['data'])==6
    result=client.post('/api/v1/research/analyses',json={'title':'值得买的二手数码'}).json()['data']
    request={'research_id':result['id'],'request_id':str(uuid.uuid4())}
    first=client.post('/api/v1/research/articles',json=request).json()['data']
    second=client.post('/api/v1/research/articles',json=request).json()['data']
    assert first['id']==second['id']
    assert first['status']=='ready'
    assert '商品原链接' in client.get(f"/api/v1/research/articles/{first['id']}/export").text
    main.app.dependency_overrides[main.identity]=lambda:'bob'
    assert client.get('/api/v1/research/listings').json()['data']==[]
    assert client.get(f"/api/v1/research/articles/{first['id']}/export").status_code==404
    assert client.post('/api/v1/research/articles',json={**request,'request_id':str(uuid.uuid4())}).status_code==404

def test_unconfigured_ai_does_not_pretend_generation(client,monkeypatch):
    monkeypatch.setattr(main,'AI_KEY','')
    response=client.post('/api/v1/research/articles',json={'research_id':'missing','request_id':str(uuid.uuid4()),'use_ai':True})
    assert response.status_code==409
    assert response.json()['code']=='AI_NOT_CONFIGURED'

def test_public_source_private_dns_is_blocked(monkeypatch):
    from app import network
    monkeypatch.setattr(network.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(network.SourceError,match='NON_PUBLIC'):network.public_get('https://source.example/feed')

def test_xianyu_login_page_not_fake_success(monkeypatch):
    from app import xianyu
    monkeypatch.setattr(xianyu,'public_get',lambda url:(b'<html>login</html>',url))
    with pytest.raises(xianyu.SourceError,match='LOGIN_OR_STRUCTURED_DATA_REQUIRED'):xianyu.public_search('phone')

def test_news_article_uses_saved_sources_and_rejects_stale(client):
    with db.connect() as conn:
        conn.execute('INSERT INTO feed_item VALUES(?,?,?,?,?,?)',('source','https://publisher.example/news','真实标题','明确摘要',AT.isoformat(),AT.isoformat()))
    request={'urls':['https://publisher.example/news'],'title':'本次选题','request_id':str(uuid.uuid4()),'use_ai':False}
    response=client.post('/api/v1/research/news/articles',json=request)
    assert response.status_code==200
    article=response.json()['data']
    assert 'https://publisher.example/news' in article['body']
    assert client.post('/api/v1/research/news/articles',json=request).json()['data']['id']==article['id']
    with db.connect() as conn:
        conn.execute('UPDATE feed_item SET published_at=?',((AT-timedelta(days=4)).isoformat(),))
    assert client.post('/api/v1/research/news/articles',json={**request,'request_id':str(uuid.uuid4())}).status_code==409

def test_budget_intent_count_is_not_reopened_by_unknown_result(client,monkeypatch):
    monkeypatch.setattr(main,'AI_KEY','test');monkeypatch.setattr(main,'AI_BASE','https://example.test/v1');monkeypatch.setattr(main,'AI_MODEL','test');monkeypatch.setattr(main,'AI_DAILY_LIMIT',0)
    response=client.post('/api/v1/research/articles',json={'research_id':'not-sent','request_id':str(uuid.uuid4()),'use_ai':True})
    assert response.status_code==409
    assert response.json()['code']=='AI_DAILY_LIMIT'

def test_model_receipt_parsing_keeps_facts_and_rejects_truncation():
    report=analyze([item()],AT)
    content='<think>internal</think>\n```json\n'+json.dumps({'title':'独立解读','body':'有依据的内容。'*30},ensure_ascii=False)+'\n```'
    title,body=main.parse_model_article(content,'stop','原标题',report)
    assert title=='独立解读' and 'internal' not in body and '商品原链接' in body
    with pytest.raises(ValueError):main.parse_model_article(content,'length','原标题',report)
