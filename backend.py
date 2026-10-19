r"""
backend.py -- Lop backend: nhan 1 trong 2 dang dau vao, tra ve .docx (bytes)
voi cong thuc $...$ da thay bang MathType OLE (mo duoc bang MathType, hien
anh xem truoc trong Word). Khong can file mau (--ref).

  Dang 1 - chuoi van ban co $...$:
      from backend import convert_text
      data, stats = convert_text("Cau 1: $\\dfrac{-15}{27}$ ...")

  Dang 2 - file Word tai len:
      from backend import convert_upload
      data, stats = convert_upload(uploaded_bytes)

Ca hai tra ve (docx_bytes, stats) voi stats = {'converted': n, 'failed': m}.
"""
import io
import docx

from docx_convert import convert_docx_bytes
from md2docx import build_docx


def convert_text(text, log=print):
    """Dang 1: dung .docx tu chuoi van ban (moi dong = 1 doan), roi chuyen $...$."""
    d = docx.Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    buf = io.BytesIO(); d.save(buf)
    return convert_docx_bytes(buf.getvalue(), log=log)


def convert_upload(docx_bytes, log=print):
    """Dang 2: file Word tai len -> chuyen $...$ thanh MathType OLE."""
    return convert_docx_bytes(docx_bytes, log=log)


def convert_markdown(markdown_text, formula_mode="mathtype", log=print):
    """Dang 3: markdown (ket qua OCR) -> .docx THAT giu bang/anh/heading.
    formula_mode: 'latex' (giu $...$) | 'omml' (Equation Word) | 'mathtype' (OLE)."""
    if formula_mode not in ("latex", "omml", "mathtype"):
        formula_mode = "mathtype"
    return build_docx(markdown_text, formula_mode=formula_mode, log=log)


def process(content, is_docx=False, log=print):
    """Cong gop: is_docx=True -> content la bytes .docx; nguoc lai la chuoi van ban."""
    if is_docx:
        return convert_upload(content, log=log)
    return convert_text(content, log=log)


if __name__ == "__main__":
    data, stats = convert_text(
        "Cau 1: $\\dfrac{-15}{27}$ va $a^2+b^2=c^2$\n"
        "Cau 2: $\\sqrt{b^2-4ac}$ ; tong $\\sum_{i=1}^{n} i^2$.")
    open("/tmp/from_text.docx", "wb").write(data)
    print("convert_text:", stats, "->", len(data), "bytes")
