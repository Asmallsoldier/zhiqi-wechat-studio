"""Evidence-first used electronics analysis. All price calculations are deterministic."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
import hashlib, re, statistics
from urllib.parse import urlsplit, parse_qs
from pydantic import BaseModel, Field, field_validator

def now():
    return datetime.now(timezone.utc).isoformat()

def normalize(value: str) -> str:
    return re.sub(r'\s+', '', value.casefold())

def listing_identity(item):
    """Provider labels must not turn one Goofish item into two market samples."""
    u=urlsplit(item['url'])
    if u.hostname in ('goofish.com','www.goofish.com','m.goofish.com'):
        ids=parse_qs(u.query).get('id',[])
        if len(ids)==1 and ids[0]:return ('goofish',ids[0])
    return (item['source_id'],item['external_id'])

def deduplicate(items):
    unique={}
    for item in items:
        key=listing_identity(item)
        previous=unique.get(key)
        if previous is None or datetime.fromisoformat(item['observed_at'])>datetime.fromisoformat(previous['observed_at']):
            unique[key]=item
        elif datetime.fromisoformat(item['observed_at'])==datetime.fromisoformat(previous['observed_at']):
            facts=('price','shipping','model','variant','condition','repair_status','battery_health','inspection_available')
            def comparable(record,key):
                value=record.get(key)
                if key in ('price','shipping'):return Decimal(str(value))
                if key in ('model','variant'):return normalize(value)
                return value
            if any(comparable(item,k)!=comparable(previous,k) for k in facts):
                unique[key]={**previous,'_evidence_conflict':True}
    return list(unique.values())

class Listing(BaseModel):
    source_id: Literal['xianyu', 'manual', 'authorized_provider'] = 'xianyu'
    external_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=2, max_length=240)
    model: str = Field(min_length=2, max_length=100)
    variant: str = Field(min_length=1, max_length=100, description='容量、内存、处理器等可比配置，不能留空')
    category: Literal['phone','tablet','laptop','gpu','camera','other'] = 'other'
    condition: Literal['new','good','fair','parts','unknown'] = 'unknown'
    price: Decimal = Field(gt=0, le=1000000, max_digits=12, decimal_places=2)
    shipping: Decimal = Field(default=Decimal('0'), ge=0, le=100000, max_digits=10, decimal_places=2)
    currency: Literal['CNY'] = 'CNY'
    url: str = Field(max_length=2048)
    observed_at: datetime
    seller_ref: str = Field(default='', max_length=128, description='仅去重用的卖家代号，不采集联系方式')
    description: str = Field(default='', max_length=8000)
    battery_health: int | None = Field(default=None, ge=0, le=100)
    inspection_available: bool = False
    repair_status: Literal['unknown','seller_claims_original','repaired','verified_original'] = 'unknown'

    @field_validator('url')
    @classmethod
    def safe_url(cls, value):
        from urllib.parse import urlsplit
        u=urlsplit(value)
        if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443):
            raise ValueError('需要有效 HTTPS 商品原链接')
        return value

    @field_validator('observed_at')
    @classmethod
    def dated(cls, value):
        if value.tzinfo is None: raise ValueError('采集时间必须包含时区')
        if (value-datetime.now(timezone.utc)).total_seconds()>300: raise ValueError('采集时间不能在未来')
        return value

    def public(self):
        data=self.model_dump(mode='json')
        data['seller_ref']=hashlib.sha256(self.seller_ref.encode()).hexdigest()[:20] if self.seller_ref else ''
        return data

class ImportBatch(BaseModel):
    items: list[Listing] = Field(min_length=1, max_length=200)

RISK_TERMS=['进水','账户锁','有锁','监管机','黑解','扩容','已维修','换屏','拆修','仅定金','订金','定金','空盒','求购','收购','不支持验机',
            '租赁','月租','首付','补差价','仅配件','仅主板']

def risks(item: dict, at: datetime) -> list[str]:
    text=item['title']+' '+item.get('description','')
    found=[f'描述含“{word}”' for word in RISK_TERMS if word in text]
    if item.get('_evidence_conflict'):found.append('同一商品在相同观察时间的资料不一致')
    if item['condition'] in ('parts','unknown'): found.append('成色/完整性不足以确认')
    age=(at-datetime.fromisoformat(item['observed_at'])).total_seconds()/3600
    if age>72: found.append('价格已超过72小时，需重新询价')
    if item.get('repair_status','unknown')=='unknown':found.append('维修史未确认')
    if item.get('repair_status')=='repaired':found.append('存在维修记录')
    if not item.get('inspection_available'):found.append('未确认支持验机')
    if item['category'] in ('phone','tablet','laptop'):
        if item.get('battery_health') is None:found.append('电池健康未知')
        elif item['battery_health']<80:found.append('电池健康低于80%')
    return found

def analyze(items: list[dict], at: datetime | None=None):
    at=at or datetime.now(timezone.utc)
    # Deduplicate by listing identity, never treat repeat imports as more market evidence.
    unique=deduplicate(items)
    groups={}
    for item in unique:
        key=(item['category'],normalize(item['model']),normalize(item['variant']),item['condition'],item['currency'])
        groups.setdefault(key,[]).append(item)
    reports=[]
    for key, group in groups.items():
        usable=[i for i in group if (at-datetime.fromisoformat(i['observed_at'])).total_seconds()<=72*3600
          and not i.get('_evidence_conflict') and i['condition'] not in ('parts','unknown') and not any(w in i['title']+' '+i.get('description','') for w in RISK_TERMS)]
        prices=[Decimal(str(i['price']))+Decimal(str(i.get('shipping',0))) for i in usable]
        median=statistics.median(prices) if prices else None
        sellers=len({i['seller_ref'] for i in usable if i.get('seller_ref')})
        enough=len(prices)>=5 and sellers>=3
        candidates=[]
        for item in group:
            total=Decimal(str(item['price']))+Decimal(str(item.get('shipping',0)))
            delta=round(float((median-total)/median*100),1) if median else None
            flags=risks(item,at)
            if delta is not None and delta>35:flags.append('显著低于同组挂牌价，先排查诱导价/故障机')
            if not enough:flags.append('可比样本或独立卖家不足')
            verdict='值得核验' if enough and not flags and delta is not None and 5<=delta<=35 else '谨慎核验' if flags else '价格一般'
            candidates.append({**item,'total_price':float(total),'discount_percent':delta,'risks':flags,'verdict':verdict})
        candidates.sort(key=lambda i:(i['verdict']!='值得核验',len(i['risks']),i['total_price']))
        reports.append({'model':group[0]['model'],'variant':group[0]['variant'],'condition':key[3],
          'sample_count':len(prices),'seller_count':sellers,'median_asking_price':float(median) if median else None,
          'confidence':'中' if enough else '低','candidates':candidates})
    return {'at':at.isoformat(),'sample_count':len(unique),'groups':reports,
      'method':'同型号、同配置、同成色，含运费挂牌价中位数；至少5个近期样本和3个卖家才给出值得核验候选。',
      'limits':['挂牌价不是成交价。','无法仅凭商品描述确认真伪、功能、维修史或卖家信用。','推荐结论仅针对本次样本，成交前需核验实时库存和验机结果。']}

def article_draft(report: dict, title: str):
    if report.get('kind')=='news':
        lines=[f'# {title}','以下为本次选题的公开资料摘要，需在正式发表前核实原文中的适用条件与时间。']
        for source in report['sources']:
            lines += [f"## {source['title']}",source['summary'],f"[参考资料]({source['url']}) · {source['published_at']}"]
        lines += ['## 编辑核验提示','摘要不代表设备实测或购买建议。应区分发布者声明、独立证实和编辑推断，不把海外售价直接等同于国内购买成本。']
        return '\n\n'.join(lines)
    lines=[f'# {title}' ,'把二手数码买得划算，关键是先比较同一配置，再判断低价背后需要承担什么。以下判断来自本次保存的商品样本。']
    for group in report['groups']:
        lines += [f"## {group['model']} · {group['variant']}",
          f"同成色可比样本 {group['sample_count']} 条，卖家代号 {group['seller_count']} 个。" +
          (f"含运费挂牌价中位数约 {group['median_asking_price']:.2f} 元。" if group['median_asking_price'] is not None else '当前没有足够有效价格，暂不判断便宜与否。')]
        for item in group['candidates'][:3]:
            lines.append(f"### {item['verdict']}：{item['title']}")
            lines.append(f"挂牌含运费 {item['total_price']:.2f} 元。"+('需要核实：'+'；'.join(item['risks'])+'。' if item['risks'] else '价格有比较优势，建议先确认设备身份、现场功能和平台担保交易条件。'))
            lines.append(f"[商品原链接]({item['url']}) · 观察时间：{item['observed_at']}")
    lines+=['## 怎么做购买决定','优先选择支持验机、描述完整且配置一致的商品。手机核对账号锁与电池，电脑核对硬件配置与稳定性；付款前再次确认价格、运费及售后条件。',
      '## 样本与限制',report['method'],*report['limits'],f"分析时间：{report['at']}。本文不代表已购买、实测或验证任何卖家。"]
    return '\n\n'.join(lines)
