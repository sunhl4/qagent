# Qiskit 官方 MCP servers 调研更新入口

请阅读 [24 — Qiskit/mcp-servers 源码复核](reviewed/README.zh-CN.md#project-24)，另有 [25 — 非官方 Qiskit MCP](reviewed/README.zh-CN.md#project-25) 的独立分析，不再混算。

量子作业提交/轮询可以借鉴接口形态，但公司算法只能从平台 catalog 发现，Agent 不直接 import 科学算法包；Qiskit job ID 不扩充公司三句柄，设备审批保持原合同。见 [本地架构对照](03-本地架构对照与工程边界.zh-CN.md)。
