# 数据源与接入

来源目录在 `backend/app/catalog.json`，包含36个候选来源。RSS、结构化页面、研究与社区链接的可用性随网站变化，目录中 `unverified` 不是在线承诺。刷新会记录成功、无条目、网络或访问限制；不把站点链接伪装成已成功接入的数据流。

公开资料仅保留选题所需标题、摘要、时间、来源链接。模型据冻结资料组织表达；原作者权利、网站访问条款和媒体转载限制不会因AI改写而消失。公开仓库不包含采集内容和用户数据库。

## 商品导入

使用 `/api/v1/research/listings/import`，最多200项。示例为虚构测试资料，不能作为文章中的真实商品证据：

```json
{"items":[{"source_id":"xianyu","external_id":"example-1","title":"测试手机样本","model":"测试型号","variant":"256GB","condition":"good","price":1000,"shipping":0,"category":"phone","url":"https://www.goofish.com/item?id=example-1","seller_ref":"anonymous-seller-1","observed_at":"2026-01-01T00:00:00+00:00","repair_status":"unknown","inspection_available":null}]}
```

实际资料应填写真实观察时间、当前挂牌价和原链接，不收集买家聊天、手机号或其他无关个人信息。seller_ref 使用去标识化代号；电池、维修、验机状态未知时保留未知，不自动推断“原装”。

## 授权数据提供方

配置 `XIANYU_PROVIDER_URL` 和 `XIANYU_PROVIDER_KEY`。适配器发送 POST，JSON正文 `{"query":"关键词","limit":100}`，头 `Authorization: Bearer ...`，期望 `{ "items": [符合 Listing 模型的商品] }`。调用超时25秒，禁止重定向，不转发密钥到其他站点。提供方需要HTTPS地址；具体数据许可和费用由运营者自行确认。

公开 goofish 页面适配器仅解析可读取的 Product JSON-LD，配置或型号不全时忽略记录。触发登录、验证码、风控或限流就停止，不导入Cookie、不绕过验证。本版本没有内置可用的官方闲鱼搜索凭据。

## 分析门槛

比较同型号、配置、成色；同组至少5条近期样本、3个卖家。含运费挂牌价低于组内中位数5%–35%且无已识别风险的候选标为“值得核验”。排除租赁、首付、配件等误导样本。超72小时资料不得新投递；数据不足就结束选题，不补造商品或价格。

市场样本偏差、描述真实性、隐藏维修、平台交易条件仍需运营者及读者核验。该能力不提供自动购买或自动交易。
