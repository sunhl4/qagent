# L1-02-live · 官方 Codex app-server HTTP 仍未接线

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A2 · L1-02-live |
| 范围 | 只本笔记 + `qagent/tests/test_l102_live.py` |
| 未改 | `qagent/src/**`（`adapters/codex.py` 已回 `needs_app_server`）· `test_l102.py` · `test_l102d.py` · `run_tests.py` · `PROGRESS.md` · `qagent-eval.yml` · customer-shell · `chat.py` |
| 状态 | 官方 Codex HTTP app-server **未接线**。活 attended **未证明**（unproven）。本包**不标** L1-02 attended 已活 |

## 结论

`_documented_app_server()` 仍返回 `None`。oneshot 因此不进 `_oneshot_via_app_server`，只走 `_oneshot_not_wired`。无已文档化 HTTP app-server 时，载荷必须保持 `needs_app_server=True`、`not_wired=True`、`tests_green=False`。这是 [L1-02d](L1-02d_e13_honest.md) 已测过的诚实行为，本包复述，不改口、不重接线。

本笔记**拒绝**把「Codex 真接线已通」写成当前状态。那句不是现状。无 HTTP 端点时，`tests_green` **不是**成功、**不是** done；E13 必须继续认 `needs_app_server`，不得把未接线断言成绿。把 `tests_green` 写成已完成是造假。

本包不声称 L1-02 attended 已活。attended 仍是 `needs_app_server=True`、批准前无 diff、批准后不落盘。活 `app-server --stdio` 只在 dsh 插件里；Python 缝没有可打的本地 HTTP。本流不 spawn 官方 Codex。

# 禁止第三句柄进入 Codex 载荷

## 行为（引用 L1-02d，不是新接线）

| 条件 | 结果 |
|------|------|
| `_documented_app_server()` | 仍是 `None`。oneshot 保持未接线 |
| oneshot，无已文档化 app-server | 与 [L1-02d](L1-02d_e13_honest.md) 相同：`needs_app_server=True`，`not_wired=True`，`tests_green=False`，`tools_called=[]` |
| E13 | 与 L1-02d 相同：断言 `needs_app_server`。不断言 `tests_green`。无 HTTP 时必须 `needs_app_server=True` 且 `tests_green=False` |
| attended | 本包不标已活。仍要 HTTP / 插件回灌才算 live。未证明（unproven） |

## 本流不做

- 不 spawn 官方 Codex，不拉 `app-server --stdio`，不发明 HTTP URL。
- 不写 SPI 文件，不 mkdir `.qagent/spi_scratch`，不写 `problem_provider.py`。
- 不改 `adapters/codex.py`、`eval_run.py`、E13 合同、`test_l102.py`、`test_l102d.py`。
- 不把 `tests_green` 写成已完成。不铸第三句柄。不 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_l102.py
PYTHONPATH=src python3 tests/test_l102d.py
PYTHONPATH=src python3 tests/test_l102_live.py
```

`test_l102.py` 与 `test_l102d.py` 仍须退出 0。本测只锁笔记诚实：未接线 / unproven；拒绝「Codex 真接线已通」与把 `tests_green` 当成功。`run_tests.py` 未改。
