# D13 · dsh-annotation

验证级别：静态阅读。提交 `48eac63badf93641f2276b8b0068f6ebbe22ba9b`，提交时间 2026-11-03T10:22:16+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D006。仓库：[omdsh-dev/dsh-annotation](https://github.com/omdsh-dev/dsh-annotation)。目录级判定是思想可取。

## 许可证

MIT。`LICENSE:1`。

## 调用链

宿主入口只导出名字和空的 `apply`。编译产物 `lib/index.js` 同样是空函数。批注行为不在宿主工具链上。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `src/index.ts:5-7`
4. `lib/index.js:5`
5. `cordis.patch.yml:1`
6. `test/shared-listeners.test.mjs:1`

## 引用

位置 `src/index.ts:5-7`。

```
export const name = 'dsh-annotation'

export function apply(): void {}
```

## 测试

快照含 `test/shared-listeners.test.mjs`。本轮没有运行。

## 公司边界

选区批注留在客户端。空的宿主入口说明它没有新增模型工具。公司沿用这个分界。
