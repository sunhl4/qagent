"""Typeset the Qagent architecture note as a formal Chinese PDF."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT_PRIMARY = Path(r"D:\Yaozheng\云平台项目\Qagent-设计架构与理念.pdf")
OUT_COPY = Path(__file__).resolve().parent / "Qagent-设计架构与理念.pdf"

INK = HexColor("#1c1915")
MUTED = HexColor("#5c564c")
LINE = HexColor("#c8c0b0")
PAPER = HexColor("#f7f4ed")
RULE = HexColor("#8f8778")
HEAD_BG = HexColor("#efeae1")

pdfmetrics.registerFont(TTFont("Song", r"C:\Windows\Fonts\simsun.ttc", subfontIndex=0))
pdfmetrics.registerFont(TTFont("Hei", r"C:\Windows\Fonts\simhei.ttf"))
pdfmetrics.registerFont(TTFont("Kai", r"C:\Windows\Fonts\simkai.ttf"))


def style(name: str, **kw) -> ParagraphStyle:
    base = dict(
        fontName="Song",
        fontSize=10.5,
        leading=18,
        textColor=INK,
        wordWrap="CJK",
        alignment=TA_JUSTIFY,
    )
    base.update(kw)
    return ParagraphStyle(name, **base)


STYLES = {
    "kicker": style(
        "kicker",
        fontName="Kai",
        fontSize=10,
        leading=16,
        alignment=TA_CENTER,
        textColor=MUTED,
    ),
    "title": style(
        "title",
        fontName="Hei",
        fontSize=18,
        leading=28,
        alignment=TA_CENTER,
        spaceAfter=6,
    ),
    "subtitle": style(
        "subtitle",
        fontName="Song",
        fontSize=11,
        leading=18,
        alignment=TA_CENTER,
        textColor=MUTED,
    ),
    "meta": style(
        "meta",
        fontName="Song",
        fontSize=9,
        leading=14,
        alignment=TA_CENTER,
        textColor=MUTED,
        spaceAfter=10,
    ),
    "h1": style(
        "h1",
        fontName="Hei",
        fontSize=13.5,
        leading=22,
        alignment=TA_LEFT,
        spaceBefore=16,
        spaceAfter=8,
    ),
    "h2": style(
        "h2",
        fontName="Hei",
        fontSize=11.5,
        leading=20,
        alignment=TA_LEFT,
        spaceBefore=12,
        spaceAfter=6,
    ),
    "h3": style(
        "h3",
        fontName="Hei",
        fontSize=10.5,
        leading=18,
        alignment=TA_LEFT,
        spaceBefore=9,
        spaceAfter=4,
    ),
    "body": style("body", spaceAfter=7),
    "quote": style(
        "quote",
        fontName="Kai",
        fontSize=10.5,
        leading=18,
        leftIndent=12,
        rightIndent=12,
        spaceBefore=4,
        spaceAfter=10,
    ),
    "item": style("item", fontSize=10.5, leading=17, alignment=TA_LEFT),
    "cell": style("cell", fontSize=9, leading=14, alignment=TA_LEFT),
    "cellh": style("cellh", fontName="Hei", fontSize=9, leading=14, alignment=TA_LEFT),
    "caption": style(
        "caption",
        fontName="Kai",
        fontSize=9,
        leading=14,
        alignment=TA_CENTER,
        textColor=MUTED,
        spaceBefore=3,
        spaceAfter=10,
    ),
}


def P(text: str, key: str = "body") -> Paragraph:
    return Paragraph(text, STYLES[key])


def bullets(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(P(item, "item"), leftIndent=14, bulletColor=INK) for item in items],
        bulletType="bullet",
        start="•",
        leftIndent=18,
        bulletFontName="Song",
        bulletFontSize=10,
        spaceBefore=2,
        spaceAfter=8,
    )


def table(headers: list[str], rows: list[list[str]], widths: list[float]) -> Table:
    data = [[P(h, "cellh") for h in headers]]
    for row in rows:
        data.append([P(cell, "cell") for cell in row])
    grid = Table(data, colWidths=widths, repeatRows=1)
    grid.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("GRID", (0, 0), (-1, -1), 0.3, LINE),
            ]
        )
    )
    return grid


PANEL = HexColor("#fffdf8")
ASK = HexColor("#f3e6d4")
STOP = HexColor("#f3e4e2")
SEAL = HexColor("#e4efe8")


def _box(c, x, y, w, h, title, sub="", fill=PANEL, bold=False):
    c.setFillColor(fill)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.7)
    c.roundRect(x, y, w, h, 3, fill=1, stroke=1)
    c.setFillColor(INK)
    c.setFont("Hei" if bold or not sub else "Hei", 8.5)
    if sub:
        c.drawCentredString(x + w / 2, y + h / 2 + 2.2, title)
        c.setFont("Song", 7.5)
        c.setFillColor(MUTED)
        c.drawCentredString(x + w / 2, y + h / 2 - 8.2, sub)
        c.setFillColor(INK)
    else:
        c.drawCentredString(x + w / 2, y + h / 2 - 3, title)


def _vdown(c, x, y_top, y_bot):
    c.setStrokeColor(RULE)
    c.setFillColor(RULE)
    c.setLineWidth(0.9)
    tip = 5.0
    c.line(x, y_top, x, y_bot + tip)
    path = c.beginPath()
    path.moveTo(x, y_bot)
    path.lineTo(x - 2.5, y_bot + tip)
    path.lineTo(x + 2.5, y_bot + tip)
    path.close()
    c.drawPath(path, fill=1, stroke=0)


def _hright(c, x0, x1, y):
    c.setStrokeColor(RULE)
    c.setFillColor(RULE)
    c.setLineWidth(0.9)
    tip = 5.0
    c.line(x0, y, x1 - tip, y)
    path = c.beginPath()
    path.moveTo(x1, y)
    path.lineTo(x1 - tip, y + 2.5)
    path.lineTo(x1 - tip, y - 2.5)
    path.close()
    c.drawPath(path, fill=1, stroke=0)


class ArchFigure(Flowable):
    """Paper-style orchestration drawing. kind: stack | ingest | job | duties."""

    def __init__(self, kind: str, caption: str, width: float):
        super().__init__()
        self.kind = kind
        self.caption = caption
        self.width = width
        self.height = {
            "stack": 118 * mm,
            "ingest": 78 * mm,
            "job": 48 * mm,
            "duties": 68 * mm,
        }[kind]

    def wrap(self, avail_width, avail_height):
        self.width = min(self.width, avail_width)
        return self.width, self.height

    def draw(self):
        if self.kind == "stack":
            self._stack()
        elif self.kind == "ingest":
            self._ingest()
        elif self.kind == "job":
            self._job()
        else:
            self._duties()

    def _stack(self):
        c = self.canv
        w = self.width
        mid = w / 2
        row_h = 13 * mm
        gap = 4.2 * mm
        y = self.height - row_h
        _box(c, 18 * mm, y, w - 36 * mm, row_h, "人", "平常话　文件　批准 / 拒绝", HEAD_BG, True)
        _vdown(c, mid, y, y - gap)
        y -= row_h + gap
        _box(c, 18 * mm, y, w - 36 * mm, row_h, "3080 公司脸", "对话　线路图　许可单　短回执　　不选型、不碰科学核")
        _vdown(c, mid, y, y - gap)
        y -= row_h + gap
        _box(c, 18 * mm, y, w - 36 * mm, row_h, "dsh Harness", "理解意图　在可见工具里选型　解释结果　　不持久化许可、不签发签收")
        _vdown(c, mid, y, y - gap)
        y -= row_h + gap
        trio_w = (w - 36 * mm - 8 * mm) / 3
        xs = [18 * mm, 18 * mm + trio_w + 4 * mm, 18 * mm + 2 * (trio_w + 4 * mm)]
        titles = [
            ("算法目录", "选型　校验　转写"),
            ("作业编排", "阶段　许可　落盘"),
            ("decide 政策", "允许　询问　拒绝"),
        ]
        for x, (title, sub) in zip(xs, titles):
            _box(c, x, y, trio_w, row_h, title, sub, HEAD_BG)
            _vdown(c, x + trio_w / 2, y, y - gap)
        y -= row_h + gap
        _box(c, 18 * mm, y, w - 36 * mm, row_h, "invoke 网关", "先政策，后端口　　插件只转调　　Agent 不得直连科学服务")
        _vdown(c, mid, y, y - gap)
        y -= row_h + gap
        pack_w = (w - 36 * mm - 8 * mm) / 5
        packs = ("量子数据", "量子化学", "离子阱栈", "线路调度", "外部互通")
        for i, name in enumerate(packs):
            _box(c, 18 * mm + i * (pack_w + 2 * mm), y, pack_w, row_h, name)
        for i in range(5):
            _vdown(c, 18 * mm + i * (pack_w + 2 * mm) + pack_w / 2, y, y - gap)
        y -= row_h + gap
        _box(c, 18 * mm, y, w - 36 * mm, row_h, "回执 / 实验记录", "对人短结论　　对机器可核验　　未签收不盖印", SEAL, True)

    def _ingest(self):
        c = self.canv
        w = self.width
        mid = w / 2
        box_w = (w - 28 * mm) / 4
        top = self.height - 14 * mm
        labels = (
            ("平常话", "交办 / 批准"),
            ("公司包 / 信封", "套上流程"),
            ("外部文件", "转到公司作业"),
            ("OpenQASM", "钉住线路"),
        )
        for i, (title, sub) in enumerate(labels):
            x = 8 * mm + i * (box_w + 4 * mm)
            _box(c, x, top, box_w, 13 * mm, title, sub, HEAD_BG)
            _vdown(c, x + box_w / 2, top, top - 7 * mm)
        y = top - 22 * mm
        _box(c, 18 * mm, y, w - 36 * mm, 13 * mm, "接入层", "分类　转写　钉句柄　　可执行脚本拒收")
        _vdown(c, mid, y, y - 7 * mm)
        y -= 20 * mm
        _box(c, 18 * mm, y, w - 36 * mm, 13 * mm, "同一条 dsh 会话", "不重开黄金路径　　内部编号不念给人听")
        _vdown(c, mid, y, y - 7 * mm)
        y -= 20 * mm
        _box(c, 18 * mm, y, w - 36 * mm, 13 * mm, "网关 + 作业编排", "估计可自动　　真机必须询问")

    def _job(self):
        c = self.canv
        w = self.width
        stages = ("解析", "校验", "估计", "询问", "执行", "回执")
        box_w = (w - 20 * mm - 5 * 6 * mm) / 6
        y = 22 * mm
        xs = []
        for i, name in enumerate(stages):
            x = 8 * mm + i * (box_w + 6 * mm)
            xs.append(x)
            fill = ASK if name == "询问" else SEAL if name == "回执" else PANEL
            _box(c, x, y, box_w, 14 * mm, name, fill=fill, bold=name in {"询问", "回执"})
            if i:
                _hright(c, xs[i - 1] + box_w, x, y + 7 * mm)
        ask_x = xs[3] + box_w / 2
        _box(c, ask_x - 28 * mm, 4 * mm, 24 * mm, 10 * mm, "人批准", fill=SEAL)
        _box(c, ask_x + 4 * mm, 4 * mm, 24 * mm, 10 * mm, "人拒绝 / 停", fill=STOP)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.7)
        c.line(ask_x, y, ask_x, 14 * mm)

    def _duties(self):
        c = self.canv
        w = self.width
        col = (w - 24 * mm) / 3
        heads = ("Harness", "作业编排", "网关")
        subs = (
            "理解　选型　解释",
            "阶段　许可　落盘",
            "允许 / 询问 / 拒绝",
        )
        bodies = (
            ("维护会话上下文", "解析自然语言", "选当前可见工具", "解释工具回包", "不够时向人追问"),
            ("固定六阶段", "流转条件", "同一条会话批准", "超时与失败态", "聚合成回执"),
            ("工具注册与图式", "政策先于端口", "凭据不进对话", "短输出后验", "签发权只在阱端口"),
        )
        y = self.height - 16 * mm
        for i, (head, sub) in enumerate(zip(heads, subs)):
            x = 8 * mm + i * (col + 4 * mm)
            _box(c, x, y, col, 14 * mm, head, sub, HEAD_BG, True)
        y = 6 * mm
        h = self.height - 38 * mm
        for i, lines in enumerate(bodies):
            x = 8 * mm + i * (col + 4 * mm)
            _box(c, x, y, col, h, "", fill=PANEL)
            c.setFont("Song", 8)
            c.setFillColor(INK)
            top = y + h - 8 * mm
            for n, line in enumerate(lines):
                c.drawString(x + 5 * mm, top - n * 10, "·  " + line)


def figure(kind: str, caption: str, width: float = 168 * mm) -> KeepTogether:
    return KeepTogether([ArchFigure(kind, caption, width), P(caption, "caption")])


def on_page(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.restoreState()
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.4)
    canvas.line(22 * mm, 14 * mm, A4[0] - 22 * mm, 14 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Song", 8)
    canvas.drawString(22 * mm, 8.5 * mm, "合肥市幺正量子科技有限公司  ·  Qagent")
    canvas.drawRightString(A4[0] - 22 * mm, 8.5 * mm, str(doc.page))
    canvas.restoreState()


def story() -> list:
    out: list = []
    out.append(Spacer(1, 8 * mm))
    out.append(P("独立分析稿　对照算法组《处理量子线路问题的 Agent-计划初稿》", "kicker"))
    out.append(Spacer(1, 4 * mm))
    out.append(P("Qagent 设计架构与理念", "title"))
    out.append(P("公司科研 Agent 的现网结构、原则与边界", "subtitle"))
    out.append(Spacer(1, 3 * mm))
    out.append(P("2026 年 9 月 3 日　基于 qagent 仓与 3080 控制台的独立复审　非正式对外宣传稿", "meta"))
    out.append(HRFlowable(width="100%", thickness=0.6, color=RULE, spaceAfter=12))

    out.append(P("1　判断", "h1"))
    out.append(
        P(
            "算法组那份初稿写的是一条正确、但范围偏窄的产品轨：用户上传量子线路，系统解析意图、"
            "校验线路、配置后端并估价，经人审核后再调用已授权工具，最后返回单一结构化结果。"
            "它把系统拆成 Agent Harness、独立工作流编排、统一网关，并强调屏蔽内部、权限白名单、"
            "真机知情同意、状态不得只活在模型上下文里。这些原则应当保留。"
        )
    )
    out.append(
        P(
            "独立复审后的结论是：不要按那份初稿再造一个 Agent。公司已经有且只应有一个 Agent，"
            "就是 Qagent。初稿描述的是 Qagent 内部的「线路作业」一条轨，不是第三套大脑，"
            "也不是与现网并行的第二份运行时。算法目录是选型与配置层，不是编排器。"
        )
    )
    out.append(
        P(
            "Qagent 比初稿覆盖得更宽。人可以用平常话交办，也可以上传公司流程信封、公司算法包，"
            "或外部软件导出的分子、哈密顿量、图与线路。系统先读懂并转到公司流程，再估计、询问、上机。"
            "科学软件以引擎包接入；跨包通货只有三条句柄。上机必须人批。没有签收句柄，不能装作已经签收。"
        )
    )
    out.append(
        P(
            "人入口是 3080 纸面控制台。这一版界面已经对齐产品锁：对话居中、两扇起步门、"
            "「本任务」栏随许可与回执打开、金色只出现在上机许可单。本轮不需要再做界面重构。"
            "「附上线路」四字略窄于现在也能收配置文件的事实，属于文案，不构成新的信息架构。"
        )
    )

    out.append(P("2　理念", "h1"))
    out.append(
        P(
            "Qagent 不是「我们有一个量子大模型」。对外是：化学家和组内可以像写代码一样用平常话交办；"
            "只有签收台上出现本公司离子阱孪生的签收句柄，并留下可核验的回执与实验纪要时，才算办完。"
            "模型可换。运行时与合同不可换。"
        )
    )
    out.append(P("下列原则是现网已经锁死、后续开发不得回退的理念，而不是愿望清单。"))
    out.append(
        bullets(
            [
                "一个 Harness。运行时是 dsh 的公司 profile，对话走 session.prompt。禁止另写自研循环。",
                "一张脸。人对 3080 说话、附文件、批上机。内部工具名、配方名、scenario 名不念给客户听。",
                "三条句柄。跨引擎通货只有线路、数据资产、签收。算法目录编号不是第四条句柄，不得出现在聊天回包上。",
                "引擎包是扩展单位。加软件只登记一包，不新写 Agent。Cirq 已接线；Pennylane 只占位。",
                "科学核不进源码树。源码与插件禁止直接导入科学包，只经 REST、CLI 或合同 store。",
                "失败闭合。没有规则就是拒绝。政策抛错就是拒绝。空槽位诚实失败，不伪造签收。",
                "人确认后才动真机。估计可以自动做；孪生签收必须询问。许可要组内令牌。",
                "状态落盘。作业阶段、许可、回执、实验记录写在文件里，不只活在模型上下文。",
                "短输出。工具回编号与摘要。禁止比特串全文、展开全文、测控与调度私货。",
                "近似不得冒充签收。对照模拟可以跑，不得签发或复制签收句柄。",
            ]
        )
    )
    out.append(
        P(
            "一句话：Agent 负责理解与选型；工作流负责阶段与许可；网关负责每一刀是否允许、落到哪一个端口。"
            "三者缺一，就会把关键控制交给模型，或把科学核拖进聊天进程。",
            "quote",
        )
    )

    out.append(P("3　架构方案", "h1"))
    out.append(P("3.1　总览", "h2"))
    out.append(
        P(
            "当系统面向公司全部科研交办，而不是只面向一张线路图时，仍然可以画成一条边界清晰、权限受控的工作流。"
            "与初稿不同的是：入口有三种形态，归一之后才进入同一套大脑与同一条网关。"
        )
    )
    out.append(
        P(
            "人在控制台提交任务（平常话，或 YAML / JSON，或 OpenQASM）→ 接入层分类并规范化 → "
            "dsh 理解意图并在当前预设的可见工具里选型 → 算法目录给出公司流程配置 → "
            "decide / invoke 按政策调用已授权端口 → 需要真机时暂停并询问 → 人批准后同一条会话继续 → "
            "只由离子阱端口签发签收句柄 → 回执与实验记录落盘，对人只给短结论。总编排如下。"
        )
    )
    out.append(figure("stack", "图 1　Qagent 总编排：一张脸、一个 Harness、一条网关、一组引擎包"))
    out.append(
        P(
            "具体而言：配置与外部文件先被读懂并套上公司流程信封；线路被钉成线路句柄并进入六阶段作业；"
            "自然语言不写死配方，由模型在白名单里选工具。无论内部经过多少步，对外仍是一段人话、"
            "必要时一张线路图、一份可下载的短回执。中间的工具名、内部编号、科学正文不出现在脸上。"
        )
    )

    out.append(P("3.2　三种输入，一条作业", "h2"))
    out.append(figure("ingest", "图 2　输入归一：四种来源进入同一条会话，不分裂成三套 Agent"))
    out.append(
        table(
            ["输入形态", "接入层做什么", "随后进入"],
            [
                [
                    "平常话",
                    "分类空话、交办、批准、拒绝。不在这里写死配方。",
                    "同一条 dsh 会话。已附线路或配置则作为隐式上下文，不把编号念给人听。",
                ],
                [
                    "公司流程或公司算法包",
                    "识别公司信封，或认出算法包并套上信封，再校验。",
                    "目录编号进入本任务记忆。人说仿真或先估计后，走对应工具。",
                ],
                [
                    "外部文件",
                    "按分子、哈密顿量、图或外部线路包转到公司作业。可执行脚本拒收。",
                    "有 OpenQASM 则钉线路并先估计；真机仍停在许可单。",
                ],
                [
                    "纯线路文件",
                    "按 OpenQASM 解析、钉住、画在对话里。",
                    "线路作业：解析、校验、估计、询问、执行、回执。",
                ],
            ],
            [32 * mm, 68 * mm, 68 * mm],
        )
    )
    out.append(Spacer(1, 3 * mm))
    out.append(
        P(
            "三种形态不是三套 Agent。接入层的职责是分类、转写、钉句柄；大脑的职责是在公司工具里选型；"
            "编排层的职责是记住阶段。把「读懂外部文件」写成另一个产品，会再次分裂运行时。"
        )
    )

    out.append(P("3.3　标准作业链", "h2"))
    out.append(
        P(
            "跨引擎的黄金路径已经固定，不因输入形态而分叉成第二条签收合同："
            "化学或数据计算留下资产句柄 → 线路必须先钉住 → 可选对照模拟 → 编译估计 → "
            "询问后的孪生签收 → 经典对照字段。编译估计与签收可以换后端实现，但不得换工具名，不得换句柄合同。"
            "线路作业的六阶段与人闸如下。"
        )
    )
    out.append(figure("job", "图 3　线路作业六阶段。金色询问是人闸：批准后同一条会话继续，拒绝则停"))

    out.append(P("4　实现方案", "h1"))
    out.append(P("4.1　方案概述", "h2"))
    out.append(
        P(
            "本方案面向公司科研交办，不限于线路图。采用 dsh 作为 Agent Harness，负责模型调用、"
            "会话上下文、任务推进和工具调用；采用落盘的作业与交办记录作为工作流编排层，"
            "管理人审核、阶段推进和异常后的同一条会话；所有服务器端算法与工具均通过 decide / invoke 网关访问。"
            "公司脸只读回包里允许出现的字段。三者职责不可互换，见图 4。"
        )
    )
    out.append(figure("duties", "图 4　三权分立：Harness 理解，编排记住阶段，网关决定每一刀"))
    out.append(P("整体设计遵循以下原则，并与初稿对齐，同时补上初稿未写明的公司边界："))
    out.append(
        bullets(
            [
                "屏蔽内部实现。人只看任务输入、估计、许可与短结论。不必了解底层算法、工具及内部工作流。",
                "严格控制执行权限。算法、代码和工具调用由服务端统一管理，经白名单与预设可见集限制。",
                "确保用户知情确认。涉及真机、费用或较长执行时间时，必须由人确认后才能执行。",
                "提高系统安全性。避免人直接访问内部工具、服务器资源、私有代码和敏感配置。",
                "保证结果一致。统一输入校验、执行流程和输出格式，降低操作差异带来的不确定性。",
                "便于审计与治理。记录参数摘要、人确认、工具调用和执行结果，实现全过程追踪。",
                "Agent 负责理解与决策，工作流负责确定性控制。",
                "所有工具调用统一经过网关，不允许 Agent 直接访问底层科学服务。",
                "每个作业节点必须具有明确的输入、输出和错误类型。",
                "工作流状态不得只保存在 Agent 上下文中。",
            ]
        )
    )

    out.append(P("4.2　核心组件职责", "h2"))
    out.append(P("4.2.1　公司脸", "h3"))
    out.append(
        P(
            "3080 控制台是人对系统的唯一日常入口。它负责收集平常话与文件、画出已钉线路、"
            "出示上机许可单、展示短回执与实验纪要。它不负责选型，不负责调用科学核，"
            "也不保存密钥明文回显。设置里只接人本机大模型与机器账户。聊天回包必须去掉会话编号、"
            "已用工具列表和算法目录编号。对人说话要短，公式按行内与独立行渲染，不必改成特殊符号。"
        )
    )
    out.append(
        P(
            "界面理念是一张作业纸，不是三房间工作台，也不是文件管理器。"
            "左侧导航退出主路径；右侧「本任务」在有许可或新回执时打开。"
            "金色只用于许可与批准，避免把装饰色当成已经上机。"
        )
    )

    out.append(P("4.2.2　Agent Harness", "h3"))
    out.append(
        P(
            "dsh 作为 Agent Harness，主要负责：维护用户会话及任务上下文；解析自然语言意图；"
            "根据当前预设选择允许调用的工具；生成符合约束的工具调用参数；解释工具返回结果；"
            "在信息不足时向人请求补充或确认。写算法时，官方 Codex 以子代理进入同一棵树，"
            "不另开一条黄金路径。"
        )
    )
    out.append(P("Agent Harness 不应直接承担以下职责："))
    out.append(
        bullets(
            [
                "用户审核状态的持久化。",
                "真机任务的幂等提交与签收句柄签发。",
                "费用扣减或资源预留。",
                "超时、重试和补偿事务的最终判定。",
                "工具权限、凭据与科学包进程的管理。",
                "工作流状态的最终判定。",
            ]
        )
    )
    out.append(
        P(
            "这些确定性要求较高的功能应由作业编排层和网关负责，避免把关键业务控制完全交给大模型。"
            "现网已经用「聊天只转 dsh，不走自研循环」把这条界线写进测试。"
        )
    )

    out.append(P("4.2.3　工作流编排层", "h3"))
    out.append(
        P(
            "编排层是业务控制的核心。现网没有另购一套工作流引擎，而是用交办记录、线路作业状态机、"
            "本任务摄入记忆来落地。可以使用更重的引擎，也可以继续用基于文件的轻量编排器。"
            "无论采用哪种方式，工作流状态都不应只保存在 Agent 上下文中。"
        )
    )
    out.append(P("编排层负责："))
    out.append(
        bullets(
            [
                "定义固定的任务执行阶段。线路作业为：解析、校验、估计、询问、执行、回执。",
                "控制节点之间的流转条件。未估计不得询问；未批准不得签收。",
                "保存每个阶段的输入和输出，以及本任务最近一次读懂的配置。",
                "管理人审核、拒绝和重新配置。批准必须落在同一条会话上，不得重开黄金路径。",
                "管理任务暂停、恢复、取消和超时。",
                "对可重试异常执行有限次数重试；对不可恢复异常进入明确的失败状态。",
                "聚合中间结果并生成最终输出：对人是短结论，对机器是回执与实验纪要。",
            ]
        )
    )
    out.append(
        P(
            "新对话清空本页与本任务记忆，并归档旧会话记录。它不是「再写一个 Agent」，"
            "只是切断这一页对旧句柄的隐式引用。"
        )
    )

    out.append(P("4.2.4　统一网关", "h3"))
    out.append(
        P(
            "所有工具和算法均注册为 Agent 可以调用的工具，并统一通过网关调用。"
            "现网网关是 decide 加 invoke：先政策，后端口。插件只转调 invoke，不自己访问科学核。"
            "每个预设只应获得当前阶段所需的工具集合，不应一次性向 Agent 暴露全部工具。"
        )
    )
    out.append(
        table(
            ["网关能力", "现网落点"],
            [
                ["工具注册", "合同目录列出名称、槽位与输入输出图式。"],
                ["权限控制", "政策规则按预设与参数决定允许、询问或拒绝。无匹配则拒绝。"],
                ["参数校验", "端口与图式拒绝非法参数；未知配方直接拒绝。"],
                ["请求路由", "端口登记把工具名映射到适配器方法。同一估计工具可换后端。"],
                ["凭据管理", "密钥只进被忽略的本地文件。Agent 只验证非空，不读值。"],
                ["资源控制", "超阈值采样量转为询问。南向改机与通用出网默认拒绝。"],
                ["可靠性治理", "空槽位与 CLI 缺失诚实报错。不本地伪造签收。"],
                ["安全审计", "用量只记工具与状态。实验记录记摘要，不记正文。"],
                ["结果标准化", "后验检查句柄、来源与泄漏键。短输出，禁止私货字段。"],
            ],
            [42 * mm, 126 * mm],
        )
    )
    out.append(Spacer(1, 3 * mm))
    out.append(
        P(
            "四个预设把同一张网关切成不同可见集：开机只对齐；实验室可计算与估计；"
            "写算法挂子代理；签收台只处理身份、签收与对照。开机产物里不得出现孪生工具。"
        )
    )

    out.append(P("4.2.5　算法目录", "h3"))
    out.append(
        P(
            "算法目录是只读的公司软件与算法卡片。它回答「有分子走化学计算，已有哈密顿量走离子阱算法包」，"
            "并且拒绝把两条轨道合成一个编号。目录可以列出、说明、选型、校验、把外来文件转成公司信封。"
            "目录从不运行，从不签发签收句柄。直播目录可由外部索引替换，缺省用仓内卡片。"
        )
    )
    out.append(
        P(
            "这是对初稿「配置执行后端」的公司化：后端不是一张用户自填的云表格，"
            "而是公司已经接线的引擎包与已经公布的作业卡。人不必报内部编号；模型也不许把编号念出脸。"
        )
    )

    out.append(P("4.2.6　引擎端口", "h3"))
    out.append(
        P(
            "科学能力以引擎包为一等公民。工具挂在包上。加开源包只登记，不新写 Agent。"
            "适配器只做包装，不把科学核 import 进聊天进程。"
        )
    )
    out.append(
        table(
            ["包", "职责", "留下什么", "硬边界"],
            [
                ["量子数据", "配方、资产、对照门", "资产句柄与对照字段", "禁止随意临时目录；未知配方拒绝"],
                ["量子化学", "分子与场景计算", "资产句柄，必要时线路句柄", "电路必须先钉住才能上机"],
                ["离子阱栈", "估计与孪生签收", "唯有此处可签发签收句柄", "未批准不得跑；失败不伪造"],
                ["线路调度", "同一估计工具换后端", "时间估计", "不换工具名，不换图式"],
                ["外部互通", "线路进出与对照模拟", "线路句柄与来源标记", "对照不得冒充签收"],
            ],
            [28 * mm, 42 * mm, 48 * mm, 50 * mm],
        )
    )

    out.append(P("4.2.7　证据、回执与实验记录", "h3"))
    out.append(
        P(
            "对人，结果是短结论加可选线路图。对机器，结果是交办回执与只读实验纪要。"
            "回执可下载、可独立核验。未签收不盖印，不伪造句柄。实验记录按时间落下，不在脸上改结论。"
            "治理灯只报告机器侧是否齐，灯亮不是许可。"
        )
    )

    out.append(P("5　与初稿的对照", "h1"))
    out.append(
        table(
            ["初稿主张", "Qagent 现网", "独立判断"],
            [
                [
                    "DSH / pi-agent 作 Harness",
                    "dsh 公司 profile。对话只转 session。",
                    "采纳。禁止再写第三套循环。",
                ],
                [
                    "独立工作流编排",
                    "交办记录加线路六阶段，状态落盘。",
                    "采纳其原则。不必另购引擎才能开工。",
                ],
                [
                    "统一网关",
                    "decide 加 invoke，插件只转调。",
                    "采纳。这就是网关，不要再包一层同名服务。",
                ],
                [
                    "上传线路 → 估价 → 人确认 → 执行",
                    "已实现，且扩展为三种输入归一。",
                    "初稿是子集。外来文件必须先转到公司流程。",
                ],
                [
                    "对外只回一个结构化结果",
                    "人话短结论、线路图、短回执。内部编号不出脸。",
                    "采纳。结构化在回执，不在把内部 JSON 摊给人看。",
                ],
                [
                    "节点只暴露当前工具集",
                    "四个预设加隐藏集。开机无孪生工具。",
                    "采纳。可见集是产品，不是调试开关。",
                ],
                [
                    "未写算法目录与引擎包",
                    "目录与五包加互通包已经是扩展单位。",
                    "必须补上。否则每个软件组都会再造 Agent。",
                ],
                [
                    "未写三条句柄",
                    "线路、资产、签收。签发权只在离子阱端口。",
                    "必须补上。否则对照模拟会冒充签收。",
                ],
            ],
            [48 * mm, 60 * mm, 60 * mm],
        )
    )

    out.append(P("6　约束与明确不做", "h1"))
    out.append(
        bullets(
            [
                "不另写 Harness，不把聊天改回自研循环。",
                "不把算法目录编号当成第四条句柄，不在聊天回包里回显。",
                "不把两条变分轨道合成一个编号。有分子走化学计算，已有哈密顿量走算法包。",
                "不在源码树里导入科学包。不把测控、穿梭、南向改机暴露成工具。",
                "对照模拟不得写签收句柄，不得佩戴孪生来源标记。",
                "未过对照合同不得写「量子胜出」。",
                "生产不挂危险绕过、通用出网、未授权的云真机入口。",
                "不加三房间、文件管理器式工作区壳。脸是作业纸。",
                "不把槽位号当成故障原因。灯亮不等于已经可上机。",
            ]
        )
    )

    out.append(P("7　现状与边界", "h1"))
    out.append(
        P(
            "截至本次复审，Qagent 已具备：公司脸与设置、dsh 会话、政策网关、算法目录与外来文件转写、"
            "线路作业六阶段、五类已接线引擎与 Cirq 互通、询问后的孪生签收、回执核验、实验记录、"
            "评测与合同围栏。Pennylane 与云真机入口仍是占位。知识库与部分组算法按包接入，尚未当作新 Agent。"
        )
    )
    out.append(
        P(
            "本文件是对现网的独立分析，用来统一组内对「我们在造什么」的理解。"
            "它不替代合同、橙皮书与评测。合同仍是真源。若实现与本文冲突，以合同和评测字段为准，并回头改本文。"
        )
    )
    out.append(Spacer(1, 6 * mm))
    out.append(HRFlowable(width="100%", thickness=0.4, color=LINE, spaceBefore=4, spaceAfter=10))
    out.append(
        P(
            "完。对照原稿：《处理量子线路问题的 Agent-计划初稿》。本文写的是整份 Qagent，而不是再写一条只处理线路图的平行方案。",
            "meta",
        )
    )
    return out


def _write(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    target = dest
    try:
        target.write_bytes(b"")
    except OSError:
        target = dest.with_name(f"{dest.stem}-图{dest.suffix}")
    doc = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title="Qagent 设计架构与理念",
        author="合肥市幺正量子科技有限公司",
        subject="对照《处理量子线路问题的 Agent-计划初稿》的独立分析",
    )
    doc.build(story(), onFirstPage=on_page, onLaterPages=on_page)
    return target


def main() -> None:
    for dest in (OUT_COPY, OUT_PRIMARY):
        print(_write(dest))


if __name__ == "__main__":
    main()
