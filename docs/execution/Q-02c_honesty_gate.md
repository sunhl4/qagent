# Q-02c · 诚实门槛

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | Q |
| 范围 | `qagent/src/qagent/services/quality.py` · `qagent/tests/test_q02c.py` |
| 层 | Layer 1 造包缝。不是客户 Agent，不是第三套 loop |

## 做了什么

`quality.py` 三个门槛助手走现有 `decide()` / `invoke()`，不新开 loop，不铸 `twin_id`，不把坏动作写成 `status=done`：

| 助手 | 坏动作 | 关上门 |
|------|--------|--------|
| `deny_forged_twin` | `qiskit_aer_run` + `claim_twin_id` | `decide=deny`，invoke `denied`，payload 无 `twin_id` |
| `deny_skip_ask` | lab 上 `ionstack_twin_run` 且未 `approved` | `decide=ask`，`status=needs_ask`，无 `twin_id` |
| `deny_cal` | `cal_edit` / `shuttle_write` | 都是 `deny` / `denied`。CAL 永不进工具 |

结构化结果是 `HonestyReport`。坏动作不是 `allow` / `ok` / `done`。不要求活 Twin：未批准的 TwinRun 到不了端口。

Q-02b 已冻 `.github/workflows/qagent-eval.yml` 两句命令。本包不改 yml。CI 已跑 `run_tests.py`；调度回收时再挂 `test_q02c.py`。

## 测

```text
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_q02c.py
```

三助手 fail-closed；无 `twin_id`；本注记存在。不拉活 Twin。

## 不做

- 不改 `qagent-eval.yml` / `test_q02b.py` / `run_tests.py` / `PROGRESS.md` / `Q-*.json` / `E*.json` / `policy.json` / `chat.py`。
- 不 `import` 科学核。不发明第四个句柄。不 commit。
