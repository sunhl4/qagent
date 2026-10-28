# H36 Cognee：PGVector引擎所有权与分区清理

项目 `topoteretes/cognee`；SHA `37f788bd287750e10d7610173e5332b3843f6ebd`，提交2026-10-16T22:07:34+02:00；来源 `/tmp/oss-topoteretes-cognee`。静态源码/测试；未运行Postgres、embedding或ETL。根LICENSE Apache-2.0。

## 聚焦调用链

PGVectorAdapter接收connection_string/schema/embedder，读取向量和关系配置→决定连接池→按schema隔离或数据库身份创建/借用engine→集合反射/索引查询→close或prune按所有权处理。
这比旧稿仅据modules目录推断entities→graph→vector更具体；本篇不宣称完整ETL已验证。

## 机制分析

- schema模式强制专用engine，search_path置为dataset schema与public，不修改共享关系engine。这防止为一个dataset设置连接状态影响其他dataset。
- 无schema时区分数据库名；同Postgres关系数据库可复用engine/sessionmaker，否则创建自有。_owns_engine明确谁负责dispose，避免误关其他任务共享连接。
- get_table_names在schema模式只反射自身schema，delete_database文档也限制本dataset；通用“列出所有集合再删除”会泄露或损坏其他租户。

```145:148:cognee/infrastructure/databases/vector/pgvector/PGVectorAdapter.py
            server_settings = dict(connect_args.get("server_settings") or {})
            server_settings["search_path"] = f"{self.schema}, public"
            connect_args["server_settings"] = server_settings
            super().__init__(
```

## 测试

`cognee/tests/unit/infrastructure/databases/vector/test_pgvector_prune.py:28-60`验证不同数据库engine归己；`:63-93`验证同库借用原engine/sessionmaker。测试importorskip asyncpg/pgvector且使用mock，不证明真实数据库租户权限已配置；未运行。

## 公司映射

知识入库/检索需要来源版本和server-side租户scope，再选择向量库。adapter接口可借，不必引Cognee完整运行面。
测试区分共享engine关闭、prune越域、schema名不可信、权限关闭状态；身份必须来自公司账号而非LLM填写schema。
`contracts/`定义短检索结果及来源引用，内部知识不得经摘要扩大可见范围；算法目录仍平台动态获取。

证据：PGVectorAdapter.py:35-67,70-103,109-133,135-175,183-214；test_pgvector_prune.py:28-93；LICENSE。未验证全部存储和图谱后端，不能以VectorDBInterface存在断言全后端隔离等价。
