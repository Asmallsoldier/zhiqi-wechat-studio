"""Owned, durable single-instance selection-to-publication jobs.

One transition per lease. No credential persistence. After restart the operator
resumes with a freshly verified session; submitting jobs resume as queries only.
"""
import asyncio
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from . import db, xianyu
from .domain import now
from .editorial import EditorialBlock, select_report, selection_hash, freshness, validate_article, wechat_html
from .publication_bridge import BridgeError, PublicationBridge, digest, CONTRACT

TERMINAL = {'published', 'draft_delivered', 'no_selection', 'rejected', 'canceled'}
STAGES = ['preflight', 'collect', 'analyze', 'write', 'validate', 'illustrate', 'deliver', 'reconcile', 'complete']


class SelectionRequest(BaseModel):
    request_id: uuid.UUID
    account_id: uuid.UUID
    query: str = Field(default='', max_length=80)
    article_id: uuid.UUID | None = None
    listing_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    title: str = Field(default='二手数码，哪些值得进一步核验？', min_length=2, max_length=64)
    delivery_mode: Literal['draft_only', 'publish'] = 'draft_only'
    use_ai: bool = True
    acknowledge_automatic_publishing: bool = False

    @model_validator(mode='after')
    def source_and_authority(self):
        self.query = self.query.strip()
        if sum((bool(self.query),bool(self.listing_ids),bool(self.article_id)))!=1 or (self.query and len(self.query) < 2):
            raise ValueError('请选择商品样本、至少两个字符的关键词或已生成文章；只能选一项')
        if self.article_id:self.use_ai=False
        if len(set(self.listing_ids)) != len(self.listing_ids):
            raise ValueError('商品记录不能重复选择')
        if self.delivery_mode == 'publish' and not self.acknowledge_automatic_publishing:
            raise ValueError('正式发表需要明确授权生成后的合格文章自动提交到所选公众号')
        return self


class PipelineError(Exception):
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def row_for(conn, run_id, owner):
    row = conn.execute('SELECT * FROM selection_run WHERE id=? AND owner=?', (run_id, owner)).fetchone()
    if not row:
        raise PipelineError('NOT_FOUND', '任务不存在或无权访问', 404)
    return dict(row)


def public_run(row):
    # Model/provider credentials, bearer tokens, image base64 and submitted HTML stay server-side.
    receipt = json.loads(row['receipt_json'])
    snapshot = json.loads(row['snapshot_json'])
    return {**{k: row[k] for k in ('id', 'request_id', 'account_id', 'delivery_mode', 'stage', 'status', 'article_id',
                                  'research_id', 'content_hash', 'error_code', 'message', 'created_at', 'updated_at')},
            'source_kind':snapshot.get('report',{}).get('kind','listings'),
            'title': snapshot.get('article', {}).get('title') or json.loads(row['request_json'])['title'], 'receipt': receipt,
            'review': snapshot.get('review'), 'sample_count': len(snapshot.get('items', [])),
            'has_submit_intent': bool(row['submit_intent']), 'stages': STAGES}


def create(request, owner):
    encoded = request.model_dump(mode='json')
    encoded['listing_ids'] = sorted(encoded['listing_ids'])
    with db.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        existing = conn.execute('SELECT * FROM selection_run WHERE owner=? AND request_id=?',
                                (owner, str(request.request_id))).fetchone()
        if existing:
            if json.loads(existing['request_json']) != encoded:
                raise PipelineError('REQUEST_ID_CONFLICT', '请求编号已用于其他选品任务')
            return dict(existing)
        # All selected IDs must be owned; silently dropping foreign/missing IDs is forbidden.
        if request.listing_ids:
            wanted = {str(i) for i in request.listing_ids}
            rows = conn.execute('SELECT id,payload FROM listing WHERE owner=? AND id IN ('
                                + ','.join('?' for _ in wanted) + ')', (owner, *sorted(wanted))).fetchall()
            items = [json.loads(r['payload']) for r in rows if r['id'] in wanted]
            if len(items) != len(wanted):
                raise PipelineError('NOT_FOUND', '部分商品不存在或无权访问', 404)
        else:
            items = []
        snapshot={'items':items}
        if request.article_id:
            source=conn.execute('SELECT * FROM article WHERE id=? AND owner=?',(str(request.article_id),owner)).fetchone()
            if not source or source['status'] not in ('ready','needs_review'):raise PipelineError('ARTICLE_NOT_READY','文章不存在或尚未完成',404)
            research=conn.execute('SELECT * FROM research WHERE id=? AND owner=?',(source['research_id'],owner)).fetchone()
            snapshot.update(report=json.loads(research['payload']),source_article_id=source['id'])
        run_id = str(uuid.uuid4())
        try:
            conn.execute('''INSERT INTO selection_run(id,owner,request_id,account_id,delivery_mode,stage,status,
                         request_json,snapshot_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                         (run_id, owner, str(request.request_id), str(request.account_id), request.delivery_mode,
                          'preflight', 'queued', db.dump(encoded), db.dump(snapshot), now(), now()))
        except sqlite3.IntegrityError:
            raise PipelineError('ACCOUNT_RUN_ACTIVE', '该公众号已有未完成的选品任务，请先处理或取消原任务') from None
        record_action(conn, owner, run_id, 'selection_created')
        return row_for(conn, run_id, owner)


def record_action(conn, owner, run_id, action):
    conn.execute('INSERT INTO audit(owner,action,detail,created_at) VALUES(?,?,?,?)',
                 (owner, action, db.dump({'run_id': run_id}), now()))


def claim(run_id, owner):
    tag = str(uuid.uuid4())
    with db.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = row_for(conn, run_id, owner)
        if row['status'] in TERMINAL or row['status'] == 'blocked' or row['lease_until'] > time.time():
            return None
        if row['next_attempt_at'] and row['next_attempt_at'] > now():
            return None
        conn.execute('UPDATE selection_run SET lease_owner=?,lease_until=? WHERE id=?', (tag, time.time() + 300, run_id))
        return row_for(conn, run_id, owner)


def save(run, **changes):
    changes['updated_at'] = now()
    changes['lease_owner'], changes['lease_until'] = '', 0
    with db.connect() as conn:
        result = conn.execute('UPDATE selection_run SET ' + ','.join(k + '=?' for k in changes)
                              + ' WHERE id=? AND owner=? AND lease_owner=? AND lease_until>?',
                              (*changes.values(), run['id'], run['owner'], run['lease_owner'], time.time()))
        if result.rowcount != 1:
            raise PipelineError('RUN_LEASE_LOST', '任务执行锁已失效，请读取当前状态')
        conn.execute('INSERT INTO audit(owner,action,detail,created_at) VALUES(?,?,?,?)',
                     (run['owner'], 'selection_transition', db.dump({'run_id': run['id'],
                       'from': run['stage'], 'to': changes.get('stage', run['stage']),
                       'status': changes.get('status'), 'code': changes.get('error_code', '')}), now()))


def recover_after_restart():
    with db.connect() as conn:
        conn.execute("""UPDATE selection_run SET status='blocked',error_code='SESSION_REQUIRED',
                     message='服务已重启，请登录后点击继续；已提交的任务将只查询原请求。',lease_owner='',lease_until=0,
                     updated_at=? WHERE status IN ('queued','running','publishing','reconciling')""", (now(),))


def resume(run_id, owner):
    with db.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = row_for(conn, run_id, owner)
        if row['status'] in TERMINAL:
            return row
        if row['lease_until'] > time.time():
            raise PipelineError('RUN_BUSY', '任务正在执行，请稍后查看')
        # A durable submit intent is irrevocable: resume never returns to PUT.
        stage = 'reconcile' if row['submit_intent'] else row['stage']
        conn.execute("UPDATE selection_run SET status='queued',stage=?,error_code='',message='',next_attempt_at='',lease_owner='',lease_until=0,updated_at=? WHERE id=?",
                     (stage, now(), run_id))
        record_action(conn, owner, run_id, 'selection_resumed')
        return row_for(conn, run_id, owner)


def cancel(run_id, owner):
    with db.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = row_for(conn, run_id, owner)
        if row['status'] in TERMINAL:
            return row
        if row['submit_intent']:
            raise PipelineError('SUBMISSION_MUST_RECONCILE', '已存在提交意图，必须查询原结果，不能取消后重复创建')
        if row['lease_until'] > time.time():
            raise PipelineError('RUN_BUSY', '任务正在执行，请等待当前步骤完成后取消')
        conn.execute("UPDATE selection_run SET status='canceled',message='用户取消，未开始正式投递。',updated_at=? WHERE id=?", (now(), run_id))
        record_action(conn, owner, run_id, 'selection_canceled')
        return row_for(conn, run_id, owner)


def freeze_intent(run):
    # Keep lease while persisting the side-effect boundary.
    with db.connect() as conn:
        result = conn.execute('UPDATE selection_run SET submit_intent=1,stage=\'reconcile\',status=\'reconciling\',updated_at=? WHERE id=? AND lease_owner=? AND lease_until>? AND submit_intent=0',
                              (now(), run['id'], run['lease_owner'], time.time()))
        if result.rowcount != 1:
            raise PipelineError('RUN_LEASE_LOST', '发布提交执行权已变化，请读取任务状态')
    run['submit_intent'] = 1


def apply_receipt(run, receipt):
    status = receipt['status']
    reason = {
        'WECHAT_48001': '公众号缺少所需接口权限，请检查认证类型及接口权限。',
        'WECHAT_40164': '服务器出口IP未在当前公众号白名单内，请添加后继续查询原任务。',
        'WECHAT_42001': '公众号Token已过期，请在账号页检查凭据与Token刷新。',
        'WECHAT_COVER_REQUIRED': '封面素材未就绪，请核对账号的封面与素材权限。',
            'EMERGENCY_STOP': '发表服务已急停，请恢复后继续查询原任务。',
    }.get(receipt.get('errorCode'), '发表服务阻断了本次任务，请核对账号、素材权限及发布记录。')
    if status in ('published', 'draft_delivered'):
        save(run, stage='complete', status=status, receipt_json=db.dump(receipt), error_code='', message='微信已确认正式发表。' if status == 'published' else '微信草稿已交付。')
    elif status in ('failed', 'rejected'):
        save(run, stage='reconcile', status='rejected', receipt_json=db.dump(receipt), error_code=receipt.get('errorCode') or 'PUBLICATION_REJECTED', message='微信拒绝或发表失败，请核对发布记录；本任务不会重新创建文章。')
    elif status == 'blocked':
        save(run, stage='reconcile', status='blocked', receipt_json=db.dump(receipt),
             error_code=receipt.get('errorCode') or 'PUBLICATION_BLOCKED', message=reason)
    else:
        phase={'cover':'正在准备封面素材。','comparison':'正在上传正文比较图。','risks':'正在上传正文风险图。','draft':'正在创建微信草稿。','submit':'正在提交正式发表。','query':'微信发布处理中，等待最终回执。'}.get(receipt.get('currentStage'),'微信发布处理中，等待最终回执。')
        save(run, stage='reconcile', status='publishing' if status == 'publishing' else 'reconciling',
             receipt_json=db.dump(receipt), error_code=receipt.get('errorCode', ''),
             message=phase, next_attempt_at=(datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat())


async def advance(run_id, owner, token, bridge=None):
    from . import main
    if main.STOP:
        raise PipelineError('EMERGENCY_STOP', '系统已暂停新业务操作', 503)
    run = claim(run_id, owner)
    if not run:
        return
    if bridge is None:
        if main.STUDIO_MODE=='standalone':
            from .local_publication import LocalBridge
            bridge=LocalBridge(token)
        else:bridge=PublicationBridge(main.SHARED,token)
    request = json.loads(run['request_json'])
    snapshot = json.loads(run['snapshot_json'])
    try:
        if run['stage'] == 'preflight':
            await bridge.capabilities(run['account_id'], run['delivery_mode'])
            if request['use_ai'] and not (main.AI_BASE and main.AI_KEY and main.AI_MODEL):
                raise EditorialBlock('AI_NOT_CONFIGURED', '尚未配置文章模型，可选择证据稿模式。')
            save(run, stage='collect', status='running', error_code='', message='账号发表能力检查通过。')
        elif run['stage'] == 'collect':
            if request.get('article_id'):
                save(run,stage='analyze',status='running',message='已读取原文章与冻结依据。');return
            if request['query'] and not snapshot.get('items'):
                # Search intent survives restarts too. A paid/provider result is never re-requested blindly.
                if snapshot.get('collect_intent') and not snapshot.get('items'):
                    raise EditorialBlock('COLLECTION_OUTCOME_UNKNOWN', '上次商品采集结果未确认，请核对数据接口记录；本任务不会自动重采。')
                snapshot['collect_intent'] = True
                with db.connect() as conn:
                    conn.execute('UPDATE selection_run SET snapshot_json=? WHERE id=? AND lease_owner=?', (db.dump(snapshot), run['id'], run['lease_owner']))
                found = await xianyu.search(request['query'])
                snapshot['items'] = [i.public() for i in found]
                with db.connect() as conn:
                    conn.execute('UPDATE selection_run SET snapshot_json=? WHERE id=? AND lease_owner=? AND lease_until>?',
                                 (db.dump(snapshot), run['id'], run['lease_owner'], time.time()))
                main.import_items(found, owner)
            if not snapshot.get('items'):
                raise EditorialBlock('NO_SAMPLES', '没有可用商品数据，请接入数据接口或选择已导入样本。')
            save(run, stage='analyze', status='running', snapshot_json=db.dump(snapshot), message='商品资料已冻结。')
        elif run['stage'] == 'analyze':
            if request.get('article_id'):
                freshness(snapshot['report'])
                with db.connect() as c:
                    source=c.execute('SELECT * FROM article WHERE id=? AND owner=?',(request['article_id'],owner)).fetchone()
                fingerprint=digest({'title':source['title'],'body':source['body']})
            else:
                snapshot['report'] = select_report(snapshot['items'])
                fingerprint = selection_hash(snapshot['items'])
            with db.connect() as conn:
                same = conn.execute('SELECT id FROM selection_run WHERE account_id=? AND selection_hash=? AND id<>?', (run['account_id'], fingerprint, run['id'])).fetchone()
                if same:
                    raise EditorialBlock('DUPLICATE_SELECTION', '该公众号已有相同样本的选品任务，请查看原记录，避免重复文章。')
                research_id = run['id']
                conn.execute('INSERT OR IGNORE INTO research VALUES(?,?,?,?,?)', (research_id, owner, request['title'], db.dump(snapshot['report']), now()))
            save(run, stage='write', status='running', snapshot_json=db.dump(snapshot), selection_hash=fingerprint, research_id=research_id, message='已选出可比样本充分且无已识别风险的候选。')
        elif run['stage'] == 'write':
            article_request_id = str(uuid.uuid5(uuid.UUID(run['id']), 'selection-article-v1'))
            with db.connect() as conn:
                existing = conn.execute('SELECT * FROM article WHERE owner=? AND request_id=?', (owner, article_request_id)).fetchone()
            if request.get('article_id'):
                with db.connect() as c:article=main.owned(c,'article',request['article_id'],owner)
            elif existing:
                article = dict(existing)
            else:
                result = await main.article_create(main.ArticleRequest(research_id=run['research_id'], request_id=article_request_id, use_ai=request['use_ai']), owner)
                article = result['data']
            if article['status'] not in ('ready', 'needs_review'):
                save(run, article_id=article['id'], status='blocked', error_code='ARTICLE_RESULT_UNCONFIRMED',
                     message='模型文章未成功完成，请在研究文章核对原调用或恢复已保存响应；本任务不会再次调用模型。')
                return
            save(run, stage='validate', status='running', article_id=article['id'], message='文章已生成，开始校验。')
        elif run['stage'] == 'validate':
            with db.connect() as conn:
                article = main.owned(conn, 'article', run['article_id'], owner)
            snapshot['review'] = validate_article(article, snapshot['report'])
            snapshot['article'] = {'title': article['title'], 'body': article['body']}
            save(run, stage='illustrate', status='running', snapshot_json=db.dump(snapshot), message='文章自动校验通过。')
        elif run['stage'] == 'illustrate':
            from .illustrations import render
            article, report = snapshot['article'], snapshot['report']
            images = []
            for key, role in (('cover', 'cover'), ('comparison', 'inline'), ('risks', 'inline')):
                image = await asyncio.to_thread(render, article['title'], report, key)
                images.append({'key': key, 'role': role, 'mime': 'image/png', 'sha256': hashlib.sha256(image).hexdigest(), 'base64': base64.b64encode(image).decode()})
            payload = {'contractVersion': CONTRACT, 'accountId': run['account_id'], 'externalRunId': run['id'],
                       'requestId': run['id'], 'deliveryMode': run['delivery_mode'], 'title': article['title'],
                       'markdown': article['body'], 'html': wechat_html(article['body']), 'images': images,
                       'evidence': {'report': report, 'review': snapshot['review'], 'selectionHash': run['selection_hash']},
                       'acknowledgeAutomaticPublishing': request['acknowledge_automatic_publishing']}
            content_hash = digest(payload)
            payload['contentHash'] = content_hash
            if len(db.dump(payload).encode()) > 1_900_000:
                raise EditorialBlock('PUBLICATION_PAYLOAD_TOO_LARGE', '图文及依据超出投递大小限制，请缩小选品范围。')
            save(run, stage='deliver', status='running', payload_json=db.dump(payload), content_hash=content_hash, message='封面和两张正文资料图解已准备。')
        elif run['stage'] == 'deliver':
            freshness(snapshot['report'])
            payload = json.loads(run['payload_json'])
            if digest({k: v for k, v in payload.items() if k != 'contentHash'}) != run['content_hash']:
                raise EditorialBlock('CONTENT_SNAPSHOT_CHANGED', '投递图文快照已变化，已停止。')
            await bridge.capabilities(run['account_id'], run['delivery_mode'])
            freeze_intent(run)
            receipt = await bridge.submit(run, payload)
            apply_receipt(run, receipt)
        elif run['stage'] == 'reconcile':
            apply_receipt(run, await bridge.query(run))
        else:
            raise EditorialBlock('RUN_STAGE_INVALID', '任务阶段无法识别，请联系管理员。')
    except EditorialBlock as exc:
        save(run, status='no_selection' if exc.code == 'NO_QUALIFIED_SELECTION' else 'blocked', error_code=exc.code, message=exc.message)
    except BridgeError as exc:
        if run['submit_intent'] and exc.retryable:
            wait = min(300, 30 * 2 ** min(run['attempts'], 4))
            save(run, stage='reconcile', status='reconciling', error_code=exc.code, message=exc.message,
                 attempts=run['attempts'] + 1, next_attempt_at=(datetime.now(timezone.utc) + timedelta(seconds=wait)).isoformat())
        else:
            save(run, stage='reconcile' if run['submit_intent'] else run['stage'], status='blocked', error_code=exc.code, message=exc.message)
    except main.HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        save(run, status='blocked', error_code=detail.get('code', 'ARTICLE_BLOCKED'), message=detail.get('message', '文章生成条件未满足。'))
    except xianyu.SourceError as exc:
        code = str(exc).split(':')[0]
        save(run, status='blocked', error_code=code, message='商品数据接口没有返回已确认资料，请检查数据源；不会重复本次采集。')
    except asyncio.CancelledError:
        save(run, status='blocked', stage='reconcile' if run['submit_intent'] else run['stage'], error_code='RUN_INTERRUPTED', message='执行中断，请核对已有结果后继续。')
        raise
    except PipelineError:
        raise
    except Exception:
        # Never include exception text: httpx/OS errors may contain signed endpoints or credentials.
        save(run, status='blocked', stage='reconcile' if run['submit_intent'] else run['stage'], error_code='RUN_INTERNAL_ERROR', message='任务执行异常，已保留当前阶段和原请求，请核对后继续。')


class PipelineWorker:
    def __init__(self):
        self.sessions = {}  # Memory only. Never persist user tokens in SQLite/audit/payload.

    def authorize(self, run_id, owner, token):
        self.sessions[run_id] = (owner, token)

    async def serve(self, interval=2):
        while True:
            for run_id, (owner, token) in list(self.sessions.items()):
                try:
                    # Revalidate permissions before each transition, including a remote query.
                    from .main import validate_session, require_account_access
                    verified_owner = await validate_session(token, execute=True)
                    if verified_owner != owner:
                        raise PipelineError('SESSION_OWNER_CHANGED', '登录用户已变化，请重新登录。')
                    with db.connect() as conn:current=row_for(conn,run_id,owner)
                    await require_account_access(current['account_id'],token)
                    await advance(run_id, owner, token)
                    with db.connect() as conn:
                        row = row_for(conn, run_id, owner)
                    if row['status'] in TERMINAL or row['status'] == 'blocked':
                        self.sessions.pop(run_id, None)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    from .main import HTTPException
                    detail = exc.detail if isinstance(exc, HTTPException) and isinstance(exc.detail, dict) else {}
                    code = detail.get('code', 'WORKER_CHECK_FAILED')
                    message = detail.get('message', '任务检查失败，请读取原记录后继续。')
                    with db.connect() as conn:
                        conn.execute("UPDATE selection_run SET status='blocked',error_code=?,message=?,updated_at=? WHERE id=? AND owner=? AND lease_until<=? AND status NOT IN ('published','draft_delivered','no_selection','rejected','canceled')", (code, message, now(), run_id, owner, time.time()))
                    self.sessions.pop(run_id, None)
            await asyncio.sleep(interval)


worker = PipelineWorker()
