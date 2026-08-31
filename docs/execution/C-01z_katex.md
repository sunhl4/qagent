# C-01z · 3080 脸渲染公式（KaTeX）

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-28 |
| 角色 | P · C-01z |
| 范围 | `customer-shell` 消息渲染 · 本地 vendor KaTeX · `_safe_static_path` · 口吻/Skill · 本笔记 · `tests/test_c01z.py` |
| 未改 | `assignment.py` 黄金路径 · 科学核 · `agent.py` · DSH `apps/web` · Overleaf / TeXLive |
| 状态 | 聊天泡用本地 KaTeX 画 `\(...\)` / `$$...$$`。钉住失败图注用人话。**不算 G0**。未 commit。 |

## 为什么不是 Overleaf

- Overleaf / 整页 TeX 要服务器和编译，不适合聊天气泡。
- DSH `apps/web` 的 remark-math 管线是 React 构建产物，3080 是 vanilla `customer-shell`，搬不过来。
- 本地 KaTeX + 现有 `fillRichText` 可离线、改完刷新即用。

## 产品锁

- vendor 在 `apps/customer-shell/vendor/katex/`，不走 CDN。
- `/static/vendor/katex/...` 只许安全相对路径（禁 `..`、禁点文件）。
- `fillRichText` 不对整段模型原文 `innerHTML`。KaTeX 只写进公式节点。
- 行内 `\(...\)`，块级 `$$...$$` / `\[...\]`；兼容 `$...$`（`$100` 不当公式）。
- API 仍回 `circuit not pinned`。脸上图注写「电路还没钉住，画不出图。」
- 气泡仍 `send("批准")`。JS 仍不许出现 `ionstack_twin_run`。
- **不算 G0 / G1 / G2**。skip 当绿 = 没做完。未 commit。

## 不算什么

- **不算 G0**。人还没按演示剧本走完。
- 未把 CAL / shuttle 塞进工具。未假 `twin_id`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_c01z.py
PYTHONPATH=src python3 tests/test_c01y.py
PYTHONPATH=src python3 tests/test_h01l.py
```

公式节点对整段 reply `innerHTML`，或静态路径能 `../` 逃出壳目录，必须失败。skip 当绿 = 没做完。不 commit。
