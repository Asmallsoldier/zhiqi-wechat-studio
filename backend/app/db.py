"""Owned SQLite store. Transactions serialize mutations; never opens the legacy database."""
import json, os, sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = os.environ.get('STUDIO_DB_PATH', './data/studio.db')

@contextmanager
def connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()

def init(recover=True):
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
        INSERT OR IGNORE INTO schema_version VALUES(1);
        CREATE TABLE IF NOT EXISTS listing(id TEXT PRIMARY KEY, owner TEXT NOT NULL, source_id TEXT NOT NULL,
          external_id TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(owner,source_id,external_id));
        CREATE TABLE IF NOT EXISTS research(id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL,
          payload TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS article(id TEXT PRIMARY KEY, owner TEXT NOT NULL, research_id TEXT NOT NULL,
          request_id TEXT NOT NULL, status TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
          mode TEXT NOT NULL, error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
          UNIQUE(owner, request_id), FOREIGN KEY(research_id) REFERENCES research(id));
        CREATE TABLE IF NOT EXISTS model_receipt(article_id TEXT PRIMARY KEY, owner TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(article_id) REFERENCES article(id));
        INSERT OR IGNORE INTO schema_version VALUES(2);
        CREATE TABLE IF NOT EXISTS feed_health(source_id TEXT PRIMARY KEY, status TEXT NOT NULL,
          detail TEXT NOT NULL, count INTEGER NOT NULL, checked_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS feed_item(source_id TEXT NOT NULL, url TEXT NOT NULL, title TEXT NOT NULL,
          summary TEXT NOT NULL, published_at TEXT NOT NULL, collected_at TEXT NOT NULL, PRIMARY KEY(source_id,url));
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL,
          action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS selection_run(
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, request_id TEXT NOT NULL,
          account_id TEXT NOT NULL, delivery_mode TEXT NOT NULL, stage TEXT NOT NULL,
          status TEXT NOT NULL, request_json TEXT NOT NULL, snapshot_json TEXT NOT NULL DEFAULT '{}',
          research_id TEXT NOT NULL DEFAULT '', article_id TEXT NOT NULL DEFAULT '',
          selection_hash TEXT NOT NULL DEFAULT '', content_hash TEXT NOT NULL DEFAULT '',
          payload_json TEXT NOT NULL DEFAULT '{}', receipt_json TEXT NOT NULL DEFAULT '{}',
          submit_intent INTEGER NOT NULL DEFAULT 0, error_code TEXT NOT NULL DEFAULT '',
          message TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,
          next_attempt_at TEXT NOT NULL DEFAULT '', lease_owner TEXT NOT NULL DEFAULT '',
          lease_until REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(owner,request_id));
        CREATE UNIQUE INDEX IF NOT EXISTS selection_account_active ON selection_run(account_id)
          WHERE status IN ('queued','running','blocked','publishing','reconciling');
        CREATE UNIQUE INDEX IF NOT EXISTS selection_account_snapshot ON selection_run(account_id,selection_hash)
          WHERE selection_hash<>'';
        INSERT OR IGNORE INTO schema_version VALUES(3);
        ''')
        # Interrupted paid calls are never silently retried after restart.
        if recover:db.execute("UPDATE article SET status='interrupted', error='服务重启时模型结果未确认，请核对后重新创建文章。' WHERE status='generating'")

def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
