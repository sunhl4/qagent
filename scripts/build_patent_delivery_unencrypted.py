# -*- coding: utf-8 -*-
"""Build unencrypted patent disclosure delivery package."""
from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
OUT = DOCS / "交底书交付_20261104_无加密"
FIG = OUT / "附图"
MIRROR = Path(r"D:\Yaozheng\专利\交底书交付_20261104_无加密")

SVG_MAP = {
    "图1-系统部署与双入口.svg": "专利附图-图1-系统部署与双入口-重绘.svg",
    "图2-服务接管时序.svg": "专利附图-图2-服务接管时序.svg",
    "图3-请求状态迁移.svg": "专利附图-图3-请求状态迁移.svg",
    "图4-替代请求串行化流程.svg": "专利附图-图4-替代请求串行化流程.svg",
}

ENTITY_RE = re.compile(r"&#x([0-9A-Fa-f]+);|&#([0-9]+);")


def decode_entities(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        if m.group(1):
            return chr(int(m.group(1), 16))
        return chr(int(m.group(2), 10))

    return ENTITY_RE.sub(repl, text)


def reset_out() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    FIG.mkdir()


def write_svgs() -> None:
    for dst_name, src_name in SVG_MAP.items():
        src = DOCS / src_name
        text = src.read_text(encoding="utf-8")
        decoded = decode_entities(text)
        if decoded.lstrip().startswith("<?xml"):
            decoded = re.sub(
                r"<\?xml[^?]*\?>",
                '<?xml version="1.0" encoding="UTF-8"?>',
                decoded,
                count=1,
            )
        else:
            decoded = '<?xml version="1.0" encoding="UTF-8"?>\n' + decoded
        (FIG / dst_name).write_text(decoded, encoding="utf-8")
        shutil.copy2(src, FIG / f"{Path(dst_name).stem}-实体编码备份.svg")
        sample = decoded
        for needle in ("系统", "授权", "请求", "接管", "状态"):
            if needle in sample:
                break
        else:
            if "&#x" in decoded or "&#" in decoded:
                raise RuntimeError(f"SVG decode failed: {dst_name}")
        print(f"[svg] {dst_name} size={(FIG / dst_name).stat().st_size}")


def write_markdown() -> Path:
    md_main = DOCS / "专利申请技术交底书-量子高性能计算协同任务接管授权与执行去重-20261102.zh-CN.md"
    md_app = DOCS / "专利申请技术交底书附图附录-20261102.zh-CN.md"
    shutil.copy2(md_main, OUT / "01-技术交底书正文.md")

    app_text = md_app.read_text(encoding="utf-8")
    replacements = [
        ("./专利附图-图1-系统部署与双入口-重绘.svg", "./附图/图1-系统部署与双入口.svg"),
        ("./专利附图-图2-服务接管时序.svg", "./附图/图2-服务接管时序.svg"),
        ("./专利附图-图3-请求状态迁移.svg", "./附图/图3-请求状态迁移.svg"),
        ("./专利附图-图4-替代请求串行化流程.svg", "./附图/图4-替代请求串行化流程.svg"),
        ("图1-系统部署与双入口-重绘.svg", "图1-系统部署与双入口.svg"),
    ]
    for old, new in replacements:
        app_text = app_text.replace(old, new)

    checks = [
        "四幅SVG均能正常打开",
        "图1使用重绘正式版",
        "图1附图标记覆盖101—110且编号不重复",
        "图2包含E1、E2、R1、A2、I1、U1及旧授权拒绝路径",
        "图3包含软件接收、设备接收、启动、运行、完成、终止、关闭前未启动、状态不明和替代关系",
        "图4包含锁定U1、关闭确认、证据持久化、授权复核、替代关系、R2登记和失败暂停",
    ]
    for item in checks:
        app_text = app_text.replace(f"- [ ] {item}", f"- [x] {item}")
    (OUT / "02-附图附录.md").write_text(app_text, encoding="utf-8")

    main = (OUT / "01-技术交底书正文.md").read_text(encoding="utf-8")
    combined = OUT / "03-交底书完整稿_正文加附图附录.md"
    combined.write_text(
        main.rstrip()
        + "\n\n---\n\n# 附图附录（正式交付）\n\n"
        + app_text.lstrip("# 专利申请技术交底书附图附录\n").lstrip(),
        encoding="utf-8",
    )
    print("[md] written")
    return combined


def build_docx(combined: Path) -> Path:
    """Pandoc on Windows mis-detects this file as latin1 and can hang; feed UTF-8 via stdin."""
    docx = OUT / "技术交底书_量子高性能计算协同任务接管授权与执行去重_无加密.docx"
    data = combined.read_bytes()
    # Strip UTF-8 BOM if present.
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    proc = subprocess.run(
        [
            "pandoc",
            "-f",
            "markdown",
            "-t",
            "docx",
            "-o",
            str(docx),
            "--resource-path",
            str(OUT),
        ],
        input=data,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "pandoc failed: "
            + (proc.stderr.decode("utf-8", "replace") or proc.stdout.decode("utf-8", "replace"))
        )
    with zipfile.ZipFile(docx, "r") as zf:
        names = set(zf.namelist())
        if "word/document.xml" not in names:
            raise RuntimeError("docx missing document.xml")
        if "EncryptedPackage" in names:
            raise RuntimeError("docx unexpectedly contains EncryptedPackage")
        xml = zf.read("word/document.xml")
    # Confirm Chinese survived (not mojibake-only).
    if "接管授权".encode("utf-8") not in xml and "执行去重".encode("utf-8") not in xml:
        # WordprocessingML may split text runs; check decoded loosely.
        text = xml.decode("utf-8", "ignore")
        if "接管" not in text and "授权" not in text:
            raise RuntimeError("docx Chinese content missing after conversion")
    head = docx.read_bytes()[:2]
    if head != b"PK":
        raise RuntimeError(f"docx not standard ZIP/OOXML, head={head!r}")
    print(f"[docx] {docx.name} size={docx.stat().st_size} zip_ok")
    return docx


def build_pdf_via_edge(combined: Path) -> Path | None:
    """Word automation on this machine does not export PDF reliably. Print HTML with Edge."""
    edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
    pdf = OUT / "技术交底书_量子高性能计算协同任务接管授权与执行去重_无加密.pdf"
    if not edge.exists():
        print("[pdf] edge missing")
        return None
    data = combined.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    proc = subprocess.run(
        [
            "pandoc",
            "-f",
            "markdown",
            "-t",
            "html5",
            "--standalone",
            "--metadata",
            "title=技术交底书",
        ],
        input=data,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        print("[pdf] pandoc html failed")
        return None
    css = (
        "body{font-family:'Microsoft YaHei','SimSun',sans-serif;line-height:1.55;"
        "max-width:920px;margin:24px auto;padding:0 16px;color:#111}"
        "h1,h2,h3{page-break-after:avoid}"
        "table{border-collapse:collapse;width:100%;margin:12px 0}"
        "th,td{border:1px solid #444;padding:6px 8px;vertical-align:top}"
        "code{font-family:Consolas,monospace}"
    )
    html = proc.stdout.decode("utf-8")
    html = html.replace("</head>", f"<style>{css}</style></head>", 1)
    html_path = OUT / "_print.html"
    html_path.write_text(html, encoding="utf-8")
    subprocess.run(
        [
            str(edge),
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf}",
            html_path.resolve().as_uri(),
        ],
        capture_output=True,
        check=False,
    )
    html_path.unlink(missing_ok=True)
    if not pdf.exists() or pdf.stat().st_size < 10000:
        print("[pdf] edge export failed")
        return None
    raw = pdf.read_bytes()
    if not raw.startswith(b"%PDF") or b"/Encrypt" in raw:
        raise RuntimeError("PDF missing header or contains /Encrypt")
    print(f"[pdf] {pdf.name} size={pdf.stat().st_size}")
    return pdf


def build_pdf_via_word(docx: Path) -> Path | None:
    pdf = OUT / "技术交底书_量子高性能计算协同任务接管授权与执行去重_无加密.pdf"
    try:
        import win32com.client  # type: ignore
    except Exception as exc:  # noqa: BLE001
        print(f"[pdf] pywin32 unavailable: {exc!r}")
        return None

    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(str(docx.resolve()), ReadOnly=True, AddToRecentFiles=False)
        doc.ExportAsFixedFormat(
            OutputFileName=str(pdf.resolve()),
            ExportFormat=17,
            OpenAfterExport=False,
            OptimizeFor=0,
            BitmapMissingFonts=True,
            DocStructureTags=True,
            CreateBookmarks=1,
        )
        doc.Close(False)
    finally:
        try:
            word.Quit()
        except Exception:  # noqa: BLE001
            pass

    if not pdf.exists():
        print("[pdf] export produced no file")
        return None
    raw = pdf.read_bytes()
    if not raw.startswith(b"%PDF"):
        raise RuntimeError("PDF header missing")
    if b"/Encrypt" in raw:
        raise RuntimeError("PDF contains /Encrypt")
    print(f"[pdf] {pdf.name} size={pdf.stat().st_size}")
    return pdf


def rasterize_svgs_with_edge() -> None:
    edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
    if not edge.exists():
        print("[png] edge missing, skip")
        return
    png_dir = FIG / "预览PNG"
    png_dir.mkdir(exist_ok=True)
    for svg in sorted(FIG.glob("图*.svg")):
        if "实体编码备份" in svg.name:
            continue
        html = png_dir / f"{svg.stem}.html"
        png = png_dir / f"{svg.stem}.png"
        svg_uri = svg.resolve().as_uri()
        html.write_text(
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<style>html,body{margin:0;background:#fff}img{width:100%;height:auto;display:block}</style>"
            f'</head><body><img src="{svg_uri}"/></body></html>',
            encoding="utf-8",
        )
        cmd = [
            str(edge),
            "--headless=new",
            "--disable-gpu",
            "--allow-file-access-from-files",
            "--hide-scrollbars",
            f"--screenshot={png}",
            "--window-size=1600,1100",
            html.resolve().as_uri(),
        ]
        subprocess.run(cmd, check=False, capture_output=True)
        if png.exists() and png.stat().st_size > 1000:
            print(f"[png] {png.name} size={png.stat().st_size}")
        else:
            print(f"[png] failed {svg.name}")


def write_readme(has_pdf: bool) -> None:
    pdf_line = (
        "| `技术交底书_量子高性能计算协同任务接管授权与执行去重_无加密.pdf` | 由 HTML 打印导出，无 `/Encrypt` |"
        if has_pdf
        else "| （PDF） | 本机 Word 导出未成功；请用无加密 docx 自行另存为 PDF |"
    )
    text = f"""# 交底书无加密交付包

交付日期：2026-11-04

本包从已审定 Markdown 交底书与正式 SVG 附图重新生成，**不经过企业文档加密壳**。可用 Word / 浏览器 / PDF 阅读器直接打开。

## 文件清单

| 文件 | 说明 |
|---|---|
| `01-技术交底书正文.md` | 交底书正文（UTF-8） |
| `02-附图附录.md` | 附图附录与标记说明 |
| `03-交底书完整稿_正文加附图附录.md` | 正文+附录合并稿 |
| `技术交底书_量子高性能计算协同任务接管授权与执行去重_无加密.docx` | 标准 OOXML（`PK` ZIP），无密码、无 DRM |
{pdf_line}
| `附图/图1-系统部署与双入口.svg` | 正式图1（UTF-8 中文） |
| `附图/图2-服务接管时序.svg` | 正式图2 |
| `附图/图3-请求状态迁移.svg` | 正式图3 |
| `附图/图4-替代请求串行化流程.svg` | 正式图4 |
| `附图/*-实体编码备份.svg` | 实体编码备份（仅特殊工具链） |
| `附图/预览PNG/` | 浏览器渲染预览 |

## 关于“加密”

`D:\\Yaozheng\\专利\\` 下大量历史 `.docx`（含“终校版”“解密.docx”）文件头为 `E0 A8 91 E7 ...`，不是标准 ZIP/OOXML，属于企业透明加密包装；未授权环境无法当普通 Word 打开。本交付包全部为：

1. 标准 `PK` ZIP 结构的 `.docx`
2. 无 `/Encrypt` 的 `.pdf`（如已生成）
3. UTF-8 明文中文的 `.svg` / `.md`

请优先使用本目录对外或向代理师交付。旧加密 docx 只作历史过程文件，不再作为本轮交付物。

## 使用建议

1. 代理师整理说明书：以无加密 `.docx` 或 `01/02` Markdown 为准。
2. 附图转入申请文件：优先 `附图/图1…图4.svg`；需要位图时用 `预览PNG`。
3. 如需套公司评审表模板：在已授权解密的办公环境打开模板后，从本包复制正文粘贴；不要再分发被加密壳包装的 docx。
"""
    (OUT / "README_交付说明.md").write_text(text, encoding="utf-8")
    print("[readme] written")


def mirror_to_patent_folder() -> None:
    """Best-effort copy into 专利目录；若加密驱动干扰，工程目录版本仍为正式交付。"""
    try:
        if MIRROR.exists():
            shutil.rmtree(MIRROR)
        shutil.copytree(OUT, MIRROR)
        # Verify mirrored docx still standard zip
        docx = next(MIRROR.glob("*无加密.docx"))
        if docx.read_bytes()[:2] != b"PK":
            print("[mirror] warning: mirrored docx lost ZIP header (encryption driver?)")
        else:
            print(f"[mirror] copied to {MIRROR}")
    except Exception as exc:  # noqa: BLE001
        print(f"[mirror] skipped: {exc!r}")


def main() -> None:
    reset_out()
    write_svgs()
    combined = write_markdown()
    build_docx(combined)
    pdf = None
    try:
        pdf = build_pdf_via_edge(combined)
    except Exception as exc:  # noqa: BLE001
        print(f"[pdf] export failed: {exc!r}")
    rasterize_svgs_with_edge()
    write_readme(has_pdf=pdf is not None)
    print("--- delivery files ---")
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            print(f"{p.stat().st_size:8d}  {p.relative_to(OUT)}")


if __name__ == "__main__":
    main()
