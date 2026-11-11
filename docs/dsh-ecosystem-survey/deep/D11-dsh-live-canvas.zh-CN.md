# D11 · dsh-live-canvas

验证级别：静态阅读。提交 `a9f02273715ea11c35eaea353b34a33929e6ffa9`，提交时间 2026-11-09T12:01:57+03:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D026。仓库：[GooDAnDReaDY/dsh-live-canvas](https://github.com/GooDAnDReaDY/dsh-live-canvas)。目录级判定是暂缓。

## 许可证

MIT。`LICENSE:1`。

## 调用链

`apply` 解析工作区根，并从 `./sandbox.js` 引入沙箱头、路径消毒和拒绝状态。工具登记函数按工作区根限制路径。预览走插件自己的 `/dsh-live-canvas/sandbox/` 路由。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `lib/index.js:23`
4. `lib/index.js:184-186`
5. `lib/tools.js:16-28`
6. `lib/index.js:632`

## 引用

位置 `lib/index.js:23`。

```
import { getSandboxHeaders, injectSandboxRuntime, sanitizePath, resolveSafePath, isTrustedRequest, isTrustedWriteRequest, getRejectionStatus, getWriteRejectionStatus } from './sandbox.js';
```

## 测试

扫描没有找到测试文件。

## 公司边界

对话旁的预览可以参考。插件自带的沙箱站点和热更新不作为公司第二执行面。
