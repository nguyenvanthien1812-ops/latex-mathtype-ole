r"""
api.py -- API goi gon cho backend xuat Word voi cong thuc MathType OLE.

Khong can GUI, khong bat buoc file mau: CLSID/CompObj MathType da duoc tao
trong cfb.py. Preview WMF va kich thuoc shape dung chung metric voi
`docx_convert.py`, tranh sai lech DPI.
"""
from latex2mtef import latex_to_ast
from mtef_encode import encode_body, wrap_equation_native
from cfb import build_mathtype_ole
from render import render_formula
from wmf import raster_to_wmf
from docx_convert import (convert_docx, convert_docx_bytes,
                          reference_template, _object_run, _shapetype)


def latex_to_equation_native(latex, header=None):
    """LaTeX -> stream Equation Native (OLE header 28 byte + MTEF)."""
    return wrap_equation_native(encode_body(latex_to_ast(latex), header=header))


def latex_to_ole_bin(latex, header=None, template=None):
    """LaTeX -> noi dung oleObjectN.bin CFB MathType."""
    eqn = latex_to_equation_native(latex, header=header)
    return build_mathtype_ole(eqn, template=template)


def latex_to_preview_wmf(latex):
    """LaTeX -> (wmf_bytes, width_px, height_px), giu API cu."""
    img, _, _, _ = render_formula(latex)
    return raster_to_wmf(img), img.width, img.height


def equation_assets(latex, header=None, template=None):
    """Tra ve day du tai nguyen de chen mot MathType OLE vao DOCX.

    Khac ban cu: width_pt/height_pt lay truc tiep tu renderer, khong quy doi
    bang he so 200 DPI trong khi anh thuc te render 300 DPI.
    """
    ole = latex_to_ole_bin(latex, header=header, template=template)
    img, width_pt, height_pt, depth_pt = render_formula(latex)
    wmf = raster_to_wmf(img)
    return {
        "ole_bin": ole,
        "wmf": wmf,
        "width_px": img.width,
        "height_px": img.height,
        "width_pt": max(1.0, round(width_pt, 2)),
        "height_pt": max(1.0, round(height_pt, 2)),
        "depth_pt": max(0.0, round(depth_pt, 2)),
        "prog_id": "Equation.DSMT4",
        "content_types": {
            "bin": "application/vnd.openxmlformats-officedocument.oleObject",
            "wmf": "image/x-wmf",
        },
    }


__all__ = [
    "convert_docx", "convert_docx_bytes", "reference_template",
    "latex_to_equation_native", "latex_to_ole_bin", "latex_to_preview_wmf",
    "equation_assets", "_object_run", "_shapetype",
]


if __name__ == "__main__":
    a = equation_assets(r"\frac{-15}{27}")
    print("ole_bin :", len(a["ole_bin"]), "bytes")
    print("wmf     :", len(a["wmf"]), "bytes")
    print("size    :", a["width_pt"], "x", a["height_pt"], "pt")
    print("depth   :", a["depth_pt"], "pt")
    print("prog_id :", a["prog_id"])
