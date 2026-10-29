"""Versioned shared publication boundary. Never receives WeChat credentials.

An ambiguous PUT is followed by GET only. A bridge must advertise this exact
contract before a run is allowed to spend on generation or submit content.
"""
import hashlib
import json
import re
from urllib.parse import urlsplit, parse_qs

import httpx

CONTRACT = 'research-publication-v1'
ROOT = '/api/v1/wechat-workspace/research-publications'
CAPABILITY_MESSAGES = {
    'PUBLICATION_PERMISSION_REQUIRED': '当前用户缺少公众号发表权限，请由管理员检查角色权限与账号绑定。',
    'PUBLICATION_ACCOUNT_NOT_AUTHORIZED': '该公众号尚未加入研究发表授权范围，请由管理员确认目标账号。',
    'PUBLICATION_CREDENTIAL_REQUIRED': '公众号凭据或账号状态不可用，请在账号页完成配置和诊断。',
    'PUBLICATION_DAILY_LIMIT': '当前公众号已达到当天研究投递上限，尚未启动本次写作。',
    'PUBLICATION_BRIDGE_DISABLED': '研究发表接口尚未启用，请完成共享服务配置。',
    'PUBLICATION_EMERGENCY_STOP': '公共服务已急停，恢复后可继续原任务。',
    'PUBLICATION_EXTERNAL_DISABLED': '公众号研究外发尚未获准，请检查公众号专用外发配置。',
    'PUBLICATION_MODE_DISABLED': '所选公众号交付模式尚未启用，请检查账号发表配置。',
    'PUBLICATION_SAFETY_UNAVAILABLE': '发布安全状态暂时无法读取，待共享服务恢复后继续。',
}


class BridgeError(Exception):
    def __init__(self, code, message, retryable=False, unknown=False):
        super().__init__(message)
        self.code, self.message = code, message
        self.retryable, self.unknown = retryable, unknown


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def official_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return ''
    try:
        u = urlsplit(value)
        if (u.scheme != 'https' or u.hostname != 'mp.weixin.qq.com' or u.username
                or u.password or u.port not in (None, 443) or u.fragment
                or not (u.path.startswith('/s/') or u.path == '/s')):
            return ''
        if any(k.casefold() in ('access_token', 'token', 'key') for k in parse_qs(u.query)):
            return ''
        if u.path == '/s' and not all(k in parse_qs(u.query) for k in ('__biz', 'mid', 'idx', 'sn')):
            return ''
        return value
    except ValueError:
        return ''


def checked_receipt(data, run):
    """Reject wrong-account/stale responses, including apparently successful ones."""
    if (not isinstance(data, dict) or data.get('contractVersion') != CONTRACT
            or data.get('requestId') != run['id'] or data.get('accountId') != run['account_id']
            or data.get('contentHash') != run['content_hash']
            or data.get('deliveryMode') != run['delivery_mode']):
        raise BridgeError('PUBLICATION_RECEIPT_MISMATCH', '发布回执与本次账号、内容或请求不一致，已停止写入。')
    status = data.get('status')
    allowed = {'accepted', 'preparing', 'draft_created', 'draft_delivered', 'publishing',
               'reconciling', 'published', 'rejected', 'failed', 'blocked'}
    if status not in allowed:
        raise BridgeError('PUBLICATION_RESPONSE_INVALID', '发布服务返回了未知状态，继续查询同一请求。', True, True)
    if status == 'draft_delivered' and (run['delivery_mode'] != 'draft_only' or not data.get('draftMediaId')):
        raise BridgeError('PUBLICATION_RECEIPT_MISMATCH', '草稿回执缺少编号或不符合本次发表模式。')
    if status == 'published' and run['delivery_mode'] != 'publish':
        raise BridgeError('PUBLICATION_RECEIPT_MISMATCH', '草稿模式收到正式发表回执，请人工核对。')
    for name in ('deliveryId', 'draftMediaId', 'publishId', 'articleId'):
        value = data.get(name, '')
        if not isinstance(value, str) or len(value) > 256 or any(ord(c) < 32 for c in value):
            raise BridgeError('PUBLICATION_RESPONSE_INVALID', '发布回执编号格式无效，继续查询同一请求。', True, True)
    result = {k: data.get(k, '') for k in ('status', 'deliveryId', 'draftMediaId', 'publishId',
                                          'articleId', 'publishedUrl', 'errorCode')}
    # Never persist arbitrary remote error strings, HTML, credentials or signed URLs.
    result['publishedUrl'] = official_url(result['publishedUrl'])
    if not isinstance(result['errorCode'], str) or not re.fullmatch(r'[A-Z0-9_]{0,100}', result['errorCode']):
        result['errorCode'] = 'PUBLICATION_REMOTE_ERROR'
    if status == 'published' and (not result['publishedUrl'] or not result['articleId']):
        result['status'] = 'reconciling'
        result['errorCode'] = 'PUBLICATION_FINAL_LINK_PENDING'
    return result


class PublicationBridge:
    def __init__(self, origin, token):
        self.origin, self.token = origin.rstrip('/'), token

    async def _call(self, method, path, **kwargs):
        try:
            async with httpx.AsyncClient(timeout=35, follow_redirects=False) as client:
                response = await client.request(method, self.origin + ROOT + path,
                                                headers={'Authorization': self.token}, **kwargs)
        except httpx.HTTPError:
            raise BridgeError('PUBLICATION_SERVICE_UNAVAILABLE', '发布服务网络异常；若已提交，将仅查询原请求。', True, method == 'PUT') from None
        if response.status_code in (401, 403):
            raise BridgeError('PUBLICATION_AUTH_REQUIRED', '登录已过期或缺少发表权限，请重新登录后继续。')
        if response.status_code == 404:
            raise BridgeError('PUBLICATION_NOT_FOUND', '发布接口或原请求不存在，请核对共享服务部署。', False, method == 'PUT')
        if response.status_code >= 500 or response.status_code in (408, 429):
            raise BridgeError('PUBLICATION_SERVICE_UNAVAILABLE', '发布服务暂时不可用，稍后查询同一请求。', True, method == 'PUT')
        try:
            body = response.json()
            if response.status_code >= 300 or body.get('success') is not True:
                raise BridgeError('PUBLICATION_SERVICE_REJECTED', '发布服务拒绝请求，请核对账号权限、封面和发表开关。', False, method == 'PUT')
            data = body['data']
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (ValueError, KeyError, TypeError, AttributeError):
            raise BridgeError('PUBLICATION_RESPONSE_INVALID', '发布服务响应无法解析；若已提交，将仅查询原请求。', True, method == 'PUT') from None

    async def capabilities(self, account_id, mode):
        try:
            data = await self._call('GET', '/capabilities', params={'accountId': account_id})
        except BridgeError as exc:
            if exc.code == 'PUBLICATION_NOT_FOUND':
                raise BridgeError('PUBLICATION_CONTRACT_UNAVAILABLE', '共享服务尚未部署研究发表接口，请先完成公共服务集成。') from None
            raise
        if (data.get('contractVersion') != CONTRACT or data.get('accountId') != account_id
                or data.get('idempotentSubmission') is not True):
            raise BridgeError('PUBLICATION_CONTRACT_UNAVAILABLE', '共享服务尚未接入当前研究发表契约。')
        if data.get('emergencyStop'):
            raise BridgeError('EMERGENCY_STOP', '公共服务已急停，请恢复后继续。')
        modes = data.get('deliveryModes')
        if not isinstance(modes, list) or any(m not in ('draft_only', 'publish') for m in modes) or mode not in modes:
            blocker = data.get('blockedReason')
            if isinstance(blocker, str) and blocker in CAPABILITY_MESSAGES:
                raise BridgeError(blocker, CAPABILITY_MESSAGES[blocker])
            raise BridgeError('PUBLICATION_MODE_UNAVAILABLE', '该公众号当前不支持所选发表模式，请检查接口权限与账号开关。')
        return data

    async def submit(self, run, payload):
        data = await self._call('PUT', '/' + run['id'], json=payload)
        return checked_receipt(data, run)

    async def query(self, run):
        data = await self._call('GET', '/' + run['id'], params={'accountId': run['account_id']})
        return checked_receipt(data, run)
