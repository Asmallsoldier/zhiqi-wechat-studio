const messages: Record<string, string> = {
  AUTOMATION_ADMISSION_REQUEST_TOO_LARGE: '内部校验请求过大，尚未调用模型；请减少输入资料或联系管理员。此限制来自平台，不是 MiniMax。',
  MODEL_QUOTA_EXHAUSTED: 'MiniMax 订阅额度已用尽，尚未调用模型；请在系统配置 → 模型额度查看恢复时间。调高平台每日预算不能增加官方额度。',
  MODEL_QUOTA_UNSUPPORTED: '当前 MiniMax 套餐不支持该能力；请在系统配置 → 模型额度查看支持范围。',
  MODEL_QUOTA_UNAVAILABLE: '暂时无法核实 MiniMax 订阅剩余额度，已停止新模型调用；请在系统配置 → 模型额度刷新并查看原因。',
  WECHAT_COVER_QUOTA_CREDENTIAL_MISMATCH: '图片订阅凭据与额度查询凭据不同，暂不能安全生成；请统一配置。',
  AUTOMATION_MODEL_INPUT_TOO_LARGE: '输入资料超过平台当前单次调用上限，尚未调用模型；请减少来源数量或资料长度。调高每日预算不能解决。',
  AUTOMATION_ADMISSION_TIMEOUT: '平台内部模型校验超时，本步骤未调用模型；费用预占可能已建立，请先核对运行记录，勿连续重试。',
  AUTOMATION_ADMISSION_UNAVAILABLE: '平台内部模型校验服务暂不可用，本步骤未调用模型；请检查服务状态及运行记录。',
  AUTOMATION_ADMISSION_RESPONSE_INVALID: '平台内部模型校验返回格式异常，本步骤未调用模型；请联系管理员检查服务。',
  AUTOMATION_ADMISSION_AUTH_FAILED: '平台内部任务校验凭证无效，本步骤未调用模型；请联系管理员，不需要重新扫码授权公众号。',
  AUTOMATION_MODEL_NOT_ADMITTED: '平台未允许本步骤调用模型，具体原因需查看执行日志；此错误不等同于模型余额不足。',
  AUTOMATION_DAILY_BUDGET_EXCEEDED: '今日自动运营模型预算不足；请查看模型与预算中的已结算和预占金额。',
}
const stages: Record<string, string> = { editor: '选题', writer: '写作', revision: '返修', fact_checker: '事实审校', quality_editor: '质量审核', visual_editor: '封面选择' }

export function formatAutomationFailure(reason = ''): string {
  const match = reason.match(/(?:^|:)\s*((?:AUTOMATION_|MODEL_QUOTA_|WECHAT_COVER_QUOTA_)[A-Z_]+)(?=:|$)/)
  const message = match && messages[match[1]!]
  if (!message) return reason
  const stage = reason.match(/^WECHAT_STAGE_FAILED:([^:]+):/)?.[1]
  return `${stage ? `${stages[stage] || stage}失败：` : ''}${message}（${match![1]}）`
}
