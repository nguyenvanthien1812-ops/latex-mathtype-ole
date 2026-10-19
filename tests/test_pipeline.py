r"""
Test suite: chay duoc khong can Word/MathType.
  python -m pytest tests/  (hoac)  python tests/test_pipeline.py
"""
import os, io, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import olefile, docx
from mtef_encode import (equation, text_char, sup, frac, encode_body,
                         wrap_equation_native, strip_ole_header, read_header)
from cfb import build_mathtype_ole
from latex2mtef import latex_to_ast
from docx_convert import convert_docx, header_from_ole

TMP = "/tmp/l2mt_test"
os.makedirs(TMP, exist_ok=True)


def test_cfb_roundtrip():
    ast = equation([text_char("a"), sup([text_char("2")])])
    eqn = wrap_equation_native(encode_body(ast))
    blob = build_mathtype_ole(eqn)
    ole = olefile.OleFileIO(io.BytesIO(blob))
    assert ole.exists("Equation Native")
    assert ole.exists("\x01CompObj") and ole.exists("\x01Ole")
    assert ole.openstream("Equation Native").read() == eqn
    ole.close()


def test_parser_structure():
    body = encode_body(latex_to_ast(r"\frac{1}{2}"))
    assert body[5:10] == b"DSMT7"          # header app string
    assert len(body) > 14                      # co than record
    # tong co subsup
    body2 = encode_body(latex_to_ast(r"\sum_{i=1}^{n} i"))
    assert len(body2) > 14


def test_header_roundtrip():
    ast = equation([text_char("x")])
    eqn = wrap_equation_native(encode_body(ast))
    blob = build_mathtype_ole(eqn)
    h = header_from_ole(blob)                   # lay header tu .bin
    hb, fields = read_header(strip_ole_header(eqn))
    assert h == hb
    assert fields["application"] == "DSMT7"


def test_docx_single_run():
    d = docx.Document()
    d.add_paragraph("Cong thuc $a^2 + b^2 = c^2$ trong dong.")
    src = os.path.join(TMP, "single_in.docx"); dst = os.path.join(TMP, "single_out.docx")
    d.save(src)
    stats = convert_docx(src, dst, log=lambda *_: None)
    assert stats["converted"] == 1 and stats["failed"] == 0
    with zipfile.ZipFile(dst) as z:
        assert z.testzip() is None
        assert any("oleObject" in n for n in z.namelist())
        dx = z.read("word/document.xml").decode("utf8")
        assert dx.count("OLEObject") == 1
    docx.Document(dst)                          # mo lai duoc


def test_docx_multi_run():
    # cong thuc bi xe ra 2 run: "$a^2 +" | " b^2$"
    d = docx.Document()
    p = d.add_paragraph()
    p.add_run("truoc $a^2 +")
    p.add_run(" b^2$ sau")
    src = os.path.join(TMP, "multi_in.docx"); dst = os.path.join(TMP, "multi_out.docx")
    d.save(src)
    stats = convert_docx(src, dst, log=lambda *_: None)
    assert stats["converted"] == 1, stats
    with zipfile.ZipFile(dst) as z:
        dx = z.read("word/document.xml").decode("utf8")
        assert dx.count("OLEObject") == 1
        # van con chu "truoc" va "sau"
        assert "truoc" in dx and "sau" in dx


def test_custom_header_used():
    # tao header gia khac thuong, kiem tra no duoc nhung vao
    fake = b"\x05\x00\x00\x09\x09" + b"FAKEAPP\x00" + b"\x01"
    d = docx.Document(); d.add_paragraph("$x$")
    src = os.path.join(TMP, "hdr_in.docx"); dst = os.path.join(TMP, "hdr_out.docx")
    d.save(src)
    convert_docx(src, dst, log=lambda *_: None, header=fake)
    with zipfile.ZipFile(dst) as z:
        blob = z.read("word/embeddings/oleObject1.bin")
    ole = olefile.OleFileIO(io.BytesIO(blob))
    mtef = strip_ole_header(ole.openstream("Equation Native").read())
    ole.close()
    assert mtef[:len(fake)] == fake


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = 0
    for fn in fns:
        try:
            fn(); print(f"PASS  {fn.__name__}"); ok += 1
        except Exception as e:
            import traceback; print(f"FAIL  {fn.__name__}: {e}"); traceback.print_exc()
    print(f"\n{ok}/{len(fns)} tests passed")
    sys.exit(0 if ok == len(fns) else 1)
