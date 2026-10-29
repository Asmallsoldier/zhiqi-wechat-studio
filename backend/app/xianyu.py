"""Two real adapters: public structured pages and a configured authorized feed contract."""
import asyncio,json,os
from urllib.parse import urlencode,urlsplit
import httpx
from bs4 import BeautifulSoup
from .network import public_get,SourceError
from .domain import Listing,now

PROVIDER_URL=os.environ.get('XIANYU_PROVIDER_URL','')
PROVIDER_KEY=os.environ.get('XIANYU_PROVIDER_KEY','')

def public_search(query):
    raw,_=public_get('https://www.goofish.com/search?'+urlencode({'q':query}))
    soup=BeautifulSoup(raw,'html.parser');items=[]
    for script in soup.select('script[type="application/ld+json"]'):
        try:data=json.loads(script.string or '')
        except (ValueError,TypeError):continue
        nodes=data if isinstance(data,list) else data.get('@graph',[data])
        for node in nodes:
            if not isinstance(node,dict) or node.get('@type')!='Product':continue
            offers=node.get('offers',{});offers=offers[0] if isinstance(offers,list) and offers else offers
            if not isinstance(offers,dict) or offers.get('priceCurrency','CNY')!='CNY':continue
            # Do not infer a configuration from a sales title; incomplete items need import confirmation.
            if not node.get('model') or not node.get('sku'):continue
            try:
                items.append(Listing(external_id=str(node.get('productID') or node['sku']),title=node['name'],model=str(node['model']),
                  variant=str(node['sku']),price=offers['price'],url=node.get('url') or offers['url'],observed_at=now(),description=node.get('description','')))
            except (ValueError,KeyError,TypeError):continue
    if not items:raise SourceError('XIANYU_LOGIN_OR_STRUCTURED_DATA_REQUIRED: 公开搜索页没有可用商品数据；请配置授权数据接口，或导入商品资料。')
    return items[:100]

async def _search(query):
    if not PROVIDER_URL:return await asyncio.to_thread(public_search,query)
    target=urlsplit(PROVIDER_URL)
    if target.scheme!='https' or not target.hostname or target.username or target.password or target.fragment:
        raise SourceError('XIANYU_PROVIDER_URL_INVALID')
    # Operator-configured origin, never supplied by the browser; redirects disabled, credentials not forwarded.
    async with httpx.AsyncClient(timeout=25,follow_redirects=False) as client:
        async with client.stream('POST',PROVIDER_URL,headers={'Authorization':'Bearer '+PROVIDER_KEY},json={'query':query,'limit':100}) as response:
            if response.status_code!=200:raise SourceError('XIANYU_PROVIDER_UNAVAILABLE')
            chunks=bytearray()
            async for chunk in response.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks)>2_000_000:raise SourceError('XIANYU_PROVIDER_RESPONSE_TOO_LARGE')
    data=json.loads(chunks)
    items=[Listing.model_validate(x) for x in data.get('items',[])[:100]]
    if not items:raise SourceError('XIANYU_NO_ITEMS: 数据接口没有返回商品。')
    return items

async def search(query):
    try:
        return await _search(query)
    except SourceError:
        raise
    except (httpx.HTTPError,ValueError,KeyError,TypeError):
        raise SourceError('XIANYU_PROVIDER_RESPONSE_INVALID: 数据接口请求或响应校验失败，请检查接口配置和字段契约。') from None
