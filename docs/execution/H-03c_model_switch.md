# H-03c / H-03d · 换默认模型，下一句生效

| 字段 | 内容 |
|------|------|
| 日期 | 2026-08-26 |
| 角色 | A1 |
| 状态 | 代码落地，测绿 |

设置里换默认模型后，**下一轮 dsh turn** 读到新的 `DEEPSEEK_MODEL`。不重启 qdata / qchem / ionstack。

## 写到哪里

- `write_dsh_env` 继续写 `DEEPSEEK_BASE_URL` / `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL`。
- `apply_env` 同步写入当前进程：`os.environ["DEEPSEEK_MODEL"]` 来自 workplace 的模型（池名会先解析成真正的 model）。chat 每轮开头调用 `apply_env()`，所以下一句人话看见新模型。
- 模型池 textarea 行格式：`name | base_url | model`。`parse_llm_pool` 在 models 层，无 I/O。payload 的 `llm_model` 命中池 **name**（或池里已列出的 model）时，把该行的 `base_url`+`model` 写进 workplace 与 `dsh.env`。否则用显式 `llm_base_url` + `llm_model`。空模型名不从池里挑一条冒充默认。

## 诚实

- `ready()` 仍要地址和模型都在。缺任一则为 False，不发明模型。
- `to_public` / `workplace_status` JSON **没有** `llm_api_key` / `hpc_secret` / `quantum_secret` 的值，只有 `has_*`。
- Workplace 对象不持有密钥。

## 测

`qagent/tests/test_h03.py`：存池+模型则 `dsh.env` 有 `DEEPSEEK_MODEL`；`apply_env` 写入进程环境；再存另一个模型则 `dsh.env` 更新；status JSON 不含密钥字符串；空地址 `ready` False。
