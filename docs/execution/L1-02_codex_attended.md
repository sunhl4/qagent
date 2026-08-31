# L1-02 · Codex attended 真接线

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | A2 |
| 范围 | `qagent/src/qagent/adapters/codex.py` · `qagent/tests/test_l102.py` |
| 层 | Layer 1 造包缝。不是客户 Agent |

## 结论

oneshot **不再**把 SPI 夹具写进 `.qagent/spi_scratch`。官方 Codex 的产品缝是 dsh 插件拉起的 `app-server --stdio`，仓内**没有**已文档化的本地 HTTP 端点，所以 Python 适配器诚实回 `not_wired` / `needs_app_server`，不造文件。`tests_green` 仍留给 E13 合同键（eval_run 认这个字段）；真信号是 `needs_app_server`，不是「Codex 跑绿了」。

attended 的 `approval_item` 仍是 `fileChange`。批准前 `applied=False`、`diff=None`、工作区不新增长文件。批准后也不静默落盘 eval stub，只回 pending `file_change` 描述符。`inherits_parent_context=False`，`permission_mode=never`。

# 禁止第三句柄进入 Codex 载荷

## 行为

| 条件 | 结果 |
|------|------|
| oneshot，无已文档化 app-server URL | `needs_app_server=True`，`not_wired=True`，`tools_called=[]`。不 mkdir，不写 `problem_provider.py`。`tests_green` 只为 E13 保留键，不靠落盘夹具伪造 |
| oneshot，将来若有已文档化本地 URL | 只 POST `task` + `inherits_parent_context=false` + `permission_mode=never`。失败则退回上一行 |
| attended，未批准 | `status=needs_approval`，`no_diff_until_approved=True`，无 diff，无新文件 |
| attended，已批准 | 仍不写盘；`file_change.status=pending`；`applied` 仍 False；载荷不含签收工具名 |

官方 one-shot 继续只活在 dsh `@deepseek-ai/dsh-subagent-codex`。本适配器不 spawn `app-server --stdio`，以免第二套线、以免父上下文漏进子进程。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_l102.py
PYTHONPATH=src python3 tests/run_tests.py
```

`test_l102.py` 退出 0。`run_tests.py` 未改；调度回收时再挂本测。

本 diff：`rg` 第三句柄字面量与签收工具名零命中。

## 不做

- 不改 `run_tests.py`、`PROGRESS.md`、chat / dsh session / workplace、assignment、customer-shell、`agent.py`。
- 不 `import` 科学核。不把签收工具注册给官方 Codex。
- 不 commit。

## 剩

- 活 `app-server --stdio` 仍只在 dsh 插件里；Python 缝没有可打的本地 HTTP。
- E13 仍断言 `tests_green`。本包不改 eval 合同；调度 / Q 的 L1-02d 应改成认 `needs_app_server`，不要再把 oneshot 当已跑绿。
- 批准后的 fileChange 回灌 3080/dsh 在办，仍要等 H-01 / attended 插件填 `fill()`。
