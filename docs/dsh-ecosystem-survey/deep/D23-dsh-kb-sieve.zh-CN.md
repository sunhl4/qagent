# D23 · dsh-kb-sieve

验证级别：静态阅读。提交 `01aba653f576658974b70514573c1f6b7b4ce4df`，提交时间 2026-08-12T14:54:17+08:00。没有运行上游测试，没有装入公司桌面。

目录卡片：D135。仓库：[omdsh-dev/dsh-kb-sieve](https://github.com/omdsh-dev/dsh-kb-sieve)。目录级判定是暂缓。

## 许可证

Apache-2.0。`LICENSE:2` 起是 Apache 许可正文。

## 调用链

`apply` 登记 `kb_build`。描述写明产物是原文副本、SQLite FTS5 和 SKILL.md，默认放到 `.dsh/skills/<name>/`，监听中的技能根会被 DSH 下一轮发现。构建声明为确定性，无向量、无 LLM。

## 证据锚

1. `LICENSE:2-4`
2. `src/index.ts:72-73`
3. `src/index.ts:78-86`
4. `cordis.patch.yml:1`
5. `package.json:1`
6. `src/constants.ts:1`

## 引用

位置 `src/index.ts:78-86`。

```
  ctx.tools.register(defineTool({
    name: 'kb_build',
    description:
      '构建知识库：把一组文档（.md/.txt/.docx/.pdf）做成可审计知识包——references/<doc_id>/doc.md 原文'
      + '+ kb.sqlite（SQLite FTS5 整文档索引，无向量无外部依赖）+ manifest.json + SKILL.md。'
      + '默认输出到当前项目根目录的 .dsh/skills/<name>/（最近的 .git 目录或当前工作目录之下）——'
      + '监听中的 skill 根目录会被 DSH 动态发现，模型下一轮即可通过 skill 目录加载该知识库。'
      + '触发场景：用户要求把若干文档整理成可检索的知识库/规范库/手册、或要求"记住这些文档"。'
      + '构建是确定性的：同样的输入产出同样的产物（chunking 参数固定，无 LLM 参与）。',
```

## 测试

扫描没有找到测试文件。确定性声明没有在这个快照里被测试钉住。

## 公司边界

本地全文索引和行级引用可以参考。自动把原文技能挂进模型可见技能根，等于把全文送进后续回合。公司检索后仍只回短摘录，不自动发布技能。
