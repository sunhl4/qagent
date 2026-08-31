# C-03 · 可选云

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | S2 |
| 范围 | `workplace.apply_env` · `qiskit.ibm_run` 仍 fill/deny · `qagent/tests/test_c03.py` |
| 状态 | 代码落地，隔离测绿 |

## 产品锁

- 设置里的 `cloud_url` 是唯一云入口。工具名不动：`qiskit_aer_run` / `qdata_*` / `qiskit_ibm_run`。没有第四个句柄，没有 `qiskit_ibm_cloud_run`。
- `apply_env` 把公开的 `cloud_url` 镜像到进程 `QAGENT_CLOUD_URL`。空则 unset。这不是密钥，GET workplace 可以看见 URL。
- **不**把云 URL 写进 `dsh.env`。超算 / 量子口令仍不进 env。
- `decide("qiskit_ibm_run", lab|algo|sign, {})` 有无 URL 都是 `deny`。`invoke` 是 `status=denied`，payload 无 `twin_id`，provenance 不是 `qccd-twin`。
- 云关（空 URL）：不声称云 / IBM 作业 `status=done`。死地址 `http://127.0.0.1:1` 若真去 HTTP GET：诚实报错，不假 done，不发 `twin_id`。
- 脑仍是 `dsh --profile qagent`。不加第三套 loop。只有 ionstack TwinRun 能发 `twin_id`。

## 写到哪里

- `Workplace.cloud_url` + 设置 `#cloud_url` 已在；本包只补 `apply_env` 镜像 / unset，以及 `cloud_url()` / `probe_cloud()`。
- `WiredQiskit.ibm_run` 仍 `fill("S-QISKIT-05", …)`。`cloud_url` 开了也不接线、不铸 id。
- 设置栏多一行提示：未填不上 IBM / 云作业；填了也不改工具名。

## 不做什么

不改 `run_tests.py` / `PROGRESS.md` / `chat.py` / `dsh_session.py` / `agent.py` / assignment / `eln.py` / `policy.json` / `Q-c05.json` / `E*.json`。不加 E23、不加 Q-c06。不 commit。

## 测

`qagent/tests/test_c03.py`：空工作台 unset；保存后 env / status 见 URL、不见密钥、`dsh.env` 无 URL；IBM 云开关都 deny；死 URL 诚实；`run_product_evals("Q-c05")` 仍绿；五包无 cirq。

```text
cd qagent
PYTHONPATH=src python3 tests/test_c03.py
```
