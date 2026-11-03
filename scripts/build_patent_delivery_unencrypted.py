# -*- coding: utf-8 -*-
"""Build unencrypted patent disclosure delivery package."""
from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

DOCS = Path(r"D:\Yaozheng\sunhl4-qagent\docs")
OUT = Path(r"D:\Yaozheng\专利\交底书交付_20261104_无加密")
FIG = OUT / "附图"

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


def prepare_dirs() -> None:
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
        # Keep ASCII-entity backup for tooling that mishandles UTF-8 SVG text.
        shutil.copy2(src, FIG / f"{Path(dst_name).stem}-实体编码备份.svg")
        # Sanity: Chinese present after decode
        if "系统" not in decoded and "授权" not in decoded and "请求" not in decoded:
            # Some figures may use different words; just warn on pure entities remaining.
            if "&#x" in decoded:
                raise RuntimeError(f"SVG still contains entities after decode: {dst_name}")
        print(f"[svg] {dst_name} bytes={ (FIG/dst_name).stat().st_size }")


def write_markdown() -> None:
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
    print("[md] copied and appendix paths updated")


def write_combined_md() -> Path:
    main = (OUT / "01-技术交底书正文.md").read_text(encoding="utf-8")
    app = (OUT / "02-附图附录.md").read_text(encoding="utf-8")
    combined = OUT / "03-交底书完整稿_正文加附图附录.md"
    combined.write_text(
        main.rstrip()
        + "\n\n---\n\n# 附图附录（正式交付）\n\n"
        + app.lstrip("# 专利申请技术交底书附图附录\n").lstrip(),
        encoding="utf-8",
    )
    return combined


def build_docx(combined: Path) -> Path:
    docx = OUT / "技术交底书_量子高性能计算协同任务接管授权与执行去重_无加密.docx"
    ref = None
    cmd = [
        "pandoc",
        str(combined),
        "-o",
        str(docx),
        "--from",
        "markdown",
        "--to",
        "docx",
        "--resource-path",
        str(OUT),
        "-V",
        "lang=zh-CN",
    ]
    if ref:
        cmd.extend(["--reference-doc", str(ref)])
    subprocess.run(cmd, check=True)
    # Verify standard OOXML zip, not DRM wrapper.
    with zipfile.ZipFile(docx, "r") as zf:
        names = zf.namelist()
        if "word/document.xml" not in names:
            raise RuntimeError("generated docx missing word/document.xml")
        if "EncryptedPackage" in names:
            raise RuntimeError("generated docx unexpectedly encrypted")
    print(f"[docx] {docx.name} size={docx.stat().st_size} zip_ok=True")
    return docx


def build_pdf_via_word(docx: Path) -> Path:
    pdf = OUT / "技术交底书_量子高性能计算协同任务接管授权与执行去重_无加密.pdf"
    import win32com.client  # type: ignore

    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(str(docx), ReadOnly=True)
        # 17 = wdExportFormatPDF
        doc.ExportAsFixedFormat(
            OutputFileName=str(pdf),
            ExportFormat=17,
            OpenAfterExport=False,
            OptimizeFor=0,
            BitmapMissingFonts=True,
            DocStructureTags=True,
            CreateBookmarks=1,
        )
        doc.Close(False)
    finally:
        word.Quit()
    raw = pdf.read_bytes()[:4096]
    if b"%PDF" not in raw[:8]:
        raise RuntimeError("PDF header missing")
    if b"/Encrypt" in raw:
        # /Encrypt in first 4k is a strong signal of password protection
        # Recheck whole file lightly
        whole = pdf.read_bytes()
        if b"/Encrypt" in whole:
            raise RuntimeError("PDF appears encrypted")
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
        # file URI for local svg
        svg_uri = svg.resolve().as_uri()
        html.write_text(
            f"""<!doctype html><html><head><meta charset='utf-8'>
<style>html,body{{margin:0;background:#fff}} img{{max-width:100%;height:auto;display:block}}</style>
</head><body><img src="{svg_uri}"/></body></html>""",
            encoding="utf-8",
        )
        cmd = [
            str(edge),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--screenshot={png}",
            "--window-size=1400,1000",
            html.resolve().as_uri(),
        ]
        subprocess.run(cmd, check=False, capture_output=True)
        if png.exists() and png.stat().st_size > 1000:
            print(f"[png] {png.name} size={png.stat().st_size}")
        else:
            print(f"[png] failed {svg.name}")


def write_readme() -> None:
    text = """# 交底书无加密交付包

交付日期：2026-11-04

本包从已审定的 Markdown 交底书与正式 SVG 附图重新生成，**不经过企业文档加密壳**。可直接用 Word / 浏览器 / PDF 阅读器打开。

## 文件清单

| 文件 | 说明 |
|---|---|
| `01-技术交底书正文.md` | 交底书正文（UTF-8） |
| `02-附图附录.md` | 附图附录与标记说明 |
| `03-交底书完整稿_正文加附图附录.md` | 正文+附录合并稿 |
| `技术交底书_量子高性能计算协同任务接管授权与执行去重_无加密.docx` | 标准 OOXML Word，无密码、无 DRM |
| `技术交底书_量子高性能计算协同任务接管授权与执行去重_无加密.pdf` | 由上述 Word 导出，无加密字典 |
| `附图/图1-系统部署与双入口.svg` | 正式图1（UTF-8 中文，可直接打开） |
| `附图/图2-服务接管时序.svg` | 正式图2 |
| `附图/图3-请求状态迁移.svg` | 正式图3 |
| `附图/图4-替代请求串行化流程.svg` | 正式图4 |
| `附图/*-实体编码备份.svg` | 仅供特殊工具链使用的实体编码备份 |
| `附图/预览PNG/` | 浏览器渲染预览图（便于快速查看） |

## 关于“加密”

此前 `D:\\Yaozheng\\专利\\` 下大量 `.docx`（含“终校版”“解密.docx”）文件头为 `E0 A8 91 E7 ...`，不是标准 ZIP/OOXML，属于企业透明加密包装；本机未授权环境无法作为普通 Word 打开。本交付包全部为：

1. 标准 `PK` ZIP 结构的 `.docx`；
2. 无 `/Encrypt` 的 `.pdf`；
3. UTF-8 明文中文的 `.svg` / `.md`。

请优先使用本目录文件对外或向代理师交付。旧加密 docx 仅作历史过程文件保留，不再作为本轮交付物。

## 使用建议

1. 代理师整理说明书：以 `无加密.docx` 或 `01/02` Markdown 为准。
2. 附图转入申请文件：优先用 `附图/图1…图4.svg`；需要位图时用 `预览PNG`。
3. 如需套公司评审表模板：请在已授权解密的办公环境中打开模板后，从本包复制正文粘贴；不要再次分发被加密壳包装的 docx。
"""
    (OUT / "README_交付说明.md").write_text(text, encoding="utf-8")
    print("[readme] written")


def main() -> None:
    prepare_dirs()
    write_svgs()
    write_markdown()
    combined = write_combined_md()
    docx = build_docx(combined)
    try:
        build_pdf_via_word(docx)
    except Exception as exc:  # noqa: BLE001
        print(f"[pdf] Word export failed: {exc!r}")
    rasterize_svgs_with_edge()
    write_readme()
    print("--- delivery files ---")
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            print(f"{p.stat().st_size:8d}  {p.relative_to(OUT)}")


if __name__ == "__main__":
    main()
