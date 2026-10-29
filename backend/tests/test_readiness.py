import importlib.util
import json
from pathlib import Path
import httpx

spec=importlib.util.spec_from_file_location('studio_readiness',Path(__file__).resolve().parents[2]/'scripts/check-publication-readiness.py')
readiness=importlib.util.module_from_spec(spec);spec.loader.exec_module(readiness)
ACCOUNT='00000000-0000-4000-8000-000000000002'

def test_readiness_is_read_only_and_never_prints_credentials():
    calls=[]
    def handler(request):
        calls.append((request.method,request.url.path))
        if request.url.path.endswith('/auth/me'):data={'role':'super_admin','status':'active'}
        elif request.url.path.endswith('/accounts'):data=[{'accountId':ACCOUNT}]
        elif request.url.path.endswith('/research/capabilities'):data={'selection_pipeline':True,'ai_configured':True,'xianyu_provider_configured':True}
        else:data={'contractVersion':'research-publication-v1','deliveryModes':['publish'],'idempotentSubmission':True}
        return httpx.Response(200,json={'success':True,'data':data})
    result=readiness.inspect('http://localhost:3102',ACCOUNT,'private-token',transport=httpx.MockTransport(handler))
    assert result['ready_for_next_acceptance_step']
    assert all(method=='GET' for method,path in calls)
    assert not any('draft' in path or 'articles' in path for method,path in calls)
    assert 'private-token' not in json.dumps(result)

def test_readiness_does_not_accept_malformed_identity_or_leak_remote_error():
    def handler(request):
        if request.url.path.endswith('/auth/me'):return httpx.Response(200,json={'success':True,'data':None})
        return httpx.Response(409,json={'success':False,'code':'secret-token-in-remote-error'})
    result=readiness.inspect('http://localhost:3102',ACCOUNT,'private-token',transport=httpx.MockTransport(handler))
    assert not result['ready_for_next_acceptance_step']
    assert 'secret-token' not in json.dumps(result)
    assert not result['checks'][0]['ready']
