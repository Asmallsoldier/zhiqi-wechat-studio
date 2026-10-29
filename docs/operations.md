# 运维与排障

## 备份和恢复

需要同时保存 SQLite 一致性备份和凭据加密密钥；只保存 studio.db 无法恢复公众号凭据。`scripts/backup.py` 使用 SQLite backup API 并验证完整性。容器内可通过 `docker compose cp scripts/backup.py api:/tmp/backup.py` 后执行：

```sh
docker compose exec api python /tmp/backup.py /data/studio.db /data/backups/studio-backup.db
```

然后将备份和 `/data/credential.key` 复制到私有加密备份目录，权限0600；如果使用 STUDIO_ENCRYPTION_KEY，应由密钥管理系统备份该值。不要把备份提交 Git 或放进官网。恢复时先在隔离的 Compose 项目停机替换数据库和对应密钥，再以急停和关闭外发的配置启动，确认数据及原任务状态后恢复操作。保留原卷以便回滚。

## 常见阻断

| 错误/现象 | 处理 |
| --- | --- |
| WECHAT_40164 | 在当前公众号自己的后台添加服务器实际出口IP白名单，不是仅添加浏览器IP |
| WECHAT_48001 | 账号缺少当前接口权限，核对微信账号类型、认证和接口权限 |
| PUBLICATION_TOKEN_UNAVAILABLE | 网络、微信响应、AppID/密钥或IP白名单；连接探测不产生文章 |
| WECHAT_42001 | Token过期；核对凭据和连接，使用原任务继续 |
| PUBLICATION_OUTCOME_UNKNOWN | 已发出的写入未取得确定回执；核对微信素材/草稿/发表记录，禁止另建相同文章重试 |
| PUBLICATION_AUTH_CHANGED / ACCOUNT_CHANGED | 用户/角色/密码/凭据版本发生变化；确认账号仍为原AppID后显式继续原任务 |
| ARTICLE_RESULT_UNCONFIRMED | 生成未完成或响应格式无效；检查文章状态，优先恢复保存的响应 |
| AI_OUTCOME_UNKNOWN | 模型调用结果不明，核对提供方记录；不会自动重复付费 |
| SESSION_REQUIRED | 服务重启或会话失效；重新登录并继续原任务 |
| XIANYU_LOGIN_OR_STRUCTURED_DATA_REQUIRED | 公开页不能提供结构化资料，改用自己的授权提供方或合规资料导入 |
| SELECTION_STALE | 来源观察时间超72小时或异常；核验更新后重新研究，不修改历史快照伪造新数据 |

页面“处理中”意味着等待官方最终结果，不能当作成功。草稿 Media ID 是素材/草稿标识，不是正式链接；publish_id 是异步查询编号，正式文章须等 article_id 和 article_url。

总急停阻断后续新调用，但无法撤回已发送请求。撤销密钥或退出登录会使旧授权失效；迟到回执仍可能归档，应核对原记录。当前没有自动修复未知写入或人工强制标记已发表的接口。

## 健康和审计

入口 `/health` 检查 Nginx；容器API `/health` 检查数据库可连接。研究审计接口 `/api/v1/research/audit` 只返回当前用户业务记录。不要开启包含完整请求URL、Authorization、模型正文或微信Token的调试日志。

升级前备份；不要在工作任务未确认时随意恢复旧快照，防止把已发送意图回滚成未发送。schema_version 记录版本，后续结构迁移应单独评审。本版无多实例运行承诺。
