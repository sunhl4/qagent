"""Declarative chart artifacts for the WPS-suite porting (P3).

WPS-SUITE-PORTING §4.9: ``render_chart`` takes one declarative spec and
renders a deterministic standalone SVG (same spec in, same bytes out) next
to the canonical spec JSON under ``artifacts/charts/<chart_id>.{json,svg}``,
so a reviewer re-checks the semantic spec instead of pixels. ``chart_id``
is the first 16 hex of the canonical spec digest. Standard library only:
no chart engines, no CDN fonts, no network; a fixed palette and fixed
frame, CJK-aware clipped labels; the result budget is honored because the
artifacts live in the workspace instead of the tool text.
"""
from __future__ import annotations

import hashlib
import json
import math

from company_agent import office_create as _oc
from company_agent import office_purpose, workspace_files

MAX_CATEGORIES = 64
MAX_SERIES = 8
MAX_VALUES = 64
MAX_SVG_BYTES = 800_000
_PALETTE = (
    "#2f6feb", "#d63384", "#198754", "#fd7e14",
    "#6f42c1", "#0dcaf0", "#b02a37", "#6c757d",
)
_SVG_W, _SVG_H = 760, 460
_MARGIN_L, _MARGIN_R, _MARGIN_T, _MARGIN_B = 64, 28, 70, 96


class OfficeChartError(ValueError):
    """Refusal that names the boundary hit without echoing paths outside the root."""


def chart(args: dict) -> dict:
    """Contract entry point: deterministic chart artifact generation."""

    purpose = office_purpose.take(args)
    root = workspace_files.root()
    compound = _compound(args)
    workspace_files._lexical(compound)
    spec = args.get("spec")
    if not isinstance(spec, dict):
        raise OfficeChartError("spec 必须是对象")
    canonical = json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    chart_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    kind, title, categories, series, extra = _validate(spec)

    svg = _render(kind, title, categories, series, extra)
    if len(svg) > MAX_SVG_BYTES:
        raise OfficeChartError(f"生成的 SVG 超过 {MAX_SVG_BYTES} 字节上限:请压缩数据规模")

    json_rel = f"artifacts/charts/{chart_id}.json"
    svg_rel = f"artifacts/charts/{chart_id}.svg"
    overwrite = args.get("overwrite", False)
    if not isinstance(overwrite, bool):
        raise OfficeChartError("overwrite 必须是布尔值")
    canonical_bytes = (canonical + "\n").encode("utf-8")
    existed_json = _write_one(root, compound, json_rel, canonical_bytes, overwrite)
    existed_svg = _write_one(root, compound, svg_rel, svg, overwrite)
    if existed_json != existed_svg:
        # 同一 chart_id 的 json/svg 只作为一对存在;半存在是脏数据,拒绝掩盖。
        raise OfficeChartError("同名图表一对文件状态不一致:请清理后以 overwrite=true 重建")
    fence = f"```lm-chart\n{canonical}\n```"
    if len(fence) > 20_000:
        raise OfficeChartError("图表规格围栏超过 20000 字符上限")
    office_purpose.audit("office_chart", purpose, {"chart_id": chart_id, "path": f"{compound}/{json_rel}"})
    return {
        "chart_id": chart_id,
        "json_path": f"{compound}/{json_rel}",
        "svg_path": f"{compound}/{svg_rel}",
        "bytes_json": len(canonical_bytes),
        "bytes_svg": len(svg),
        "sha256_json": hashlib.sha256(canonical_bytes).hexdigest(),
        "sha256_svg": hashlib.sha256(svg).hexdigest(),
        "overwrote": existed_json,
        "fence": fence,
    }


def _validate(spec: dict):
    kind = spec.get("type")
    if kind not in ("bar", "line", "stacked_bar", "pie"):
        raise OfficeChartError("type 只支持 bar / line / stacked_bar / pie")
    title = spec.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 200 or any(ord(c) < 32 for c in title):
        raise OfficeChartError("title 必须是 1..200 字符且不含控制字符")
    labels = spec.get("categories")
    if not isinstance(labels, list) or not labels or len(labels) > MAX_CATEGORIES:
        raise OfficeChartError(f"categories 必须是 1..{MAX_CATEGORIES} 个的数组")
    categories = []
    for label in labels:
        if not isinstance(label, str) or len(label) > 60 or any(ord(c) < 32 for c in label):
            raise OfficeChartError("categories 条目必须是 <=60 字符且不含控制字符")
        categories.append(label)
    rows = spec.get("series")
    if not isinstance(rows, list) or not rows or len(rows) > MAX_SERIES:
        raise OfficeChartError(f"series 必须是 1..{MAX_SERIES} 个的数组")
    if kind == "pie" and len(rows) > 1:
        raise OfficeChartError("pie 只支持单个 series")
    series = []
    for row in rows:
        if not isinstance(row, dict):
            raise OfficeChartError("每个 series 必须是对象")
        name = row.get("name")
        values = row.get("values")
        if not isinstance(name, str) or not name.strip() or len(name) > 60:
            raise OfficeChartError("series.name 必须是 1..60 字符")
        if not isinstance(values, list) or not values or len(values) > MAX_VALUES:
            raise OfficeChartError(f"series.values 必须是 1..{MAX_VALUES} 的数组")
        if len(values) != len(categories):
            raise OfficeChartError("series.values 与 categories 长度不一致:拒绝渲染")
        numbers = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise OfficeChartError("series.values 只接受有限的数")
            numbers.append(float(value))
        if kind == "pie" and any(value < 0 for value in numbers):
            raise OfficeChartError("pie 的占比必须非负")
        series.append((name, numbers))
    extra = {}
    for key, limit in (("unit", 32), ("source", 200), ("notes", 400)):
        raw = spec.get(key)
        if raw is None:
            continue
        if not isinstance(raw, str) or len(raw) > limit or any(ord(c) < 32 for c in raw):
            raise OfficeChartError(f"spec.{key} 必须是 <= {limit} 字符且不含控制字符")
        extra[key] = raw
    return kind, title, categories, series, extra


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _width(text: str) -> int:
    return sum(2 if ord(c) > 0x2E7F else 1 for c in text)


def _clip(text: str, limit: int) -> str:
    if _width(text) <= limit:
        return text
    while text and _width(text) > limit - 2:
        text = text[:-1]
    return text + "…"


def _fmt(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.4g}"


def _y_of(value: float, top: float, bottom: float, high: float, low: float) -> float:
    span = (high - low) or 1.0
    ratio = (value - low) / span
    return bottom - (bottom - top) * ratio


def _render(
    kind: str,
    title: str,
    categories: list[str],
    series: list[tuple[str, list[float]]],
    extra: dict[str, str],
) -> bytes:
    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_SVG_W}" height="{_SVG_H}"'
        ' viewBox="0 0 760 460" font-family="sans-serif" font-size="12">'
    )
    parts.append(
        f'<text x="{_MARGIN_L}" y="26" font-size="18" font-weight="600">{_esc(_clip(title, 56))}</text>'
    )
    baseline = 48
    if extra.get("unit"):
        parts.append(
            f'<text x="{_MARGIN_L}" y="{baseline}" fill="#444">{_esc(_clip(extra["unit"], 24))}</text>'
        )
        baseline += 16
    plot_top, plot_left, plot_right = baseline + 12, _MARGIN_L, _SVG_W - _MARGIN_R
    plot_bottom = _SVG_H - _MARGIN_B
    if kind in ("bar", "stacked_bar", "line"):
        if kind == "stacked_bar":
            highs = [sum(values[i] for _n, values in series) for i in range(len(categories))]
            lows = [0.0] * len(categories)
        else:
            highs = [max(values[i] for _n, values in series) for i in range(len(categories))]
            lows = [min(0.0, min(values[i] for _n, values in series)) for i in range(len(categories))]
        high, low = max(highs), min(lows)
        if high == low:
            high += 1.0
        for tick in range(5):
            value = high - (high - low) * tick / 4
            gy = plot_top + (plot_bottom - plot_top) * tick / 4
            parts.append(
                f'<line x1="{plot_left}" y1="{gy:.1f}" x2="{plot_right}" y2="{gy:.1f}" stroke="#e5e7eb"/>'
                f'<text x="{plot_left - 6}" y="{gy + 4:.1f}" text-anchor="end" fill="#666" font-size="10">'
                f'{_fmt(value)}</text>'
            )
        slot = (plot_right - plot_left) / len(categories)
    if kind == "bar":
        group = slot / (len(series) + 1)
        for s_idx, (_name, values) in enumerate(series):
            color = _PALETTE[s_idx % len(_PALETTE)]
            for c_idx, value in enumerate(values):
                x = plot_left + slot * c_idx + group * (s_idx + 1)
                top = _y_of(value, plot_top, plot_bottom, high, low)
                zero = _y_of(0.0, plot_top, plot_bottom, high, low)
                parts.append(
                    f'<rect x="{x:.1f}" y="{min(top, zero):.1f}" '
                    f'width="{max(group - 3, 1):.1f}" height="{max(abs(zero - top), 1):.1f}" '
                    f'fill="{color}"/>'
                )
    elif kind == "stacked_bar":
        for c_idx in range(len(categories)):
            accumulator = 0.0
            for s_idx, (_name, values) in enumerate(series):
                value = values[c_idx]
                y_low = _y_of(accumulator, plot_top, plot_bottom, high, low)
                y_high = _y_of(accumulator + value, plot_top, plot_bottom, high, low)
                parts.append(
                    f'<rect x="{plot_left + slot * c_idx + 8:.1f}" y="{y_high:.1f}" '
                    f'width="{max(slot - 16, 1):.1f}" height="{max(y_low - y_high, 0.5):.1f}" '
                    f'fill="{_PALETTE[s_idx % len(_PALETTE)]}"/>'
                )
                accumulator += value
    elif kind == "line":
        for s_idx, (_name, values) in enumerate(series):
            color = _PALETTE[s_idx % len(_PALETTE)]
            points = " ".join(
                "{:.1f},{:.1f}".format(
                    plot_left + slot * c_idx + slot / 2,
                    _y_of(value, plot_top, plot_bottom, high, low),
                )
                for c_idx, value in enumerate(values)
            )
            parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{points}"/>')
            for c_idx, value in enumerate(values):
                marker_x = plot_left + slot * c_idx + slot / 2
                marker_y = _y_of(value, plot_top, plot_bottom, high, low)
                parts.append(
                    f'<circle cx="{marker_x:.1f}" cy="{marker_y:.1f}" r="2.5" fill="{color}"/>'
                )
    elif kind == "pie":
        totals = series[0][1]
        biggest = sum(totals)
        cx = _SVG_W / 2
        cy = (plot_top + plot_bottom) / 2 + 8
        radius = min(plot_right - plot_left, plot_bottom - plot_top) / 3
        sweep_start = -math.pi / 2
        for c_idx, value in enumerate(totals):
            sweep = (value / (biggest or 1.0)) * 2 * math.pi
            sweep_end = sweep_start + sweep
            large = 1 if sweep > math.pi else 0
            x0 = cx + radius * math.cos(sweep_start)
            y0 = cy + radius * math.sin(sweep_start)
            x1 = cx + radius * math.cos(sweep_end)
            y1 = cy + radius * math.sin(sweep_end)
            parts.append(
                f'<path d="M {cx:.1f} {cy:.1f} L {x0:.1f} {y0:.1f} '
                f'A {radius:.1f} {radius:.1f} 0 {large} 1 {x1:.1f} {y1:.1f} Z" '
                f'fill="{_PALETTE[c_idx % len(_PALETTE)]}" stroke="#ffffff" stroke-width="1"/>'
            )
            sweep_start = sweep_end
    legend: list[tuple[str, str]] = (
        [(categories[idx], _PALETTE[idx % len(_PALETTE)]) for idx in range(len(categories))]
        if kind == "pie"
        else [(name, _PALETTE[idx % len(_PALETTE)]) for idx, (name, _values) in enumerate(series)]
    )
    for c_idx, label in enumerate(categories):
        if kind == "pie":
            cx, cy = _SVG_W / 2, (plot_top + plot_bottom) / 2 + 8
            radius = min(plot_right - plot_left, plot_bottom - plot_top) / 3
            step = 2 * math.pi / len(categories)
            mid = -math.pi / 2 + step * (c_idx + 0.5)
            parts.append(
                f'<text x="{cx + (radius + 20) * math.cos(mid):.1f}" '
                f'y="{cy + (radius + 20) * math.sin(mid):.1f}" text-anchor="middle" '
                f'font-size="10" fill="#333">{_esc(_clip(label, 14))}</text>'
            )
        else:
            x = plot_left + slot * c_idx + slot / 2
            parts.append(
                f'<text x="{x:.1f}" y="{plot_bottom + 16}" text-anchor="middle" font-size="10" fill="#333">'
                f'{_esc(_clip(label, 14))}</text>'
            )
    cursor = _MARGIN_L
    legend_y = _SVG_H - 24
    for name, color in legend:
        parts.append(
            f'<rect x="{cursor}" y="{legend_y - 9}" width="9" height="9" fill="{color}"/>'
            f'<text x="{cursor + 14}" y="{legend_y}" font-size="10" fill="#333">'
            f'{_esc(_clip(name, 26))}</text>'
        )
        cursor += 14 + _width(_clip(name, 26)) * 6.2 + 24
        if cursor > _SVG_W - 120:
            break
    parts.append('</svg>')
    return "".join(parts).encode("utf-8")


def _compound(args: dict) -> str:
    project = args.get("project")
    if not isinstance(project, str) or not project.strip() or project != project.strip():
        raise OfficeChartError("project is invalid")
    if len(project.encode("utf-8")) > workspace_files.MAX_PATH_BYTES:
        raise OfficeChartError("project exceeds the workspace path bound")
    return project


def _write_one(root, compound: str, relative: str, data: bytes, overwrite: bool) -> bool:
    """Write one artifact file inside the project behind the P0 fences."""

    existed, target = _oc._resolve_target(root, f"{compound}/{relative}", overwrite)
    _oc._write_atomic(target, data, existed)
    _oc._verify_written(target, data)
    return existed
