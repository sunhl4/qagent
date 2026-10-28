# 受管发布与人工验收证据

日期：2026-10-09。适用合同 2.0。工程工具完成不等于生产授权。

## 发布完整性

`scripts/release_manifest.py create` 要求 `--root`、`--runtime-root`、`--output` 都指向显式路径，输出必须尚不存在。`--immutable` 对生产材料要求文件和目录均无写权限。清单覆盖合同、Python 源码、插件、profile、Skill、内置知识、启动脚本和锁文件；记录文件真实路径、模式、尺寸、SHA-256、Node/DSH 精确版本、固定 OS Python 解释器身份，并摘要整个 Runtime 和各 profile 的已安装 node_modules（包括符号链接目标）。生产缺任一 profile 依赖树即拒绝。禁止越界链接和组/其他用户可写文件。

`scripts/release_manifest.py verify --manifest ... --root ... --runtime-root ... --require-immutable --attestation ... --trust-config ...` 重新核对全部材料。提供签认时，先检查外部 HMAC 签认，再校验源码及依赖内容，最后才运行版本探测；验签与内容校验使用同一份已解析清单，不在两步之间重读清单。无效签认、缺少配对信任文件或内容被篡改时，待验 Node 不会执行。`create` 和未提供签认的开发校验仍会执行版本探测，只能用于操作员已信任的本地材料。认证文件使用外部操作员保管的 HMAC-SHA256 密钥与 key_id，签名绑定整个 manifest 及两个根路径；签认和信任配置的真实路径必须在发布根和 Runtime 根之外，内置同名文件不能作为信任来源。测试只使用合成密钥。脚本只验证签名，不生成生产签认或替操作员批准发布。任何 additions/deletions/content/mode/realpath/version 变化均需重建清单并重新签认。

`start_runtime.sh` 默认为 development，明确提示当前可写工作区不是生产部署。production 必须显式设置 `COMPANY_AGENT_RELEASE_MANIFEST`、`COMPANY_AGENT_RELEASE_ATTESTATION`、`COMPANY_AGENT_RELEASE_TRUST_CONFIG`；先以隔离的 `/usr/bin/python3 -I` 验证清单，再允许启动。生产固定 Python 解释器、清除预加载环境和配置知识根，且 DSH profile 必须解析至已验签的发布目录。当前开发工作区不满足只读发布要求，本轮没有改变真实运行时或创建生产签认。

可信操作系统、Python 标准库、operator-private 外部信任文件及不能被运行服务用户替换的只读挂载是部署前提。权限位检查不是对同一属主/管理员的防篡改隔离，也不消除验证后被高权限主体修改的竞态。应由管理员持有发布根，服务使用不同非特权 UID，发布材料和依赖使用只读挂载，DSH 可写状态保持独立。全树哈希有启动成本，当前没有生产规模启动时间数据。

清单和关联 JSON 最多 4 MiB、32 层、100,000 个结构节点；人工证据和关联 JSON 最多 1 MiB、24 层、20,000 个节点。读取前确认普通文件，拒绝叶级符号链接及管道，超限、重复字段、非有限数、不安全数字及无效 Unicode 失败闭合；CLI 只输出固定短错误，不回显文件正文。文件祖先权限、挂载和操作员身份仍属于主机信任边界。

## 人工证据导入

模板为 `docs/manual-evidence-template.json`，仅用于结构说明，不能作为真实证据。`scripts/verify_manual_evidence.py` 检查封闭字段、真实日期、合同/锁/发布摘要关联、逐次审批 ID、调用 ID、request_id、参数摘要、服务计数、拒绝零调用、两次独立批准、未知结果对账及零自动重试。输出与输入隔离，只返回短元数据。

真实证据必须由操作员在受管 DSH 界面和独立服务观测侧采集、脱敏，再由外部信任配置验证 HMAC 签认。自报 `real`、`contains_secrets=false` 或计数不能证明真实事件；有效签名只能证明持钥方签认。所有结果恒保留 `physical_truth_certified=false`，签认后仍为 `awaiting_independent_review`。结构通过不自动开启设备执行或生产权限。

## 本轮验证的范围

2026-10-08 的五组门禁见 [历史四阶段记录](implementation-2026-10-08.zh-CN.md) 和 [历史机器摘要](evidence/closure-20261008-05/summary.json)。2026-10-09 的发布顺序修复、当前复验与环境恢复另见 [续行实施记录](implementation-2026-10-09.zh-CN.md)，不将两轮不同输入合并为一次验收。发布回归在临时目录使用合成 Runtime、两个 profile 的受管内部链接以及外部测试签认，完成只读创建→校验往返。内容、权限、缺依赖、越界链接、失效链接和内置信任文件均拒绝；生产启动正例只运行 Node 测试替身，无效签认负例在任何 Node 版本探测、创建 preset 和启动前退出。

本轮未对真实锁定依赖的完整生产副本执行只读发布往返，也未验证管理员/服务用户分离或生产规模启动性能。已有 pnpm 依赖的受管内部链接与源码开发链接应分别处理；生产打包必须物化越界开发依赖，不能放宽根边界。工作区源码首尾身份报告也不包含已安装依赖，不能替代生产清单。

`record_closure.py` 的本地证据目录与人工证据格式是两个独立用途：前者记录离线命令、枚举输入身份、退出码、日志摘要和逐次基准样本，后者关联真实审批与服务观测。离线报告不会自动成为人工批准，最终仍保持 `release_accepted=false`、`production_authorized=false`。

`verify_acceptance.py --mode real --evidence ...` 可导入证据；与版本关联选项配合核验，仍保持外部验收 blocked。真实脱敏语料、浏览器中审批参数显示、公司生产环境及真实 provider 对账需要人员提供材料并验收，本轮没有用合成结果替代这些门槛。
