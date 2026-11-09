# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import subprocess
from pathlib import Path


def enc(s: str) -> str:
    out: list[str] = []
    for ch in s:
        o = ord(ch)
        if 32 <= o < 127 and ch not in "<>&\"'":
            out.append(ch)
        else:
            out.append(f"&#x{o:X};")
    return "".join(out)


ENTITY_RE = re.compile(r"&#x([0-9A-Fa-f]+);|&#([0-9]+);")


def decode(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        if m.group(1):
            return chr(int(m.group(1), 16))
        return chr(int(m.group(2), 10))

    return ENTITY_RE.sub(repl, text)


def main() -> None:
    parts: list[str] = []
    a = parts.append
    a(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="1120" '
        'viewBox="0 0 1800 1120" role="img" aria-labelledby="title desc">'
    )
    a(f'  <title id="title">{enc("图2 服务接管时序")}</title>')
    a(
        f'  <desc id="desc">{enc("旧服务以E1处理R1后故障；新服务恢复后持久化E2，双入口确认并形成A2；用R1原编号查询设备；迟到E1在入口被拒绝。")}</desc>'
    )
    a(
        """  <defs>
    <marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L12,6 L0,12 z" fill="#243746"/></marker>
    <marker id="arrow-blue" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L12,6 L0,12 z" fill="#2f6f9f"/></marker>
    <marker id="arrow-green" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L12,6 L0,12 z" fill="#3c7d55"/></marker>
    <marker id="arrow-red" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L12,6 L0,12 z" fill="#a63d40"/></marker>
    <style>
      .title{font-family:"Microsoft YaHei","Noto Sans CJK SC",SimSun,Arial,sans-serif;font-size:30px;font-weight:600;fill:#1f2933;letter-spacing:1px}
      .subtitle{font-family:"Microsoft YaHei","Noto Sans CJK SC",SimSun,Arial,sans-serif;font-size:16px;fill:#52606d}
      .head{fill:#f3f7f9;stroke:#435563;stroke-width:1.8}
      .head-old{fill:#f8f5ee;stroke:#8b7957;stroke-width:1.8}
      .head-new{fill:#f2f7fb;stroke:#2f6f9f;stroke-width:1.8}
      .head-device{fill:#f3f8f5;stroke:#3c7d55;stroke-width:1.8}
      .head-title{font-family:"Microsoft YaHei","Noto Sans CJK SC",SimSun,Arial,sans-serif;font-size:16px;font-weight:600;fill:#1f2933}
      .head-sub{font-family:"Microsoft YaHei","Noto Sans CJK SC",SimSun,Arial,sans-serif;font-size:13px;fill:#52606d}
      .life{stroke:#b7c1c8;stroke-width:1.6;stroke-dasharray:7 8}
      .axis{stroke:#d9e0e5;stroke-width:1.4}
      .flow{stroke:#243746;stroke-width:2.2;fill:none;marker-end:url(#arrow)}
      .blue{stroke:#2f6f9f;stroke-width:2.2;fill:none;marker-end:url(#arrow-blue)}
      .green{stroke:#3c7d55;stroke-width:2.2;fill:none;marker-end:url(#arrow-green)}
      .red{stroke:#a63d40;stroke-width:2.2;stroke-dasharray:9 6;fill:none;marker-end:url(#arrow-red)}
      .event{font-family:"Microsoft YaHei","Noto Sans CJK SC",SimSun,Arial,sans-serif;font-size:14px;fill:#263746}
      .event-blue{font-family:"Microsoft YaHei","Noto Sans CJK SC",SimSun,Arial,sans-serif;font-size:14px;fill:#2f6f9f}
      .event-green{font-family:"Microsoft YaHei","Noto Sans CJK SC",SimSun,Arial,sans-serif;font-size:14px;fill:#3c7d55}
      .event-red{font-family:"Microsoft YaHei","Noto Sans CJK SC",SimSun,Arial,sans-serif;font-size:14px;fill:#a63d40}
      .row-no{font-family:Arial,sans-serif;font-size:13px;font-weight:700;fill:#52606d}
      .old-note{fill:#fffaf0;stroke:#d4c190;stroke-width:1.5}
      .new-note{fill:#f3f8fc;stroke:#9fc0d4;stroke-width:1.5}
      .device-note{fill:#f3f8f5;stroke:#a8c8b2;stroke-width:1.5}
      .stop-note{fill:#fff5f4;stroke:#d39a9d;stroke-width:1.5}
      .note-title{font-family:"Microsoft YaHei","Noto Sans CJK SC",SimSun,Arial,sans-serif;font-size:15px;font-weight:600;fill:#374957}
      .note-text{font-family:"Microsoft YaHei","Noto Sans CJK SC",SimSun,Arial,sans-serif;font-size:13px;fill:#52606d}
      .legend{font-family:"Microsoft YaHei","Noto Sans CJK SC",SimSun,Arial,sans-serif;font-size:13px;fill:#52606d}
    </style>
  </defs>
  <rect width="1800" height="1120" fill="#ffffff"/>"""
    )

    a(f'  <text x="900" y="48" text-anchor="middle" class="title">{enc("图2  服务接管时序")}</text>')
    a(
        f'  <text x="900" y="78" text-anchor="middle" class="subtitle">{enc("旧授权故障 → 新授权围栏 → 双入口确认 → 设备事实查询 → 旧消息拒绝")}</text>'
    )

    heads = [
        (55, "head-old", "旧服务", "E1 / R1"),
        (285, "head-new", "新服务", "接管实例"),
        (515, "head-new", "接管授权102", "E1 → E2"),
        (745, "head-new", "经典入口104", "HPC确认"),
        (975, "head-new", "量子入口105", "QPU确认"),
        (1205, "head", "执行历史106", "I1 / U1 / R1"),
        (1435, "head-device", "量子设备110", "R1状态查询"),
    ]
    a("  <!-- participant headers -->")
    for x, cls, title, sub in heads:
        a(f'  <g transform="translate({x} 115)">')
        a(f'    <rect width="175" height="74" rx="8" class="{cls}"/>')
        a(f'    <text x="87.5" y="31" text-anchor="middle" class="head-title">{enc(title)}</text>')
        a(f'    <text x="87.5" y="54" text-anchor="middle" class="head-sub">{enc(sub)}</text>')
        a("  </g>")

    a(
        """  <!-- lifelines -->
  <line x1="142.5" y1="189" x2="142.5" y2="930" class="life"/>
  <line x1="372.5" y1="189" x2="372.5" y2="930" class="life"/>
  <line x1="602.5" y1="189" x2="602.5" y2="930" class="life"/>
  <line x1="832.5" y1="189" x2="832.5" y2="930" class="life"/>
  <line x1="1062.5" y1="189" x2="1062.5" y2="930" class="life"/>
  <line x1="1292.5" y1="189" x2="1292.5" y2="930" class="life"/>
  <line x1="1522.5" y1="189" x2="1522.5" y2="930" class="life"/>

  <!-- phase strips -->
  <rect x="55" y="212" width="1560" height="166" rx="8" class="old-note"/>"""
    )
    a(f'  <text x="75" y="238" class="note-title">{enc("阶段一：旧授权下的提交与故障")}</text>')
    a(
        f'  <text x="75" y="260" class="note-text">{enc("旧服务持有E1，提交R1；随后故障、进程退出或回执丢失，R1设备事实暂不可见。")}</text>'
    )
    a('  <rect x="55" y="398" width="1560" height="304" rx="8" class="new-note"/>')
    a(f'  <text x="75" y="424" class="note-title">{enc("阶段二：新服务接管并形成E2/A2")}</text>')
    a(
        f'  <text x="75" y="446" class="note-text">{enc("恢复I1、U1、R1及历史；持久化高于E1的E2；104与105分别确认后写入共同批准A2。")}</text>'
    )
    a('  <rect x="55" y="722" width="1560" height="208" rx="8" class="device-note"/>')
    a(f'  <text x="75" y="748" class="note-title">{enc("阶段三：设备事实查询与旧授权阻断")}</text>')
    a(
        f'  <text x="75" y="770" class="note-text">{enc("以R1原编号查询设备；迟到的E1消息在105被拒绝，但R1历史不删除。")}</text>'
    )

    a("  <!-- event rows -->")
    a('  <line x1="55" y1="285" x2="1615" y2="285" class="axis"/><text x="66" y="280" class="row-no">1</text>')
    a('  <path d="M142.5 302 H1522.5" class="flow"/>')
    a(f'  <text x="832.5" y="297" text-anchor="middle" class="event">{enc("旧服务以E1提交R1并等待设备侧回执")}</text>')

    a('  <line x1="55" y1="335" x2="1615" y2="335" class="axis"/><text x="66" y="330" class="row-no">2</text>')
    a('  <path d="M142.5 352 C240 352 260 352 330 352" class="red"/>')
    a(f'  <text x="242" y="347" text-anchor="middle" class="event-red">{enc("故障 / 退出 / 回执丢失")}</text>')

    a('  <line x1="55" y1="468" x2="1615" y2="468" class="axis"/><text x="66" y="463" class="row-no">3</text>')
    a('  <path d="M372.5 485 H1292.5" class="blue"/>')
    a(f'  <text x="832.5" y="480" text-anchor="middle" class="event-blue">{enc("新服务恢复I1、U1、R1及历史")}</text>')

    a('  <line x1="55" y1="522" x2="1615" y2="522" class="axis"/><text x="66" y="517" class="row-no">4</text>')
    a('  <path d="M372.5 539 H602.5" class="blue"/>')
    a(f'  <text x="487.5" y="534" text-anchor="middle" class="event-blue">{enc("请求生成高于E1的授权")}</text>')
    a('  <rect x="510" y="550" width="185" height="34" rx="6" fill="#ffffff" stroke="#9fc0d4" stroke-width="1.5"/>')
    a(f'  <text x="602.5" y="572" text-anchor="middle" class="event-blue">{enc("持久化E2")}</text>')

    a('  <line x1="55" y1="612" x2="1615" y2="612" class="axis"/><text x="66" y="607" class="row-no">5</text>')
    a('  <path d="M602.5 629 H832.5" class="blue"/>')
    a(f'  <text x="717.5" y="624" text-anchor="middle" class="event-blue">{enc("104确认E2")}</text>')
    a('  <path d="M602.5 665 H1062.5" class="blue"/>')
    a(f'  <text x="832.5" y="660" text-anchor="middle" class="event-blue">{enc("105确认E2")}</text>')
    a(f'  <text x="1080" y="700" class="event-blue">{enc("两侧确认后写入103")}</text>')

    a('  <line x1="55" y1="802" x2="1615" y2="802" class="axis"/><text x="66" y="797" class="row-no">6</text>')
    a('  <path d="M1062.5 819 H1292.5" class="green"/>')
    a(f'  <text x="1177.5" y="814" text-anchor="middle" class="event-green">{enc("复核后形成A2")}</text>')
    a('  <path d="M1292.5 855 H1522.5" class="green"/>')
    a(f'  <text x="1407.5" y="850" text-anchor="middle" class="event-green">{enc("以R1原编号查询")}</text>')
    a('  <path d="M1522.5 891 H1292.5" class="green"/>')
    a(f'  <text x="1407.5" y="886" text-anchor="middle" class="event-green">{enc("返回设备侧状态事实")}</text>')

    a('  <line x1="55" y1="950" x2="1615" y2="950" class="axis"/><text x="66" y="945" class="row-no">7</text>')
    a('  <path d="M142.5 970 H1062.5" class="red"/>')
    a(
        f'  <text x="602.5" y="965" text-anchor="middle" class="event-red">{enc("迟到E1消息到达105，因授权不匹配被拒绝")}</text>'
    )
    a('  <rect x="1120" y="946" width="420" height="54" rx="7" class="stop-note"/>')
    a(f'  <text x="1140" y="969" class="note-title">{enc("拒绝但不删除历史")}</text>')
    a(f'  <text x="1140" y="989" class="note-text">{enc("R1原记录、状态来源与时间均保留")}</text>')

    a("  <!-- decision note -->")
    a('  <rect x="55" y="1018" width="1560" height="55" rx="8" fill="#fffdf7" stroke="#d8c27a" stroke-width="1.5"/>')
    a(f'  <text x="76" y="1041" class="note-title">{enc("后续判定")}</text>')
    a(
        f'  <text x="190" y="1041" class="note-text">{enc("按设备事实分别进入：已完成则返回原结果；运行中则继续跟踪；未启动且可关闭则进入替代判断；状态不明则暂停自动重发。")}</text>'
    )
    a(
        f'  <text x="190" y="1062" class="note-text">{enc("符号：E1/E2=授权序号；I1=稳定执行身份；U1=执行单元；R1=原设备请求；A2=新共同执行批准。")}</text>'
    )

    a('  <g transform="translate(58 1094)">')
    a(f'    <line x1="0" y1="0" x2="34" y2="0" class="flow"/><text x="46" y="5" class="legend">{enc("旧授权提交")}</text>')
    a(f'    <line x1="156" y1="0" x2="190" y2="0" class="blue"/><text x="202" y="5" class="legend">{enc("新服务接管")}</text>')
    a(
        f'    <line x1="326" y1="0" x2="360" y2="0" class="green"/><text x="372" y="5" class="legend">{enc("设备事实查询")}</text>'
    )
    a(f'    <line x1="528" y1="0" x2="562" y2="0" class="red"/><text x="574" y="5" class="legend">{enc("拒绝/故障")}</text>')
    a("  </g>")
    a("</svg>")

    svg = "\n".join(parts) + "\n"
    svg.encode("ascii")  # must stay ASCII-safe

    src = Path(__file__).resolve().parents[1] / "docs" / "专利附图-图2-服务接管时序.svg"
    src.write_text(svg, encoding="ascii")
    print("wrote source", src.stat().st_size)

    decoded = '<?xml version="1.0" encoding="UTF-8"?>\n' + decode(svg)
    deliv = Path(r"D:\Yaozheng\sunhl4-qagent\docs\交底书交付_20261104_无加密\附图")
    (deliv / "图2-服务接管时序.svg").write_text(decoded, encoding="utf-8")
    (deliv / "图2-服务接管时序-实体编码备份.svg").write_text(svg, encoding="ascii")
    print("delivery ok", "接管" in decoded, "服务" in decoded)

    edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
    html = deliv / "预览PNG" / "图2-服务接管时序.html"
    png = deliv / "预览PNG" / "图2-服务接管时序.png"
    svg_uri = (deliv / "图2-服务接管时序.svg").resolve().as_uri()
    html.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;background:#fff}img{width:100%;height:auto;display:block}</style>"
        f'</head><body><img src="{svg_uri}"/></body></html>',
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
            "--window-size=1600,1100",
            html.resolve().as_uri(),
        ],
        capture_output=True,
        check=False,
    )
    print("png", png.exists(), png.stat().st_size if png.exists() else None)


if __name__ == "__main__":
    main()
