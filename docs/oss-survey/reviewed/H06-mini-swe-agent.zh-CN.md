# H06 mini-swe-agent：预算、错误收费和轨迹保存

项目 `SWE-agent/mini-swe-agent`；SHA `04d809ceab9df28f9adaed044884180159172930`，提交2026-09-03T01:05:59-04:00；来源 `/tmp/oss-SWE-agent-mini-swe-agent`。静态复核，未执行本地shell测试；根LICENSE.md为MIT。

## 核心链路

run创建system/user消息，循环step；step=query后execute_actions；query检查预算、调用模型并累计成本；execute_actions将每个action交给environment；finally保存轨迹。公司只读这个控制流，不引入第二循环。

## 机制与限制

1. step_limit、cost_limit和wall_time_limit在下一次query前检查。cost_limit文档明确exceeding，上一调用可能已超支，不是精确预扣额度。
2. FormatError虽使query没完成，但模型调用已计费，异常分支仍累计error.messages里的cost；连续格式错误到阈值写exit消息。公司模型回归同样不能把坏输出费用当零。
3. finally保存所有出口，但save仅在output_path存在时写文件，且是直接write_text；不能据此宣称原子持久/防篡改审计。

```120:124:src/minisweagent/agents/default.py
            finally:
                self.save(self.config.output_path)
            if self.messages[-1].get("role") == "exit":
                break
        return self.messages[-1].get("extra", {})
```

## 测试

`tests/agents/test_default.py:154-182` 验证一步上限与成本上限触发LimitsExceeded。
`:185-229` 验证命令超时、部分输出及后续恢复；这些是本地执行测试，不证明外部设备可重试。

## 公司落点

- `contracts/results.json`已有设备零重试和unknown，不能套用本地命令恢复路径。
- 模型预算需明确预估/实际/超额与是否预扣，和HPC/QPU计费分离。
- `diagnostics.py`可借每次出口都留状态的纪律，但持久化策略单独设计。
- `tests/`加入格式错误仍消耗预算、保存失败不伪造执行状态的反例。

证据：default.py:19-35,88-124,130-157,159-190；test_default.py:154-229；LICENSE.md。未验证全部环境适配或真实成本精度。
