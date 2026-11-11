# D27 · gongwen-skill

验证级别：静态阅读。提交 `6a41282aa5ae3ed3bbc55ad9adc33bcff80c7353`，提交时间 2026-10-02T01:30:44+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D188。仓库：[linhut/gongwen-skill](https://github.com/linhut/gongwen-skill)。目录级判定是只借机制。

## 许可证

MIT。`LICENSE:1`。

## 调用链

宿主注释把 Python CLI 定为工具层，DSH 插件负责登记模型工具、设置项，并调用 CLI。`inject` 为 tools。`apply` 先探测公文根目录，找不到只记警告，再调用 `registerGongwenTool`。

## 证据锚

1. `LICENSE:1`
2. `LICENSE:3`
3. `dsh/index.js:6-14`
4. `dsh/index.js:493`
5. `dsh/index.js:495-511`
6. `presets/preset.yml:1`

## 引用

位置 `dsh/index.js:493-511`。

```
export const inject = ["tools"];

// apply() — Cordis 生命周期管理（所有注册均为可逆副作用）
export function apply(ctx) {
  const disposers = [];

  // 软探测 gongwen 根目录：找不到仅记录，不阻塞插件自身注册
  // （工具/设置/skill 注册不依赖项目根；call/runCli 才需要）
  let projectRoot = null;
  try {
    projectRoot = _resolve_gongwen_root();
  } catch {
    ctx.logger?.warn?.("gongwen-skill: gongwen 包未定位，CLI 调用将在执行时失败");
  }

  try {
    // 1. 注册官方模型工具（inject 硬依赖，fiber dispose 自动注销）
    try {
      registerGongwenTool(ctx);
```

## 测试

扫描没有找到测试文件。

## 公司边界

公文版式和规则表可以对照现有办公工具与 WPS。插件不成为第二套文书运行时。规则覆盖 JSON 不进入模型可见的长正文。
