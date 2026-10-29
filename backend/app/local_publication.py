"""Standalone official WeChat executor. Every write intent is durable before send."""
import asyncio,base64,hashlib,json,os,time,uuid
from io import BytesIO
from urllib.parse import urlsplit,urlunsplit
import httpx
from PIL import Image
from . import db,local_identity as auth,local_store as store
from .local_identity import LocalError
from .publication_bridge import CONTRACT,digest,official_url,BridgeError
from .editorial import wechat_html
from .domain import now

TERMINAL={'published','draft_delivered','rejected'}
STEPS={'cover':'material/add_material','comparison':'media/uploadimg','risks':'media/uploadimg','draft':'draft/add','submit':'freepublish/submit','query':'freepublish/get'}

def flags():
    from .main import STOP
    return {'stop':STOP,'draft':os.environ.get('STUDIO_DRAFT_ENABLED','false')=='true','publish':os.environ.get('STUDIO_PUBLISH_ENABLED','false')=='true'}

def actor(owner,expected=None):
    with db.connect() as c:r=c.execute('SELECT * FROM local_user WHERE id=?',(owner,)).fetchone()
    if not r or r['status']!='active' or r['must_change'] or (expected is not None and r['version']!=expected):raise LocalError('PUBLICATION_AUTH_CHANGED','任务的用户授权已失效',403)
    perms=auth.ROLES[r['role']]
    if '*' not in perms and any(p not in perms for p in ('wechat.read','wechat.write','wechat.execute','wechat.publish')):raise LocalError('PUBLICATION_PERMISSION_REQUIRED','没有公众号执行与发表权限',403)
    return dict(r)

def capabilities(owner,account_id):
    actor(owner);row=store.account(account_id,owner);f=flags();modes=[]
    if not f['stop'] and row['credential']:
        if f['draft']:modes.append('draft_only')
        if f['publish'] and row['allow_publish']:modes.append('publish')
    reason='PUBLICATION_EMERGENCY_STOP' if f['stop'] else 'PUBLICATION_CREDENTIAL_REQUIRED' if not row['credential'] else 'PUBLICATION_MODE_DISABLED'
    return {'contractVersion':CONTRACT,'accountId':account_id,'idempotentSubmission':True,'emergencyStop':f['stop'],
            'deliveryModes':modes,'blockedReason':reason if not modes else ''}

def get_row(id,owner):
    with db.connect() as c:r=c.execute('SELECT * FROM local_publication WHERE id=? AND owner=?',(id,owner)).fetchone()
    if not r:raise LocalError('PUBLICATION_NOT_FOUND','发表请求不存在或无权访问',404)
    return dict(r)

def receipt(row):
    saved=json.loads(row['receipts'])
    return {'contractVersion':CONTRACT,'requestId':row['id'],'accountId':row['account_id'],'contentHash':row['content_hash'],
            'deliveryMode':row['mode'],'status':row['state'],'deliveryId':row['id'],'currentStage':row['stage'],
            'draftMediaId':saved.get('draft',''),'publishId':saved.get('submit',''),'articleId':saved.get('article_id',''),
            'publishedUrl':saved.get('url','') if row['state']=='published' else '','errorCode':row['error_code']}

def put(owner,id,payload):
    user=actor(owner)
    if payload.get('contractVersion')!=CONTRACT or payload.get('requestId')!=id or payload.get('externalRunId')!=id:raise LocalError('PUBLICATION_REQUEST_INVALID','请求编号或契约无效',400)
    if len(db.dump(payload).encode())>1_900_000:raise LocalError('PUBLICATION_TOO_LARGE','请求超出大小限制',413)
    content=digest({k:v for k,v in payload.items() if k!='contentHash'})
    if content!=payload.get('contentHash'):raise LocalError('PUBLICATION_HASH_MISMATCH','图文快照已变化',400)
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT * FROM local_publication WHERE id=?',(id,)).fetchone()
        if old:
            if old['owner']!=owner:raise LocalError('PUBLICATION_NOT_FOUND','发表请求不存在或无权访问',404)
            if old['payload']!=db.dump(payload):raise LocalError('REQUEST_ID_CONFLICT','编号已用于其他内容',409)
            return receipt(dict(old))
        run=c.execute('SELECT payload_json,content_hash FROM selection_run WHERE id=? AND owner=?',(id,owner)).fetchone()
        if not run or run['content_hash']!=content or json.loads(run['payload_json'])!=payload:
            raise LocalError('PUBLICATION_REVIEW_REQUIRED','图文必须来自本平台已冻结校验的任务',409)
        row=store.account(payload['accountId'],owner)
        modes=capabilities(owner,row['id'])['deliveryModes']
        mode=payload['deliveryMode']
        if mode not in modes or mode=='publish' and payload.get('acknowledgeAutomaticPublishing') is not True:raise LocalError('PUBLICATION_MODE_DISABLED','当前账号未开放该交付方式',409)
        if payload['html']!=wechat_html(payload['markdown']):raise LocalError('PUBLICATION_HTML_INVALID','排版与冻结正文不一致',400)
        images=payload['images']
        if len(images)!=3 or {i['key'] for i in images}!={'cover','comparison','risks'}:raise LocalError('PUBLICATION_IMAGES_INVALID','需要封面及两张正文图',400)
        pixels=0
        for image in images:
            raw=base64.b64decode(image['base64'],validate=True)
            if len(raw)>1048576 or hashlib.sha256(raw).hexdigest()!=image['sha256'] or image['mime']!='image/png':raise LocalError('PUBLICATION_IMAGES_INVALID','图片校验失败',400)
            with Image.open(BytesIO(raw)) as pic:
                if pic.format!='PNG' or pic.width>4096 or pic.height>4096:raise LocalError('PUBLICATION_IMAGES_INVALID','图片格式或尺寸不合要求',400)
                pixels+=pic.width*pic.height
                if pixels>8000000:raise LocalError('PUBLICATION_IMAGES_INVALID','图片像素超出限制',400)
                pic.verify()
        used=c.execute('SELECT count(*) FROM local_publication WHERE account_id=? AND created_at>=?',(row['id'],now()[:10])).fetchone()[0]
        if used>=int(os.environ.get('STUDIO_PUBLISH_DAILY_LIMIT','5')):raise LocalError('PUBLICATION_DAILY_LIMIT','当天投递请求已达上限',429)
        c.execute('''INSERT INTO local_publication(id,owner,account_id,mode,content_hash,payload,credential_version,user_version,expires,created_at,application_id)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(id,owner,row['id'],mode,content,db.dump(payload),row['version'],user['version'],time.time()+3600,now(),row['app_id']))
    return receipt(get_row(id,owner))

async def access_token(account):
    data=store.secrets_for(account)
    if data.get('token_expires',0)>time.time()+120 and data.get('access_token'):return data['access_token']
    try:
        async with httpx.AsyncClient(timeout=15,follow_redirects=False) as client:
            response=await client.post('https://api.weixin.qq.com/cgi-bin/stable_token',json={'grant_type':'client_credential','appid':account['app_id'],'secret':data['app_secret'],'force_refresh':False})
            response.raise_for_status();result=response.json()
        if result.get('errcode',0):raise LocalError('WECHAT_'+str(int(result['errcode'])),'微信拒绝凭据请求，请检查AppID、密钥和IP白名单',409)
        value=result['access_token']
        if not isinstance(value,str) or not value or len(value)>2048:raise ValueError()
        store.token_cache(account,value,time.time()+int(result.get('expires_in',7200)))
        return value
    except LocalError:raise
    except (httpx.HTTPError,ValueError,KeyError,TypeError):raise LocalError('PUBLICATION_TOKEN_UNAVAILABLE','暂时无法取得微信Token',503) from None

async def official(stage,account,payload,saved,validate):
    token=await access_token(account)
    await validate()
    path='https://api.weixin.qq.com/cgi-bin/'+STEPS[stage]
    params={'access_token':token}
    kwargs={}
    if stage in ('cover','comparison','risks'):
        image=next(i for i in payload['images'] if i['key']==stage)
        raw=base64.b64decode(image['base64'])
        boundary='studio'+uuid.uuid4().hex
        # Explicit legacy CGI multipart format; no filename* parameter.
        data=(f'--{boundary}\r\nContent-Disposition: form-data; name="media"; filename="{image["sha256"]}.png"\r\nContent-Type: image/png\r\n\r\n').encode()+raw+f'\r\n--{boundary}--\r\n'.encode()
        kwargs={'content':data,'headers':{'Content-Type':'multipart/form-data; boundary='+boundary}}
        if stage=='cover':params['type']='image'
    elif stage=='draft':
        rendered=payload['html']
        for key in ('comparison','risks'):rendered=rendered.replace('{{image:'+key+'}}',saved[key])
        kwargs={'json':{'articles':[{'title':payload['title'],'content':rendered,'thumb_media_id':saved['cover'],'need_open_comment':0,'only_fans_can_comment':0}]}}
    elif stage=='submit':kwargs={'json':{'media_id':saved['draft']}}
    else:kwargs={'json':{'publish_id':saved['submit']}}
    try:
        async with httpx.AsyncClient(timeout=25,follow_redirects=False) as client:
            async with client.stream('POST',path,params=params,**kwargs) as response:
                if response.status_code!=200:raise BridgeError('PUBLICATION_RESULT_UNKNOWN','微信请求结果待核对',True,True)
                raw=bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw)>1048576:raise ValueError()
        result=json.loads(raw)
        if not isinstance(result,dict):raise ValueError()
        if result.get('errcode',0):raise LocalError('WECHAT_'+str(int(result['errcode'])),'微信明确拒绝本次请求，请核对账号和接口权限',409)
        if stage in ('cover','draft'):value=result['media_id']
        elif stage in ('comparison','risks'):
            value=result['url'];u=urlsplit(value)
            if u.hostname!='mmbiz.qpic.cn' or u.scheme not in ('https','http') or u.username or u.password or u.port not in (None,80,443):raise ValueError()
            value=urlunsplit(('https',u.netloc,u.path,u.query,''))
        elif stage=='submit':value=str(result['publish_id'])
        else:return result
        if not isinstance(value,str) or not value or len(value)>2048 or any(ord(c)<32 for c in value):raise ValueError()
        return value
    except LocalError:raise
    except BridgeError:raise
    except (httpx.HTTPError,ValueError,TypeError,KeyError):raise BridgeError('PUBLICATION_RESULT_UNKNOWN','微信请求或回执结果未确认，不会自动重复写入',True,True) from None

def _save(row,**changes):
    with db.connect() as c:
        n=c.execute('UPDATE local_publication SET '+','.join(k+'=?' for k in changes)+' WHERE id=? AND lease=? AND lease_until>?',(*changes.values(),row['id'],row['lease'],time.time()))
        if n.rowcount!=1:raise LocalError('PUBLICATION_LEASE_LOST','执行锁已变化，未覆盖原记录')

def resume(owner,id):
    user=actor(owner);row=get_row(id,owner)
    if row['state'] in TERMINAL:return receipt(row)
    account=store.account(row['account_id'],owner)
    if account['app_id']!=row['application_id']:raise LocalError('PUBLICATION_ACCOUNT_CHANGED','公众号身份已变化，不能恢复旧素材')
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT 1 FROM local_publication_step WHERE publication_id=? AND state IN ('intent','unknown') AND stage<>'query'",(id,)).fetchone():
            raise LocalError('PUBLICATION_OUTCOME_UNKNOWN','原写入结果未确认，只能核对原请求')
        if row['lease_until']>time.time():raise LocalError('PUBLICATION_BUSY','任务仍在执行')
        c.execute("UPDATE local_publication SET state='accepted',error_code='',credential_version=?,user_version=?,expires=?,next_at=0 WHERE id=? AND owner=?",(account['version'],user['version'],time.time()+3600,id,owner))
    return receipt(get_row(id,owner))

async def advance(id):
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT * FROM local_publication WHERE id=?',(id,)).fetchone()
        if not old or old['state'] in TERMINAL|{'blocked','reconciling'} or old['next_at']>time.time() or old['lease_until']>time.time():return
        tag=uuid.uuid4().hex
        c.execute('UPDATE local_publication SET lease=?,lease_until=? WHERE id=?',(tag,time.time()+180,id))
        row=dict(c.execute('SELECT * FROM local_publication WHERE id=?',(id,)).fetchone())
    stage=row['stage'];saved=json.loads(row['receipts'])
    try:
        async def validate():
            actor(row['owner'],row['user_version'])
            account=store.account(row['account_id'],row['owner']);f=flags()
            if f['stop']:raise LocalError('EMERGENCY_STOP','系统已急停')
            if account['version']!=row['credential_version'] or account['app_id']!=row['application_id']:raise LocalError('PUBLICATION_ACCOUNT_CHANGED','账号凭据或应用身份已变化')
            if stage!='query' and (time.time()>row['expires'] or row['mode'] not in capabilities(row['owner'],row['account_id'])['deliveryModes']):raise LocalError('PUBLICATION_AUTH_EXPIRED','本次发表授权已失效')
            with db.connect() as c:
                current=c.execute('SELECT lease,lease_until FROM local_publication WHERE id=?',(id,)).fetchone()
                if current['lease']!=tag or current['lease_until']<=time.time():raise LocalError('PUBLICATION_LEASE_LOST','任务执行权已变化')
        await validate()
        with db.connect() as c:
            previous=c.execute('SELECT state FROM local_publication_step WHERE publication_id=? AND stage=?',(id,stage)).fetchone()
            if previous and previous['state'] in ('intent','unknown') and stage!='query':
                _save(row,state='reconciling',error_code='PUBLICATION_OUTCOME_UNKNOWN');return
            c.execute('INSERT OR REPLACE INTO local_publication_step VALUES(?,?,?,?)',(id,stage,'intent','{}'))
        _save(row,state='publishing' if stage in ('submit','query') else 'preparing')
        result=await official(stage,store.account(row['account_id'],row['owner']),json.loads(row['payload']),saved,validate)
        # Persist a received result even if a stop was triggered while it was in flight.
        next_stage={'cover':'comparison','comparison':'risks','risks':'draft','draft':'done' if row['mode']=='draft_only' else 'submit','submit':'query','query':'query'}[stage]
        state='draft_delivered' if next_stage=='done' else 'publishing' if next_stage=='query' else 'preparing'
        error=''
        if stage=='query':
            status=result.get('publish_status')
            if status==0:
                detail=result.get('article_detail',{});items=detail.get('item',detail.get('item_list',[]))
                urls=[i.get('article_url','') for i in items if isinstance(i,dict)]
                def normalize(url):
                    u=urlsplit(url)
                    if u.scheme=='http' and u.hostname=='mp.weixin.qq.com' and not u.username and not u.password and u.port in (None,80):url=urlunsplit(('https',u.hostname,u.path,u.query,u.fragment))
                    return official_url(url)
                url=next((normalize(u) for u in urls if normalize(u)), '')
                if url and result.get('article_id'):
                    saved.update(url=url,article_id=str(result['article_id']));state='published';next_stage='done'
                else:error='PUBLICATION_FINAL_LINK_PENDING'
            elif status in (2,3,4,5,6):state='rejected';error='WECHAT_PUBLISH_STATUS_'+str(status)
            elif status!=1:error='PUBLICATION_QUERY_PENDING'
        else:saved[stage]=result
        with db.connect() as c:
            c.execute('UPDATE local_publication_step SET state=?,receipt=? WHERE publication_id=? AND stage=?',('complete',db.dump(result),id,stage))
            n=c.execute('UPDATE local_publication SET state=?,stage=?,receipts=?,error_code=?,next_at=? WHERE id=? AND lease=? AND lease_until>?',
               (state,next_stage,db.dump(saved),error,time.time()+(30 if next_stage=='query' else 0),id,tag,time.time()))
            if n.rowcount!=1:raise LocalError('PUBLICATION_LEASE_LOST','迟到回执已归档，未覆盖当前执行者')
    except BridgeError:
        with db.connect() as c:c.execute('UPDATE local_publication_step SET state=? WHERE publication_id=? AND stage=?',('failed' if stage=='query' else 'unknown',id,stage))
        _save(row,state='publishing' if stage=='query' else 'reconciling',error_code='PUBLICATION_QUERY_PENDING' if stage=='query' else 'PUBLICATION_OUTCOME_UNKNOWN',next_at=time.time()+30)
    except LocalError as exc:
        with db.connect() as c:c.execute("UPDATE local_publication_step SET state='failed' WHERE publication_id=? AND stage=? AND state='intent'",(id,stage))
        _save(row,state='blocked',error_code=exc.code)
    except asyncio.CancelledError:raise
    except Exception:
        _save(row,state='publishing' if stage=='query' else 'reconciling',error_code='PUBLICATION_QUERY_PENDING' if stage=='query' else 'PUBLICATION_OUTCOME_UNKNOWN',next_at=time.time()+30)
    finally:
        with db.connect() as c:c.execute("UPDATE local_publication SET lease='',lease_until=0 WHERE id=? AND lease=?",(id,tag))

async def worker():
    while True:
        with db.connect() as c:ids=[r[0] for r in c.execute("SELECT id FROM local_publication WHERE state IN ('accepted','preparing','publishing') AND next_at<=? LIMIT 20",(time.time(),))]
        for id in ids:
            try:await advance(id)
            except asyncio.CancelledError:raise
            except Exception:pass
        await asyncio.sleep(2)

class LocalBridge:
    def __init__(self,token):self.token=token
    def owner(self):return auth.authorize(self.token,execute=True)
    async def capabilities(self,account_id,mode):
        try:
            result=capabilities(self.owner(),account_id)
            if mode not in result['deliveryModes']:raise LocalError(result['blockedReason'],'当前账号未开放此交付模式')
            return result
        except LocalError as e:raise BridgeError(e.code,e.message) from None
    async def submit(self,run,payload):
        try:return put(self.owner(),run['id'],payload)
        except LocalError as e:raise BridgeError(e.code,e.message) from None
    async def query(self,run):
        try:return receipt(get_row(run['id'],self.owner()))
        except LocalError as e:raise BridgeError(e.code,e.message) from None
