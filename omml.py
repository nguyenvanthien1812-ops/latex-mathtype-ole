r"""
omml.py -- LaTeX -> OMML (<m:oMath>) cho Equation goc cua Word.

Dung lai parser latex_to_ast (cung AST voi nhanh MathType). Phu cac dang:
phan so, mu/chi so/ca hai, can (bac 2 & bac n), ngoac. Dang chua ho tro ->
de nguyen text trong run (an toan).
"""
from lxml import etree
from latex2mtef import latex_to_ast
from mtef_encode import RecordType, SelectorType

M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
XML = "http://www.w3.org/XML/1998/namespace"
_S = SelectorType
SCRIPT = {_S.tmSUP, _S.tmSUB, _S.tmSUBSUP}
FENCE = {_S.tmPAREN, _S.tmBRACK, _S.tmBRACE, _S.tmBAR, _S.tmDBAR}
FENCE_CH = {_S.tmPAREN: ("(", ")"), _S.tmBRACK: ("[", "]"),
            _S.tmBRACE: ("{", "}"), _S.tmBAR: ("|", "|"), _S.tmDBAR: ("\u2016", "\u2016")}


def _q(tag):
    return f"{{{M}}}{tag}"


def _run(text):
    r = etree.Element(_q("r"))
    t = etree.SubElement(r, _q("t"))
    t.set(f"{{{XML}}}space", "preserve")
    t.text = text
    return r


def _box(tag, elements):
    e = etree.Element(_q(tag))
    for x in elements:
        e.append(x)
    return e


def _emit_seq(nodes):
    """Tra ve danh sach phan tu OMML cho mot day node."""
    out = []
    for node in nodes:
        if node.tag == RecordType.CHAR:
            out.append(_run(chr(node.value.mtcode)))
        elif node.tag == RecordType.LINE:
            out.extend(_emit_seq(node.children))
        elif node.tag == RecordType.TMPL:
            sel = node.value.selector
            slots = node.children
            if sel in SCRIPT:
                base = out.pop() if out else _run("")
                if sel == _S.tmSUP:
                    el = etree.Element(_q("sSup"))
                    el.append(_box("e", [base]))
                    el.append(_box("sup", _slot(slots[0])))
                elif sel == _S.tmSUB:
                    el = etree.Element(_q("sSub"))
                    el.append(_box("e", [base]))
                    el.append(_box("sub", _slot(slots[0])))
                else:
                    el = etree.Element(_q("sSubSup"))
                    el.append(_box("e", [base]))
                    el.append(_box("sub", _slot(slots[0])))
                    el.append(_box("sup", _slot(slots[1])))
                out.append(el)
            elif sel == _S.tmFRACT:
                f = etree.Element(_q("f"))
                f.append(_box("num", _slot(slots[0])))
                f.append(_box("den", _slot(slots[1])))
                out.append(f)
            elif sel == _S.tmROOT:
                rad = etree.Element(_q("rad"))
                pr = etree.SubElement(rad, _q("radPr"))
                if node.value.variation == 0 or len(slots) < 2:
                    dh = etree.SubElement(pr, _q("degHide")); dh.set(_q("val"), "1")
                    rad.append(_box("deg", []))
                    rad.append(_box("e", _slot(slots[0])))
                else:
                    rad.append(_box("deg", _slot(slots[1])))
                    rad.append(_box("e", _slot(slots[0])))
                out.append(rad)
            elif sel in FENCE:
                beg, end = FENCE_CH.get(sel, ("(", ")"))
                d = etree.Element(_q("d"))
                dpr = etree.SubElement(d, _q("dPr"))
                bc = etree.SubElement(dpr, _q("begChr")); bc.set(_q("val"), beg)
                ec = etree.SubElement(dpr, _q("endChr")); ec.set(_q("val"), end)
                d.append(_box("e", _slot(slots[0])))
                out.append(d)
            else:
                out.extend(_emit_seq(node.children))
    return out


def _slot(line_node):
    if line_node is None or not getattr(line_node, "children", None):
        return []
    return _emit_seq(line_node.children)


def latex_to_omath(latex):
    """Tra ve phan tu lxml <m:oMath>. Loi parse -> oMath chi chua text goc."""
    try:
        ast = latex_to_ast(latex)
        children = _emit_seq(ast.children)
    except Exception:
        children = [_run(latex)]
    omath = etree.Element(_q("oMath"))
    for el in children:
        omath.append(el)
    return omath


def latex_to_omath_xml(latex):
    return etree.tostring(latex_to_omath(latex), encoding="unicode")
