# 配置说明

Compose 从私有 `.env` 读取；`.env.example` 只含公开模板。后端直接运行时使用环境变量。

| 变量 | 默认值/用途 |
| --- | --- |
| STUDIO_MODE | standalone；shared 需额外显式配置共享服务 |
| STUDIO_DB_PATH | 本地 ./data/studio.db，容器 /data/studio.db |
| STUDIO_BIND_ADDRESS / STUDIO_PORT | Compose 127.0.0.1 / 3103 |
| STUDIO_ENCRYPTION_KEY | 留空时自动生成凭据加密密钥，保存于数据库旁 credential.key，权限0600；必须备份 |
| STUDIO_EMERGENCY_STOP | false；true 阻断新业务执行及官方执行器 |
| STUDIO_DRAFT_ENABLED | false；允许上传素材、创建草稿 |
| STUDIO_PUBLISH_ENABLED | false；允许正式发表，仍需账号开关和单次授权 |
| STUDIO_PUBLISH_DAILY_LIMIT | 每账号每日最多5个新投递意图，包括失败和结果不明的请求 |
| STUDIO_SOURCE_SCHEDULER | Compose false；true 每6小时刷新候选来源，可能访问境外站点 |
| STUDIO_PIPELINE_WORKER | true；按次任务后台处理开关 |
| STUDIO_AI_BASE_URL | 兼容 Chat Completions 的 API 基础地址，包含 /v1（按提供方约定），不含 /chat/completions |
| STUDIO_AI_KEY / STUDIO_AI_MODEL | 自己的提供方密钥与模型名；三项齐备才显示 AI 可用 |
| STUDIO_AI_DAILY_LIMIT | 每部署每日5次新文章调用意图，失败和未知结果同样计入 |
| XIANYU_PROVIDER_URL / XIANYU_PROVIDER_KEY | 自行获授权的 HTTPS 结构化商品接口及密钥；不是闲鱼官方开放接口地址 |
| SHARED_API_ORIGIN | shared 模式必填；standalone 不使用 |

模型响应应为 choices[0].message.content 内的 JSON：title 和 body（Markdown），finish_reason 为 stop。输入资料不作为指令执行。已收到的响应保存在 model_receipt；解析失败可以恢复已有响应，不重新付费调用。

修改环境配置后重建 api 容器。密钥丢失会阻断解密，不会生成新密钥覆盖已有密文。加密不能代替部署访问控制；有权读取卷或环境变量的管理员仍能访问数据。
