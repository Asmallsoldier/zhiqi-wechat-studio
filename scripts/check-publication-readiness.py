"""Read-only acceptance preflight. No collection, model, draft or publish calls.

The token file is created by the operator, permission 0600, containing a raw
access token or JSON with accessToken. Credentials are never printed.
"""
import argparse
import json
import re
from pathlib import Path
import stat
import sys
import uuid
import httpx


def inspect(origin, account_id, token, mode='publish', imported=False, use_ai=True, transport=None):
    checks=[]
    with httpx.Client(base_url=origin.rstrip('/'),headers={'Authorization':'Bearer '+token},timeout=15,follow_redirects=False,transport=transport) as client:
        def read(path, label):
            try:
                response=client.get('/api/v1/'+path)
                payload=response.json()
                if response.status_code!=200 or payload.get('success') is not True:
                    code=str(payload.get('code','HTTP_'+str(response.status_code)))
                    checks.append({'check':label,'ready':False,'code':code if re.fullmatch(r'[A-Z0-9_]{1,80}',code) else 'SERVICE_REJECTED'})
                    return None
                data=payload['data']
                expected=list if label in ('target_account','data_source') else dict
                if not isinstance(data,expected):raise TypeError()
                return data
            except (httpx.HTTPError,ValueError,KeyError,TypeError):
                checks.append({'check':label,'ready':False,'code':'READ_OR_RESPONSE_FAILED'})
                return None
        profile=read('auth/me','identity')
        if profile is not None:
            permitted=profile.get('role')=='super_admin' or all(p in profile.get('permissions',[]) for p in ('wechat.read','wechat.write','wechat.execute','wechat.publish'))
            checks.append({'check':'identity','ready':permitted and profile.get('status')=='active' and not profile.get('mustChangePassword'),'code':'PERMISSIONS_AND_ACCOUNT_STATUS'})
        accounts=read('wechat-workspace/accounts','target_account')
        if accounts is not None:
            checks.append({'check':'target_account','ready':any(a.get('accountId')==account_id and a.get('platform','wechat_official')=='wechat_official' for a in accounts),'code':'OWNED_OFFICIAL_ACCOUNT'})
        caps=read('research/capabilities','research_api')
        if caps is not None:
            checks.append({'check':'pipeline','ready':caps.get('selection_pipeline') is True and not caps.get('emergency_stop'),'code':'PIPELINE_ENABLED'})
            checks.append({'check':'model','ready':not use_ai or caps.get('ai_configured') is True,'code':'MODEL_CONFIGURATION_ONLY_NOT_MODEL_CALL'})
            if not imported:
                checks.append({'check':'data_source','ready':caps.get('xianyu_provider_configured') is True,'code':'PROVIDER_NOT_CONFIGURED' if not caps.get('xianyu_provider_configured') else 'PROVIDER_CONFIGURATION_ONLY_NOT_COLLECTION'})
        if imported:
            rows=read('research/listings','data_source')
            if rows is not None:checks.append({'check':'data_source','ready':len(rows)>=5,'code':'IMPORTED_SAMPLE_COUNT_ONLY_NOT_PRICE_OR_RISK_APPROVAL','count':len(rows)})
        publication=read('research/publication-capabilities/'+account_id+'?mode='+mode,'publication_bridge')
        if publication is not None:
            checks.append({'check':'publication_bridge','ready':publication.get('contractVersion')=='research-publication-v1' and mode in publication.get('deliveryModes',[]) and publication.get('idempotentSubmission') is True and not publication.get('emergencyStop'),'code':'BRIDGE_CONTRACT_AND_MODE'})
    return {'ready_for_next_acceptance_step':bool(checks) and all(x['ready'] for x in checks),'mode':mode,'read_only':True,'checks':checks,
            'limits':'配置与读取检查不代表商品已采集、模型已成功或微信已发表。'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin',required=True)
    parser.add_argument('--account-id',required=True,type=uuid.UUID)
    parser.add_argument('--token-file',required=True)
    parser.add_argument('--mode',choices=['draft_only','publish'],default='publish')
    parser.add_argument('--imported-samples',action='store_true')
    parser.add_argument('--evidence-only',action='store_true')
    args=parser.parse_args()
    path=Path(args.token_file)
    if stat.S_IMODE(path.stat().st_mode)&0o077:
        raise SystemExit('Token文件权限需为0600，仅当前用户可读写。')
    value=path.read_text().strip()
    if value.startswith('{'):value=json.loads(value).get('accessToken','')
    if not value or len(value)>16384 or any(c.isspace() for c in value):raise SystemExit('Token文件格式无效。')
    from urllib.parse import urlsplit
    u=urlsplit(args.origin)
    if u.scheme not in ('https','http') or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise SystemExit('入口地址必须是不带凭据或查询参数的HTTP/HTTPS origin。')
    if u.scheme=='http' and u.hostname not in ('localhost','127.0.0.1','::1'):
        raise SystemExit('带身份检查请从本机localhost入口或HTTPS访问，避免通过明文局域网传送Token。')
    result=inspect(args.origin,str(args.account_id),value,args.mode,args.imported_samples,not args.evidence_only)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    sys.exit(0 if result['ready_for_next_acceptance_step'] else 1)
