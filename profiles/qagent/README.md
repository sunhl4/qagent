# profile `qagent`

Pin：`@deepseek-ai/dsh@0.1.0-rc.8`、`@openai/codex@0.147.0`、`@deepseek-ai/dsh-subagent-codex@0.1.0-rc.8`。

```bash
bash scripts/bootstrap_wp0.sh
bash scripts/start_ui.sh
```

人入口是对话：`bash scripts/start_ui.sh`。dsh 只做 runtime：

```bash
bash scripts/start_runtime.sh
```

preset：`boot|lab|algo|sign`。`boot` 是最小对齐（无 Twin）。启动可用 `QAGENT_PRESET`；也可用 `qagent_list_engines` 的 `preset` 参数写入 `.qagent/active_preset`。第一阶段 profile 见 `profiles/qagent-minimal`。官方 Codex 子代理已挂上，政策在 lab 上 deny。不要启用 `dsh-tool-cordis`、web fetch、`dangerously-bypass`。

Skills：`skill-visibility.json` 决定 lab / sign / algo 可见集。`start_runtime.sh` 做 skills sync 到 `$DSH_HOME/skills`，不碰 credentials。lab / sign 可见量子轨（含 twin-run）；algo 只见造包（write-provider / qchem-scenario），不可见 Twin。不要把 TwinRun 注册成 Codex MCP。
