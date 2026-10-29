"""Standalone identity. Opaque expiring sessions, scrypt, no shared authority."""
import base64, hashlib, hmac, os, re, secrets, time, uuid
from . import db

class LocalError(Exception):
    def __init__(self,code,message,status=409):
        super().__init__(message);self.code,self.message,self.status=code,message,status

ROLES={'super_admin':['*'],'wechat_operator':['wechat.read','wechat.write','wechat.execute','wechat.publish'],'readonly_operator':['wechat.read']}

def init():
    with db.connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS local_user(id TEXT PRIMARY KEY,username TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,
          role TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'active',must_change INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS local_session(hash TEXT PRIMARY KEY,owner TEXT NOT NULL,kind TEXT NOT NULL,expires REAL NOT NULL,version INTEGER NOT NULL,
          FOREIGN KEY(owner) REFERENCES local_user(id));
        CREATE TABLE IF NOT EXISTS local_login_limit(key TEXT PRIMARY KEY,failures INTEGER NOT NULL,until REAL NOT NULL);
        ''')

def password_hash(value):
    if not 12<=len(value) or len(value.encode())>72 or value.isspace():raise LocalError('PASSWORD_INVALID','密码至少12字符，最多72个UTF-8字节',400)
    salt=secrets.token_bytes(16)
    result=hashlib.scrypt(value.encode(),salt=salt,n=32768,r=8,p=1,maxmem=67108864,dklen=32)
    return base64.b64encode(salt+result).decode()

def password_matches(value,encoded):
    try:
        if len(value.encode())>72:return False
        raw=base64.b64decode(encoded,validate=True)
        if len(raw)!=48:return False
        result=hashlib.scrypt(value.encode(),salt=raw[:16],n=32768,r=8,p=1,maxmem=67108864,dklen=32)
        return hmac.compare_digest(result,raw[16:])
    except (ValueError,TypeError):return False

DUMMY=password_hash('test-only-unused-dummy-password')

def create_user(username,password,role='wechat_operator',must_change=False):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}',username) or role not in ROLES:raise LocalError('USER_INVALID','用户名或角色无效',400)
    encoded=password_hash(password);id=str(uuid.uuid4())
    with db.connect() as c:
        c.execute('INSERT INTO local_user(id,username,password_hash,role,must_change) VALUES(?,?,?,?,?)',(id,username,encoded,role,int(must_change)))
    return id

def profile(user):
    return {'userId':user['id'],'username':user['username'],'displayName':user['username'],'role':user['role'],
            'status':user['status'],'mustChangePassword':bool(user['must_change']),'permissions':ROLES[user['role']]}

def token_hash(token):return hashlib.sha256(token.encode()).hexdigest()

def _tokens(c,user):
    result={}
    for kind,key,ttl in (('access','accessToken',3600),('refresh','refreshToken',604800)):
        raw=secrets.token_urlsafe(32)
        c.execute('INSERT INTO local_session VALUES(?,?,?,?,?)',(token_hash(raw),user['id'],kind,time.time()+ttl,user['version']))
        result[key]=raw
    return {**profile(user),**result}

def login(username,password):
    key=token_hash(username.casefold());at=time.time()
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        limit=c.execute('SELECT * FROM local_login_limit WHERE key=?',(key,)).fetchone()
        if limit and limit['until']>at and limit['failures']>=10:raise LocalError('LOGIN_RATE_LIMIT','登录尝试过多，请15分钟后重试',429)
        row=c.execute('SELECT * FROM local_user WHERE username=?',(username,)).fetchone()
        valid=password_matches(password,row['password_hash'] if row else DUMMY)
        if not row or not valid or row['status']!='active':
            count=limit['failures']+1 if limit and limit['until']>at else 1
            c.execute('INSERT OR REPLACE INTO local_login_limit VALUES(?,?,?)',(key,count,at+900))
            error=True
        else:
            c.execute('DELETE FROM local_login_limit WHERE key=?',(key,));result=_tokens(c,dict(row));error=False
    if error:raise LocalError('LOGIN_FAILED','账号或密码不正确',401)
    return result

def user_for(token,kind='access'):
    if not token or len(token)>512:raise LocalError('LOGIN_REQUIRED','请先登录',401)
    if token.startswith('Bearer '):token=token[7:]
    with db.connect() as c:
        row=c.execute('''SELECT u.* FROM local_user u JOIN local_session s ON s.owner=u.id
          WHERE s.hash=? AND s.kind=? AND s.expires>? AND s.version=u.version AND u.status='active' ''',(token_hash(token),kind,time.time())).fetchone()
    if not row:raise LocalError('LOGIN_EXPIRED','登录已失效，请重新登录',401)
    return dict(row)

def refresh(raw):
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('''SELECT u.* FROM local_user u JOIN local_session s ON s.owner=u.id
         WHERE s.hash=? AND s.kind='refresh' AND s.expires>? AND s.version=u.version AND u.status='active' ''',(token_hash(raw),time.time())).fetchone()
        if not row:raise LocalError('LOGIN_EXPIRED','刷新凭据已失效',401)
        c.execute('DELETE FROM local_session WHERE hash=?',(token_hash(raw),))
        return _tokens(c,dict(row))

def logout(token):
    user=user_for(token)
    with db.connect() as c:
        c.execute('UPDATE local_user SET version=version+1 WHERE id=?',(user['id'],))
        c.execute('DELETE FROM local_session WHERE owner=?',(user['id'],))

def change_password(token,current,new):
    user=user_for(token)
    if not password_matches(current,user['password_hash']):raise LocalError('PASSWORD_CURRENT_INVALID','当前密码不正确',400)
    encoded=password_hash(new)
    with db.connect() as c:
        c.execute('UPDATE local_user SET password_hash=?,must_change=0,version=version+1 WHERE id=?',(encoded,user['id']))
        c.execute('DELETE FROM local_session WHERE owner=?',(user['id'],))

def authorize(token,write=False,execute=False):
    user=user_for(token);perms=ROLES[user['role']]
    if user['must_change']:raise LocalError('PASSWORD_CHANGE_REQUIRED','请先修改初始密码',403)
    required=['wechat.read']+(['wechat.write'] if write or execute else [])+(['wechat.execute','wechat.publish'] if execute else [])
    if '*' not in perms and any(p not in perms for p in required):raise LocalError('FORBIDDEN','没有该操作权限',403)
    return user['id']
