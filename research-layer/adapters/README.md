# 集成适配层（本工程侧）

## 目录

```text
adapters/
  stub/              本地桩，默认装配
  company-agent/     ComputePort 翻译层，默认不替换桩
  README.md          本文件
```

## 原则

本工程**不实现**第二套云平台、HPC 或模型网关。根目录已有公司 provider。`adapters/company-agent/` 实现研究层 `ComputePort`：保留资源种类，未知执行只可查询、不可重新提交，`qpu` 只生成设备审批交接。它保持 `degraded: true`，默认不替换 `adapters/stub/`。

本工程做这三件事：

1. 定义端口（在 `contracts/`）。
2. 在开发与测试中默认使用桩（在 `adapters/stub/`）。
3. 用一致性测试约束公司翻译层。翻译层不发起真实云、HPC 或模型调用。

## 装配点

建议在单一位置装配，避免散落：

```ts
// platform/src/integration/compose.ts
import type {
  ArtifactStorePort,
  ComputePort,
  ModelGatewayPort,
} from "@company/dsh-contracts";
import { createStubBundle } from "../../../adapters/stub/src/index.js";

export interface IntegrationBundle {
  model: ModelGatewayPort;
  compute: ComputePort;
  artifacts: ArtifactStorePort;
}

export function composeIntegration(env: "local" | "staging" | "production"): IntegrationBundle {
  if (env === "local") {
    return createStubBundle();
  }
  // staging / production：由 harness-core 提供的适配器
  throw new Error("wire harness-core adapters here");
}
```

## 反腐蚀层

真实实现返回的 DTO 不直接进入领域对象。必须先映射：

```text
Provider DTO → contracts DTO → ACL 映射 → 领域对象
```

映射层要求：

- 集中在一处。
- 有单元测试。
- 契约升级只改这里。
- 不把供应商状态透传。

## 切换检查

- [ ] 端口版本一致
- [ ] 能力声明已读取
- [ ] 降级路径已验证
- [ ] 错误码已映射
- [ ] 租户与数据分类已校验
- [ ] 用量与成本口径一致
- [ ] 凭据不落盘
- [ ] 一致性测试通过
