# 公司知识库根

约定正文：[docs/execution/H-04a_knowledge_layout.md](../../docs/execution/H-04a_knowledge_layout.md)

| 目录 | 放什么 | 不放什么 |
|------|--------|----------|
| `manuals/` | 人读手册 | 实验原始比特串 |
| `specs/` | 已发布规范摘要 | 密钥、未公开电路 |
| `patents/` | 已公开专利摘要 | 申请稿全文、未脱敏数据 |

检索走 `qccd_docs_search`。workplace 设置里的「公司知识库路径」写入 `QAGENT_KNOWLEDGE_PATH`。本目录可以是其中一根。

手册条目：`twinrun_fields.md`（TwinRun 字段）、`list_engines.md`（哪些包 / 五包）、`route_estimate.md`（估计 / makespan_ns）、`receipt.md`（回执 / verify_receipt）、`eln.md`（ELN / recipe_pin）、`tenant.md`（租户 / 隔离）。
