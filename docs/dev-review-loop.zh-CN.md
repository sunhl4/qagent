# 开发审查循环

本文件是公司仓库开发和审查自动迭代的操作入口。循环本体在 `scripts/dev_review_loop.py`，测量在 `scripts/dev_review_gates.py`，本轮计划在 `docs/dev-review/plan.json`。

它跑在 DSH 外面，只执行计划里已经登记的命令。DSH 仍是唯一 Agent Runtime。`company_research_run` 仍是研究时钟。计算提交仍走各自的公司工具，并且每次单独批准。

## 从 QML-FF 的循环里拿来的部分

QML-FF 的 `qmlff/research_loop.py` 把一轮收成固定顺序：审阅，运行一个预先登记的候选，从该次产物读取指标，再给出保留、放弃或升级。指标只认这次 attempt 目录里的文件。候选自己带上的数字不算数。调度器命令会被拒绝。状态在执行前落盘；中断后的不确定执行不会被静默重跑。

2026-11-09 上午，QML-FF 工程里正在进行的对话先把仓库挂回本机，审了自适应探索方案，然后继续全自动探索，并追问为什么探索一会儿就停。那次探索停得早，是协议写成了短预算：

- 候选名单是事先登记的有限集合。ℓ=2 那一轮是 4 组、2 个种子、每组 2000 步，跑完后提议函数返回空名单，循环以队列耗尽结束。
- `max_rounds`、`max_attempts`、超时、预算、连续失败、审阅失败，都会停。
- `stop_on_keep` 为真时，第一个达到阈值的候选会结束后面的名单。
- 命令一旦被识别成调度器提交，循环拒绝执行。远程提交当时仍不可用，所以它不会自己改到集群上接着算。
- 同一条科学臂没有双种子同时改善时，协议不允许悄悄加步数。

公司仓库的开发和审查用同一套顺序，计划改成适合改代码和复查的形状。

## 一拍怎么走

```text
读计划
  → 审阅命令
       失败 → 停止原因 review_failed，不启动候选
  → 队列里的下一个候选
       队列空了 → 运行提议命令
            下一项 → 回到队列
            名单空了 → requires_new_review
       实现候选且 status=open、没有 edits → needs_implementation，本拍停在这里
       实现候选带有 edits → 循环只改 allowed_paths 里的文件，再测量
       路径不符合开发顺序 → development_order
       成本超过剩余预算 → budget
  → 运行共享的测量命令
  → 只读本次 metrics.json
  → keep / discard
  → 队列还有候选，且 stop_on_keep 为 false → 继续
  → 写明停止原因
```

当前计划的 `stop_on_keep` 是 `false`，`task_bound` 是 `true`。一次启动按优先级做完目录里每一项还没结的改动，不被 1000 轮、1000 次尝试或总预算 1000 截断。这三个数是下限。单条测量命令不设墙钟超时。开跑前的审阅先跳过这些还没落地的改动，每一项落地后再测。已经保留或放弃的目录项不会再跑。第一次保留不会把后面的项丢掉。目录用尽、连续失败、审阅失败、内核冻结和源码指纹变化仍会停。研究实验卡的 `max_attempts` 仍是 1 到 5。

测量是 `checks_failed`，方向为减小，基线 1，最小效应 1。产物里的失败数为 0 才保留。失败数来自门禁脚本写下的 JSON，不来自候选声明。

## 这轮已经登记的检查

| 候选 | 在查什么 |
| --- | --- |
| `development-order` | `AGENTS.md` 仍要求先合同、再适配器、再插件、再测试 |
| `device-policy` | `quantum_device_run` 在 lab、sign 询问，在 boot、algo 拒绝 |
| `not-a-second-runtime` | `src/`、`packages/`、`profiles/`、`contracts/` 没有把这个循环注册进去 |
| `early-stop-disabled` | 计划不会在第一次保留时停，轮数盖得住整份名单，命令里没有调度器 |
| `failure-record` | 崩溃、超时和脏工作树只留下类别、错误码、阶段和是否可重试。未知执行不可重试。工具回执不带这条记录 |
| `proposal-continues` | 队列空了以后按目录提议下一项；目录用尽就要求新的书面协议 |
| `charter-boundary` | 章程槽位是问题、基线、指标和预算。回执只写新立或变了的槽位名 |
| `surface-discards` | 目录用尽时，本拍若有放弃项，停止原因仍是 `discarded` |
| `snapshot-matches-ledger` | 状态快照的循环标识和停止原因等于账本最后一拍 |
| `release-boundary` | 发布计划仍写明座席边界，S4、S5、S6 不开始，生产授权仍为否 |
| `seat-card-once` | 每一拍自己编译并跑一张实验卡，未批准先询问，未复现的基线不运行 |
| `loop-writes-code` | 实现候选附上 edits 时，循环改允许路径里的文件；测量未保留则改回 |
| `kernel-stays` | 已安装运行时和 runCli 入口不改。启动界面可以改成公司账号和密码，再进入带公司风格的 DSH 界面 |

审阅命令每次都跑上表。提议只走 `docs/dev-review/catalog.json`。已经保留的项不进入这一拍的测量。`failure-record` 仍由审阅命令检查。

改合同、适配器、插件或预设时，实现候选的 `allowed_paths` 必须同时包含 `tests/` 下的路径。启动界面可以改：填写公司账号和密码，进入带公司风格和适配的 DSH 界面。已安装运行时和 `scripts/dsh-cli.mjs` 的 runCli 入口不改。只改文档或脚本时，写清相对路径即可。下一项实现只改该项列出的路径。目录用尽以后要新的书面协议，把新候选写进目录，再用新的输出目录开一轮。循环不会自己发明下一项。实现候选附上 edits 时，循环只改 allowed_paths 里唯一匹配的旧文本；测量没有保留就把文件改回。

## 停止原因

| 原因 | 含义 | 下一拍 |
| --- | --- | --- |
| `drained` | 计划里直接列出的候选全部保留，队列空了 | 有新的开发工作时，先写成新的目录项，再用新的输出目录开一轮 |
| `requires_new_review` | 已审阅目录用尽 | 新协议先写入目录。不能把目录用尽说成开发已经做完 |
| `needs_implementation` | 下一个实现候选没有附上 edits | 把改动写进该候选的 edits，再用新的输出目录开一轮 |
| `discarded` | 至少一项测量没有达到阈值。目录用尽也不会把这次放弃说成正常结束 | 看对应 attempt 的 `metrics.json`，修完新开一轮 |
| `kept` | `stop_on_keep` 在第一次保留后停了 | 开发审查计划应保持 `stop_on_keep` 为 false |
| `max_rounds` / `max_attempts` | `task_bound` 为 false 时，上限到了，后面还有候选 | 开发计划保持 `task_bound` 为 true。未跑的候选不能记成完成 |
| `budget` / `deadline` | `task_bound` 为 false 时登记成本到了，或过了截止时间 | 开发计划按任务继续。设了 `deadline_at` 时仍按截止时间停 |
| `consecutive_failures` | 测量命令连续失败达到上限 | 先看 stderr，再新开一轮 |
| `withheld` | 命令被识别成调度器提交 | 换成仓库内的检查命令 |
| `review_failed` | 审阅命令失败或被拒绝 | 先修审阅，再新开一轮 |
| `development_order` | 实现候选没有按开发顺序写路径 | 补上 `tests/` 路径 |
| `kernel_frozen` | 改动碰到已安装运行时或 runCli 入口 | 改启动界面或公司节点。启动仍是公司账号和密码，进去仍是 DSH 界面 |
| `interrupted` | 上次执行意图没有对完 | 核对产物；不要把不确定的结果改成成功 |
| `source_changed` | 循环程序或它启动的脚本在本轮里变了 | 新开一轮 |
| `planned` | 干跑，没有测量 | 去掉 `--dry-run` |

产品源码不在指纹里，因为下一拍本来就要改它。指纹锁的是循环脚本、计划和它点名启动的脚本。改了这些，就换一个输出目录。已经结束且队列为空的状态可以 `--resume`，它不会把同一轮再跑一遍。带有未完成执行意图的状态不会自动重跑。

## 怎么跑

人用自然语言说下一件要改的事。开始前的书面手续由执行的人填完，再启动：

1. 把这句话写成 `docs/dev-review/catalog.json` 里的一项，填上标识、假设、成本、种类、状态、允许修改的路径和 edits。
2. 状态写 `open`，并写下 `edits`。每一处包含路径、旧文本和新文本。循环替换允许路径里的唯一匹配，再测量。没有保留时，循环把文件改回。
3. 选一个新的空目录作为这一拍的输出目录，再执行下面的命令。上一拍的目录已经结束，不能再拿来开新的一拍。

在仓库根目录：

```powershell
python scripts/dev_review_loop.py `
  --config docs/dev-review/plan.json `
  --output-dir $env:TEMP\company-dev-review-next `
  --status-out docs/dev-review/STATUS.md
```

退出码 0 表示 `drained`、`kept`、`planned`、`needs_implementation` 或 `requires_new_review`。其余停止原因退出码为 2。干跑加 `--dry-run`，它不启动测量，也不能当作通过。

被放弃的项不会在同一项上自动加码重试。要重做就换一个新标识，重新写进目录。

座席审查里把 minimal 组合里的超算、云和计划写工具拿掉，仍是有条件的下一步，不在这份目录里。那要单独写成下一份受审阅协议。GitLab、平台地址和模型端口也不由这个圈子填写。

状态快照写在 `docs/dev-review/STATUS.md`。每一拍覆盖它，并且必须和 `LEDGER.md` 最后一拍是同一次循环、同一个停止原因。账本只追加本拍的停止原因和候选决定，不覆盖上一拍，也不写入假设正文。
