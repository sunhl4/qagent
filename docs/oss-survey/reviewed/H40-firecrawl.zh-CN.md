# H40 Firecrawl：网页提取可复用，注入检测不是授权边界

对象 `mendableai/firecrawl`；SHA `16d4aa9c167089d9031a311f50a27b0b41a74de5`，提交2026-10-21T20:05:11-07:00；来源 `/tmp/oss-mendableai-firecrawl`。根许可AGPL，选用组件及服务条款需分别评估。本轮仅静态复核抓取后的注入检测链，未启动抓取服务。

## 实际链

scrape文档 → `performPromptInjectionGuard`检查开关与长度 → `checkForPromptInjection`分块 → 分类模型 → 抛出检测异常或返回扫描完整性 → 文档/警告。默认关闭该选项时直接返回文档；内容超过transformer上限也不执行检测，返回带警告的文档。这与公司的未知状态失败闭合策略不同。

分类器使用32000字符块、2000字符重叠，并发5；随机标签划分不可信网页和系统指令，避免固定闭合标签被直接模拟。分类schema约束`isInjection`与原因，但模型判别仍有误报漏报。已发现注入及成本超限异常重抛；一般分类错误被捕获，记录`none`并继续，源码明确称为fail-open。

```168:173:apps/api/src/scraper/scrapeURL/lib/promptInjectionGuard.ts
    // Deliberately fail-open so a guard outage doesn't take down the whole scrape.
    logger.warn(
      "Prompt injection guard call failed; proceeding without a guard verdict (fail-open)",
      { error },
    );
    return false;
```

固定`gpt-4o-mini`并经`getModel(...,"openai")`选择模型；这是本次源码路径的默认调用，不可误写成已兼容公司本地模型或完全离线。零保留选项控制遥测，不能独自证明模型提供商不会收到网页正文。

## 测试证据

`apps/api/src/scraper/scrapeURL/transformers/promptInjectionGuard.test.ts:31-90`覆盖未启用、检测异常、上下文标识、扫描不完整警告及超长内容。此处用mock验证分支，不是对抗攻击有效率证明，本轮未执行。

## 公司落点

网页采集适合隔离为知识入库服务：域名/网络出口限制、文件大小预算、来源记录、正文与摘要分离。对外网页始终是数据，不能成为Skills、系统指令或权限来源。检测不完整应明确标为未验证，禁止据其自动提交云/HPC/QPU任务。

有价值的是分块重叠、共享并发限制、检测状态与计费关联；不能照搬其fail-open为公司的高风险执行策略。接入本地分类模型须单独评测、部署及合同设计，现有DeepSeek继续作为DSH宿主模型。AGPL源码的部署、修改和分发义务由实际选型触发，不能仅以“内网”推断无义务。

证据范围：transformer `promptInjectionGuard.ts:6-39`；lib同名文件`:14-30,101-134,151-176,188-246`；上述测试；根LICENSE。该复核不覆盖完整爬虫、反爬与网络安全实现。
