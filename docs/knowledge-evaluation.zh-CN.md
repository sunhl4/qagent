# 知识检索评测入口

`scripts/evaluate_knowledge.py` 只运行本地确定性检索，不调用模型、科学计算或设备。必须显式提供已授权目录、用例文件和尚不存在的输出文件。真实业务数据应先由人员脱敏；脚本不能自动证明语料已脱敏。

用例 JSON 的封闭顶层字段为 `version`（`1.0`）、`scope`（`synthetic` 或 `operator_deidentified`）和 `cases`。最多 1000 个用例；每项为唯一字母数字 `id`、长度不超过 1000 的 `query` 和最多 32 个语料内相对路径 `relevant`。空 relevant 表示期望没有检索命中。路径禁止逃逸；语料根必须为绝对非符号链接目录。

执行示例：使用已安装开发环境的 Python 运行 `scripts/evaluate_knowledge.py --corpus /absolute/deidentified-corpus --cases /absolute/cases.json --output /absolute/new-report.json`。该命令只应对操作员明确提供的资料使用；本次工程验证只生成临时合成集。

报告包含首位命中率、前八条召回率与平均倒数排名、无证据正确率、扫描覆盖和中位耗时，不输出 query、正文、来源路径或配置凭据。合同摘要和用例文件摘要用于复核输入版本；它们不是完整语料快照证明。检索本身为每条引用产生文档摘要版本。扫描不完整时仍写报告但退出码为 1；输出文件已存在时拒绝覆盖。

当前检索使用中文双字扩展和固定重叠片段，每文档保留一个最佳片段；它不是向量语义检索。通过小型合成集不能推断真实业务准确率。`operator_deidentified` 仅标记操作员声明的输入范围，报告仍要求人工复核，不自动升级为业务验收通过。
