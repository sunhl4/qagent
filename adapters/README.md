# 集成适配层（本工程侧）

## 目录

```text
adapters/
  stub/            本地桩，独立开发用
  README.md        本文件
```

## 原则

本工程**不实现**云平台、本地 HPC、本地模型的真实适配器。这些由 harness-core 提供。

本工程只做三件事：

1. 定义端口（在 `contracts/`）。
2. 在开发与测试中使用桩（在 `adapters/stub/`）。
3. 在运行时装配 harness-core 提供的真实实现。

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
