# 参与开发

按[部署指南](docs/deployment.md)运行独立开发环境。创建分支，保持修改集中，附可复现的验证步骤。后端使用 pytest，前端使用 Vitest 与 TypeScript/Vite 构建；真实模型、供应商与微信调用不是默认测试的一部分。

修改投递流程必须验证：提交意图先于发送、同请求不重复、结果不明停发、迟到回执、重启、权限变更、处理中与最终成功的区别。不要用Mock结果声称真实发表成功。数据库变化需记录版本与升级/回滚过程，不静默丢弃历史状态。

新增数据源需标明来源类型、原链接及使用限制；不可接入登录绕过、验证码规避或私密信息采集。新增依赖更新锁文件和 `docs/dependencies.json`，保留许可证。Python直接依赖维护在 requirements.txt；安装审核后的版本，再用开发虚拟环境执行 `python scripts/dependency-inventory.py` 更新解析锁文件与清单。

文档链接运行 `python scripts/check-docs.py`；公开包运行 `python scripts/release.py --check`。提交源码前检查 `git diff --cached`。CI不使用生产密钥，不在测试中调用真实发布。

贡献应为本人有权提交的内容，并按本项目 Apache-2.0 许可。讨论和评审尊重参与者，不公开他人的账号资料。仓库地址确定后再配置Issue模板、维护者和安全报告入口。
