---
name: company-literature-review
description: 逐篇检索、取回并索引文献，把公式、附件和代码记成短回执，再用公司 LaTeX 写综述。
---

# 文献综述

一次调用只做一件事：`company_literature_search` 做一次有界检索，或 `company_literature_fetch` 取回一篇论文，或 `company_literature_index` 为这篇论文写下公式账、附件账和代码账。不要把多篇论文合成一次调用。

## 检索

来源是 arXiv、OpenAlex、Semantic Scholar、Crossref，Europe PMC 可以打开。每个来源只取第一页。引用只做 OpenAlex 一跳。`exhaustive` 保持 false。检索返回、去重、纳入、全文和引用的计数分开写。没有全文时不编造数字。

## 全文

顺序是 arXiv 源码，PMC JATS，HTML，PDF 文本层，最后才是单张图的视觉读数。版本钉在 arXiv 的 vN 或 DOI。证据写成 source kind、version 和 anchor。复现候选里的公式证据必须带公式账编号。

工具回执只有计数和编号。TeX、图和补充材料留在工作区。引用不超过 500 字。近似号保持原样，宏展不开就标未展开。图只登记源文件，不裁切。

## 报告

报告用已有的 `company.latex` 工具编译。20 页不是门禁。覆盖数字按检索、去重、纳入、全文和引用分开。科学章留给另一个会话或人审阅，作者会话不给自己盖章。

背景论文可以停在宽松方法卡。准备复现的候选必须通过严格编译：公式或表格锚点、单位、是否能进入平台短指标、容差、数据划分，以及钉住的 commit 或明确的缺失说明。化学误差和其他五种平台单位以外的指标留在账本里，不送进研究时钟。实验卡的 `primary_metric` 仍是 `val_loss`。

## 代码与超算

写代码的工单只接收已经通过严格编译的复现候选、7 到 64 位十六进制 commit，以及实验卡上的 `changed_path`。路径最长 120，拒绝 `..`、绝对路径和反斜杠。作者不能评审自己，大小写不同也算自审。合并仍走现有软件门禁。文献工具不新建 `component_id`。

超算是复现通过之后的另一张实验卡。只从已经复现的 cpu 或 gpu `val_loss` 另开标识和幂等键，`resource_type` 为 `hpc`，不勾 `baseline_reproduced`，不写集群小时。编译前去掉幂等键。仍由现有交接调用 `hpc_submit`，提交单独批准。文献工具不调用 `company_research_run`、`hpc_submit` 或 `quantum_device_run`。
