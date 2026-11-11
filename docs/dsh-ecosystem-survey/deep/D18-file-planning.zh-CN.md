# D18 · file-planning

验证级别：静态阅读。提交 `50cf9109eac515b79c5e5661ffcb7f146f017ed4`，提交时间 2026-08-17T09:31:12+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D097。仓库：[JohnXu22786/file-planning](https://github.com/JohnXu22786/file-planning)。目录级判定是只借机制。

## 许可证

MIT。`LICENSE:1`。

## 调用链

计划别名拒绝路径分隔符和 `..`。依赖图把已完成和已取消的步骤移出环检测，取消被写成破环的合法出口。`findCycle` 用三色深度搜索返回第一条环。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `lib/store.js:22-28`
4. `lib/machine.js:72-77`
5. `lib/machine.js:82-84`
6. `test/store.test.js:1`

## 引用

位置 `lib/store.js:22-28`。

```
/** 计划目录：name 为空 → 根计划；否则 plans/<name>。name 必须是纯目录名，拒绝路径穿越。 */
export function resolvePlanDir(workspace, name = null) {
  if (name === undefined || name === null || name === '') return trailRoot(workspace)
  if (!/^[^/\\]+$/.test(String(name)) || String(name).includes('..')) {
    throw new TrailError(E.INVALID_ARG, `非法的计划别名：${name}（只能是不含路径分隔符与 .. 的目录名）`)
  }
  return path.join(scopedRoot(workspace), String(name))
```

## 测试

快照含 `test/store.test.js`。本轮没有运行。

## 公司边界

里程碑和步骤状态可以记在工单旁边。权威进度仍是上游工单。磁盘上的计划文件不成为第二套状态机。
