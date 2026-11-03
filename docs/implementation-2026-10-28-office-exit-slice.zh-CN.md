# WPS 套件移植 · office.convert + office.open 出口切片(2026-10-28 P5/P6)

对应清单:§4.6/§4.7(L6 转换/交付出口)+ §5.1(L7 open_in_wps 的 Windows 档)+ 附录 B 的「交付:导出/落位」与「`open_in_wps`」两项。与并行会话不重叠(office 9→11 工具,合同全量 66→68)。

## office.convert(P5,`company_office_convert` / `office.convert`)

- 转换矩阵:`.docx→pdf` 与 `.doc→docx`,经显式无头引擎:`COMPANY_AGENT_SOFFICE` 绝对路径优先,`soffice`/`libreoffice` PATH 解析兜底;**无引擎是硬失败**(如实失败,不出替身产物、不上传任何内容)。
- **两阶段落盘**(对齐真实 soffice 会静默覆盖 `--outdir` 同名文件的事实):先在一次性临时目录完成转换 + 三重校验(存在/非空/magic:`%PDF-` 或可打开的 `word/document.xml` 包),再按交付名原子写入工作区;源文件在两种路径下都不可能被覆盖。
- 命名:源旁 `<stem>.<ext>`,占用则 `<stem>_01.._99`,99 后如实拒绝;`overwrite=true` 允许替换第一个同名交付(仍是旁路文件,不是源)。
- 引擎租约:`%TEMP%/soffice-<workspace-hash>.lock` 跨进程锁(O_CREAT|O_EXCL),600 秒视死回收,等待上限 120 秒,防多任务互抢转换器。
- 子进程纪律:数组化参数、白名单环境(PATH/SystemRoot/TEMP/TMP/COMSPEC/PATHEXT,不继承全量 env)、stdout 256KB 上限、120 秒超时。
- 源字节校验:.docx 必须是 zip 包、.doc 必须带 OLE 签名,否则"字节与扩展名不符"如实拒绝。

## office.open(P6,`company_office_open` / `office.open`)

- §5.1 三不变量落 Windows 档:**验证启动器 + 审计 + 失败人话,不静默回退**。
- 启动必须显式开关:`COMPANY_AGENT_OPEN_WPS=wps|startfile`;未配置 → 如实拒绝("未配置拉起方式"),适配器绝不会在被无人值守的宿主上意外拉起 GUI。
- `wps` 档:注册表链 `HKCR\.<ext>` → ProgID → `shell\open\command` 解析出程序路径,**非 WPS/Kingsoft 关联 → 拒绝并给修复指引**,不加系统默认回退;非 Windows 宿主如实说 `wps` 档不可用。
- `startfile` 档:操作员显式选择的系统关联打开(`os.startfile`),回执如实标 `launcher=shell`(可能不是 WPS)。
- 审计:每次打开写 `open_with_wps` 台账行(HMAC 链,失败不阻断 open 本身,`audited=false` 如实标记);notes 进 detail。回执不带工作区外的机器路径,launcher 只回 basename。

## 门禁结果

- `tests/test_office_convert.py` 6/6(fake engine seam 让三重校验端到端跑通):引擎配置后的 pdf/docx 转换、docx 产物包校验、自动序号避让 + overwrite 两个分支、无引擎硬失败、magic/后缀守卫、失败退出码拒绝。
- `tests/test_office_open.py` 8/8(注册表/启动双接缝,不懂 WPS 也能跑):未配置拒绝、wps 启动+审计行、非 WPS 关联拒绝且零启动、posix 宿主拒绝、startfile 档、后缀白名单/缺文件、审计故障不阻断。
- 顺手修正 `test_plugin_runtime` 的计数位(59→65→66→68 与 boot 期望列表);本切片两文件 14 + `test_office_audit` 11 + `test_office_pptx` 8 = 33/33 通过,合同与无遗留命名门禁通过。`test_only_company_architecture_roots_remain` 的 `wsl_pnpm_setup.sh` 一项失败来自并行会话正在重建该文件的在途状态(22:14 重新出现),非本切片所致,不代改。
- Lint(stdin 通道,E902 机器异常见 audit 切片记录):本切片 5 个触碰文件 + 2 个模块全部 0 违规。

## 全量清单剩余(经此轮后仍开放,供并行会话与后续批次安排)

1. `run_compute` 沙箱(§4.9,JS/受限执行 + 白名单 API + 高安全档禁用)——清单独立项,未动。
2. OCR(§4.6/§4.7 的三环第二环:tesseract 子进程 + 共享预算)——摄取层已对未知 OCR 如实拒绝,补 OCR 属环境级能力。
3. officecli 解析层 + vendoring(§4.1;stdlib-only 路线下视觉预览未做,可先做"解析层 + 显式 env + 测试桩"以便部署真机时即插)。
4. `audit` 的 `@@目标|quote@@` 渲染/定位回跳(§3.3/§3.4 的桌面渲染面)——适配器侧无对应 UI 面,存疑不做。
5. 加载项(§5.2)——参考实现自己标注二期,暂缓。
6. DeepSeek 观测纪律(fixed/cached/uncached 三件套日志)——DSH runtime 侧(Java/Node),不在 Python 适配器。
