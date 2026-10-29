"""Public standalone APIs. Never proxy a local credential or session elsewhere."""
import json,uuid
from fastapi import APIRouter,Request
from pydantic import BaseModel,Field
from . import db,local_identity as auth,local_store as store,local_publication as pub
from .local_identity import LocalError
from .domain import now

router=APIRouter()
def ok(value):return {'success':True,'data':value}
def token(request):return request.headers.get('Authorization','')
def owner(request,write=False):return auth.authorize(token(request),write=write)

class Login(BaseModel):
    username:str=Field(min_length=1,max_length=64)
    password:str=Field(min_length=1,max_length=72)
class Refresh(BaseModel):refreshToken:str=Field(min_length=1,max_length=512)
class Password(BaseModel):
    currentPassword:str=Field(max_length=72)
    newPassword:str=Field(max_length=72)
class Account(BaseModel):
    requestId:uuid.UUID
    accountName:str=Field(min_length=1,max_length=128)
    platformAccountId:str=Field(default='',max_length=64)
    allowPublish:bool=False
class EditAccount(BaseModel):
    accountName:str=Field(min_length=1,max_length=128)
    allowPublish:bool=False
class Credential(BaseModel):
    appId:str=Field(max_length=64)
    appSecret:str=Field(max_length=256)

@router.post('/auth/login')
async def login(data:Login):return ok(auth.login(data.username,data.password))
@router.post('/auth/refresh')
async def refresh(data:Refresh):return ok(auth.refresh(data.refreshToken))
@router.get('/auth/me')
async def me(request:Request):return ok(auth.profile(auth.user_for(token(request))))
@router.post('/auth/logout')
async def logout(request:Request):auth.logout(token(request));return ok({})
@router.post('/auth/change-password')
async def password(data:Password,request:Request):auth.change_password(token(request),data.currentPassword,data.newPassword);return ok({})

@router.get('/wechat-workspace/accounts')
async def accounts(request:Request):
    user=owner(request)
    with db.connect() as c:rows=c.execute('SELECT * FROM local_account WHERE owner=? ORDER BY created_at',(user,)).fetchall()
    return ok([store.public_account(dict(r)) for r in rows])
@router.post('/wechat-workspace/accounts')
async def create(data:Account,request:Request):
    user=owner(request,True);id=str(data.requestId)
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT * FROM local_account WHERE id=?',(id,)).fetchone()
        if old:
            if old['owner']!=user:raise LocalError('ACCOUNT_NOT_FOUND','公众号不存在或无权访问',404)
        else:c.execute('INSERT INTO local_account(id,owner,name,allow_publish,created_at) VALUES(?,?,?,?,?)',(id,user,data.accountName,int(data.allowPublish),now()))
    return ok(store.public_account(store.account(id,user)))
@router.put('/wechat-workspace/accounts/{account_id}')
async def edit(account_id:uuid.UUID,data:EditAccount,request:Request):
    user=owner(request,True);id=str(account_id);store.account(id,user)
    with db.connect() as c:c.execute('UPDATE local_account SET name=?,allow_publish=?,version=version+1 WHERE id=? AND owner=?',(data.accountName,int(data.allowPublish),id,user))
    return ok(store.public_account(store.account(id,user)))
@router.get('/wechat-workspace/accounts/{account_id}/credential')
async def credential(account_id:uuid.UUID,request:Request):
    row=store.account(str(account_id),owner(request));return ok({'configured':bool(row['credential']),'authStatus':'configured' if row['credential'] else 'missing','appId':row['app_id']})
@router.put('/wechat-workspace/accounts/{account_id}/credential')
async def save_credential(account_id:uuid.UUID,data:Credential,request:Request):return ok(store.save_secret(str(account_id),owner(request,True),data.appId,data.appSecret))
@router.delete('/wechat-workspace/accounts/{account_id}/credential')
async def revoke(account_id:uuid.UUID,request:Request):
    user=owner(request,True);id=str(account_id);store.account(id,user)
    with db.connect() as c:c.execute("UPDATE local_account SET credential='',version=version+1 WHERE id=? AND owner=?",(id,user))
    return ok({})
@router.post('/wechat-workspace/accounts/{account_id}/probe')
async def probe(account_id:uuid.UUID,request:Request):
    user=owner(request,True)
    if pub.flags()['stop']:raise LocalError('EMERGENCY_STOP','系统已急停')
    row=store.account(str(account_id),user)
    if not row['credential']:raise LocalError('CREDENTIAL_REQUIRED','请先保存公众号凭据')
    await pub.access_token(row)
    return ok({'tokenConnected':True,'note':'已连接微信Token接口；正式发表权限以实际回执为准，本次没有上传或发表。'})
@router.get('/wechat-workspace/research-publications/capabilities')
async def capabilities(accountId:uuid.UUID,request:Request):return ok(pub.capabilities(owner(request),str(accountId)))
@router.put('/wechat-workspace/research-publications/{request_id}')
async def put(request_id:uuid.UUID,request:Request):
    user=auth.authorize(token(request),execute=True);raw=await request.body()
    if len(raw)>1900000:raise LocalError('BODY_TOO_LARGE','请求过大',413)
    try:payload=json.loads(raw)
    except ValueError:raise LocalError('JSON_INVALID','请求不是有效的JSON',400) from None
    if not isinstance(payload,dict):raise LocalError('JSON_INVALID','请求需为JSON对象',400)
    return ok(pub.put(user,str(request_id),payload))
@router.get('/wechat-workspace/research-publications/{request_id}')
async def get(request_id:uuid.UUID,accountId:uuid.UUID,request:Request):
    user=owner(request);row=pub.get_row(str(request_id),user)
    if row['account_id']!=str(accountId):raise LocalError('NOT_FOUND','发表请求不存在或无权访问',404)
    return ok(pub.receipt(row))
