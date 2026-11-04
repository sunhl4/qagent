# 端口一致性测试

## 目的

本目录定义 `@company/dsh-contracts` 的语义验收条件。双方（harness-core 与 research-platform）都必须能通过，才能在联调环境互相替换。

## 文件

- `cases.yaml`：用例集，机器可读。
- `cases.schema.json`：用例集的结构约束（可选）。
- 本 README：运行约定。

## 用例字段

| 字段 | 说明 |
|---|---|
| `id` | 稳定 ID，双方引用同一编号 |
| `port` | 端口名，`*` 表示通用 |
| `level` | `MUST` 必须通过；`SHOULD` 可声明为限制 |
| `title` | 一句话说明 |
| `given` | 前置条件 |
| `when` | 调用动作 |
| `then` | 断言列表 |

## 运行约定

1. 实现方自行选择测试框架（pytest / vitest / Go test）。
2. 每个 `MUST` 用例必须有对应测试。
3. 结果写入 integration manifest 的 `knownLimitations`。
4. 联调前双方交换结果。
5. 契约升级后重跑。

## 建议的测试组织

```text
conformance/
  cases.yaml
  harness-core/
    results.json
  research-platform/
    results.json
```

`results.json` 结构：

```json
{
  "implementation": "harness-core",
  "contractVersion": "0.1.0",
  "runAt": "2026-10-29T00:00:00Z",
  "passed": ["GEN-001", "MOD-001"],
  "failed": [],
  "skipped": [
    {"id": "CMP-006", "reason": "HPC queueInfo 尚未实现"}
  ]
}
```

## 允许的跳过

`SHOULD` 用例可以跳过，但必须：

- 在 `results.json` 的 `skipped` 中给出原因。
- 在 integration manifest 的 `knownLimitations` 中声明。
- 调用方在 `describe()` 中看到对应 feature 缺失并走降级。

`MUST` 用例不得跳过。

## 反模式

- 为了让用例通过而伪造结果。
- 把未知执行报告为 failed。
- 把超范围权限写入凭据。
- 在错误信息中泄露密钥。
- 只在 happy path 下测试。
