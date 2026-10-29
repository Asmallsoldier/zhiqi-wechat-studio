"""Generate explicitly simulated, non-publishable contract data for isolated integration.

No database, model, network or platform credentials. Never submit this fixture to
production. The test account and request IDs are reserved example identifiers.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.domain import Listing,article_draft
from app.editorial import select_report,validate_article,selection_hash,wechat_html
from app.illustrations import render
from app.publication_bridge import digest,CONTRACT


def fixture():
    at=datetime.now(timezone.utc)
    items=[Listing(external_id=f'test-fixture-{n}',title=f'隔离测试样本{n}',model='模拟型号A',variant='256GB',
       condition='good',category='phone',price=price,url=f'https://www.goofish.com/item?id=test-fixture-{n}',
       observed_at=at,seller_ref=f'test-seller-{n}',battery_health=90,inspection_available=True,
       repair_status='verified_original').public() for n,price in enumerate([1000,1000,1000,1000,1000,900])]
    report=select_report(items)
    article={'title':'隔离测试选品图文，请勿正式发表','body':article_draft(report,'隔离测试选品图文，请勿正式发表')}
    review=validate_article(article,report)
    images=[]
    for key,role in (('cover','cover'),('comparison','inline'),('risks','inline')):
        image=render(article['title'],report,key)
        images.append({'key':key,'role':role,'mime':'image/png','sha256':hashlib.sha256(image).hexdigest(),'base64':base64.b64encode(image).decode()})
    payload={'contractVersion':CONTRACT,'accountId':'00000000-0000-4000-8000-000000000002',
       'externalRunId':'00000000-0000-4000-8000-000000000001','requestId':'00000000-0000-4000-8000-000000000001',
       'deliveryMode':'publish','title':article['title'],'markdown':article['body'],'html':wechat_html(article['body']),
       'images':images,'evidence':{'report':report,'review':review,'selectionHash':selection_hash(items)},
       'acknowledgeAutomaticPublishing':True}
    payload['contentHash']=digest(payload)
    return payload

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    payload=fixture()
    dest=Path(args.output);dest.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps({'fixture':str(dest),'contentHash':payload['contentHash'],'images':len(payload['images']),'bytes':dest.stat().st_size,'simulated':True}))
