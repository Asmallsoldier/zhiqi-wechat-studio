# 部署与开发

## Docker 独立部署

在项目根目录复制 `.env.example` 为 `.env`，执行 README 的三条启动命令。Compose 仅启动本项目的 api、web，使用独立命名卷 `studio-data`。API 只在容器网络开放，宿主机默认监听 127.0.0.1:3103。

局域网演示可设置 `STUDIO_BIND_ADDRESS=0.0.0.0`。公网运营应先在入口配置 HTTPS、访问限制和备份；不要将模型密钥或公众号密钥放进 VITE 变量。生产与验收使用不同的 Compose 项目名、端口及卷。

```sh
docker compose ps
docker compose logs --tail=100 api
docker compose exec api python -m app.manage create-user --username operator --role wechat_operator --must-change-password
```

用户管理通过容器内交互式 CLI 完成。可用命令：`create-user`、`reset-password`、`set-role --role readonly_operator`、`disable-user`、`enable-user`；每条命令需要 `--username`。密码不接受命令行参数。密码重置要求下次修改，角色或状态变化立即撤销会话及旧任务授权。

## 开放草稿与正式发表

1. 添加公众号，保存 AppID、AppSecret，配置微信后台的出口 IP 白名单。
2. `.env` 设置 `STUDIO_DRAFT_ENABLED=true`；执行 `docker compose up -d api`，选择证据稿或已生成文章，投递草稿验收。
3. 正式发表需要 `STUDIO_PUBLISH_ENABLED=true`、账号页的“允许正式发表”以及本次任务授权同时满足。保留已选账号和文章，确认其具备微信所需接口权限。
4. 只有微信最终回执包含文章编号和有效文章地址才显示已发表。主动群发不在范围内。

开关不是在运行期间自动改成正式发表的策略：每个任务固定账号、正文快照、草稿/发表方式和授权版本。打开开关不会补发历史内容。总急停设置 `STUDIO_EMERGENCY_STOP=true` 并重建 api 容器；已发出的微信请求不能被本地急停撤回。

## 本地开发

Python 3.12+、Node.js 22.22.2+，建议独立虚拟环境。

```sh
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
python -m app.manage create-user --username owner --role super_admin
STUDIO_SOURCE_SCHEDULER=false uvicorn app.main:app --host 127.0.0.1 --port 8102 --workers 1
```

另一终端：

```sh
cd web
npm ci
npm run dev -- --mode wechat
```

访问 Vite 提示的地址。开发代理指向本机 8102；API 和前端使用同源请求。不要把端口 8102 暴露公网。测试：后端 `python -m pytest -q`；前端 `npm run test:run` 和 `npm run build`。

本版任务执行只支持**单个 API 进程、单个副本**。多实例、高可用、共享租户协作需要额外调度与一致性设计；不要直接提高 workers 数量。

## 已有部署迁移

不读取旧平台数据库或自动复制旧凭据。先单独部署空库验收，再通过受控导出/导入迁移资料，重新配置账号和授权。旧任务、草稿和失败内容不自动补发。`STUDIO_MODE=shared` 与显式 `SHARED_API_ORIGIN` 仅适配旧私有平台接口，不提供该平台代码或可用性保证。
