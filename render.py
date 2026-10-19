r"""
render.py -- Render cong thuc LaTeX thanh anh xem truoc PIL va do chinh xac
kich thuoc/baseline de chen vao Word duoi dang WMF.

Muc tieu:
  - Full size 13 pt giong file Times New Roman13.eqp.
  - Uu tien Times New Roman; tren Linux tu dong dung Tinos/Liberation Serif.
  - Khong ep \frac thanh \dfrac, tranh cong thuc inline qua cao.
  - Lay truc tiep bitmap + depth tu MathTextParser('agg'), khong qua figure
    bbox/padding nen baseline on dinh hon.

render_formula(latex) -> (PIL.Image RGB, width_pt, height_pt, depth_pt)
  depth_pt la phan anh nam duoi baseline, da tinh ca padding duoi.
"""
from __future__ import annotations

import io
import os
import re
from functools import lru_cache
from latex_normalize import normalize_sqrt_groups

FULL_PT = float(os.getenv("MATHTYPE_FULL_PT", "13"))
_DPI = max(96, int(os.getenv("MATHTYPE_RENDER_DPI", "300")))
_PAD_PX = max(0, int(os.getenv("MATHTYPE_RENDER_PAD_PX", "1")))


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return float(default)


_CASES_ROW_GAP_EM = _env_float("MATHTYPE_CASES_ROW_GAP_EM", 0.20)
_CASES_COL_GAP_EM = _env_float("MATHTYPE_CASES_COL_GAP_EM", 0.40)
_CASES_SIDE_GAP_EM = _env_float("MATHTYPE_CASES_SIDE_GAP_EM", 0.075)
_CASES_BRACE_WIDTH_RATIO = _env_float("MATHTYPE_CASES_BRACE_WIDTH_RATIO", 0.155)
_CASES_BRACE_STROKE_RATIO = _env_float("MATHTYPE_CASES_BRACE_STROKE_RATIO", 0.0090)
_CASES_BRACE_OVERHANG_EM = _env_float("MATHTYPE_CASES_BRACE_OVERHANG_EM", 0.045)

# MathText khong ho tro tot tfrac/cfrac; parser MTEF hien cung quy ca bon dang
# ve cung mot template phan so, vi vay preview quy ve \frac la sat nhat.
_FRAC_RE = re.compile(r"\\(?:dfrac|tfrac|cfrac)\b")
_OPERATOR_STAR_RE = re.compile(r"\\operatorname\*\s*\{")
_ENV_RE = re.compile(
    r"\\begin\{(?P<env>cases|aligned|alignedat|array|matrix|pmatrix|bmatrix|vmatrix)\}"
    r"(?P<body>[\s\S]*?)"
    r"\\end\{(?P=env)\}",
    re.I,
)

# Cac dang ma MathJax cho preview dep hon ro ret. Cong thuc thuong se dung
# MathText de toc do nhanh hon.
_MATHJAX_COMPLEX_RE = re.compile(
    r"(?:"
    r"\\begin\{(?:cases|aligned|alignedat|array|matrix|pmatrix|bmatrix|vmatrix)\}"
    r"|\\(?:int|iint|iiint|oint)\b"
    r"|\\(?:overbrace|underbrace|overset|underset|substack)\b"
    r")",
    re.I,
)


def _needs_mathjax(latex: str) -> bool:
    """Chi dua cau truc phuc tap sang MathJax trong che do hybrid."""
    return bool(_MATHJAX_COMPLEX_RE.search(latex or ""))



def _normalize(latex: str) -> str:
    """Chuan hoa vua du de MathText render gan giong OLE MTEF hien tai."""
    s = normalize_sqrt_groups((latex or "").strip())
    s = _FRAC_RE.sub(r"\\frac", s)
    s = s.replace(r"\displaystyle", "").replace(r"\textstyle", "")
    s = _OPERATOR_STAR_RE.sub(r"\\operatorname{", s)

    # Matplotlib MathText khong nhan mot so alias LaTeX pho bien (dac biet \ge,
    # \le, \ne, \lvert/\rvert) du MathType/MTEF van nhan. Chuan hoa chi
    # cho PREVIEW de anh trong Word khop voi cong thuc khi mo bang MathType.
    s = re.sub(r"\\ge(?![A-Za-z])", r"\\geq", s)
    s = re.sub(r"\\le(?![A-Za-z])", r"\\leq", s)
    s = re.sub(r"\\ne(?![A-Za-z])", r"\\neq", s)
    s = s.replace(r"\lvert", "|").replace(r"\rvert", "|")

    # Backend MTEF hien bo qua cac lenh spacing nay, nen preview cung bo de khop.
    for cmd in (r"\!", r"\,", r"\;", r"\:", r"\quad", r"\qquad"):
        s = s.replace(cmd, " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


@lru_cache(maxsize=1)
def _font_family() -> str:
    """Chon font preview.

    Mac dinh `mathtype` dung bo STIX native, hinh dang gan preview MathType hon
    tren Linux. Che do `tnr` uu tien Times New Roman that, roi moi fallback Tinos.
    Co the nap font co ban quyen tu thu muc rieng bang MATHTYPE_FONT_DIR.
    """
    from pathlib import Path
    from matplotlib.font_manager import FontProperties, findfont, fontManager

    font_dir = os.getenv("MATHTYPE_FONT_DIR", "").strip()
    if font_dir:
        root = Path(font_dir)
        if root.is_dir():
            for pattern in ("*.ttf", "*.otf", "*.ttc"):
                for fp in root.glob(pattern):
                    try:
                        fontManager.addfont(str(fp))
                    except Exception:
                        pass

    requested = os.getenv("MATHTYPE_PREVIEW_FONT", "").strip()
    style = os.getenv("MATHTYPE_PREVIEW_STYLE", "mathtype").strip().lower()

    if requested:
        candidates = [requested]
    elif style in ("tnr", "times", "times-new-roman"):
        candidates = ["Times New Roman", "Tinos", "Liberation Serif", "STIXGeneral"]
    else:
        # Day la kieu ma ban dau nguoi dung danh gia dep hon.
        candidates = ["STIXGeneral", "Times New Roman", "Tinos", "Liberation Serif"]

    for name in candidates:
        try:
            findfont(FontProperties(family=name), fallback_to_default=False)
            return name
        except Exception:
            continue
    return "STIXGeneral"


def _preview_style() -> str:
    return os.getenv("MATHTYPE_PREVIEW_STYLE", "mathtype").strip().lower()


def _configure_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    family = _font_family()
    style = _preview_style()

    # STIX native co spacing, integral, radical va italic gan MathType hon.
    if style not in ("tnr", "times", "times-new-roman") and family == "STIXGeneral":
        matplotlib.rcParams["font.family"] = "STIXGeneral"
        matplotlib.rcParams["mathtext.fontset"] = "stix"
    else:
        # Khi server co Times New Roman that, dung no cho Latin/so va STIX cho glyph thieu.
        matplotlib.rcParams["font.family"] = family
        matplotlib.rcParams["mathtext.fontset"] = "custom"
        matplotlib.rcParams["mathtext.rm"] = family
        matplotlib.rcParams["mathtext.it"] = f"{family}:italic"
        matplotlib.rcParams["mathtext.bf"] = f"{family}:bold"
        matplotlib.rcParams["mathtext.cal"] = "STIXGeneral"
        matplotlib.rcParams["mathtext.sf"] = "DejaVu Sans"
        matplotlib.rcParams["mathtext.tt"] = "DejaVu Sans Mono"
        matplotlib.rcParams["mathtext.fallback"] = "stix"
    return matplotlib, family


def _render_math_row(latex: str):
    """Render mot cong thuc bang dung engine preview chinh.

    Tra ve (PIL.Image RGB, depth_px). Ham nay duoc dung cho ca cong thuc thuong
    va tung dong/o cua cases, aligned, matrix de khong roi vao fallback chu tho.
    """
    _configure_matplotlib()
    import numpy as np
    from matplotlib.font_manager import FontProperties
    from matplotlib.mathtext import MathTextParser
    from PIL import Image, ImageOps

    expr = f"${_normalize(latex)}$"
    prop = FontProperties(family=_font_family(), size=FULL_PT)
    parsed = MathTextParser("agg").parse(expr, dpi=_DPI, prop=prop)
    coverage = np.asarray(parsed.image, dtype=np.uint8)
    img = Image.fromarray(255 - coverage, mode="L").convert("RGB")
    if _PAD_PX:
        img = ImageOps.expand(img, border=_PAD_PX, fill="white")
    return img, float(parsed.depth) + _PAD_PX




def _split_top_level(text: str, separator: str) -> list[str]:
    """Tach chuoi theo separator o ngoai cac nhom { }."""
    parts, current = [], []
    depth = 0
    i = 0
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}" and depth:
            depth -= 1
        if depth == 0 and text.startswith(separator, i):
            parts.append("".join(current).strip())
            current = []
            i += len(separator)
            if separator == r"\\" and i < len(text) and text[i] == "[":
                close = text.find("]", i + 1)
                if close >= 0:
                    i = close + 1
            continue
        current.append(c)
        i += 1
    parts.append("".join(current).strip())
    return parts


def _render_cell(latex: str):
    """Dung chinh renderer TNR13 cu cho tung o cua he/matrix."""
    try:
        return _render_math_row(latex)
    except Exception:
        from PIL import Image, ImageDraw, ImageFont

        size_px = max(12, round(FULL_PT * _DPI / 72.0))
        font = None
        for candidate in (
            "Tinos-Regular.ttf",
            "LiberationSerif-Regular.ttf",
            "DejaVuSerif.ttf",
        ):
            try:
                font = ImageFont.truetype(candidate, size_px)
                break
            except Exception:
                pass
        if font is None:
            font = ImageFont.load_default()
        text = latex or ""
        tmp = Image.new("RGB", (10, 10), "white")
        box = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font)
        image = Image.new(
            "RGB",
            (max(1, box[2] - box[0] + 8), max(1, box[3] - box[1] + 8)),
            "white",
        )
        ImageDraw.Draw(image).text((4, 2), text, fill="black", font=font)
        return image, image.height * 0.22


def _pil_delimiter_font(size_px: int):
    from PIL import ImageFont

    candidates = [
        os.getenv("MATHTYPE_BRACE_FONT", "").strip(),
        "STIXGeneral.ttf",
        "STIXSizeOneSym-Regular.ttf",
        "Tinos-Regular.ttf",
        "LiberationSerif-Regular.ttf",
        "DejaVuSerif.ttf",
    ]
    for name in candidates:
        if not name:
            continue
        try:
            return ImageFont.truetype(name, size_px)
        except Exception:
            pass
    return ImageFont.load_default()


def _draw_delimiter(char: str, target_h: int):
    """Ve dau phan cach cho khoi nhieu dong.

    Luu y quan trong: khong phong to truc tiep ky tu "{" tu font text,
    vi cach do lam ngoac bi dam va day. Thay vao do, ngoac nhon duoc ve
    bang duong cong o do phan giai cao roi thu nho lai, cho net manh va
    giong preview MathType hon.
    """
    from PIL import Image, ImageDraw

    def _draw_curly(is_right: bool, h: int):
        scale = 4
        out_h = max(8, int(h))
        out_w = max(8, round(out_h * _CASES_BRACE_WIDTH_RATIO))
        H = out_h * scale
        W = out_w * scale
        stroke = max(3, round(H * _CASES_BRACE_STROKE_RATIO))

        def mirror_x(x: float) -> float:
            return (W - 1 - x) if is_right else x

        def cubic(p0, p1, p2, p3, n=32):
            pts = []
            for i in range(n + 1):
                t = i / n
                mt = 1.0 - t
                x = (mt**3)*p0[0] + 3*(mt**2)*t*p1[0] + 3*mt*(t**2)*p2[0] + (t**3)*p3[0]
                y = (mt**3)*p0[1] + 3*(mt**2)*t*p1[1] + 3*mt*(t**2)*p2[1] + (t**3)*p3[1]
                pts.append((mirror_x(x), y))
            return pts

        w = float(W - 1)
        h2 = float(H - 1)
        segments = [
            ((0.82*w, 0.00*h2), (0.45*w, 0.02*h2), (0.37*w, 0.17*h2), (0.48*w, 0.28*h2)),
            ((0.48*w, 0.28*h2), (0.56*w, 0.36*h2), (0.34*w, 0.45*h2), (0.12*w, 0.50*h2)),
            ((0.12*w, 0.50*h2), (0.34*w, 0.55*h2), (0.56*w, 0.64*h2), (0.48*w, 0.72*h2)),
            ((0.48*w, 0.72*h2), (0.37*w, 0.83*h2), (0.45*w, 0.98*h2), (0.82*w, 1.00*h2)),
        ]

        img = Image.new('L', (W, H), 255)
        draw = ImageDraw.Draw(img)
        points = []
        for idx, seg in enumerate(segments):
            pts = cubic(*seg, n=36)
            if idx:
                pts = pts[1:]
            points.extend(pts)
        draw.line(points, fill=0, width=stroke, joint='curve')
        # Nhan nhe vi ngoac MathType co chan gap o giua.
        cx = mirror_x(0.12*w)
        draw.line([(cx, 0.472*h2), (cx, 0.528*h2)], fill=0, width=stroke)

        rgb = img.convert('RGB').resize((out_w, out_h), Image.Resampling.LANCZOS)
        return rgb

    target_h = max(4, int(target_h))
    if char == "|":
        width = max(1, round(target_h * 0.013))
        return Image.new("RGB", (width, target_h), "black")
    if char in ("[", "]"):
        width = max(4, round(target_h * 0.07))
        stroke = max(1, round(target_h * 0.008))
        image = Image.new("RGB", (width, target_h), "white")
        draw = ImageDraw.Draw(image)
        x = 0 if char == "[" else width - 1
        other = width - 1 if char == "[" else 0
        draw.line((x, 0, x, target_h - 1), fill="black", width=stroke)
        draw.line((x, 0, other, 0), fill="black", width=stroke)
        draw.line((x, target_h - 1, other, target_h - 1), fill="black", width=stroke)
        return image
    if char == '{':
        return _draw_curly(False, target_h)
    if char == '}':
        return _draw_curly(True, target_h)

    font = _pil_delimiter_font(max(18, round(target_h * 1.06)))
    temp = Image.new("RGB", (target_h * 2 + 40, target_h * 2 + 40), "white")
    draw = ImageDraw.Draw(temp)
    box = draw.textbbox((0, 0), char, font=font)
    draw.text((4 - box[0], 2 - box[1]), char, fill="black", font=font)
    inverse = temp.convert("L").point(lambda value: 255 - value)
    bbox = inverse.getbbox()
    if not bbox:
        return Image.new("RGB", (max(3, target_h // 10), target_h), "white")
    glyph = temp.crop(bbox)
    if glyph.height != target_h and glyph.height > 0:
        ratio = target_h / glyph.height
        glyph = glyph.resize(
            (max(1, round(glyph.width * ratio)), target_h),
            Image.Resampling.LANCZOS,
        )
    return glyph


def _render_environment(latex: str):
    """Render rieng cases/aligned/matrix, khong thay doi renderer cong thuc thuong."""
    from PIL import Image

    match = _ENV_RE.search(latex or "")
    if not match:
        return None

    env = match.group("env").lower()
    body = match.group("body")
    if env == "array":
        body = re.sub(r"^\s*\{[^{}]*\}\s*", "", body, count=1)

    raw_rows = [row for row in _split_top_level(body, r"\\") if row]
    if not raw_rows:
        raw_rows = [body.strip()]
    rows = [_split_top_level(row, "&") for row in raw_rows]
    ncols = max(1, max(len(row) for row in rows))
    rows = [row + [""] * (ncols - len(row)) for row in rows]

    rendered = []
    col_widths = [1] * ncols
    row_heights = []
    for row in rows:
        out_row = []
        row_h = 1
        for col, cell in enumerate(row):
            image, depth_px = _render_cell(cell)
            out_row.append((image, depth_px))
            col_widths[col] = max(col_widths[col], image.width)
            row_h = max(row_h, image.height)
        rendered.append(out_row)
        row_heights.append(row_h)

    em_px = max(1, round(FULL_PT * _DPI / 72.0))
    row_gap = max(3, round(em_px * _CASES_ROW_GAP_EM))
    if env == "cases":
        col_gap = max(4, round(em_px * _CASES_COL_GAP_EM))
    elif env in ("aligned", "alignedat"):
        col_gap = max(2, round(em_px * 0.10))
    else:
        col_gap = max(4, round(em_px * 0.36))

    content_w = sum(col_widths) + col_gap * max(0, ncols - 1)
    content_h = sum(row_heights) + row_gap * max(0, len(rows) - 1)
    content = Image.new("RGB", (content_w, content_h), "white")
    y = 0
    for row_index, row in enumerate(rendered):
        x = 0
        for col, (image, _) in enumerate(row):
            # aligned: cot truoc & can phai, cot sau & can trai.
            if env in ("aligned", "alignedat") and col % 2 == 0:
                dx = col_widths[col] - image.width
            elif env in ("matrix", "pmatrix", "bmatrix", "vmatrix", "array"):
                dx = (col_widths[col] - image.width) // 2
            else:
                dx = 0
            dy = (row_heights[row_index] - image.height) // 2
            content.paste(image, (x + dx, y + dy))
            x += col_widths[col] + col_gap
        y += row_heights[row_index] + row_gap

    fence_map = {
        "cases": ("{", None),
        "pmatrix": ("(", ")"),
        "bmatrix": ("[", "]"),
        "vmatrix": ("|", "|"),
    }
    left_char, right_char = fence_map.get(env, (None, None))
    brace_overhang = max(1, round(em_px * _CASES_BRACE_OVERHANG_EM)) if env == "cases" else 0
    delimiter_h = content_h + 2 * brace_overhang
    left = _draw_delimiter(left_char, delimiter_h) if left_char else None
    right = _draw_delimiter(right_char, delimiter_h) if right_char else None
    side_gap = max(2, round(em_px * _CASES_SIDE_GAP_EM))

    inner_h = max(content.height, delimiter_h)
    width = content.width + 2 * _PAD_PX
    if left is not None:
        width += left.width + side_gap
    if right is not None:
        width += right.width + side_gap
    out = Image.new("RGB", (width, inner_h + 2 * _PAD_PX), "white")
    content_y = _PAD_PX + (inner_h - content.height) // 2
    delimiter_y = _PAD_PX + (inner_h - delimiter_h) // 2
    x = _PAD_PX
    if left is not None:
        out.paste(left, (x, delimiter_y))
        x += left.width + side_gap
    out.paste(content, (x, content_y))
    x += content.width
    if right is not None:
        x += side_gap
        out.paste(right, (x, delimiter_y))

    pt_per_px = 72.0 / float(_DPI)
    width_pt = max(1.0, out.width * pt_per_px)
    height_pt = max(1.0, out.height * pt_per_px)
    # MathType can khoi nhieu dong quanh baseline trung tam.
    depth_pt = max(0.0, height_pt * 0.5 - 0.15)
    return out, width_pt, height_pt, depth_pt

def render_formula(latex: str):
    """Tra ve (img RGB, width_pt, height_pt, depth_pt).

    Mac dinh dung che do hybrid: MathJax chi cho cases, matrix, integral va
    cau truc phuc tap; cong thuc thuong dung MathText nhanh hon. Neu Node/MathJax/CairoSVG khong san sang, tu dong roi ve
    renderer Matplotlib cu de backend van tra file Word thay vi loi ca request.
    """
    engine = os.getenv("MATHTYPE_RENDER_ENGINE", "hybrid").strip().lower()
    use_mathjax = (
        engine in ("mathjax", "all")
        or (engine in ("hybrid", "auto") and _needs_mathjax(latex or ""))
    )
    if use_mathjax:
        try:
            from mathjax_renderer import render_mathjax
            return render_mathjax(latex or "", FULL_PT, _DPI, _PAD_PX)
        except Exception:
            # Fallback ben duoi la co chu y; khong de loi preview lam hong OLE.
            pass

    environment = _render_environment(latex or "")
    if environment is not None:
        return environment
    try:
        img, depth_px = _render_math_row(latex)
        pt_per_px = 72.0 / float(_DPI)
        width_pt = max(1.0, img.width * pt_per_px)
        height_pt = max(1.0, img.height * pt_per_px)
        depth_pt = max(0.0, depth_px * pt_per_px)
        return img, width_pt, height_pt, depth_pt

    except Exception:
        # Fallback chi de khong lam hong ca file khi gap LaTeX MathText chua ho tro.
        from PIL import Image, ImageDraw, ImageFont

        size_px = max(12, round(FULL_PT * _DPI / 72.0))
        font = None
        for candidate in (
            "Tinos-Regular.ttf",
            "LiberationSerif-Regular.ttf",
            "DejaVuSerif.ttf",
        ):
            try:
                font = ImageFont.truetype(candidate, size_px)
                break
            except Exception:
                pass
        if font is None:
            font = ImageFont.load_default()

        text = latex or ""
        tmp = Image.new("RGB", (10, 10), "white")
        draw = ImageDraw.Draw(tmp)
        box = draw.textbbox((0, 0), text, font=font)
        w = max(1, box[2] - box[0] + 2 * _PAD_PX + 4)
        h = max(1, box[3] - box[1] + 2 * _PAD_PX + 4)
        img = Image.new("RGB", (w, h), "white")
        ImageDraw.Draw(img).text((_PAD_PX + 2, _PAD_PX + 1), text,
                                 fill="black", font=font)
        pt_per_px = 72.0 / float(_DPI)
        return img, w * pt_per_px, h * pt_per_px, h * pt_per_px * 0.22


def render_pil(latex: str):
    return render_formula(latex)[0]


def render_png(latex: str):
    img = render_pil(latex)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue(), img.width, img.height


def render_info() -> dict:
    """Thong tin huu ich de health-check/debug tren Render."""
    info = {
        "full_pt": FULL_PT,
        "dpi": _DPI,
        "pad_px": _PAD_PX,
        "engine": os.getenv("MATHTYPE_RENDER_ENGINE", "hybrid"),
        "legacy_font_family": _font_family(),
        "preview_style": _preview_style(),
        "legacy_environments": True,
    }
    try:
        from mathjax_renderer import mathjax_info
        info["mathjax"] = mathjax_info()
    except Exception as exc:
        info["mathjax"] = {"available": False, "error": str(exc)}
    return info
