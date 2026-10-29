# 接口说明

基址 `/api/v1`，同源请求，除 login、refresh、product、health 外均需 `Authorization: Bearer <accessToken>`。成功返回 `{success:true,data:...}`；业务错误返回 `{success:false,code,message}`。数据结构以运行服务 `/openapi.json` 为准，交互说明 `/docs`（API容器内端口8102）。

| 方法与路径 | 用途 |
| --- | --- |
| GET /product | 模式与版本，不含私有配置 |
| POST /auth/login | username/password；返回用户和访问/刷新令牌 |
| GET /auth/me | 当前用户、角色、权限、强制改密状态 |
| POST /auth/refresh | refreshToken 单次轮换，必须保存新令牌 |
| POST /auth/logout | 撤销当前用户会话和旧任务授权 |
| POST /auth/change-password | currentPassword/newPassword，成功后重新登录 |
| GET /wechat-workspace/accounts | 自己的账号，永不返回 AppSecret |
| POST /wechat-workspace/accounts | requestId、accountName、allowPublish（默认false） |
| PUT /wechat-workspace/accounts/{id} | accountName、allowPublish；版本递增 |
| GET/PUT/DELETE /wechat-workspace/accounts/{id}/credential | 查看配置状态/保存 appId appSecret/撤销 |
| POST /wechat-workspace/accounts/{id}/probe | 只请求 Token，不创建素材或文章 |
| GET /research/capabilities | AI/数据提供方配置状态与任务能力 |
| GET /research/sources | 候选源及当前健康状态 |
| POST /research/sources/{id}/refresh | 刷新单个公开来源 |
| GET /research/news | 读取资料缓存 |
| POST /research/news/articles | 选择资料生成文章，字段见 OpenAPI |
| POST /research/listings/import | items 商品数组，校验后导入自己的资料 |
| GET /research/listings | 自己的商品样本 |
| POST /research/analyses | 按样本生成确定性分析 |
| GET /research/analyses | 自己的历史研究 |
| POST /research/articles | research_id、request_id、use_ai |
| GET /research/articles | 自己的文章及生成状态 |
| POST /research/articles/{id}/recover-response | 只重解析已有模型响应 |
| GET /research/articles/{id}/export | format=markdown 或 html |
| GET /research/articles/{id}/illustration | 文章资料图解 |
| POST /research/selection-runs | 创建单次分析/文章到公众号的任务 |
| GET /research/selection-runs | 自己的任务、阶段、阻断、正式链接 |
| GET /research/selection-runs/{id} | 任务详情 |
| POST /research/selection-runs/{id}/resume | 继续原任务，不创建新请求 |
| POST /research/selection-runs/{id}/cancel | 只允许提交意图前取消 |
| GET /research/publication-capabilities/{account_id}?mode=draft_only | 账号与部署开关检查，不代表官方权限验收 |

创建任务示意（使用自己导入的记录编号）：

```json
{"request_id":"00000000-0000-4000-8000-000000000001","account_id":"00000000-0000-4000-8000-000000000002","listing_ids":["00000000-0000-4000-8000-000000000003"],"use_ai":false,"delivery_mode":"draft_only","title":"本周数码选购核验"}
```

来源只能三选一：listing_ids、query、article_id。正式方式 `delivery_mode=publish` 必须额外 `acknowledge_automatic_publishing=true`。实际选品还要求足够样本，不会把单条商品直接当成可靠购买推荐。

底层 `wechat-workspace/research-publications` 接口供内部执行器适配；仅接受本用户经过校验且已冻结的任务快照，不能以任意 HTML 或图片绕过内容检查。不要在客户端直接重发官方素材或发表请求。
