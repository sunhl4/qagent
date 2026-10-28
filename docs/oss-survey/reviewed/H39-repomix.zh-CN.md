# H39 Repomix：代码上下文打包与读取资源边界

对象 `yamadashy/repomix`；SHA `e696384d062f08f0246ffd2580d5a206484fc0a4`，提交2026-10-18T21:26:50+09:00；来源 `/tmp/oss-yamadashy-repomix`。本轮静态复核文件收集与读取路径，未对公司内部代码执行打包；许可证以根LICENSE为准。

## 调用链与实现

`collectFiles(filePaths, rootDir, config)` → 并发池 → `readRawFile(fullPath,maxFileSize)` → 按原始顺序生成`rawFiles`与`skippedFiles`。池大小50；完成顺序可以不同，但每项写入原索引，最终输出不因I/O时序随机变化。跳过理由单独返回，适合在界面明确告知“哪些文件未进入上下文”，而非把缺失伪装为完整扫描。

读取层先排除已知二进制扩展，然后读取整个文件，才检查大小；随后检查NULL字节、BOM及UTF-8，必要时走编码检测。这是面向仓库打包吞吐的设计取舍，不能被描述成读取前的内存硬上限。

```80:89:src/core/file/fileRead.ts
    // Read the file directly and check size afterward, avoiding a separate stat() syscall.
    // This halves the number of I/O operations per file.
    // Files exceeding maxFileSize are rare, so the occasional oversized read is acceptable.
    const buffer = await fs.readFile(filePath);

    if (buffer.length > maxFileSize) {
      const sizeKB = (buffer.length / 1024).toFixed(1);
      const maxSizeKB = (maxFileSize / 1024).toFixed(1);
      logger.trace(`File exceeds size limit: ${sizeKB}KB > ${maxSizeKB}KB (${filePath})`);
      return { content: null, skippedReason: 'size-limit' };
```

`path.resolve`负责构造路径，不自动证明路径位于授权仓库内。调用者提供的文件清单、符号链接及仓库来源仍需独立检查；本轮不据此断言整个Repomix缺少路径保护。

## 测试与公司落点

`tests/core/file/fileCollect.test.ts:17-81`通过依赖注入模拟读取，检查大小参数、文件结果和跳过项。该类单测不能证明真实巨型文件的峰值内存，也不能证明敏感信息已全部剔除。本轮未执行上游测试。

可借鉴收集阶段的确定顺序、显式缺失清单和进度回调，服务于内网代码知识索引。进入公司知识库之前先做用户/项目权限、密钥排除、来源追踪与总量限制；大文件用受限流式读取而不是照搬整文件读取策略。内部算法实现只向有权内部账号提供，外部账号不能通过“仓库摘要”得到内部代码。

不把全仓库打包当作默认聊天附件；DSH只接收受控短摘要和引用，完整制品留在平台。该项目不提供企业身份、设备审批或云/HPC调度事务。

证据范围：`src/core/file/fileCollect.ts:9-36,39-64,66-81`；`src/core/file/fileRead.ts:70-95,97-125`；`tests/core/file/fileCollect.test.ts:17-81`；根LICENSE。范围限于读取/打包机制，未验证所有过滤器。
