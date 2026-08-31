# L1-02d · E13 诚实：未接线不是绿

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | Q |
| 范围 | `adapters/codex.py` · `services/eval_run.py` · `contracts/eval/E13.json` · `tests/test_l102d.py` |
| 层 | Layer 1 造包缝。不是客户 Agent，不是第三套 loop |

## 结论

oneshot 在没有已文档化 app-server 时，载荷是 `needs_app_server=True`、`not_wired=True`、`tests_green=False`。E13 合同改认 `needs_app_server`，不再把「没接线」断言成跑绿。`eval_run` 新增 `needs_app_server` 断言键；若合同仍写 `tests_green` 而载荷带 `needs_app_server`，判红。E17 未改，仍过。

活路径 `_oneshot_via_app_server` 只抄 live 里的 `tests_green`，不发明 `True`。`_documented_app_server()` 仍是 `None`。官方 Codex：`permission_mode=never`，`inherits_parent_context=false`。algo 看不见签收工具。

# 禁止第三句柄进入 Codex 载荷

## 行为

| 条件 | 结果 |
|------|------|
| oneshot，无已文档化 app-server | `needs_app_server=True`，`not_wired=True`，`tests_green=False`，`tools_called=[]` |
| oneshot，将来若有 live URL 且 live 说绿 | `tests_green` 仅当 live 字段为真 |
| E13 | 断言 `needs_app_server`，并 `did_not_call` 签收工具。不断言 `tests_green` |
| E17 | 仍是 `approval_item` + `no_diff_until_approved` |

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_l102d.py
PYTHONPATH=src python3 tests/test_l102.py
```

`test_l102d.py` 与 `test_l102.py` 退出 0。`run_tests.py` 未改。E01–E21 里 E13 改合同后仍绿，因为断言对上了诚实载荷。

## 不做

- 不改 `run_tests.py`、`PROGRESS.md`、chat / dsh session / workplace、assignment、customer-shell、`agent.py`。
- 不 `import` 科学核。不把签收工具注册给官方 Codex。
- 不铸第三句柄。不新写 agent loop。
- 不 commit。

## 剩

- 活 `app-server --stdio` 仍只在 dsh 插件里；Python 缝没有可打的本地 HTTP。
- 批准后的 fileChange 回灌仍要等 H-01 / attended 插件填 `fill()`。
