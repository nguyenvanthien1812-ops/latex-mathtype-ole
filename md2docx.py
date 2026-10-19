r"""
md2docx.py -- Markdown (ket qua OCR) -> .docx THAT, giu bang/anh/heading,
va xu ly cong thuc theo 3 che do (latex / omml / mathtype).

QUAN TRONG: cong thuc duoc "bao ve" bang placeholder TRUOC khi chay markdown,
roi khoi phuc sau. Nho vay markdown khong an mat dau \( \) \[ \] va khong lam
hong noi dung ben trong (vd dau _ trong $a_1$).

API:  build_docx(markdown, formula_mode="mathtype") -> (bytes, stats)
Nhan ca 4 kieu dau: $...$  $$...$$  \(...\)  \[...\]
Va tu dong nhan LaTeX tran: \begin{cases}...\end{cases}.

FIX 2026-07:
- lxml gan el.tag cua HTML comment/processing-instruction bang mot Cython
  function object, khong phai chuoi.
- OCR co the chen marker nhu <!-- Trang 1 -->.
- Khong duoc goi .lower() truc tiep tren el.tag; dung _tag_name() va bo qua
  cac node comment/PI.
"""
import io
import re
import base64

import markdown as _md
from lxml import html as _html
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

from omml import latex_to_omath
from docx_convert import convert_docx_bytes

_FORMULA = re.compile(
    r"(\$\$.+?\$\$|\\\[.+?\\\]|\$[^$\n]+?\$|\\\(.+?\\\))", re.S)

# Gemini/OCR doi khi tra LaTeX moi truong truc tiep ma khong boc $...$.
# Bao ve cac moi truong nay truoc khi chay Markdown de backend van nhan la cong thuc.
_BARE_ENV = re.compile(
    r"\\begin\{(?P<env>cases|aligned|alignedat|array|matrix|pmatrix|bmatrix|vmatrix)\}"
    r"(?P<body>[\s\S]*?)"
    r"\\end\{(?P=env)\}",
    re.I,
)

_PH_OPEN, _PH_CLOSE = "\ue000", "\ue001"
_PH_RE = re.compile(_PH_OPEN + r"(\d+)" + _PH_CLOSE)
_MAX_IMG_IN = 6.0
# Anh TikZ duoc compile o 300 DPI -> px/300 = kich thuoc vat ly that.
_IMG_DPI = 300


def _tag_name(node):
    """Tra ve ten tag chu thuong; comment/PI cua lxml tra ve chuoi rong."""
    tag = getattr(node, "tag", "")
    if not isinstance(tag, str):
        return ""
    # Ho tro ca tag co namespace: {namespace}tag
    return tag.rsplit("}", 1)[-1].lower()


def _strip_math(seg):
    if seg.startswith("$$") and seg.endswith("$$") and len(seg) >= 4:
        return seg[2:-2].strip()
    if seg.startswith("\\[") and seg.endswith("\\]") and len(seg) >= 4:
        return seg[2:-2].strip()
    if seg.startswith("\\(") and seg.endswith("\\)") and len(seg) >= 4:
        return seg[2:-2].strip()
    if seg.startswith("$") and seg.endswith("$") and len(seg) >= 2:
        return seg[1:-1].strip()
    return None


def build_docx(markdown_text, formula_mode="mathtype", log=print):
    return _Builder(formula_mode).run(markdown_text, log)


# ─── Định dạng xuất Word ─────────────────────────────────────────────
DOC_FONT = "Times New Roman"
DOC_SIZE = Pt(13)
BLUE = RGBColor(0x00, 0x00, 0xFF)    # nhãn Câu/Bài, phương án A B C D, a) b) c) d)
GREEN = RGBColor(0x00, 0x80, 0x00)   # công thức Equation (OMML)

# Nhãn được tô xanh + đậm: "Câu 12.", "Bài 3.", "A.", "D.", "a)", "d)"
import re as _re
# Bắt phần NHÃN ở đầu run rồi TÁCH RA, chỉ tô đúng nhãn — không loang sang
# phần chữ phía sau (kể cả khi model viết liền "Câu 1. Giá trị..." trong 1 run).
_LABEL_HEAD_RE = _re.compile(r'^(\s*(?:C\u00e2u|B\u00e0i)\s+\d+\s*[.:]|\s*[A-D]\.|\s*[a-d]\))(\s|$)')


def _apply_base_font(doc):
    """Times New Roman 13 cho toàn tài liệu qua style Normal — khỏi set từng run."""
    st = doc.styles["Normal"]
    st.font.name = DOC_FONT
    st.font.size = DOC_SIZE
    # Font cho ký tự Đông Á (dấu tiếng Việt dựng sẵn vẫn ăn Times, nhưng set cho chắc)
    rpr = st.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(a), DOC_FONT)


_M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _color_omml(omath, hexcolor):
    """Tô màu chữ cho mọi <m:r> trong công thức OMML.

    OMML lấy thuộc tính chữ từ <m:rPr>/<w:rPr> bên trong mỗi <m:r>. Chèn
    <w:color w:val="RRGGBB"> vào rPr của từng run toán học là công thức đổi màu.
    """
    for mr in omath.iter(qn("m:r")):
        # m:rPr (định dạng toán) — tạo nếu chưa có, phải đứng trước m:t
        mrpr = mr.find(qn("m:rPr"))
        # w:rPr (định dạng chữ) nằm trong m:r, song song m:rPr
        wrpr = mr.find(qn("w:rPr"))
        if wrpr is None:
            wrpr = mr.makeelement(qn("w:rPr"), {})
            # chèn sau m:rPr nếu có, nếu không thì lên đầu
            if mrpr is not None:
                mrpr.addnext(wrpr)
            else:
                mr.insert(0, wrpr)
        # bỏ color cũ rồi thêm mới
        for old in wrpr.findall(qn("w:color")):
            wrpr.remove(old)
        color = wrpr.makeelement(qn("w:color"), {qn("w:val"): hexcolor})
        wrpr.insert(0, color)


class _Builder:
    def __init__(self, mode):
        self.mode = mode if mode in ("latex", "omml", "mathtype") else "mathtype"
        self.spans = []

    def _protect(self, md):
        def add_span(latex):
            # Giu \\ la dau xuong dong trong cases, chi gom whitespace that.
            latex = (latex or "").replace("\r\n", "\n").replace("\r", "\n")
            latex = re.sub(r"[ \t]*\n[ \t]*", " ", latex).strip()
            idx = len(self.spans)
            self.spans.append(latex)
            return f"{_PH_OPEN}{idx}{_PH_CLOSE}"

        def repl_math(m):
            inner = _strip_math(m.group(0))
            return add_span(inner if inner is not None else m.group(0))

        def repl_env(m):
            return add_span(m.group(0))

        # Bao ve cong thuc co delimiter truoc; sau do moi bat moi truong LaTeX tran.
        protected = _FORMULA.sub(repl_math, md)
        protected = _BARE_ENV.sub(repl_env, protected)
        return protected

    def run(self, markdown_text, log):
        protected = self._protect(markdown_text)
        html = _md.markdown(
            protected, extensions=["tables", "fenced_code", "sane_lists", "nl2br"])
        root = _html.fragment_fromstring(html, create_parent="body")
        doc = Document()
        _apply_base_font(doc)
        for el in root:
            # Bo qua HTML comment / processing instruction.
            if not _tag_name(el):
                continue
            self._block(doc, el)
        buf = io.BytesIO()
        doc.save(buf)
        data = buf.getvalue()
        if self.mode == "mathtype":
            return convert_docx_bytes(data, log=log)
        return data, {"converted": len(self.spans), "failed": 0}

    def _block(self, doc, el):
        tag = _tag_name(el)
        if not tag:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            lvl = int(tag[1])
            para = doc.add_heading("", level=lvl)
            self._inline(para, el, {})
            # Heading mặc định của Word có màu xanh nhạt + font khác. Ép về
            # Times New Roman, ĐEN, in đậm; cỡ to dần theo cấp (h1 lớn nhất).
            size = {1: 16, 2: 15, 3: 14}.get(lvl, 13)
            for r in para.runs:
                r.font.name = DOC_FONT
                r.font.size = Pt(size)
                r.font.bold = True
                r.font.color.rgb = RGBColor(0, 0, 0)
                rpr = r._element.get_or_add_rPr()
                rf = rpr.find(qn("w:rFonts"))
                if rf is None:
                    rf = rpr.makeelement(qn("w:rFonts"), {}); rpr.append(rf)
                rf.set(qn("w:eastAsia"), DOC_FONT)
        elif tag == "p":
            imgs = el.findall("img")
            if len(imgs) == 1 and not (el.text or "").strip() and len(el) == 1:
                self._image(doc.add_paragraph(), imgs[0], block=True)
                return
            self._inline(doc.add_paragraph(), el, {})
        elif tag in ("ul", "ol"):
            self._list(doc, el, ordered=(tag == "ol"), level=0)
        elif tag == "blockquote":
            for ch in el:
                if not _tag_name(ch):
                    continue
                self._inline(doc.add_paragraph(style="Quote"), ch, {})
        elif tag == "pre":
            code = el.find("code")
            text = (code.text if code is not None else el.text) or ""
            r = doc.add_paragraph().add_run(text.rstrip("\n"))
            r.font.name = "Consolas"
            r.font.size = Pt(10)
        elif tag == "table":
            self._table(doc, el)
        elif tag == "hr":
            doc.add_paragraph("\u2500" * 30)
        elif tag == "img":
            self._image(doc.add_paragraph(), el, block=True)
        else:
            self._inline(doc.add_paragraph(), el, {})

    def _list(self, doc, el, ordered, level):
        base = "List Number" if ordered else "List Bullet"
        style = base if level == 0 else f"{base} {level + 1}"
        for li in el.findall("li"):
            self._inline(doc.add_paragraph(style=style), li, {}, skip_lists=True)
            for sub in li:
                sub_tag = _tag_name(sub)
                if sub_tag in ("ul", "ol"):
                    self._list(doc, sub, ordered=(sub_tag == "ol"), level=level + 1)

    def _table(self, doc, el):
        rows = el.findall(".//tr")
        if not rows:
            return
        ncol = max(len(r.findall("th") + r.findall("td")) for r in rows)
        t = doc.add_table(rows=0, cols=ncol)
        t.style = "Table Grid"
        for r in rows:
            cells = r.findall("th") + r.findall("td")
            row = t.add_row().cells
            for i, c in enumerate(cells):
                if i >= ncol:
                    break
                self._inline(
                    row[i].paragraphs[0],
                    c,
                    {"bold": _tag_name(c) == "th"},
                )

    def _inline(self, para, el, fmt, skip_lists=False):
        self._text(para, el.text, fmt)
        for ch in el:
            ctag = _tag_name(ch)

            # Comment/PI: khong xu ly noi dung comment, nhung giu tail neu co.
            if not ctag:
                self._text(para, ch.tail, fmt)
                continue

            if skip_lists and ctag in ("ul", "ol"):
                self._text(para, ch.tail, fmt)
                continue
            if ctag in ("strong", "b"):
                self._inline(para, ch, {**fmt, "bold": True})
            elif ctag in ("em", "i"):
                self._inline(para, ch, {**fmt, "italic": True})
            elif ctag == "code":
                r = para.add_run(ch.text or "")
                r.font.name = "Consolas"
            elif ctag == "a":
                self._inline(para, ch, {**fmt, "underline": True})
            elif ctag == "br":
                para.add_run().add_break()
            elif ctag == "img":
                self._image(para, ch, block=False)
            else:
                self._inline(para, ch, fmt)
            self._text(para, ch.tail, fmt)

    def _text(self, para, text, fmt):
        if not text:
            return
        pos = 0
        for m in _PH_RE.finditer(text):
            if m.start() > pos:
                self._run(para, text[pos:m.start()], fmt)
            self._formula(para, self.spans[int(m.group(1))])
            pos = m.end()
        if pos < len(text):
            self._run(para, text[pos:], fmt)

    def _formula(self, para, latex):
        if not latex:
            return
        if self.mode == "omml":
            omath = latex_to_omath(latex)
            _color_omml(omath, "008000")   # xanh green cho mọi run trong công thức
            para._p.append(omath)
        else:
            # MathType OLE là ảnh WMF — không tô màu được, để đen.
            self._run(para, f"${latex}$", {})

    @staticmethod
    def _style_run(r, fmt, *, label=False):
        """Ép Times 13 + Đông Á; tô xanh đậm nếu là nhãn, ngược lại theo fmt."""
        r.font.name = DOC_FONT
        r.font.size = DOC_SIZE
        rpr = r._element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = rpr.makeelement(qn("w:rFonts"), {})
            rpr.append(rfonts)
        rfonts.set(qn("w:eastAsia"), DOC_FONT)
        if label:
            r.bold = True
            r.font.color.rgb = BLUE
        else:
            if fmt.get("bold"):
                r.bold = True
            if fmt.get("italic"):
                r.italic = True
        if fmt.get("underline"):
            r.underline = True
        return r

    @classmethod
    def _run(cls, para, text, fmt):
        text = text or ""
        # Nếu run MỞ ĐẦU bằng nhãn (Câu 1. / A. / a) ...) thì tách:
        #   phần nhãn  -> xanh đậm (dừng ĐÚNG ở dấu chấm/ngoặc)
        #   phần còn lại -> định dạng thường
        # Chỉ tách khi model in đậm cả cụm (fmt.bold) HOẶC nhãn đứng đầu đoạn —
        # tránh tô nhầm "A." nằm giữa câu.
        m = _LABEL_HEAD_RE.match(text)
        if m and (fmt.get("bold") or m.start() == 0):
            label = m.group(1)
            rest = text[m.end(1):]
            r1 = para.add_run(label)
            cls._style_run(r1, fmt, label=True)
            if rest:
                r2 = para.add_run(rest)
                # phần sau nhãn KHÔNG kế thừa bold của cụm **...**
                cls._style_run(r2, {k: v for k, v in fmt.items() if k != "bold"})
            return r1

        r = para.add_run(text)
        return cls._style_run(r, fmt)

    @staticmethod
    def _picture_width(raw):
        """Kich thuoc that cua anh (inch), gioi han trong _MAX_IMG_IN.

        Truoc day luon ep cung Inches(6.0) nen hinh nho bi phong to het be ngang
        trang. PNG khong co chunk pHYs thi python-docx mac dinh 72 DPI -> cang sai.
        """
        try:
            if raw[:8] == b"\x89PNG\r\n\x1a\n":
                w_px = int.from_bytes(raw[16:20], "big")
            else:
                from PIL import Image as _PILImage
                w_px = _PILImage.open(io.BytesIO(raw)).width
            if w_px <= 0:
                return Inches(_MAX_IMG_IN)
            return Inches(min(w_px / _IMG_DPI, _MAX_IMG_IN))
        except Exception:
            return Inches(_MAX_IMG_IN)

    def _image(self, para, img_el, block):
        src = img_el.get("src", "")
        if not isinstance(src, str) or not src.startswith("data:"):
            alt = img_el.get("alt", "")
            if alt:
                para.add_run(f"[{alt}]")
            return
        try:
            _, b64 = src.split(",", 1)
            raw = base64.b64decode(b64)
            width = self._picture_width(raw)
            if block:
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            para.add_run().add_picture(io.BytesIO(raw), width=width)
        except Exception as e:
            alt = img_el.get("alt", "")
            # Truoc day nuot loi im lang -> anh bien mat ma khong ai biet vi sao.
            print(f"  [bo qua anh] {alt or '(khong alt)'}: {type(e).__name__}: {e}")
            if alt:
                para.add_run(f"[{alt}]")
