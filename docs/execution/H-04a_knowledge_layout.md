# H-04a · 知识库目录约定

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | S1 |
| 环境 | `QAGENT_KNOWLEDGE_PATH`（workplace 设置写入） |
| 检索 | `qagent/src/qagent/adapters/docs.py` · 工具 `qccd_docs_search` |

## 目录（默认仓内）

```text
qagent/knowledge/
  README.md          本约定的人读版
  manuals/           手册（TwinRun 字段、回执、preset）
  specs/             规范（句柄、政策、评测 ID）
  patents/           已公开专利摘要，不是申请稿全文
```

栈内手册 `qagent/handbooks/` 继续作为内置兜底（`docs.py` 已读）。workplace 的知识路径是**追加**，不是替换。

多根目录用 `os.pathsep` 拼进 `QAGENT_KNOWLEDGE_PATH`。

## 准许

- Markdown / 纯文本。  
- 手册、已发布规范、公开专利摘要。  
- 命中必须带回**相对该根的 path**（现有适配器已做）。

## 禁止

- 实验原始比特串、shots 明细、未脱敏 `counts`。  
- 密钥、`.qagent/secrets.json`、dsh credentials。  
- 把整段 QASM / Pauli 全文当知识条（电路只经 `circuit_id`）。  
- 出网抓取（H-04c：`qccd_docs_search` 不出网）。

## 空库

根不存在或没有命中时：诚实「没有这条」。内置 `handbooks/twin_run.md` 只在**完全没有外部根**时作为合同兜底，不把空的客户知识库假装成手册命中。H-04b 改 `docs.py` 时要把「空外部库」和「内置兜底」分开断言。

## H-04b 下一步

分段 + 索引；命中短摘录；测：查 TwinRun 字段必中 `mode` / `shots` / `body`。
