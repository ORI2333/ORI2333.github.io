"""把 Obsidian Excalidraw 插件的绘图文件转换为独立 SVG。

背景：博客文章里的 ![[xxx.excalidraw]] 是 Obsidian 专有嵌入语法，Hexo 不解析；
且插件默认不开启自动导出，绘图文件里只有 LZString 压缩的场景 JSON，没有现成
PNG/SVG。本模块用纯 Python（零第三方依赖）完成：

1. 从 .excalidraw.md 中提取场景 JSON（compressed-json / json 代码块 / 裸 JSON）；
2. 解压 LZString base64（与插件所用 lz-string 1.x 算法一致）；
3. 把常见元素（freedraw/line/arrow/rectangle/ellipse/diamond/text/image）
   渲染为干净的 SVG（不模拟手绘抖动，技术图表观感更好）。

限制：不还原 roughness 手绘风格；hachure/cross-hatch 填充近似为半透明纯色；
文字排版为近似定位。若插件开启了自动导出（存在同名 .svg/.png），调用方应
优先使用官方导出文件，保真度更高。
"""

from __future__ import annotations

import json
import re
from xml.sax.saxutils import escape

__all__ = ["extract_scene", "render_scene_svg", "excalidraw_text_to_svg"]

_BASE64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
_BASE64_VALUES = {ch: i for i, ch in enumerate(_BASE64_ALPHABET)}


def _lzstring_decompress_base64(compressed: str) -> str:
    """移植 lz-string decompressFromBase64（resetValue=32，6bit/字符）。"""
    length = len(compressed)
    if length == 0:
        return ""

    state = {"val": _BASE64_VALUES[compressed[0]], "position": 32, "index": 1}

    def read_bits(num_bits: int) -> int:
        bits = 0
        power = 1
        max_power = 1 << num_bits
        while power != max_power:
            resb = state["val"] & state["position"]
            state["position"] >>= 1
            if state["position"] == 0:
                state["position"] = 32
                ch = compressed[state["index"]] if state["index"] < length else ""
                state["val"] = _BASE64_VALUES.get(ch, 0)
                state["index"] += 1
            bits |= (1 if resb > 0 else 0) * power
            power <<= 1
        return bits

    dictionary: dict[int, str] = {0: "", 1: "", 2: ""}
    enlarge_in = 4
    dict_size = 4
    num_bits = 3

    first = read_bits(2)
    if first == 0:
        c = chr(read_bits(8))
    elif first == 1:
        c = chr(read_bits(16))
    elif first == 2:
        return ""
    else:
        raise ValueError("Invalid LZString data")
    dictionary[3] = c
    w = c
    result = [c]

    while True:
        if state["index"] > length:
            return ""
        code = read_bits(num_bits)
        if code == 0:
            dictionary[dict_size] = chr(read_bits(8))
            dict_size += 1
            code = dict_size - 1
            enlarge_in -= 1
        elif code == 1:
            dictionary[dict_size] = chr(read_bits(16))
            dict_size += 1
            code = dict_size - 1
            enlarge_in -= 1
        elif code == 2:
            return "".join(result)

        if enlarge_in == 0:
            enlarge_in = 1 << num_bits
            num_bits += 1

        if code in dictionary and code >= 3:
            entry = dictionary[code]
        elif code == dict_size:
            entry = w + w[0]
        else:
            raise ValueError("Invalid LZString stream")
        result.append(entry)
        dictionary[dict_size] = w + entry[0]
        dict_size += 1
        enlarge_in -= 1
        w = entry

        if enlarge_in == 0:
            enlarge_in = 1 << num_bits
            num_bits += 1


def extract_scene(text: str) -> dict:
    """从 .excalidraw.md（或裸 .excalidraw JSON）中提取场景 dict。"""
    match = re.search(r"```compressed-json\s*\n(.*?)```", text, re.S)
    if match:
        raw = re.sub(r"\s+", "", match.group(1))
        decompressed = _lzstring_decompress_base64(raw)
        if not decompressed:
            raise ValueError("LZString 解压失败")
        return json.loads(decompressed)
    match = re.search(r"```json\s*\n(.*?)```", text, re.S)
    if match:
        return json.loads(match.group(1))
    stripped = text.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    raise ValueError("未识别的 Excalidraw 文件格式")


_FONT_FAMILIES = {
    1: "'Segoe Print','Bradley Hand','Comic Sans MS',cursive",
    2: "'Helvetica Neue',Arial,'PingFang SC','Microsoft YaHei',sans-serif",
    3: "'Cascadia Code',Consolas,'Courier New',monospace",
    5: "'Segoe Print','Excalifont',cursive",
    6: "'Segoe Print','Excalifont',cursive",
    7: "'Helvetica Neue',Arial,'PingFang SC','Microsoft YaHei',sans-serif",
    8: "'Cascadia Code',Consolas,'Courier New',monospace",
}


def _fmt(value: float) -> str:
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return str(rounded)


def _normalize_box(x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
    if w < 0:
        x, w = x + w, -w
    if h < 0:
        y, h = y + h, -h
    return x, y, w, h


def _stroke_attrs(el: dict) -> str:
    stroke = el.get("strokeColor") or "#1e1e1e"
    width = el.get("strokeWidth", 2)
    style = el.get("strokeStyle", "solid")
    attrs = [f'stroke="{stroke}"', f'stroke-width="{_fmt(width)}"']
    if style == "dashed":
        attrs.append(f'stroke-dasharray="{_fmt(width * 4)} {_fmt(width * 3)}"')
    elif style == "dotted":
        attrs.append(f'stroke-dasharray="{_fmt(width)} {_fmt(width * 2)}"')
    return " ".join(attrs)


def _fill_attrs(el: dict) -> str:
    bg = el.get("backgroundColor")
    if not bg or bg == "transparent":
        return 'fill="none"'
    fill_style = el.get("fillStyle", "solid")
    if fill_style == "solid":
        return f'fill="{bg}"'
    # hachure / cross-hatch 近似为半透明纯色
    return f'fill="{bg}" fill-opacity="0.4"'


def _points_path(el: dict) -> str:
    x0 = float(el.get("x", 0))
    y0 = float(el.get("y", 0))
    points = el.get("points") or [[0, 0]]
    coords = [(x0 + float(p[0]), y0 + float(p[1])) for p in points]
    parts = [f"M {_fmt(coords[0][0])} {_fmt(coords[0][1])}"]
    for cx, cy in coords[1:]:
        parts.append(f"L {_fmt(cx)} {_fmt(cy)}")
    return " ".join(parts)


def _arrow_head(coords: list[tuple[float, float]], size: float) -> str:
    """末端箭头：取最后两个不重合点确定方向，画两条短线。"""
    if len(coords) < 2:
        return ""
    (px, py), (qx, qy) = coords[-2], coords[-1]
    if px == qx and py == qy:
        return ""
    import math

    angle = math.atan2(qy - py, qx - px)
    spread = math.radians(25)
    x1 = qx - size * math.cos(angle - spread)
    y1 = qy - size * math.sin(angle - spread)
    x2 = qx - size * math.cos(angle + spread)
    y2 = qy - size * math.sin(angle + spread)
    return (
        f'<path d="M {_fmt(x1)} {_fmt(y1)} L {_fmt(qx)} {_fmt(qy)} L {_fmt(x2)} {_fmt(y2)}" '
        f'fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    )


def _element_bounds(el: dict) -> tuple[float, float, float, float]:
    x0 = float(el.get("x", 0))
    y0 = float(el.get("y", 0))
    points = el.get("points")
    if points:
        xs = [x0 + float(p[0]) for p in points]
        ys = [y0 + float(p[1]) for p in points]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    w = abs(float(el.get("width", 0)))
    h = abs(float(el.get("height", 0)))
    x, y = min(x0, x0 + float(el.get("width", 0))), min(y0, y0 + float(el.get("height", 0)))
    return x, y, w, h


def _render_element(el: dict, files: dict) -> str:
    kind = el.get("type")
    if kind == "selection":
        return ""
    opacity = float(el.get("opacity", 100)) / 100.0
    parts: list[str] = []

    angle = float(el.get("angle", 0))
    open_g, close_g = "", ""
    if angle:
        import math

        bx, by, bw, bh = _element_bounds(el)
        cx, cy = bx + bw / 2, by + bh / 2
        deg = math.degrees(angle)
        open_g = f'<g transform="rotate({_fmt(deg)} {_fmt(cx)} {_fmt(cy)})">'
        close_g = "</g>"
    if opacity < 1:
        open_g += f'<g opacity="{_fmt(opacity)}">'
        close_g = "</g>" + close_g

    if kind in ("freedraw", "line"):
        x0 = float(el.get("x", 0))
        y0 = float(el.get("y", 0))
        points = el.get("points") or [[0, 0]]
        coords = [(x0 + float(p[0]), y0 + float(p[1])) for p in points]
        parts.append(
            f'<path d="{_points_path(el)}" fill="none" {_stroke_attrs(el)} '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
        )
        if kind == "line" and el.get("startArrowhead"):
            head = _arrow_head(list(reversed(coords)), 10 + 2 * float(el.get("strokeWidth", 2)))
            if head:
                parts.append(head.replace("<path ", f'<path {_stroke_attrs(el)} ', 1))
    elif kind == "arrow":
        x0 = float(el.get("x", 0))
        y0 = float(el.get("y", 0))
        points = el.get("points") or [[0, 0]]
        coords = [(x0 + float(p[0]), y0 + float(p[1])) for p in points]
        parts.append(
            f'<path d="{_points_path(el)}" fill="none" {_stroke_attrs(el)} '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
        )
        size = 10 + 2 * float(el.get("strokeWidth", 2))
        if el.get("endArrowhead", "arrow") == "arrow":
            head = _arrow_head(coords, size)
            if head:
                parts.append(head.replace("<path ", f'<path {_stroke_attrs(el)} ', 1))
        if el.get("startArrowhead") == "arrow":
            head = _arrow_head(list(reversed(coords)), size)
            if head:
                parts.append(head.replace("<path ", f'<path {_stroke_attrs(el)} ', 1))
    elif kind == "rectangle":
        x, y, w, h = _normalize_box(el.get("x", 0), el.get("y", 0), el.get("width", 0), el.get("height", 0))
        rx = 8 if el.get("roundness") else 0
        parts.append(
            f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" height="{_fmt(h)}" rx="{rx}" '
            f'{_fill_attrs(el)} {_stroke_attrs(el)}/>'
        )
    elif kind == "ellipse":
        x, y, w, h = _normalize_box(el.get("x", 0), el.get("y", 0), el.get("width", 0), el.get("height", 0))
        parts.append(
            f'<ellipse cx="{_fmt(x + w / 2)}" cy="{_fmt(y + h / 2)}" rx="{_fmt(w / 2)}" ry="{_fmt(h / 2)}" '
            f'{_fill_attrs(el)} {_stroke_attrs(el)}/>'
        )
    elif kind == "diamond":
        x, y, w, h = _normalize_box(el.get("x", 0), el.get("y", 0), el.get("width", 0), el.get("height", 0))
        pts = f"{_fmt(x + w / 2)},{_fmt(y)} {_fmt(x + w)},{_fmt(y + h / 2)} {_fmt(x + w / 2)},{_fmt(y + h)} {_fmt(x)},{_fmt(y + h / 2)}"
        parts.append(f'<polygon points="{pts}" {_fill_attrs(el)} {_stroke_attrs(el)}/>')
    elif kind == "text":
        text = el.get("text") or el.get("originalText") or ""
        font_size = float(el.get("fontSize", 20))
        family = _FONT_FAMILIES.get(el.get("fontFamily", 2), _FONT_FAMILIES[2])
        color = el.get("strokeColor") or "#1e1e1e"
        align = el.get("textAlign", "left")
        width = abs(float(el.get("width", 0)))
        x = float(el.get("x", 0))
        y = float(el.get("y", 0))
        anchor = {"left": "start", "center": "middle", "right": "end"}.get(align, "start")
        if anchor == "middle":
            tx = x + width / 2
        elif anchor == "end":
            tx = x + width
        else:
            tx = x
        line_height = float(el.get("lineHeight", 1.25)) * font_size
        lines = text.split("\n")
        parts.append(
            f'<text x="{_fmt(tx)}" y="{_fmt(y + font_size * 0.95)}" fill="{escape(color)}" '
            f'font-family="{family}" font-size="{_fmt(font_size)}" text-anchor="{anchor}" '
            f'style="white-space:pre">'
        )
        for i, line in enumerate(lines):
            dy = _fmt(i * line_height)
            parts.append(f'<tspan x="{_fmt(tx)}" dy="{dy if i else "0"}">{escape(line)}</tspan>')
        parts.append("</text>")
    elif kind == "image":
        file_id = el.get("fileId")
        entry = files.get(file_id) if file_id else None
        data_url = (entry or {}).get("dataURL") or (entry or {}).get("dataUrl")
        if data_url:
            x, y, w, h = _normalize_box(el.get("x", 0), el.get("y", 0), el.get("width", 0), el.get("height", 0))
            parts.append(
                f'<image href="{escape(data_url)}" x="{_fmt(x)}" y="{_fmt(y)}" '
                f'width="{_fmt(w)}" height="{_fmt(h)}" preserveAspectRatio="none"/>'
            )
    elif kind in ("frame", "magicframe"):
        return ""
    else:
        return ""

    if not parts:
        return ""
    return open_g + "".join(parts) + close_g


def render_scene_svg(scene: dict) -> str:
    """把 Excalidraw 场景 dict 渲染为独立 SVG 字符串。"""
    elements = [e for e in scene.get("elements", []) if isinstance(e, dict) and not e.get("isDeleted")]
    if not elements:
        raise ValueError("Excalidraw 绘图没有任何可见元素")
    files = scene.get("files") or {}
    app = scene.get("appState") or {}

    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for el in elements:
        bx, by, bw, bh = _element_bounds(el)
        min_x, min_y = min(min_x, bx), min(min_y, by)
        max_x, max_y = max(max_x, bx + bw), max(max_y, by + bh)

    pad = 16
    vb_x = min_x - pad
    vb_y = min_y - pad
    vb_w = (max_x - min_x) + 2 * pad
    vb_h = (max_y - min_y) + 2 * pad

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'version="1.1" viewBox="{_fmt(vb_x)} {_fmt(vb_y)} {_fmt(vb_w)} {_fmt(vb_h)}" '
        f'width="{_fmt(vb_w)}" height="{_fmt(vb_h)}">'
    ]
    if app.get("exportWithBackground", True):
        bg = app.get("viewBackgroundColor", "#ffffff")
        if bg and bg != "transparent":
            parts.append(
                f'<rect x="{_fmt(vb_x)}" y="{_fmt(vb_y)}" width="{_fmt(vb_w)}" height="{_fmt(vb_h)}" fill="{escape(bg)}"/>'
            )
    for el in elements:
        rendered = _render_element(el, files)
        if rendered:
            parts.append(rendered)
    parts.append("</svg>")
    return "".join(parts)


def excalidraw_text_to_svg(text: str) -> str:
    """一步完成：.excalidraw.md 文本 → SVG 字符串。"""
    return render_scene_svg(extract_scene(text))
