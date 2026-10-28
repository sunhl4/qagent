# 量子能力使用说明

公司量子算法、资产和科学结果的真源是 `uniqon`。Q-agent 不保存算法名单，也不直接导入 `company_quantum` 或任何科学包。

以后所有算法都按该平台架构开发：内置组件、配方和独立插件的元数据来自同一目录；被发现不等于有可信执行入口或已经获得授权。平台服务适配器只把显式注册且通过准入的条目标为可运行；仅配置 URL/token 不会自动接通全部科学能力。Q-agent 只对接平台的 `algorithm.catalog` 与 `algorithm.run`，不为单个算法增加工具。

发现必须调用 `quantum_algorithm_catalog`。返回的 `id` 是平台 `component_id`（不在知识库维护示例名单），并带有 `version`、`maturity` 与 `runnable`。运行必须原样绑定 `algorithm=id`、`component_version=version` 和目录响应的 `catalog_version`，参数遵守平台发布的机器可验证合同。目录声明不等于授权执行；只有 `runnable` 为 true 的标识才可交给 `quantum_algorithm_run`。不要编造 `__list_algorithms__` 一类哨兵名，也不要把知识检索结果当作算法名单。

模拟器、编译器和设备分别是独立 provider。设备执行必须由 `quantum_device_run` 完成并经过人工批准。只有该工具可返回 `twin_id` 和 `qccd-twin` 来源。

云平台模拟器任务(`quantum_cloud_submit` 到 `qiskit-sim`/`iontrap-sim`)接受标准 OpenQASM-3 网络文本文件；适配器会在提交前把静态的 `h`、`x`、`y`、`z`、`s`、`sdg`、`t`、`tdg`、`sx`、`sxdg`、`rz`、`p`、`u1`、`u2`、`u3`、`cx`、`cz`、`swap` 门编译成平台接受的 `rzz`、`rx`、`ry` 方言。原生 `rzz`、`rx`、`ry` 也可直接使用；动态结构、自定义门和不在编译名单内的门在网络提交前失败闭合。`shots` 为 100 到 1000 且是 100 的倍数；`rzz` 不在 `stdgates.inc` 里，编译后的程序会补充 `gate rzz(p0) a, b { cx a, b; rz(p0) b; cx a, b; }` 定义；测量使用逐位赋值形式(`bit[N] meas; meas[i] = measure q[i];`)，整寄存器裸 `measure q;` 会被提交通道自动改写。
