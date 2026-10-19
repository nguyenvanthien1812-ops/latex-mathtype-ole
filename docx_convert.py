r"""
docx_convert.py -- Tim $...$ trong file Word va thay bang MathType OLE object.

convert_docx(in_path, out_path, log=print, header=None) -> dict
header_from_ole(path_or_bytes) -> bytes   # lay header THAT tu 1 cong thuc co san

Nang cap so voi ban dau:
  - Nhan 'header' tu mot cong thuc MathType that (giam rui ro MathType khong mo).
  - Xu ly $...$ TRAI tren nhieu run (xu ly o muc doan van, gop cac run text lien ke).
"""
import os, re, zipfile, shutil, io
from copy import deepcopy
from lxml import etree

from latex2mtef import latex_to_ast
from mtef_encode import (encode_body, wrap_equation_native,
                         strip_ole_header, read_header)
from cfb import build_mathtype_ole, read_ole_template
from render import render_formula as _render_formula
from wmf import raster_to_wmf


def reference_template(path):
    """Lay vo OLE (clsid/CompObj/Ole) + header tu mot cong thuc MathType THAT.
    path: file .docx co cong thuc MathType, hoac mot oleObject .bin."""
    if path.lower().endswith(".docx"):
        with zipfile.ZipFile(path) as z:
            bins = sorted(n for n in z.namelist()
                          if re.search(r"embeddings/oleObject.*\.bin$", n))
            if not bins:
                raise ValueError("Khong tim thay cong thuc OLE (oleObject*.bin) trong docx nay")
            tmpl = read_ole_template(z.read(bins[0]))
    else:
        tmpl = read_ole_template(path)
    return tmpl

W  = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R  = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
V  = "urn:schemas-microsoft-com:vml"
O  = "urn:schemas-microsoft-com:office:office"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"

REL_OLE   = R + "/oleObject"
REL_IMAGE = R + "/image"
EQ_RE = re.compile(r"\$(?!\$)(.+?)(?<!\$)\$")


def _env_float(name, default):
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return float(default)


# Tinh chinh nhe de preview WMF ngang baseline Word hon. Don vi point.
# Co the thay doi tren Render ma khong sua code.
BASELINE_EXTRA_PT = _env_float("MATHTYPE_BASELINE_EXTRA_PT", 0.65)
OBJECT_WIDTH_SCALE = _env_float("MATHTYPE_OBJECT_WIDTH_SCALE", 1.0)
OBJECT_HEIGHT_SCALE = _env_float("MATHTYPE_OBJECT_HEIGHT_SCALE", 1.0)


# ----------------------------------------------------------------------
# Lay header that tu mot cong thuc MathType co san (.bin hoac bytes)
# ----------------------------------------------------------------------
def header_from_ole(src):
    import olefile
    if isinstance(src, (bytes, bytearray)):
        ole = olefile.OleFileIO(io.BytesIO(src))
    else:
        ole = olefile.OleFileIO(src)
    eqn_native = ole.openstream("Equation Native").read()
    ole.close()
    mtef = strip_ole_header(eqn_native)
    header_bytes, _ = read_header(mtef)
    return header_bytes


# ----------------------------------------------------------------------
# Anh fallback (placeholder ve chu LaTeX). Thay bang render that neu muon.
# ----------------------------------------------------------------------
def _preview_wmf(latex):
    """Tra ve (wmf_bytes, w_pt, h_pt, depth_pt) -- anh WMF dung co 13pt + baseline."""
    img, w_pt, h_pt, depth_pt = _render_formula(latex)
    return raster_to_wmf(img), w_pt, h_pt, depth_pt


# ----------------------------------------------------------------------
# Tao cac phan tu XML
# ----------------------------------------------------------------------
def _text_run(text, rpr):
    r = etree.Element(f"{{{W}}}r")
    if rpr is not None:
        r.append(deepcopy(rpr))
    t = etree.SubElement(r, f"{{{W}}}t")
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = text
    return r


def _shapetype():
    # Ban day du giong het MathType/Word that
    st = etree.fromstring(
        '<v:shapetype xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'id="_x0000_t75" coordsize="21600,21600" o:spt="75" o:preferrelative="t" '
        'path="m@4@5l@4@11@9@11@9@5xe" filled="f" stroked="f">'
        '<v:stroke joinstyle="miter"/>'
        '<v:formulas>'
        '<v:f eqn="if lineDrawn pixelLineWidth 0"/><v:f eqn="sum @0 1 0"/>'
        '<v:f eqn="sum 0 0 @1"/><v:f eqn="prod @2 1 2"/>'
        '<v:f eqn="prod @3 21600 pixelWidth"/><v:f eqn="prod @3 21600 pixelHeight"/>'
        '<v:f eqn="sum @0 0 1"/><v:f eqn="prod @6 1 2"/>'
        '<v:f eqn="prod @7 21600 pixelWidth"/><v:f eqn="sum @8 21600 0"/>'
        '<v:f eqn="prod @7 21600 pixelHeight"/><v:f eqn="sum @10 21600 0"/>'
        '</v:formulas>'
        '<v:path o:extrusionok="f" gradientshapeok="t" o:connecttype="rect"/>'
        '<o:lock v:ext="edit" aspectratio="t"/>'
        '</v:shapetype>')
    return st


def _object_run(shape_id, obj_id, img_rid, ole_rid, w_pt, h_pt, depth_pt, rpr, with_shapetype):
    wp = max(1.0, float(w_pt) * OBJECT_WIDTH_SCALE)
    hp = max(1.0, float(h_pt) * OBJECT_HEIGHT_SCALE)
    # w:position dung don vi nua-point. Gia tri am ha object xuong.
    # depth_pt la phan anh duoi baseline; cong them mot hieu chinh nho cho Word/VML.
    baseline = max(0.0, float(depth_pt) + BASELINE_EXTRA_PT)
    pos = -int(round(baseline * 2.0))
    r = etree.Element(f"{{{W}}}r")
    # rPr: giu dinh dang goc + them/thay <w:position> de canh baseline
    rpr2 = deepcopy(rpr) if rpr is not None else etree.Element(f"{{{W}}}rPr")
    for old in rpr2.findall(f"{{{W}}}position"):
        rpr2.remove(old)
    if pos != 0:
        posel = etree.SubElement(rpr2, f"{{{W}}}position")
        posel.set(f"{{{W}}}val", str(pos))
    r.append(rpr2)
    obj = etree.SubElement(r, f"{{{W}}}object")
    obj.set(f"{{{W}}}dxaOrig", str(int(round(wp * 20))))
    obj.set(f"{{{W}}}dyaOrig", str(int(round(hp * 20))))
    if with_shapetype:
        obj.append(_shapetype())
    shape = etree.SubElement(obj, f"{{{V}}}shape")
    shape.set("id", shape_id); shape.set("type", "#_x0000_t75")
    shape.set("style", f"width:{wp:.2f}pt;height:{hp:.2f}pt"); shape.set(f"{{{O}}}ole", "")
    imgd = etree.SubElement(shape, f"{{{V}}}imagedata")
    imgd.set(f"{{{R}}}id", img_rid); imgd.set(f"{{{O}}}title", "")
    ole = etree.SubElement(obj, f"{{{O}}}OLEObject")
    ole.set("Type", "Embed"); ole.set("ProgID", "Equation.DSMT4")
    ole.set("ShapeID", shape_id); ole.set("DrawAspect", "Content")
    ole.set("ObjectID", obj_id); ole.set(f"{{{R}}}id", ole_rid)
    return r


def _is_simple_text_run(r):
    """run chi gom (rPr?) + dung mot w:t -> co the gop an toan."""
    kids = [c for c in r if not isinstance(c.tag, str) or
            c.tag not in (f"{{{W}}}rPr",)]
    ts = r.findall(f"{{{W}}}t")
    if len(ts) != 1:
        return False
    for c in r:
        if c.tag not in (f"{{{W}}}rPr", f"{{{W}}}t"):
            return False
    return True


# ----------------------------------------------------------------------
# Chuyen doi chinh
# ----------------------------------------------------------------------
def convert_docx(in_path, out_path, log=print, header=None, template=None):
    # neu co template MathType that ma chua chi dinh header -> lay header tu no
    if template and header is None and template.get("equation_native"):
        try:
            header, _ = read_header(strip_ole_header(template["equation_native"]))
        except Exception:
            pass
    work = out_path + ".tmpdir"
    if os.path.exists(work): shutil.rmtree(work)
    os.makedirs(work)
    with zipfile.ZipFile(in_path) as z:
        z.extractall(work)

    doc_xml  = os.path.join(work, "word", "document.xml")
    rels_xml = os.path.join(work, "word", "_rels", "document.xml.rels")
    ct_xml   = os.path.join(work, "[Content_Types].xml")
    os.makedirs(os.path.join(work, "word", "embeddings"), exist_ok=True)
    os.makedirs(os.path.join(work, "word", "media"), exist_ok=True)

    tree = etree.parse(doc_xml); root = tree.getroot()
    rels_tree = etree.parse(rels_xml); rels_root = rels_tree.getroot()
    used_ids = {e.get("Id") for e in rels_root}

    def new_rid():
        n = 1
        while f"rId{n}" in used_ids: n += 1
        used_ids.add(f"rId{n}"); return f"rId{n}"

    state = {"converted": 0, "failed": 0, "seq": 0, "shapetype": False}

    def make_object(latex, rpr):
        """LaTeX -> mot <w:r> object run (kem ghi file). Co the nem loi."""
        ast = latex_to_ast(latex)
        eqn = wrap_equation_native(encode_body(ast, header=header))
        ole_bin = build_mathtype_ole(eqn, template=template)
        img_bytes, w_pt, h_pt, depth_pt = _preview_wmf(latex)
        state["seq"] += 1; k = state["seq"]
        bin_name, img_name = f"oleObject{k}.bin", f"image{k}.wmf"
        with open(os.path.join(work, "word", "embeddings", bin_name), "wb") as f: f.write(ole_bin)
        with open(os.path.join(work, "word", "media", img_name), "wb") as f: f.write(img_bytes)
        ole_rid, img_rid = new_rid(), new_rid()
        _add_rel(rels_root, ole_rid, REL_OLE,   f"embeddings/{bin_name}")
        _add_rel(rels_root, img_rid, REL_IMAGE, f"media/{img_name}")
        first = not state["shapetype"]; state["shapetype"] = True
        return _object_run(f"_xS{k}", f"_xO{k}", img_rid, ole_rid,
                           w_pt, h_pt, depth_pt, rpr, first)

    # duyet tung doan van (w:p), gop cac run text lien ke roi tim $...$
    for para in root.iter(f"{{{W}}}p"):
        children = list(para)
        i = 0
        while i < len(children):
            r = children[i]
            if r.tag != f"{{{W}}}r" or not _is_simple_text_run(r):
                i += 1; continue
            # gom day run text lien tiep
            j = i; group = []
            while j < len(children) and children[j].tag == f"{{{W}}}r" \
                    and _is_simple_text_run(children[j]):
                group.append(children[j]); j += 1
            full = "".join((g.find(f"{{{W}}}t").text or "") for g in group)
            if "$" not in full or not EQ_RE.search(full):
                i = j; continue

            # ban do vi tri -> rPr cua run chua vi tri do
            spans = []; pos = 0
            for g in group:
                txt = g.find(f"{{{W}}}t").text or ""
                spans.append((pos, pos + len(txt), g.find(f"{{{W}}}rPr")))
                pos += len(txt)
            def rpr_at(p):
                for a, b, rp in spans:
                    if a <= p < b: return rp
                return spans[-1][2] if spans else None

            # tao danh sach node moi thay cho ca group
            # QUAN TRONG: mot doan text giua hai cong thuc co the trai tren nhieu
            # run co rPr KHAC nhau (vd "Cau 1." mau xanh + " noi dung" mau den).
            # Neu chi lay rpr_at(dau_doan) thi mau/dam cua run dau se loang ra ca
            # doan. Vi vay tach tiep doan text theo tung span rPr goc.
            def emit_text(seg_start, seg_end):
                p = seg_start
                for a, b, rp in spans:
                    lo, hi = max(a, seg_start), min(b, seg_end)
                    if lo < hi:
                        new_nodes.append(_text_run(full[lo:hi], rp))
                        p = hi
                if p < seg_end:  # phan du (hiem) -> dung rPr cuoi
                    new_nodes.append(_text_run(full[p:seg_end], rpr_at(p)))

            new_nodes = []; cursor = 0
            for m in EQ_RE.finditer(full):
                if m.start() > cursor:
                    emit_text(cursor, m.start())
                latex = m.group(1).strip()
                try:
                    new_nodes.append(make_object(latex, rpr_at(m.start())))
                    state["converted"] += 1
                except Exception as e:
                    log(f"  [bo qua] ${latex}$  ({e})")
                    state["failed"] += 1
                    new_nodes.append(_text_run(m.group(0), rpr_at(m.start())))
                cursor = m.end()
            if cursor < len(full):
                emit_text(cursor, len(full))

            # thay group bang new_nodes
            insert_at = list(para).index(group[0])
            for g in group: para.remove(g)
            for off, node in enumerate(new_nodes):
                para.insert(insert_at + off, node)

            children = list(para)
            i = insert_at + len(new_nodes)

    tree.write(doc_xml, xml_declaration=True, encoding="UTF-8", standalone=True)
    rels_tree.write(rels_xml, xml_declaration=True, encoding="UTF-8", standalone=True)
    _ensure_content_types(ct_xml)

    if os.path.exists(out_path): os.remove(out_path)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _, files in os.walk(work):
            for fn in files:
                full = os.path.join(base, fn)
                z.write(full, os.path.relpath(full, work))
    shutil.rmtree(work)
    return {"converted": state["converted"], "failed": state["failed"]}


def convert_docx_bytes(data, log=print, header=None, template=None):
    """Phien ban in-memory cho backend: nhan bytes .docx, tra ve (bytes, stats)."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        ip = os.path.join(td, "in.docx"); op = os.path.join(td, "out.docx")
        with open(ip, "wb") as f:
            f.write(data)
        stats = convert_docx(ip, op, log=log, header=header, template=template)
        with open(op, "rb") as f:
            out = f.read()
    return out, stats


def _add_rel(rels_root, rid, rtype, target):
    e = etree.SubElement(rels_root, f"{{{PR}}}Relationship")
    e.set("Id", rid); e.set("Type", rtype); e.set("Target", target)


def _ensure_content_types(ct_path):
    tree = etree.parse(ct_path); root = tree.getroot()
    have = {e.get("Extension") for e in root if e.tag == f"{{{CT}}}Default"}
    for ext, mt in {"bin": "application/vnd.openxmlformats-officedocument.oleObject",
                    "wmf": "image/x-wmf", "png": "image/png", "emf": "image/x-emf"}.items():
        if ext not in have:
            d = etree.SubElement(root, f"{{{CT}}}Default")
            d.set("Extension", ext); d.set("ContentType", mt)
    tree.write(ct_path, xml_declaration=True, encoding="UTF-8", standalone=True)
