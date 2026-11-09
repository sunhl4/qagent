---
name: company-office-desk
description: 用公司办公工具处理 docx、xlsx、pptx，并把写好的文件交给用户。
---

# 办公桌面

工作区里的办公文件走公司办公工具。阅读用 `company_office_analyze`，新建用 `company_office_create`，改稿用 `company_office_edit`，表格计算用 `company_office_compute`，幻灯片用 `company_office_pptx`，交付前用 `company_office_validate`。时间线、大事记和思维导图仍只用 `company_office_matter` 的固定文件，不另建同类文件。

材料不足先问，不编造。多步任务用 `todo_write` 保持一条 `in_progress`。写完的 docx、xlsx 或 pptx 用 `present` 交给用户，每次最多 4 个已经存在的文件。工具结果保持短，不把全文、密钥或完整电路贴进回复。
