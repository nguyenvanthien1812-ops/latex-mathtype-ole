"""
mtef_encode.py  --  MTEF v5 ENCODER (AST -> bytes)

Day la chieu NGUOC LAI cua decoder mtef.py cua ban. Moi ham enc_* o duoi
la nghich dao chinh xac cua mot ham read* trong mtef.py:

    read header (readRecord)  <->  encode_header
    readLine                  <->  enc_line
    readChar                  <->  enc_char
    readTMPL  + enc_variation  <->  enc_tmpl
    readPile                  <->  enc_pile
    readMatrix                <->  enc_matrix
    readEmbell                <->  enc_embell
    cay (makeAST)             <->  emit_node  (de quy + END marker)
    OLE 'Equation Native' hdr <->  wrap_equation_native

CACH KIEM THU (quan trong nhat):
    Vi ban da co decoder chay tot, hay round-trip:
        ast      = <decode mot cong thuc that cua ban>
        body     = encode_body(ast)
        ast2     = MTEF.OpenBytes(wrap_ole(body)).ast   # decoder cua ban
    roi so sanh ast == ast2. Sai o dau lo ngay o do.

PHAM VI v1: char, phan so, sub/sup/subsup, can/can bac n, ngoac (fence),
tong/tich/tich phan co can. Ma tran + dau phu (hat/dot/prime/vector) = phase 2,
da danh dau ro o duoi.
"""

import struct
from record import (
    RecordType, OptionType, CharTypeface, SelectorType,
    MtAST, MtChar, MtTmpl, MtLine, MtPile, MtMatrix, MtEmbellRd,
)

# ----------------------------------------------------------------------
# 1. Cac ham ghi byte co ban (nghich dao Helper.bytes2int + read)
# ----------------------------------------------------------------------
def u8(v):   return bytes([v & 0xFF])
def u16(v):  return struct.pack("<H", v & 0xFFFF)   # little-endian, giong reader
def u32(v):  return struct.pack("<I", v & 0xFFFFFFFF)
def cstr(s): return s.encode("ascii", "replace") + b"\x00"   # null-terminated


# ----------------------------------------------------------------------
# 2. Header MTEF (nghich dao phan dau readRecord)
#    Layout: ver u8, platform u8, product u8, version u8, versionSub u8,
#            application cstring, inline u8
#
#    KHUYEN NGHI: copy 'header' tu MOT cong thuc that da decode duoc de
#    MathType mo chac chan. Default duoi la gia tri Windows/MathType pho bien.
# ----------------------------------------------------------------------
def encode_header(mtef_ver=5, platform=1, product=0, version=7,
                  version_sub=10, application="DSMT7", inline=1):
    return (u8(mtef_ver) + u8(platform) + u8(product) + u8(version) +
            u8(version_sub) + cstr(application) + u8(inline))

# Header + phan dau chuan lay tu MOT cong thuc MathType THAT (DSMT7).
# STANDARD_PREAMBLE = ENCODING_DEF "WinAllBasicCodePages" + 4 FONT_DEF
# (Times New Roman, Symbol, Courier New, MT Extra) + EQN_PREFS.
# Day la phan Word/MathType CAN de render; thieu no -> cong thuc rong.
DEFAULT_HEADER = encode_header()
STANDARD_PREAMBLE = bytes.fromhex(
    "1357696e416c6c4261736963436f6465506167657300110554696d6573204e6577"
    "20526f6d616e00110353796d626f6c001105436f7572696572204e65770011044d"
    "5420457874726100120008213f458f442f4150f4100f475f4150f21f1e4150f415"
    "0f4100f445f425f48f425f4100f4100f435f4100f48f45f42a5f48f48f4100f4100"
    "f40f48f417f48f4100f412a5f445f45f45f45f45f410f0c0100010001020202020"
    "002000101010003000100040000"
)


# ----------------------------------------------------------------------
# 3. Cac record (nghich dao tung read*)
# ----------------------------------------------------------------------
def enc_end():
    # RecordType.END = 0 ; pop mot container ra khoi stack khi decode
    return u8(RecordType.END)


def enc_variation(v):
    # Nghich dao doc variation 1-2 byte trong readTMPL:
    #   decode: variation = (byte1 & 0x7F) | (byte2 << 8) neu byte1 co bit 0x80
    if v <= 0x7F:
        return u8(v)
    b1 = (v & 0x7F) | 0x80
    b2 = (v >> 8) & 0xFF
    return u8(b1) + u8(b2)


def enc_line(null=False):
    # readLine: option; (nudge); (lspace); (ruler); co bit Null -> line.null=True
    option = OptionType.MtefOptLineNull if null else 0   # 0x01
    return u8(RecordType.LINE) + u8(option)


def enc_char(typeface, mtcode, has_embell=False, func_start=False, bits8=None):
    # readChar: option; (nudge); typeface u8; (neu KHONG co NoMtcode) mtcode u16;
    #           (char8) bits8; (char16) bits16
    option = 0
    if func_start:
        option |= OptionType.MtefOptCharFuncStart   # 0x02
    if has_embell:
        option |= OptionType.MtefOptCharEmbell       # 0x01
    if bits8 is not None:
        option |= OptionType.MtefOptCharEncChar8     # 0x04 -> co bits8 (vi tri glyph trong font)
    out = u8(RecordType.CHAR) + u8(option) + u8(typeface | 0x80) + u16(mtcode)
    if bits8 is not None:
        out += u8(bits8)
    return out


def enc_tmpl(selector, variation, options=0):
    # readTMPL: option; (nudge); selector u8; variation(1-2 byte); options u8
    return (u8(RecordType.TMPL) + u8(0) + u8(selector) +
            enc_variation(variation) + u8(options))


def enc_pile(halign, valign):
    # readPile: option; (nudge); halign u8; valign u8
    return u8(RecordType.PILE) + u8(0) + u8(halign) + u8(valign)


def enc_matrix(valign, h_just, v_just, rows, cols):
    # readMatrix: option; (nudge); valign; h_just; v_just; rows; cols
    return (u8(RecordType.MATRIX) + u8(0) + u8(valign) + u8(h_just) +
            u8(v_just) + u8(rows) + u8(cols))


def enc_embell(embell_type):
    # readEmbell: option; (nudge); embellType u8
    return u8(RecordType.EMBELL) + u8(0) + u8(embell_type)


# ----------------------------------------------------------------------
# 4. Cay -> stream (nghich dao makeAST)
#    makeAST dung stack: LINE(non-null)/TMPL/PILE/MATRIX/EMBELL day vao stack,
#    cac record sau la con cua no cho toi khi gap END thi pop.
#    => Khi encode: ghi record, ghi con de quy, roi ghi END (voi container).
#       LINE null thi tu dong (khong con, khong END).
#       CHAR la la (khong con, khong END).
# ----------------------------------------------------------------------
# --- nhom selector co cach ma hoa rieng (giong MathType that) ---
_S = SelectorType
SCRIPT_SELS = {_S.tmSUP, _S.tmSUB, _S.tmSUBSUP}
FENCE_SELS  = {_S.tmPAREN, _S.tmBRACK, _S.tmBRACE, _S.tmBAR, _S.tmDBAR,
               _S.tmFLOOR, _S.tmCEILING, _S.tmANGLE, _S.tmOBRACK}
BIGOP_SELS  = {_S.tmSUM, _S.tmPROD, _S.tmINTEG, _S.tmCOPROD, _S.tmUNION,
               _S.tmINTER, _S.tmINTOP, _S.tmSUMOP}
# MathType co xu huong giu style/cramped-size cua mot so template cho node ke tiep.
# Neu khong reset sau radical, cac thanh phan dung ngay sau \sqrt/... co the bi nho
# bat thuong (vi du: \sqrt[3]{10+6\sqrt3}(\sqrt3-1) hoac 6+2\sqrt5-\sqrt5).
# Vi vay xem ROOT la template doi co can duoc FULL reset tuong tu script/bigop.
_SIZE_CHANGERS = SCRIPT_SELS | BIGOP_SELS | {_S.tmROOT}         # sau cac template nay can FULL de reset co
FENCE_CHARS = {_S.tmPAREN:(0x28,0x29), _S.tmBRACK:(0x5b,0x5d),
               _S.tmBRACE:(0x7b,0x7d), _S.tmBAR:(0x7c,0x7c), _S.tmDBAR:(0x7c,0x7c)}
ACCENT_SELS = {_S.tmHAT}                       # dau phu o tren: hat/widehat
ACCENT_CHAR = {_S.tmHAT: 0x0302}               # combining circumflex (dau mu)
BIGOP_CHAR  = {_S.tmSUM:0x2211, _S.tmPROD:0x220f, _S.tmINTEG:0x222b,
               _S.tmCOPROD:0x2210, _S.tmUNION:0x222a, _S.tmINTER:0x2229}


def emit_seq(nodes, out):
    """Emit mot day node anh em; chen FULL sau template doi co (script/bigop)
    neu con node phia sau -> giong MathType."""
    n = len(nodes)
    for k, node in enumerate(nodes):
        out = emit_node(node, out)
        if (k < n - 1 and node.tag == RecordType.TMPL
                and node.value.selector in _SIZE_CHANGERS):
            out += u8(RecordType.FULL)
    return out


def _emit_slot(line_node, out):
    """Mot slot: LINE NULL neu rong, nguoc lai LINE{noi dung}END."""
    if line_node is None or not getattr(line_node, "children", None):
        out += enc_line(null=True)
    else:
        out += enc_line(null=False)
        out = emit_seq(line_node.children, out)
        out += enc_end()
    return out


def emit_node(node, out):
    tag = node.tag

    if tag == RecordType.LINE:
        is_null = bool(getattr(node.value, "null", False)) if node.value else False
        if is_null:
            out += enc_line(null=True)
        else:
            out += enc_line(null=False)
            out = emit_seq(node.children, out)
            out += enc_end()

    elif tag == RecordType.TMPL:
        t = node.value
        sel = t.selector
        slots = node.children                      # cac LINE-slot tu builder

        if sel in SCRIPT_SELS:
            # [SUB] [slot duoi] [slot tren] ; thu tu luon [duoi, tren]
            out += enc_tmpl(sel, 0, 0)
            out += u8(RecordType.SUB)
            if sel == _S.tmSUP:
                out = _emit_slot(None, out)        # duoi rong
                out = _emit_slot(slots[0], out)    # tren = so mu
            elif sel == _S.tmSUB:
                out = _emit_slot(slots[0], out)    # duoi = chi so
                out = _emit_slot(None, out)        # tren rong
            else:                                  # tmSUBSUP
                out = _emit_slot(slots[0], out)    # duoi
                out = _emit_slot(slots[1], out)    # tren
            out += enc_end()

        elif sel == _S.tmROOT:
            out += enc_tmpl(sel, t.variation, 0)
            out = _emit_slot(slots[0], out)        # bieu thuc duoi can
            out += u8(RecordType.SUB)
            if t.variation == 0 or len(slots) < 2:
                out = _emit_slot(None, out)        # can bac 2 -> bac rong
            else:
                out = _emit_slot(slots[1], out)    # can bac n -> chi so bac
            out += enc_end()

        elif sel in FENCE_SELS:
            out += enc_tmpl(sel, t.variation, 0)
            out = _emit_slot(slots[0], out)        # noi dung ben trong
            lc, rc = FENCE_CHARS.get(sel, (0x28, 0x29))
            if t.variation & 0x01:
                out += enc_char(CharTypeface.fnEXPAND, lc)   # ngoac trai (co gian)
            if t.variation & 0x02:
                out += enc_char(CharTypeface.fnEXPAND, rc)   # ngoac phai
            out += enc_end()

        elif sel in ACCENT_SELS:
            out += enc_tmpl(sel, t.variation, 0)
            out = _emit_slot(slots[0], out)        # noi dung ben duoi dau phu
            out += enc_char(CharTypeface.fnEXPAND, ACCENT_CHAR.get(sel, 0x0302))
            out += enc_end()

        elif sel in BIGOP_SELS:
            out += enc_tmpl(sel, t.variation, 0)
            out = _emit_slot(slots[0] if slots else None, out)              # than (body)
            out += u8(RecordType.SUB)
            out = _emit_slot(slots[1] if len(slots) > 1 else None, out)     # can duoi
            out = _emit_slot(slots[2] if len(slots) > 2 else None, out)     # can tren
            out += u8(RecordType.SYM)
            out += enc_char(CharTypeface.fnSYMBOL, BIGOP_CHAR.get(sel, 0x2211))
            out += enc_end()

        else:                                      # tmFRACT va cac template khac
            out += enc_tmpl(sel, t.variation, t.options)
            for slot in slots:
                out = emit_node(slot, out)
            out += enc_end()

    elif tag == RecordType.PILE:
        p = node.value
        out += enc_pile(p.halign, p.valign)
        out = emit_seq(node.children, out)
        out += enc_end()

    elif tag == RecordType.MATRIX:
        m = node.value
        out += enc_matrix(m.valign, m.h_just, m.v_just, m.rows, m.cols)
        for c in node.children:
            out = emit_node(c, out)
        out += enc_end()

    elif tag == RecordType.CHAR:
        c = node.value
        has_embell = bool(getattr(c, "embellishments", None)) or bool(node.children)
        func_start = bool(getattr(c, "options", 0) & OptionType.MtefOptCharFuncStart)
        out += enc_char(c.typeface, c.mtcode, has_embell=has_embell,
                        func_start=func_start, bits8=getattr(c, "bits8", None))
        for ch in node.children:
            out = emit_node(ch, out)

    elif tag == RecordType.EMBELL:
        out += enc_embell(node.value.embellType)
        for c in node.children:
            out = emit_node(c, out)
        out += enc_end()

    elif tag in (RecordType.SUB, RecordType.SUB2, RecordType.SYM,
                 RecordType.SUBSYM, RecordType.FULL):
        out += u8(tag)

    return out


def encode_body(ast, header=None, preamble=None, wrap=True):
    """ast: cay MtAST (root tag 0xff). Tra ve TOAN BO MTEF stream.
    Mac dinh nhung phan dau chuan (ENCODING_DEF + FONT_DEF + EQN_PREFS) va boc
    FULL ... END giong het cong thuc MathType that, de Word/MathType render dung."""
    if header is None:
        header = DEFAULT_HEADER
    if preamble is None:
        preamble = STANDARD_PREAMBLE
    out = bytearray()
    out += header
    out += preamble
    if wrap:
        out += u8(RecordType.FULL)        # 0x0a: marker co chu day du (giong that)
    for child in ast.children:
        out = emit_node(child, out)
    if wrap:
        out += enc_end()                  # END duoi (sentinel) khop MathType
    return bytes(out)


# ----------------------------------------------------------------------
# 5. Boc OLE 'Equation Native' (nghich dao MTEF.Open EQNOLEFILEHDR 28 byte)
#    cbHdr u16=28 ; version u32 ; cf u16 ; cbSize u32 = len(mtef) ; pad -> 28
# ----------------------------------------------------------------------
OLE_CB_HDR = 28
def wrap_equation_native(mtef_stream, version=0x00020000, cf=0x0000):
    hdr = bytearray()
    hdr += u16(OLE_CB_HDR)        # cbHdr  @0
    hdr += u32(version)           # version @2
    hdr += u16(cf)                # cf     @6
    hdr += u32(len(mtef_stream))  # cbSize @8
    hdr += b"\x00" * (OLE_CB_HDR - len(hdr))   # reserved -> du 28 byte
    assert len(hdr) == OLE_CB_HDR
    return bytes(hdr) + mtef_stream
    # B2 (file rieng): goi stream nay vao CFB voi cac stream
    # 'Equation Native', '\1Ole', '\1CompObj'(ProgID=Equation.DSMT4) -> oleObjectN.bin


# ----------------------------------------------------------------------
# 6. Builder: LaTeX-construct -> cay MtAST (de ban lap tu LaTeX parser)
#    Cac order slot/variation duoi la theo hieu biet tu record.py;
#    nhung cho danh dau (?) hay round-trip kiem chung bang decoder cua ban.
# ----------------------------------------------------------------------
def Char(mtcode, typeface=CharTypeface.fnVARIABLE, bits8=None, func_start=False):
    c = MtChar(); c.typeface = typeface; c.mtcode = mtcode
    c.bits8 = bits8                      # None = KHONG co char8 (chu/so thuong)
    if func_start:
        c.options |= OptionType.MtefOptCharFuncStart
    return MtAST(RecordType.CHAR, c, [])

def function_text(text):
    """Tao ten ham MathType chu dung; ky tu dau mang co FuncStart."""
    return [Char(ord(ch), CharTypeface.fnFUNCTION, func_start=(i == 0))
            for i, ch in enumerate(text)]

def text_char(ch):
    """Chon typeface theo kinh nghiem: chu->VARIABLE, so->NUMBER, con lai->TEXT."""
    o = ord(ch)
    if ch.isdigit():       tf = CharTypeface.fnNUMBER
    elif ch.isalpha():     tf = CharTypeface.fnVARIABLE
    else:                  tf = CharTypeface.fnTEXT
    return Char(o, tf)

def Line(children, null=False):
    ln = MtLine(); ln.null = null
    return MtAST(RecordType.LINE, ln, list(children))

def Tmpl(selector, variation, slots, options=0):
    """slots: list cac list-node; moi slot thanh mot LINE con cua template."""
    t = MtTmpl(); t.selector = selector; t.variation = variation; t.options = options
    children = [Line(slot) for slot in slots]
    return MtAST(RecordType.TMPL, t, children)

# --- cac construct hay gap ---
def frac(num, den):
    return Tmpl(SelectorType.tmFRACT, 0, [num, den])             # tu, mau

def sup(exp):
    # dat SAU char goc: [base, sup(...)] ; template chi chua slot mu
    return Tmpl(SelectorType.tmSUP, 0, [exp])

def sub(idx):
    return Tmpl(SelectorType.tmSUB, 0, [idx])

def subsup(idx, exp):
    return Tmpl(SelectorType.tmSUBSUP, 0, [idx, exp])            # (?) thu tu sub,sup

def sqrt(rad):
    return Tmpl(SelectorType.tmROOT, 0, [rad])                   # tvROOT_SQ = 0

def nth_root(rad, index):
    return Tmpl(SelectorType.tmROOT, 1, [rad, index])            # (?) tvROOT_NTH=1, thu tu slot

def fenced(inner, left=True, right=True, kind=SelectorType.tmPAREN):
    var = (0x0001 if left else 0) | (0x0002 if right else 0)    # tvFENCE_L | tvFENCE_R
    return Tmpl(kind, var, [inner])

def hat(content):
    """\\widehat / \\hat (dau mu rong, dung cho ky hieu goc) -> tmHAT."""
    return Tmpl(SelectorType.tmHAT, 0, [content])

def equation(nodes):
    """Boc danh sach node thanh mot equation hoan chinh (1 LINE goc)."""
    root = MtAST(0xff, None, [Line(nodes)])
    return root


# ----------------------------------------------------------------------
# 7. Self-test: dung "a^2 + b^2 = c^2", encode, in hex + trace tag
# ----------------------------------------------------------------------
def _trace(mtef_stream):
    """Doc lai nhanh chuoi tag de mat kiem tra (khong phai decoder day du)."""
    names = {v: k for k, v in vars(RecordType).items() if isinstance(v, int)}
    i = 0
    # bo qua header: 5 byte + app cstring + 1 byte inline
    i = 5
    while mtef_stream[i] != 0: i += 1
    i += 1 + 1
    depth, seq = 0, []
    while i < len(mtef_stream):
        tag = mtef_stream[i]; i += 1
        if tag == RecordType.END:
            depth -= 1; seq.append("  " * depth + "END"); continue
        nm = names.get(tag, f"?{tag}")
        if tag == RecordType.CHAR:
            opt = mtef_stream[i]; tf = mtef_stream[i+1]
            code = struct.unpack("<H", mtef_stream[i+2:i+4])[0]; i += 4
            seq.append("  " * depth + f"CHAR tf={tf} code=0x{code:04x} '{chr(code) if 32<=code<127 else '?'}'")
        elif tag == RecordType.LINE:
            opt = mtef_stream[i]; i += 1
            null = bool(opt & OptionType.MtefOptLineNull)
            seq.append("  " * depth + f"LINE{' (null)' if null else ''}")
            if not null: depth += 1
        elif tag == RecordType.TMPL:
            opt = mtef_stream[i]; sel = mtef_stream[i+1]; i += 2
            b1 = mtef_stream[i]; i += 1
            var = b1
            if b1 & 0x80:
                var = (b1 & 0x7F) | (mtef_stream[i] << 8); i += 1
            i += 1  # options
            selnames = {v: k for k, v in vars(SelectorType).items() if isinstance(v, int)}
            seq.append("  " * depth + f"TMPL {selnames.get(sel, sel)} var={var}")
            depth += 1
        else:
            seq.append("  " * depth + nm)
    return "\n".join(seq)


if __name__ == "__main__":
    # a^2 + b^2 = c^2
    nodes = [
        text_char("a"), sup([text_char("2")]),
        text_char("+"),
        text_char("b"), sup([text_char("2")]),
        text_char("="),
        text_char("c"), sup([text_char("2")]),
    ]
    ast = equation(nodes)
    body = encode_body(ast)
    full = wrap_equation_native(body)

    print("MTEF stream:", len(body), "bytes | Equation Native:", len(full), "bytes")
    print("\n--- hex (MTEF body) ---")
    print(" ".join(f"{b:02x}" for b in body))
    print("\n--- tag trace (kiem tra cau truc) ---")
    print(_trace(body))


# ----------------------------------------------------------------------
# 8. Doc header tu mot cong thuc MathType THAT (giam rui ro MathType khong mo)
#    Tach 28-byte OLE header, roi doc prefix MTEF de tai su dung y nguyen.
# ----------------------------------------------------------------------
def strip_ole_header(equation_native):
    """Bo 28-byte EQNOLEFILEHDR, tra ve MTEF stream (bat dau bang mMtefVer)."""
    if len(equation_native) < OLE_CB_HDR:
        return equation_native
    cb_hdr = struct.unpack("<H", equation_native[0:2])[0]
    if cb_hdr != OLE_CB_HDR:
        return equation_native            # co the da la MTEF tho
    return equation_native[OLE_CB_HDR:]


def read_header(mtef_stream):
    """Tra ve (header_bytes, fields) tu dau mot MTEF stream."""
    i = 5
    end = mtef_stream.index(b"\x00", i)   # ket thuc application cstring
    i = end + 1 + 1                       # + null + inline byte
    header_bytes = bytes(mtef_stream[:i])
    fields = {
        "mtef_ver": mtef_stream[0], "platform": mtef_stream[1],
        "product": mtef_stream[2], "version": mtef_stream[3],
        "version_sub": mtef_stream[4],
        "application": mtef_stream[5:end].decode("ascii", "replace"),
        "inline": mtef_stream[end + 1],
    }
    return header_bytes, fields
