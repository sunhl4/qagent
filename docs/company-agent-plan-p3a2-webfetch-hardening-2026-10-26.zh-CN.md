# P3 批次 A2 执行记录：受管网页检索硬化（2026-10-26）

依据：[约 2000 人天计划](company-agent-2000-person-days-development-plan-v1.0.zh-CN.md) P3 受管网页检索工作包；[P3-A1 批次记录](company-agent-plan-p3a1-webfetch-2026-10-26.zh-CN.md)「诚实的不完整」三项的直接收尾。本批次不新增工具，只对 `company_fetch` 做硬化：地址钉扎、来源引用（title）、注入信号检测。

## 1. 交付

1. **地址钉扎，关闭重解析窗口**：`webfetch.py` 不再经 opener 二次解析。`_resolve_guard` 只解析一次，然后在**已验证的地址**上直接建连（`http.client` + 自管 socket）；HTTPS 仍按原始主机名做证书身份校验（SNI/明确校验），所以钉扎没有削弱 TLS——DNS 重绑定在「解析后、连入前」的窗口被构造性消除。多地址解析时取排序后的第一个地址（单请求语义决定只触达一个端点）。回环字面量例外路径完全不碰 OS resolver。
2. **来源引用**：HTML 提取增加独立 `title` 字段（\(\le 256\) 字节、字节安全截断），`<title>` 正文同时从 body 文本中剔除，避免重复计入；text/plain 页面 `title` 为空串。
3. **注入信号检测（确定性、有界、只算证据）**：对返回的截断文本运行四类固定检测模式并输出 `signals: {fired, reasons}`——`override_language`（覆盖前文指令类措辞）、`tool_invocation_directive`（调用/执行工具或 company 前缀工具名的指令）、`credential_disclosure`（要求导出/打印密钥凭据类）、`role_identity_claim`（声称系统提示词或「你现在就是」身份声明）。检测是模式匹配证据而非安全裁定：`trust=untrusted_reference_data` 恒定不变，未截断整页不参与扫描（被截断片段诚实标记）。
4. 合同同步：`tools.json` 中 `company_fetch` 输出增加 `title` 与 `signals`（reasons 四值枚举、maxItems 8、封闭对象），描述更新为「直接对 allowlist 验证过的公网地址发一请求，证书身份钉在请求主机名上」；DSH schema 投影自动跟随，无插件改动。

## 2. 验证（不含全量前的定向）

- `tests/test_web_fetch.py` 18 → **24 项**：新增四类检测的正例/反例分类、页面级 signals 端到端、title 字节边界截断（中文 85 字边界）、回环字面量短路 resolver、连接地址钉扎（loopback 连接记录）与「主机名只解析一次、连到解析地址而非主机名」的假 resolver 用例；既有 18 项全部改为新输出形状的等价断言。
- ruff 对触碰文件无告警；合同加载与 50 工具目录（并行 P2 里程碑批次叠加后）保持一致。

## 3. 边界（诚实的不完整）

- 信号检测是启发式模式匹配：class 的漏报/误报都可能；正例集合由测试钉住，页面文本永远只是数据、不构成任何授权来源。
- 证书校验按请求主机名执行——allowlist 条目应使用与证书一致的名称；自签名/私有 CA 页面会按传输失败闭合（P3 下一批次才考虑受管 CA 集合）。
- 未对多 AAAA/A 记录做全地址触达与比对；IPv6 字面量仍在 allowlist 语法之外（失效闭合）。
- 上传截断文本之外的部分（超 20000 字节片段、超 1MB 正文）不参与信号扫描，这一事实由 `scan` 原因显式声明。
