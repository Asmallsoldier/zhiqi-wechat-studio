"""Owned account store; encrypted credentials live only in this platform's volume."""
import os,time,uuid,json
from pathlib import Path
from cryptography.fernet import Fernet,InvalidToken
from . import db
from .local_identity import LocalError


def init():
    with db.connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS local_account(id TEXT PRIMARY KEY,owner TEXT NOT NULL,name TEXT NOT NULL,
          app_id TEXT NOT NULL DEFAULT '',credential TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1,
          allow_publish INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS local_publication(id TEXT PRIMARY KEY,owner TEXT NOT NULL,account_id TEXT NOT NULL,
          mode TEXT NOT NULL,content_hash TEXT NOT NULL,payload TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'accepted',
          stage TEXT NOT NULL DEFAULT 'cover',receipts TEXT NOT NULL DEFAULT '{}',error_code TEXT NOT NULL DEFAULT '',
          credential_version INTEGER NOT NULL,user_version INTEGER NOT NULL,expires REAL NOT NULL,
          application_id TEXT NOT NULL,lease TEXT NOT NULL DEFAULT '',lease_until REAL NOT NULL DEFAULT 0,next_at REAL NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS local_publication_step(publication_id TEXT NOT NULL,stage TEXT NOT NULL,
          state TEXT NOT NULL,receipt TEXT NOT NULL DEFAULT '{}',PRIMARY KEY(publication_id,stage));
        INSERT OR IGNORE INTO schema_version VALUES(4);
        ''')
    key()  # Fail at startup if the key is unavailable rather than discard credentials.

def key():
    supplied=os.environ.get('STUDIO_ENCRYPTION_KEY','')
    if supplied:return Fernet(supplied.encode())
    file=Path(db.DB_PATH).parent/'credential.key'
    if not file.exists():
        with db.connect() as c:
            if c.execute("SELECT count(*) FROM local_account WHERE credential<>''").fetchone()[0]:
                raise LocalError('ENCRYPTION_KEY_MISSING','请恢复原凭据加密密钥，不能自动生成替代密钥',503)
        try:
            fd=os.open(file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(Fernet.generate_key())
        except FileExistsError:pass
    return Fernet(file.read_bytes())

def account(account_id,owner):
    with db.connect() as c:r=c.execute('SELECT * FROM local_account WHERE id=? AND owner=?',(account_id,owner)).fetchone()
    if not r:raise LocalError('ACCOUNT_NOT_FOUND','公众号不存在或无权访问',404)
    return dict(r)

def public_account(row):
    return {'accountId':row['id'],'accountName':row['name'],'platform':'wechat_official','platformAccountId':row['app_id'],
            'configured':bool(row['credential']),'allowPublish':bool(row['allow_publish']),'version':row['version']}

def secrets_for(row):
    try:return json.loads(key().decrypt(row['credential'].encode())) if row['credential'] else {}
    except (InvalidToken,ValueError,TypeError):raise LocalError('CREDENTIAL_DECRYPT_FAILED','无法解密公众号凭据，请检查密钥备份',503) from None

def save_secret(account_id,owner,app_id,app_secret):
    import re
    if not re.fullmatch(r'wx[A-Za-z0-9]{10,32}',app_id) or not 8<=len(app_secret)<=256:
        raise LocalError('CREDENTIAL_INVALID','请填写有效AppID和AppSecret',400)
    row=account(account_id,owner)
    cipher=key().encrypt(db.dump({'app_secret':app_secret}).encode()).decode()
    with db.connect() as c:
        c.execute('UPDATE local_account SET app_id=?,credential=?,version=version+1 WHERE id=? AND owner=?',(app_id,cipher,account_id,owner))
    return public_account(account(account_id,owner))

def token_cache(row,value,expires):
    data=secrets_for(row);data.update(access_token=value,token_expires=expires)
    with db.connect() as c:
        c.execute('UPDATE local_account SET credential=? WHERE id=? AND version=?',
          (key().encrypt(db.dump(data).encode()).decode(),row['id'],row['version']))
