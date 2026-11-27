# 电商客服信箱：平台接入与 GitHub 预留

查证日期：2026-11-27。已核对公开官方资料；没有用生产商家授权、没有读取真实买家消息、没有向买家发信。当前客服信箱仍是手工登记、保存草稿和处理状态。

## 接入优先级

1. TikTok Shop 美国站：优先做单店试点。官方 Customer Service API 可读取会话和历史、订阅新会话和新消息、标记已读、发送人工回复。它属于 TikTok Shop Partner Center，不是现有社交发布渠道的 TikTok API。[29][35][42]
2. Lazada：第二个原生适配候选。`/im/session/list`、`/im/message/list`、`/im/message/send` 和 IM Push 覆盖列表、历史、人工回复和新消息。[4]
   卖家自用申请 `In-house IM Chat`，使用卖家白名单授权；商业服务商申请 `ERP IM Chat`，走服务市场订购及授权。先核对目标站点和批准的应用类别，不用普通订单应用代替。[15][73]
3. Shopee：有 Chat API 和 Push Mechanism，但官方 FAQ（2026-11-16 更新）称，个人第三方和第三方合作平台的新客服应用申请自 2024-11-18 起关闭。不能把自动消息伪装成人工回复。[18]
   卖家自用对应 `Seller In House System`；先按目标市场确认申请入口和店铺条件。未批准或未登录的 API 详情页不能证明有调用权限。[18][19]
4. Amazon：公开 SP-API Messaging v1 是按订单查询允许的消息类型并发送，Messaging Automations 管理自动回复规则；这两套参考都没有通用买家会话列表、聊天历史或实时客服收件接口。先保留手工处理；如需替代，可研究 Seller Central 的授权邮箱及买家加密邮件地址，但不承诺拉取全量历史。[21][22][7]
5. Temu：已检查美国站和 Global 的公开 Partner API 导航与授权文档，可见订单、退货退款、履约及事件能力，未核实可读取买家会话或发送聊天回复的官方公开接口。需要持对应站点和商家类型的账号确认是否有单独权限；在确认前不接入。[41][28]

## TikTok Shop：先验权限，再做试点

### 1. 核对准入

- 主账号进入 `Partner Center → App & Service → Manage → Manage API`，选择美国站的应用，查找 `Customer Service (seller.customer_service)`。`Active` 才可继续验证；`Inactive` 则走权限申请。若没有这一项，先看当前应用类别、应用类型与目标市场是否支持；不匹配时按官方流程用合适类别新建应用，而不是试用订单权限或复用社交授权。[29]
- 申请材料要能演示可交互的会话列表、历史、双方收发与续聊；工作测试环境或已运行的其他平台客服产品可用。只有登记和草稿的页面还不满足这项演示。对外应用可用具名卖家试点、合作记录或意向证明需求，官方这条路径不设最低卖家数，不必先达到规模门槛；平台认定为卖家自研的应用走既有免审流程，不能据此推断我们的美国店已获权。[35]
- 不把首轮「文本收发」等同于完整 App 功能验收。正式范围还要逐项对照官方功能清单，包括历史、已读、入站图片和视频、商品卡、订单卡、人工文本及图片回复等；订单卡需能取得订单信息。独立的拆包物流和退货退款场景可为可选项。[29][35]
- 真实订单和订单卡测试看 Full Function 开发店资格；通用开发店指南注明 Full Function 当前不支持跨境卖家模式，不假设 US 店可以开通。[31][44]

### 2. 数据与消息流

- 店铺授权：后台交换授权码并刷新 token；用 Get Authorized Shops（`seller.authorization.info` 是其授权之一）取得真实 `shop_id` 和 `shop_cipher`，将已授权店铺绑定到明确的工作区。使用独立的商家凭据和签名请求；不复用社交 token，敏感字段不进客户端、日志或版本库。[45][51][82]
- 首次同步：Get Conversations 和 Get Conversation Messages 分页读取（本次核对为 `202309`）；拉取历史不会在平台标记已读，已读调用单独控制。[12][13]
- 增量同步：接 New Conversation / New Message Webhook，验签、持久化入队后才返回成功。[14][29] 用 `tts_notification_id` 和店铺范围的外部消息 ID 去重，并用分页补拉修复漏投。[61]
- 数据结构建议：分出店铺连接、会话和逐条消息，保留人工录入为独立来源，不用店铺名、买家昵称或订单号作为账号／会话主键。以 `(provider, market, shop_id)` 校验数据归属，消息按 `(connection_id, external_message_id)` 去重。平台消息状态、工作台待处理状态与本地草稿分开；同步不覆盖草稿。
- 回复：先限定现有会话、人工确认及开发店，使用 Send Message 的 `202606` 版本（读写接口不必同版本）；分别处理平台已关闭、缺权限、限流、发送失败与结果不确定的状态。不确定是否已发出时先对账，不能无条件重发。不做主动营销、机器人回复或跨店铺群发。[35][42]
- 试点验收：一条开发买家消息入箱、历史可回拉、重复事件不加行、其他工作区看不到、测试买家收到人工回复、token 过期时显示待重授权。[44]
- 若暂拿不到 scope，运营可用美区卖家中心的未读提醒邮件及邮件回复作为过渡；官方标明约 15 分钟的提醒节奏，并非实时，也不代表已同步进本站。[87]

## GitHub：与电商独立，暂不接入真实仓库

- 预留 `GET /workspace/<workspace_id>/integrations/github/status/`（也支持 `HEAD`）。仅登录且在该工作区具备 `manage_workspace_settings` 权限的用户可读；归档工作区无有效状态。正常响应固定为 `{"provider":"github","status":"reserved","connected":false}`，禁止缓存；不接受写入请求。
- 当前没有 GitHub 凭据、安装流程、Webhook、外部请求或后台任务，也不把 GitHub 加到电商平台下拉并冒充客服来源。
- 业务用途明确后再选择 GitHub App 的仓库范围和最小权限；只有确需接收事件才加入签名验证。Issue、PR、仓库内容读取或任何写入不在本次范围，买家消息不得自动流入 GitHub。[20][57]

## Sources

[4] https://open.lazada.com/apps/doc/getting_started — Lazada Open Platform — LazOP 2.0 Overview / Instant Message API
[7] https://sellercentral.amazon.com/help/hub/reference/external/G200389080?ots=1 — Amazon Seller Central (US) — Buyer–Seller Messaging
[12] https://partner.tiktokshop.com/docv2/page/get-conversations-202309 — TikTok Shop — Get Conversations (202309)
[13] https://partner.tiktokshop.com/docv2/page/get-conversation-messages-202309 — TikTok Shop — Get Conversation Messages (202309)
[14] https://partner.tiktokshop.com/docv2/page/14-new-message — TikTok Shop — New Message webhook
[15] https://open.lazada.com/apps/doc/doc?docId=108002&nodeId=10398 — Lazada Open Platform — Create an App
[18] https://open.shopee.com/faq/56 — Shopee Open Platform — How to apply Chat API document permission
[19] https://open.shopee.com/documents/v2/v2.sellerchat.get_message?module=109&type=1 — Shopee Open Platform — v2.sellerchat.get_message
[20] https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/differences-between-github-apps-and-oauth-apps — GitHub Docs — Differences between GitHub Apps and OAuth apps
[21] https://developer-docs.amazon/sp-api/docs/messaging-api — Amazon SP-API — Messaging API
[22] https://developer-docs.amazon/sp-api/docs/messaging-automations-api — Amazon SP-API — Messaging Automations API
[28] https://partner.temu.com/documentation?menu_code=fb16b05f7a904765aac4af3a24b87d4a — Temu Partner Platform (Global) — API reference
[29] https://partner.tiktokshop.com/docv2/page/app-features — TikTok Shop — Customer Service App features
[31] https://partner.tiktokshop.com/docv2/page/seller-center-development-shops — TikTok Shop — Seller Center development shops
[35] https://partner.tiktokshop.com/docv2/page/customer-service-api-overview — TikTok Shop — Customer Service API overview and approval requirements
[41] https://partner-us.temu.com/documentation?menu_code=fb16b05f7a904765aac4af3a24b87d4a — Temu Partner Platform (US) — API reference
[42] https://partner.tiktokshop.com/docv2/page/send-message-202606 — TikTok Shop — Send Message (202606)
[44] https://partner.tiktokshop.com/docv2/page/end-to-end-testing-handbook — TikTok Shop — Customer Service end-to-end testing handbook
[45] https://partner.tiktokshop.com/docv2/page/sign-your-api-request — TikTok Shop — Sign your API request
[51] https://partner.tiktokshop.com/docv2/page/authorization-overview-202407 — TikTok Shop — Authorization overview
[57] https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries — GitHub Docs — Validating webhook deliveries
[61] https://partner.tiktokshop.com/docv2/page/configuration-guide — TikTok Shop — Webhook configuration guide
[73] https://open.lazada.com/apps/doc/doc?docId=108056&nodeId=10533 — Lazada Open Platform — App Authorization Policy
[82] https://partner.tiktokshop.com/docv2/page/get-authorized-shops-202309 — TikTok Shop — Get Authorized Shops (202309)
[87] https://seller-us.tiktok.com/university/essay?knowledge_id=5846413191907074&role=1&course_type=1&from=search&identity=1 — TikTok Shop US Academy — How to Contact Customers via Email
