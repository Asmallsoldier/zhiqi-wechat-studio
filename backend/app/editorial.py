"""Deterministic selection and article checks; no invented market/transaction data."""
from datetime import datetime, timezone
from decimal import Decimal
import html
import re
from urllib.parse import urlsplit

from .domain import analyze, deduplicate, listing_identity
from .publication_bridge import digest


class EditorialBlock(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def select_report(items):
    if not items or len(items) > 200:
        raise EditorialBlock('SAMPLE_LIMIT', '每次选品需要 1–200 条明确的商品记录。')
    if any(i['source_id'] not in ('xianyu', 'authorized_provider') for i in items):
        raise EditorialBlock('XIANYU_EVIDENCE_REQUIRED', '本流程仅分析有来源标识的闲鱼或已配置接口商品。')
    report = analyze(items)
    groups = [g for g in report['groups'] if any(c['verdict'] == '值得核验' for c in g['candidates'])]
    groups.sort(key=lambda g: max(c['discount_percent'] or 0 for c in g['candidates'] if c['verdict'] == '值得核验'), reverse=True)
    if not groups:
        raise EditorialBlock('NO_QUALIFIED_SELECTION', '没有通过门槛的选品：同配置需至少 5 条近期样本、3 个卖家，并有价格优势且无已识别风险的候选。')
    report['groups'] = groups[:3]
    report['selection_rule'] = '候选含运费挂牌价较同组中位数低5%–35%，且无已识别风险；最多三个可比组，不把异常低价或风险未确认的商品作为购买推荐。'
    # Frozen full samples are retained separately. Keep model input bounded and factual.
    for group in report['groups']:
        for candidate in group['candidates']:
            candidate['description'] = candidate.get('description', '')[:300]
    if len(str(report)) > 60000:
        raise EditorialBlock('SELECTION_TOO_LARGE', '选品资料过多，请按型号缩小样本范围。')
    return report


def selection_hash(items):
    values=[]
    for item in deduplicate(items):
        identity=listing_identity(item)
        # A refreshed observation time alone is not a new deal/article. Keep the
        # complete timestamped source snapshot separately for freshness and audit.
        excluded={'id','observed_at'}
        if identity[0]=='goofish':excluded|={'source_id','external_id','url'}
        facts={k:v for k,v in item.items() if k not in excluded}
        for key in ('price','shipping'):
            facts[key]=format(Decimal(str(facts.get(key,0))).normalize(),'f')
        values.append({'identity':identity,'facts':facts})
    return digest(sorted(values,key=lambda x:x['identity']))


def freshness(report):
    at = datetime.now(timezone.utc)
    if report.get('kind')=='news':
        if not report.get('sources'):raise EditorialBlock('NO_SOURCES','文章缺少冻结资料')
        for source in report['sources']:
            age=(at-datetime.fromisoformat(source['published_at'])).total_seconds()
            if age>72*3600 or age< -300:raise EditorialBlock('SELECTION_STALE','资讯超过72小时或时间无效')
    for group in report.get('groups', []):
        for candidate in group['candidates']:
            age = (at - datetime.fromisoformat(candidate['observed_at'])).total_seconds()
            if age > 72 * 3600 or age < -300:
                raise EditorialBlock('SELECTION_STALE', '选品观察时间已超过72小时或时间无效，不能继续提交文章。')


def validate_article(article, report):
    freshness(report)
    body, title = article['body'], article['title']
    issues = []
    if not 2 <= len(title) <= 64:
        issues.append('标题需为2–64个字符')
    if not 200 <= len(body) <= 20000:
        issues.append('正文长度需为200–20000个字符')
    if re.search(r'闭眼买|稳赚|保证升值|全网最低|本人亲测|我们实测|已经验机|百分百正品', title + body):
        issues.append('存在缺少证据的实测、真伪或收益承诺')
    if report.get('kind')=='news':
        links={s['url'] for s in report['sources']}
        if any(u not in links for u in re.findall(r'https?://[^\s)<>]+',body)):issues.append('正文引用了未冻结的资料链接')
        if issues:raise EditorialBlock('ARTICLE_VALIDATION_FAILED','；'.join(issues))
        return {'passed':True,'checks':['来源时效','正文长度','引用范围','承诺用语'],'content_hash':digest({'title':title,'body':body})}
    allowed_prices = set()
    allowed_discounts = set()
    for group in report['groups']:
        if group['median_asking_price'] is not None:
            allowed_prices.add(Decimal(str(group['median_asking_price'])))
            allowed_prices.add(Decimal(f"{group['median_asking_price']:.2f}"))
        for c in group['candidates']:
            allowed_prices.update(Decimal(str(c[k])) for k in ('price', 'shipping', 'total_price'))
            if c['discount_percent'] is not None:
                allowed_discounts.add(Decimal(str(c['discount_percent'])))
    for left, right in re.findall(r'[¥￥]\s*(\d+(?:\.\d+)?)|(?<![\d.])(\d+(?:\.\d+)?)\s*元', title + body):
        if Decimal(left or right) not in allowed_prices:
            issues.append('正文含原始分析中不存在的金额'); break
    for value in re.findall(r'(?<![\d.])(\d+(?:\.\d+)?)\s*%', title + body):
        # Battery percentages and the explicit 35% anomaly rule are also source facts.
        known = allowed_discounts | {Decimal('5'), Decimal('35')} | {Decimal(str(c['battery_health'])) for g in report['groups'] for c in g['candidates'] if c.get('battery_health') is not None}
        if Decimal(value) not in known:
            issues.append('正文含原始分析中不存在的百分比'); break
    if not all(word in body for word in ('挂牌', '成交', '核验')):
        issues.append('正文缺少挂牌价、成交价和核验边界')
    allowed_links = {c['url'] for g in report['groups'] for c in g['candidates']}
    for value in re.findall(r'https?://[^\s)<>]+', body):
        if value not in allowed_links:
            issues.append('正文引用了未冻结的商品或资料链接'); break
    if issues:
        raise EditorialBlock('ARTICLE_VALIDATION_FAILED', '；'.join(dict.fromkeys(issues)))
    return {'passed': True, 'checks': ['来源时效', '选品样本门槛', '金额和百分比', '引用链接', '承诺用语', '文章长度'],
            'content_hash': digest({'title': title, 'body': body})}


def wechat_html(markdown):
    """Small escaped Markdown subset, no raw HTML, scripts or external pictures."""
    def inline(text):
        escaped = html.escape(text)
        def link(m):
            url = html.unescape(m.group(2))
            try:
                u = urlsplit(url)
                safe = u.scheme == 'https' and u.hostname and not u.username and not u.password and u.port in (None, 443)
            except ValueError:
                safe = False
            return '<a href="' + html.escape(url, quote=True) + '">' + m.group(1) + '</a>' if safe else m.group(1)
        escaped = re.sub(r'(?<!!)\[([^\]]+)\]\(([^)]+)\)', link, escaped)
        return re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', escaped)
    parts = []
    for paragraph in markdown.split('\n\n'):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        tag = 'h2' if paragraph.startswith('#') else 'p'
        parts.append(f'<{tag}>' + inline(paragraph.lstrip('# ')).replace('\n', '<br>') + f'</{tag}>')
    for offset, key in ((len(parts) // 2, 'risks'), (min(2, len(parts)), 'comparison')):
        parts.insert(offset, '<p><img src="{{image:' + key + '}}" alt="原创选品资料图解，非产品实拍"></p>')
    return '<section>' + ''.join(parts) + '</section>'
