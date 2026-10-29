import asyncio, calendar, json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit
import feedparser
from bs4 import BeautifulSoup
from .network import public_get, SourceError
from .db import connect
from .domain import now

CATALOG=json.loads(Path(__file__).with_name('catalog.json').read_text())

def clean(value):return BeautifulSoup(str(value),'html.parser').get_text(' ',strip=True)[:1500]

def collect(source):
    payload,_=public_get(source['url'])
    feed=feedparser.parse(payload)
    if not feed.entries:raise SourceError('SOURCE_NO_FEED_ENTRIES')
    entries=[];at=datetime.now(timezone.utc)
    for entry in feed.entries[:100]:
        stamp=entry.get('published_parsed') or entry.get('updated_parsed')
        if not stamp:continue
        date=datetime.fromtimestamp(calendar.timegm(stamp),timezone.utc)
        if date>at+timedelta(minutes=5) or at-date>timedelta(hours=72):continue
        url=entry.get('link','');u=urlsplit(url)
        if u.scheme!='https' or not u.hostname or u.username:continue
        entries.append({'source_id':source['id'],'url':url,'title':clean(entry.get('title',''))[:240],
          'summary':clean(entry.get('summary','')),'published_at':date.isoformat(),'collected_at':now()})
    return entries[:30]

async def refresh(source_id):
    source=next((s for s in CATALOG if s['id']==source_id),None)
    if not source:raise SourceError('SOURCE_NOT_FOUND')
    try:
        rows=await asyncio.to_thread(collect,source)
        status='available' if rows else 'stale';detail='' if rows else '暂无72小时内的有效条目'
    except Exception as exc:
        rows=[];status='unavailable';detail=str(exc) if isinstance(exc,SourceError) else type(exc).__name__
    with connect() as db:
        for row in rows:
            db.execute('INSERT OR REPLACE INTO feed_item VALUES(:source_id,:url,:title,:summary,:published_at,:collected_at)',row)
        db.execute('INSERT OR REPLACE INTO feed_health VALUES(?,?,?,?,?)',(source_id,status,detail,len(rows),now()))
    return {'source_id':source_id,'status':status,'detail':detail,'count':len(rows)}
