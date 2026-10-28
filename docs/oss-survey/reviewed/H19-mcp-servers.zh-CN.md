# H19 MCP 参考服务器：文件根、符号链接与写入竞争

项目 `modelcontextprotocol/servers`；SHA `51b6382a3e827aceb6bce430b1208d69b93d95ea`，提交2026-10-19T02:37:30-04:00；来源 `/tmp/oss-modelcontextprotocol-servers`。静态阅读filesystem实现/测试，未执行文件工具；许可根LICENSE。

## 调用链

validatePath展开/解析路径→允许目录字符串边界→realpath符号链接边界→新文件父目录检查，合法路径再进入读写函数。writeFileContent先以wx排他创建，遇EEXIST才进入overwriteInPlace。

## 三个关键细节

1. 无allowed directories并非放开cwd：虽然相对路径解析有cwd fallback，后续isAllowed仍拒绝，错误明确no allowed directories。只读前半函数会得出错误结论。
2. 处理Unicode等价路径仍要以真实允许root为依据，不能为兼容名字而扩展访问域。
3. 覆写经lstat、O_NOFOLLOW（POSIX）、打开后dev/ino一致性校验，再通过已验证handle写入，防路径替换；代价是非crash-atomic，进程中断可能留下部分内容。

```242:247:src/filesystem/lib.ts
  // Security: Handle symlinks by checking their real path to prevent symlink attacks
  // This prevents attackers from creating symlinks that point outside allowed directories
  try {
    const realPath = await fs.realpath(absolute);
    const normalizedReal = normalizePath(realPath);
    if (!isPathWithinAllowedDirectories(normalizedReal, allowedDirectories)) {
```

## 测试

path-validation.test.ts:54-85断言相同目录/子目录允许、相似前缀project2拒绝；文件头检测宿主符号链接能力，不支持可能跳过相关测试。因此Windows/WSL测试通过与Linux不能无条件等价。

## 公司映射

文件工具需分别核实授权root、symlink、竞态和写入完整性；前端路径可见不等于读取获准。
`tests/`可采用前缀穿越、Unicode/Windows路径、新文件父目录和竞态反例。
内部算法源码检索与外部用户文件区要分域，返回仍过短结果和内容限制。
不直接把filesystem server挂成可绕审批的shell替代；公司执行边界仍由受管preset和合同定义。

证据：lib.ts:65-89,95-132,210-270,292-359；path-validation.test.ts:9-51,54-85；LICENSE。未审该仓全部服务器；文件系统机制不能证明记忆/fetch服务器的安全性。
