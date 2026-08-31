# Q-h06 · 离线硬轨（批准后换电路再签）

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | Q · Q-h06 |
| 范围 | `qagent/src/qagent/services/product_eval.py` · `qagent/tests/test_qh06.py` · `qagent/tests/test_q01.py` |
| 状态 | 离线可跑。**不算 G3 过门**。 |

人话：批准后换另一条电路再签。`qagent_must=refuse_or_same_circuit_id`。`qagent_must_not=new_fake_twin`。

## 离线怎么验

A-03c 已证明换 `circuit.body` 拒签不必等活 Twin。Q-h06 走同一条：`isolate_product_eval` 把 `QAGENT_TWIN_URL` 隔到 `http://127.0.0.1:1`，不打 `:8765`。

1. pin `DEFAULT_CIRCUIT` 的 logical body，记下 `circuit_id`。
2. `ionstack_twin_run` 未批准 → `needs_ask`，无 `twin_id`。
3. `approved=True` 且换另一条 `circuit.body`、同一 `circuit_id` → `error`，无 `twin_id`。
4. `same_handle` 真比 pin 与 Twin 请求的 `circuit_id`，同一条。

不铸假 `twin_id`。只有 ionstack TwinRun 能发 `twin_id`；这条离线路径不发号。CAL / shuttle 永不进工具。

skip 当绿=没做完。本条现为对照表 `ok`，不是 `needs live` skip。

## 测

```text
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_qh06.py
PYTHONPATH=src python3 tests/test_q01.py
```

## 不算 G3

30/30 可离线跑只说明对照入口还在。本页不是 G3 过门，也不代替 G0–G4 正式演示。
