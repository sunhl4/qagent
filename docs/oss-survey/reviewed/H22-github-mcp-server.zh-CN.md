# H22 GitHub MCP Server：工具元数据的AST门禁

项目 `github/github-mcp-server`；SHA `b98d115bbb080e9555466a96656ec4df605aea21`，提交2026-10-21T11:46:50+02:00；来源 `/tmp/oss-github-github-mcp-server`。根LICENSE MIT。静态源码/测试阅读，未调用GitHub。

## 实现链

`pkg/toolvalidation/readonlyhint.go` 提供供测试使用的AST扫描器：解析单个Go包的非test文件→识别MCP导入别名→遍历mcp.Tool字面量→检查Annotations.ReadOnlyHint显式存在→输出文件/行号/工具名/原因。

## 三个细节

1. Go bool零值无法区别“没写”和“显式false”，因此用AST而非运行时对象检查；这属于合同完整性而非工具行为检测。
2. 支持import别名，拒绝不能静态验证的Annotations函数返回、位置字段和缺失字段，避免漏掉动态构造的不明工具声明。
3. 扫描跳过_test.go允许fixture不受限制，并跨build tags解析本包；不能据此证明所有编译产物或下游动态工具都已检查。

```143:146:pkg/toolvalidation/readonlyhint.go
	if findFieldValue(annoLit, "ReadOnlyHint") == nil {
		return []ReadOnlyHintViolation{mk("ToolAnnotations literal does not explicitly set ReadOnlyHint")}
	}
	return nil
```

## 测试

readonlyhint_test.go:23-110建立合法、缺hint、缺annotations、非字面量、别名导入等fixture，再按expectCount/expectReason比较。明确标false也应通过，因为检查的是声明齐全，不是所有工具必须只读。

## 公司落点

公司已有contracts工具列表，优先从真源生成DSH注册并比对，不能为了快照再维护第二名单。
只读metadata可显式化，但绝不以外部readOnlyHint授予设备免审。`tests/test_contracts.py`和注册投影测试可借“字段必须显式”门禁。
对新工具同时检查capability/provider/输出句柄/错误形状，禁止未知工具通过可见清单绕过。

证据：readonlyhint.go:19-43,45-94,97-148；readonlyhint_test.go:23-110；LICENSE。未审全GitHub API实现或远程SaaS租户隔离。
