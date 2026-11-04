.PHONY: help validate schemas canvas-check tree test stubs-check contracts-typecheck check conformance handoff demo

help:
	@echo "常用命令："
	@echo "  make validate            校验 schema、YAML、契约、桩声明与 Canvas"
	@echo "  make test                运行契约与流水线测试"
	@echo "  make stubs-check         只检查桩声明与端口契约"
	@echo "  make contracts-typecheck 检查契约与包可编译/可加载"
	@echo "  make conformance         校验一致性结果交换样例"
	@echo "  make handoff             打印联调交换包体检与交接清单"
	@echo "  make demo                桩上跑一次有界实验循环演示"
	@echo "  make check               validate + test + typecheck"
	@echo "  make schemas             列出全部 schema"
	@echo "  make canvas-check        检查 canvas 文件"
	@echo "  make tree                打印工程结构"

schemas:
	@ls -1 schemas/

validate:
	@python3 scripts/validate.py

test:
	@node --test "tests/*.test.ts"

stubs-check:
	@node --test tests/contracts.test.ts

contracts-typecheck:
	@node scripts/typecheck.mjs

check: validate contracts-typecheck test conformance

conformance:
	@node scripts/check-conformance-results.mjs

handoff: conformance
	@node scripts/contract-bundle.mjs

demo:
	@node scripts/demo.mjs

canvas-check:
	@test -f canvas/autonomous-ai-research-workflow.canvas.tsx && echo "canvas ok"

tree:
	@find . -type f -not -path './.git/*' -not -path './node_modules/*' | sort
