# -*- coding: utf-8 -*-
"""Apply review fixes to formal patent SVGs. Chinese is written as XML entities."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

DOCS = Path(r"D:\Yaozheng\sunhl4-qagent\docs")


def enc(text: str) -> str:
    out: list[str] = []
    for ch in text:
        o = ord(ch)
        if 32 <= o < 127 and ch not in "<>&\"'":
            out.append(ch)
        else:
            out.append(f"&#x{o:X};")
    return "".join(out)


def must_replace(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 0:
        raise SystemExit(f"missing snippet in {label}: {old[:80]}")
    return text.replace(old, new)


def patch_fig2(text: str) -> str:
    old = enc("旧服务以E1提交R1并等待设备侧回执")
    new = enc("仅当R1已到达110：以E1提交并等待回执")
    text = must_replace(text, old, new, "fig2")
    old_note = enc("旧服务持有E1，提交R1；随后故障、进程退出或回执丢失，R1设备事实暂不可见。")
    new_note = enc("故障也可发生在到达设备之前。到110的箭头仅在R1已经提交到设备时成立。")
    text = must_replace(text, old_note, new_note, "fig2-note")
    text = text.replace(
        ".green{stroke:#3c7d55;stroke-width:2.2;fill:none;marker-end:url(#arrow-green)}",
        ".green{stroke:#3c7d55;stroke-width:2.2;stroke-dasharray:8 5;fill:none;marker-end:url(#arrow-green)}",
        1,
    )
    return text


def patch_fig3(text: str) -> str:
    pairs = [
        (
            "Software facts and device facts are separated; STARTED is irreversible and UNKNOWN cannot trigger replacement",
            "软件事实与设备事实分开；已启动不可回退；状态不明不能进入替代",
        ),
        ("NORMAL EXECUTION CHAIN", "正常执行链"),
        ("software record only", "仅有软件记录"),
        ("received, not started", "已接收，尚未启动"),
        ("authoritative device fact", "设备侧权威事实"),
        ("continue tracking", "继续跟踪"),
        (">device receive<", ">设备接收<"),
        (">start evidence<", ">启动证据<"),
        (">running<", ">运行中<"),
        ("keep start evidence", "保留启动记录"),
        (">completed<", ">已完成<"),
        ("fault after start", "启动后故障"),
        ("cannot start later", "以后不能再启动"),
        (
            "device confirms closed and not restartable",
            "设备确认已关闭且不能再启动",
        ),
        ("RECOVERY BRANCH", "恢复分支"),
        ("pause; never auto-replace", "暂停，不自动替代"),
        ("R1-R2 exists; R2 blocked", "关系已写入，R2暂不提交"),
        ("Recovery decision", "恢复判定"),
        ("RECOVERY_DECISION", "仅S7可进入替代"),
        ("only S7 may enter", "仅关闭前未启动"),
        ("query failure or conflict", "查询失败或来源冲突"),
        (">only S7<", ">仅S7<"),
        ("serialize U1, then register R2", "锁定U1后再登记R2"),
        (
            "SOFTWARE_ACCEPTED is not DEVICE_ACCEPTED; DEVICE_ACCEPTED is not STARTED; STARTED cannot revert; UNKNOWN cannot become not-started.",
            "软件已接收不等于设备已接收；设备已接收不等于已启动；已启动不能回退；状态不明不能改成未启动。",
        ),
        (
            "Only CLOSED_BEFORE_START with device evidence that restart is impossible may enter replacement.",
            "未登记不进入设备路径。只有关闭前未启动，且设备确认以后不能再启动，才进入替代。",
        ),
    ]
    for old, new in pairs:
        text = must_replace(text, old, enc(new), "fig3")
    text = text.replace("&#x72C4;&#x5219;", enc("规则"), 1)
    text = text.replace(
        ".gr{fill:none;stroke:#3c7d55;stroke-width:2.3;marker-end:url(#g)}",
        ".gr{fill:none;stroke:#3c7d55;stroke-width:2.3;stroke-dasharray:10 4;marker-end:url(#g)}",
        1,
    )
    return text


def patch_fig4(text: str) -> str:
    pairs = [
        (
            "U1 is the serialization boundary; R2 is admitted only after R1 is closed and not restartable",
            "U1是串行化边界；R1确认关闭且以后不能启动之后才接收R2",
        ),
        (
            "Recheck authorization and approval before each persistent write. An uncertain R2 submission never creates R3.",
            "每次持久化写入前复核授权和批准。R2结果不确定时不生成R3。",
        ),
        ("mutex, lease, or equivalent serialization", "互斥、租约或等效串行化"),
        ("original state, current authorization, approval", "原状态、当前授权和批准"),
        ("use R1 as device query and close key", "以R1原编号关闭或取消"),
        ("R1 not started and not restartable", "未启动且以后不能再启动"),
        ("authorization and approval must still match", "授权和批准必须仍然匹配"),
        (">recheck passed<", ">复核通过<"),
        ("R1 history retained; R2 keeps I1 and U1", "保留R1历史；R2仍用I1和U1"),
        ("persist software acceptance, then release control", "先登记软件接收，再释放控制"),
        (
            "The following failures do not overwrite R1 and do not create R3.",
            "下列失败不覆盖R1，也不生成R3。",
        ),
        ("Lock or lease failure", "未取得锁或租约"),
        ("U1 has no current serialization right", "没有当前串行化资格"),
        ("Close result unknown", "关闭结果不明"),
        ("no not-restartable evidence", "没有不可再启动的证据"),
        ("E2 or A2 changed", "E2或A2已变化"),
        ("current authorization no longer matches", "当前授权或批准已不匹配"),
        ("Relation or R2 write fails", "关系已写、R2未登记"),
        ("partial new state is not accepted", "保留待登记，不生成R3"),
        (">U1 = PAUSED<", ">U1暂停<"),
        (
            "retain R1, failure reason, recovery entry",
            "保留R1。关系未写成则不登记R2",
        ),
        ("After R2 registration", "R2登记之后"),
        ("R2 still passes through quantum ingress", "R2仍须经过量子入口"),
        ("and current E/A checks.", "并检查当前授权和批准。"),
        ("Uncertain result: query R2, no R3.", "结果不确定时查询R2，不生成R3。"),
        (
            "R1 and R2 share I1 and U1. R2 references R1 close evidence and replacement reason; R1 is never deleted.",
            "R1与R2同属I1和U1。R2引用R1的关闭证据和替代原因；R1不删除。",
        ),
        (
            "A timeout or a lock expiry proves neither device closure nor non-start.",
            "通信超时或锁超时既不能证明设备已关闭，也不能证明请求未启动。",
        ),
    ]
    for old, new in pairs:
        text = must_replace(text, old, enc(new), "fig4")
    text = text.replace(
        ".gr{fill:none;stroke:#3c7d55;stroke-width:2.3;marker-end:url(#g)}",
        ".gr{fill:none;stroke:#3c7d55;stroke-width:2.3;stroke-dasharray:10 4;marker-end:url(#g)}",
        1,
    )
    return text


def preview(svg: Path, png_name: str) -> None:
    edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
    work = DOCS / "_fig_preview"
    work.mkdir(exist_ok=True)
    # Decode entities so the screenshot shows Chinese glyphs.
    raw = svg.read_text(encoding="utf-8")
    decoded = re.sub(
        r"&#x([0-9A-Fa-f]+);",
        lambda m: chr(int(m.group(1), 16)),
        raw,
    )
    shown = work / svg.name
    if not decoded.lstrip().startswith("<?xml"):
        decoded = '<?xml version="1.0" encoding="UTF-8"?>\n' + decoded
    shown.write_text(decoded, encoding="utf-8")
    html = work / f"{svg.stem}.html"
    png = work / png_name
    html.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;background:#fff}img{width:100%;height:auto;display:block}</style>"
        f"</head><body><img src=\"{shown.resolve().as_uri()}\"/></body></html>",
        encoding="utf-8",
    )
    subprocess.run(
        [
            str(edge),
            "--headless=new",
            "--disable-gpu",
            "--allow-file-access-from-files",
            "--hide-scrollbars",
            f"--screenshot={png}",
            "--window-size=1500,1000",
            html.resolve().as_uri(),
        ],
        capture_output=True,
        check=False,
    )
    print(png.name, png.stat().st_size if png.exists() else "missing")


def main() -> None:
    fig2 = DOCS / "专利附图-图2-服务接管时序.svg"
    fig3 = DOCS / "专利附图-图3-请求状态迁移.svg"
    fig4 = DOCS / "专利附图-图4-替代请求串行化流程.svg"
    fig2.write_text(patch_fig2(fig2.read_text(encoding="utf-8")), encoding="ascii")
    fig3.write_text(patch_fig3(fig3.read_text(encoding="utf-8")), encoding="ascii")
    fig4.write_text(patch_fig4(fig4.read_text(encoding="utf-8")), encoding="ascii")
    for path in (fig2, fig3, fig4):
        path.read_text(encoding="ascii")
        print("ascii-ok", path.name, path.stat().st_size)
    preview(fig2, "fig2.png")
    preview(fig3, "fig3.png")
    preview(fig4, "fig4.png")


if __name__ == "__main__":
    main()
