# WPS 套件移植 · run_compute 沙箱 + 交付命名切片(2026-10-29)

对应清单:§4.9(run_compute 附录 B 独立项)+ §3.7/§4.3(MeWork 交付命名 `标题_YYYYMMDD_NN`)。office 工具 11→13,合同全量 66→68→**70**;boot/lab/algo 可见,sign office-free。

## office.compute(`company_office_compute` / `office.compute`,§4.9 run_compute 端口)

- 结构:父适配器(`office_compute.py`)生成**独立解释器子进程**(`office_compute_child.py`,stdin 传 `{project, source}`,argv 传归一化 workspace 根);程序运行结束只回一行 JSON。
- 白名单 helper(全部复用 P0 围栏与有界生成器):`list_files`(≤2000,超限拒) / `read_text`(200k 看 cap) / `read_table`(.xlsx/.csv/.json/.txt/.md;xlsx 经 `_ingest._xlsx_book` 5000×64) / `stats`(逐列数值 min/max/sum/mean) / `write_text` / `write_table`(经 `_oc._xlsx_package` 表格上限) / `emit_chart`(直接落 `office_chart` 的确定性 json+svg) / 受限 `math` `re`。
- 沙箱边界(诚实、非掩饰):`exec` 命名空间显式钉住 `__builtins__` 为受限子集(无 `__import__`,`import os` 即 `ImportError: __import__ not found`)、print 捕获(≤40 行)、写预算(≤200 文件/4MB)、source ≤80k、RESULT JSON ≤20KB(超出标 `{"truncated":true}`)、30 秒父级强制(Windows 无 SIGALRM,靠父 kill);**进程隔离 + 受管命名空间不是操作系统级安全边界**——机器级开关 `COMPANY_AGENT_COMPUTE_ALLOW=1` 是控制项:未启用即如实拒绝(高安全档保持关闭)。
- 磁盘真相(B5):回执的每个写路径由父进程重读——`workspace_files.fingerprint` 逐文件对照 child 声称的 bytes;charts 必须存在;笔迹输出按写路径顺序给出 sha256;不符即"沙箱回执与磁盘不符,如实拒绝"。
- 坑位记录:① `exec` 会自动注入真 `__builtins__`,必须显式钉住;② Windows 短路径(ADMINI~1)与长路径会让 `is_relative_to` 误判"逃逸"——子进程 argv 根必须 `resolve()` 归一;③ 子进程 stdout 编码随 cp936,须 `PYTHONIOENCODING=utf-8` + `reconfigure`;④ 写路径返回一律以项目根为基(相对mount 与相对 project 两种口径用 `_relative_posix` 收敛);⑤ 生成器复用禁止新增解释器循环,全部走 P0 围栏。

## office.deliver(`company_office_deliver` / `office.deliver`,§3.7/§4.3 交付命名端口)

- 行为:把源文件原子复制进项目级 `deliverables/`,命名 `<标题>_<UTC YYYYMMDD>_<NN>.<ext>`;标题缺省=源文件 stem 并剥掉旧日期戳(`_20260101`/`_20260101_02`/`_20260101_02_123456`);NN 对同标题同日期扫 `01..99`,满 99 如实拒绝;**源文件永不被触碰,交付名永不覆盖**;20MB 上限;回执 project/relative 路径(§3.7 的"引用闭包"由显式 `company_office_validate` 承担,不在本工具内)。

## 测试与门禁

- `tests/test_office_compute.py` 10/10:allow 开关拒绝、read/stats/write/print 全链(oracle:落盘内容)、表格写经 `company_office_analyze` 交叉验证、用户程序异常命名回执、import 即 ImportError、逃逸路径拒绝、写预算拒绝、RESULT 截断、source 80k 上限、print 行截断。
- `tests/test_office_deliver.py` 4/4:缺省标题剥旧 戳 + 序号 01→02、显式标题、后缀/缺文件守卫、title 不接受路径分隔符。
- 计数位修正:`test_plugin_runtime`(工具总量 66→68→70、boot 期望列表累计五批)37+ 通过;`test_verify_dsh_profiles::test_verifier_builds_exact_tool_probe_per_profile` 期望 73→78、17→22(profile probe 计数位,office 五批累计)。至此 本会话全部 office 切片 60+ 用例、contract/no-legacy/profiles/plugin-runtime 全绿,倒计时门禁仅 `test_no_legacy` 的根目录检查剩并行会话在途残留 `wsl_pnpm_setup.sh`。
- Lint(stdin 通道,机器 E902 记录见 audit 切片):本切片全部 0 违规。

## 全量清单状态总账(至本记录)

已落地(section/项):P0 基座/审计链、P1 摄取、P2 生成、P3 修订全链、P4 证据闸门、P4.5 三件套、§4.9 run_compute、§4.6/4.7 转换出口(P5)、§5.1 open_in_wps(P6 Windows 档)、§4.12 格式体检、§4.5 pptx 生成/回写、§3.7 交付命名。工程侧 MeWork 行为面已全量铺设;以下三项是**环境依赖边界**,默认拒等开关,不属于行为缺失:

1. **OCR 第二环**(tesseract 子进程 + 共享预算):引擎未装时摄取层已如实拒绝,安装 tesseract 后给 `COMPANY_AGENT_OCR_CMD` 即可接入(留待需要时专项)。
2. **officecli(视觉预览/截图/shape 枚举)**:stdlib-only 路线在合同描述已如实声明不含预览;安装 officecli 后可加解析层(env `COMPANY_AGENT_OFFICECLI` + 视觉预览包装),行为面已由 pptx 工具覆盖读/改。
3. **加载项(§5.2)**:参考实现自评"二期",跨进程协议不在适配器。
4. **DeepSeek fixed/cached/uncached 观测**(§2.2):DSH runtime 侧(Node),Python 适配器无模型循环。
