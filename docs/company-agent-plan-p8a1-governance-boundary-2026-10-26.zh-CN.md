# P8 批次 A1 执行记录：治理边界一致性（H03 即时性 / 过期缝对齐）（2026-10-26）

依据：[约 2000 人天计划](company-agent-2000-person-days-development-plan-v1.0.zh-CN.md) P8「双租户、撤权、资产越域和权限缓存测试」与第十节 H 反例映射表（H03：撤权即时生效且有跨实例反例；H02：无确认路径默认拒绝）。P8 前置批次优先于插件面积增长。

## 1. 盘点结论

- **H02（无确认路径默认拒绝）已被三层既有钉覆盖**：CLI 三重门禁（`--approved` 仅在 `COMPANY_AGENT_APPROVAL_CONTEXT=dsh` 且完整 profile 下合法；未批准时环境里出现审批上下文是错误；非 invoke 命令禁止审批上下文）、DSH runtime 源码钉、release manifest 的 91 号环境检查——无需新增代码。
- **H03（撤权即时生效）在 tenants 注册表上缺进程内即时性钉**（knowledge 侧已在 P5-b2 钉住）。缺口还牵出一个**真实的内核不一致**。

## 2. 发现并修复的实际不一致 + 交付

`tenants.projection` 的有效期判定原来是 `expires_epoch > now`（**边界当秒即过期**），而 knowledge 注册表的判定是 `time > expires`（**边界当秒仍有效**）——同一 `expires_epoch` 词汇在两处治理面有相反的缝语义，运维按一个口径写的登记行会在另一个面提前/推迟一眨眼失效。这正是把 H03 的类比测试补到 tenants 上时暴露出来的。

统一对齐到 knowledge 语义（`now <= expires_epoch` 有效，下一秒过期），`tenants.py` 一行判定 + 注释；test 用例反向钉住新缝。

新增 `tests/test_governance_immediacy.py` **4 项**：

1. 撤/复即时性：注册表行改写（approved→revoked→恢复）在同进程下两次 `projection()` 之间生效（共享持久文件即跨实例媒介，契约本身就是跨实例反例）。
2. 过期缝：注册 `expires_epoch` 后冻结时钟，边界当秒仍 `approved`、下一拍点 `expired`（与 knowledge 的已有拍点钉完全一致）。
3. 文件消失降级：注册表文件被删除（配置态）必须 `unavailable` + 四服务 `registry_unavailable`，不得静默退回 legacy-with-facts（跨实例反例：媒介本身消失）。
4. 主体降级：可信主体 env 在进程内消失（`unknown@unknown`/untrusted）后，注册表行**永不**被该主体消费（H03 与 P1 主体绑定的合取）。

## 3. 验证（不含全量，按工作方式约束）

- `tests/test_governance_immediacy.py` 4 项 + 既有 `tests/test_tenants.py` 18 项 + `tests/test_knowledge_recall.py` 4 项 = **26 passed**；ruff 触碰文件干净。
- 门禁（23/23）不受影响（场景未增删、digest 未变——本批修改不改合同文件，只有代码语义对齐）。

## 4. 边界

- `expires_epoch` 的统一口径从本批次起是契约语义（知识注册表与租户注册表一致）， diligence：任何未来治理面（skills、objects）必须沿用同缝（记入本记录向 P8 验收映射表）。
- 企业 IdP 撤权推送延迟（registry 之外的真实撤权源）仍是 P1 Owner 范围。
