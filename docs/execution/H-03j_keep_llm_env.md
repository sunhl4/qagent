# H-03j · 空 llm save 不冲掉 dsh.env 的 DEEPSEEK_*

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-27 |
| 角色 | A1 · H-03j |
| 范围 | `qagent/src/qagent/adapters/workplace_store.py` · 本笔记 · `qagent/tests/test_h03j.py` |
| 未改 | `start_ui.sh` · `start_runtime.sh` · `dsh.env` 活文件（本包测用临时文件） · `workplace.json` 活文件 · `secrets.json` · `chat.py` · `agent.py` · `run_tests.py` · `PROGRESS.md` · ionstack 核 |
| 状态 | `write_dsh_env` 在传入的 base/model/key 为空时，保留盘上已有 `DEEPSEEK_*`。有值仍覆盖。HOME 空行仍不写。`QAGENT_CLOUD_URL` / hpc / quantum secret 仍不进 `dsh.env`。**不写密钥到活 workplace**。**不重启 dsh**。**不算 G0**。未 commit。 |

## 产品锁

- 活 `workplace.json` 只有三条 HOME，llm 字段空。若对这份盘 `save()` / PUT 设置，旧实现会整文件重写 `dsh.env`，把已有 `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` 冲掉。
- 完成线：空 llm 的 save 仍能写出 HOME，且留下原来的 `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`。原来没有 API key 就不要新写一把。
- 非空 llm 仍覆盖（换模型下一句生效）。
- 云 URL 与超算/量子密钥永不进 `dsh.env`。旧文件里误写的 `QAGENT_CLOUD_URL` 也丢掉。
- **不算 G0**。没在 3080 填模型，没走「扫氢分子」。不重启 3081。
- skip 当绿 = 没做完。未 commit。

## 改了什么

`write_dsh_env` 先读现有 `dsh.env`。`DEEPSEEK_BASE_URL` / `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL`：传入非空用新值，传入空留旧值。HOME 仍只写传入的非空值（空 HOME 仍删行，H-03f 的 clear 合同不动）。

不读 `secrets.json` 来补 key。不把 CAL / shuttle 写进环境。

## 不算什么

- **不算 G0**。ready 仍看人填的模型。
- 不算活 dsh 进程已经看见 HOME。3081 仍是启动时的环境；本包不 `pkill dsh`。
- 未改 `start_ui.sh` / `start_runtime.sh`。未改活 `workplace.json`。未 commit。

## 测

```bash
cd /Users/shl/nvidia/qagent
PYTHONPATH=src python3 tests/test_h03j.py
PYTHONPATH=src python3 tests/run_tests.py
```

空 llm save 冲掉 `DEEPSEEK_*` 必须失败。skip 当绿 = 没做完。不 commit。
