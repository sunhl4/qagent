# G-01 · DSH 治理包（一次性落地）

对照 2026-08-29 生态调研与 qagent 宪法。不换框架、不自研 loop、不改工具名、不发明第四句柄。

## 做成什么样

| 层 | 落地 | 明确不做 |
|----|------|----------|
| `boot` preset | 只挂轨：list_engines / pin / docs / identity。TwinRun 在可见集里不存在 | 第四个 preset 当第四句柄 |
| `profiles/qagent-minimal` | 只组合 policy + engines + docs + brand | 往 minimal 塞 twin / qdata / Codex |
| 后验证人 | `invoke()` 成功后扫 payload：假 twin、无证据 `quantum_wins`、泄漏键 → error | 第三套 loop |
| doctor | CLI + `GET /api/doctor`。默认只扫本次 payload；显式开店才扫 ELN/交办 | 读 secrets |
| 交接 | `qagent.handoff/v1`：三句柄 + 短 intent + unresolved。原会话不动 | 拷贝 session 全文 |
| 回放 | ELN + 交办 + usage 投影 | 替换 agent loop |
| SAFE MODE | 切到 `boot` + 旗标。策略层 Twin 已不可见 | 靠 CSS 藏工具 |
| ask 触达 | `.qagent/asks.jsonl`；可选 `QAGENT_ASK_WEBHOOK`（失败仍落盘） | 做微信/APK |
| 五池评测 | E28–E32：政策 / 出处 / B3 / 句柄 / 短输出。E23 留给 L1-03-pl | 改 E01–E21 合同 |
| GenUI | 3080 侧栏「句柄与证据」，读 `/api/gov/face` | 新 React 应用、JS 里写 `ionstack_twin_run` |
| 用量 | `.qagent/usage.jsonl`：tool/preset/status，无 payload | 把密钥写入用量 |
| 知识 | handbook + `QAGENT_KNOWLEDGE_PATH` 关键词重叠；不改 `qccd_docs_search` schema | 接入 MemOS |
| 橙皮书 | `handbooks/orange-book.md` + AGENTS Read First | 把系统提示词写进 persona |
| 打包 | `qagent/Dockerfile` 只跑 3080 shell | 把 ionstack 打进镜像 |

## 硬轨

句柄只有三个。只有 ionstack TwinRun 能发 `twin_id`。造包 profile 的产物里没有 Twin 插件。官方 Codex 仍 `permissionMode: never`。CAL / shuttle 永不进工具。失败闭合：没有规则 = deny。

## 评测

E22 保持 `empty`。E23 不加（Pennylane 锁）。E28–E32 `implemented`。默认 `qagent-eval` 跑 E01–E21 与 E28–E32。

## 已落地（2026-08-29）

| 项 | 位置 |
|----|------|
| 合同 | `contracts/gov.json`、`contracts/handoff/v1.json`、`contracts/presets.json` 的 `boot`、`S-GOV-01`…`S-GOV-10` |
| 层 | `models/gov.py` → `adapters/gov_store.py` → `services/{witness,doctor,handoff,replay,savepoint,usage,notify,knowledge,gov_face}` → `entrypoints/{doctor_cli,gov_cli}` |
| 后验证人 | `invoke()` 成功后再扫；诚实 `ionstack_twin_run` 放行 |
| HTTP | `GET /api/doctor` `/api/gov/face` `/api/asks` `/api/usage` `/api/replay` `/api/handoff`；`POST /api/handoff` `/api/savepoint` `/api/safe-mode`（写要 token） |
| 3080 | 侧栏「句柄与证据」只画布尔/短词，JS 无 `ionstack_twin_run`、无 `twin_id=` |
| 评测 | `qagent-eval` 默认 E01–E21 + E28–E32 全绿 |
| 离线锁 | `gov` / `chat` / `h01d` / `i02` / `c02f` / `l103_pl` 绿 |

活 Twin `:8765` 与 qdata HTTP `:8787` 仍要本机进程。没有它们时 `i03n` / `a03g` 等活门会红；不要用假 `twin_id` 把它们涂绿。
