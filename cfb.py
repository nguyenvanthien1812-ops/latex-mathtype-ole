"""
cfb.py -- Trinh ghi Compound File Binary (OLE2) toi thieu.

Du de goi mot cong thuc MathType: cac stream nho (<4096B) deu nam trong
mini-stream, nen co ho tro mini-FAT day du. Kiem thu bang cach doc lai
bang olefile (xem __main__).

build_mathtype_ole(equation_native_bytes) -> bytes  (noi dung oleObjectN.bin)
"""
import struct, io

SECTOR     = 512
MINISECTOR = 64
ENDOFCHAIN = 0xFFFFFFFE
FREESECT   = 0xFFFFFFFF
FATSECT    = 0xFFFFFFFD
NOSTREAM   = 0xFFFFFFFF
MINI_CUTOFF = 4096


def _name_bytes(name):
    u = name.encode("utf-16-le") + b"\x00\x00"          # null-terminated UTF-16LE
    return u.ljust(64, b"\x00"), len(u)


def _dir_entry(name, otype, left, right, child, start, size, clsid=b"\x00" * 16):
    nb, nlen = _name_bytes(name)
    e = bytearray(128)
    e[0:64] = nb
    struct.pack_into("<H", e, 64, nlen)                 # name length (bytes, incl null)
    e[66] = otype                                       # 1=storage 2=stream 5=root
    e[67] = 1                                            # color = black
    struct.pack_into("<I", e, 68, left)
    struct.pack_into("<I", e, 72, right)
    struct.pack_into("<I", e, 76, child)
    e[80:96] = clsid
    struct.pack_into("<I", e, 116, start)               # starting sector
    struct.pack_into("<Q", e, 120, size)                # stream size (8 bytes)
    return bytes(e)


def _cfb_name_key(name):
    # So sanh ten CFB: do dai truoc, roi UTF-16 viet HOA
    return (len(name), name.upper())


def build_cfb(streams, root_clsid=b"\x00" * 16):
    """streams: list[(name, data)]. Tat ca <4096B -> dung mini-stream."""
    # --- 1. mini-stream + mini-FAT ---
    mini_data = bytearray()
    minifat = []
    stream_meta = []                                    # (name, start_minisector, size)
    for name, data in streams:
        if len(data) == 0:
            stream_meta.append((name, ENDOFCHAIN, 0)); continue
        start = len(minifat)
        n = (len(data) + MINISECTOR - 1) // MINISECTOR
        for i in range(n):
            minifat.append(start + i + 1 if i < n - 1 else ENDOFCHAIN)
        mini_data += data + b"\x00" * (n * MINISECTOR - len(data))
        stream_meta.append((name, start, len(data)))
    mini_used = len(mini_data)
    if len(mini_data) % SECTOR:
        mini_data += b"\x00" * (SECTOR - len(mini_data) % SECTOR)
    while len(minifat) % (SECTOR // 4):
        minifat.append(FREESECT)
    minifat_bytes = b"".join(struct.pack("<I", e) for e in minifat)

    # --- 2. directory (root + cac stream), cay can bang ---
    entries = [("Root Entry", 5)] + [(n, 2) for n, _, _ in stream_meta]
    n_entries = len(entries)
    left  = [NOSTREAM] * n_entries
    right = [NOSTREAM] * n_entries
    child = [NOSTREAM] * n_entries

    order = sorted(range(1, n_entries), key=lambda i: _cfb_name_key(entries[i][0]))

    def build_tree(lo, hi):
        if lo > hi:
            return NOSTREAM
        mid = (lo + hi) // 2
        idx = order[mid]
        left[idx]  = build_tree(lo, mid - 1)
        right[idx] = build_tree(mid + 1, hi)
        return idx
    if order:
        child[0] = build_tree(0, len(order) - 1)        # root.child -> goc cay stream

    # --- 3. bo tri sector thuong: [dir][minifat][ministream][FAT] ---
    dir_bytes = bytearray()
    meta_by_name = {nm: (st, sz) for nm, st, sz in stream_meta}
    # root truoc
    ndir_sects_data = []  # placeholder, build after we know mini start

    ndir = max(1, (n_entries * 128 + SECTOR - 1) // SECTOR)
    nminifat = len(minifat_bytes) // SECTOR
    nmini = len(mini_data) // SECTOR

    dir_start     = 0
    minifat_start = dir_start + ndir
    mini_start    = minifat_start + nminifat
    non_fat       = ndir + nminifat + nmini

    nfat = 1
    while True:
        total = non_fat + nfat
        if nfat * (SECTOR // 4) >= total:
            break
        nfat += 1
    fat_start = mini_start + nmini
    total_sectors = non_fat + nfat

    # bay gio dung dir bytes (can biet mini_start cho root.start)
    dir_bytes += _dir_entry("Root Entry", 5, NOSTREAM, NOSTREAM, child[0],
                            mini_start if nmini else ENDOFCHAIN, mini_used, root_clsid)
    for i in range(1, n_entries):
        nm = entries[i][0]
        st, sz = meta_by_name[nm]
        dir_bytes += _dir_entry(nm, 2, left[i], right[i], child[i], st, sz)
    if len(dir_bytes) % SECTOR:
        dir_bytes += b"\x00" * (SECTOR - len(dir_bytes) % SECTOR)
    # neu dir chiem nhieu sector hon du bao thi mo rong (hiem voi vai stream)
    ndir = len(dir_bytes) // SECTOR

    # --- 4. FAT ---
    fat = [FREESECT] * total_sectors
    def chain(start, count):
        for k in range(count):
            s = start + k
            fat[s] = (start + k + 1) if k < count - 1 else ENDOFCHAIN
    chain(dir_start, ndir)
    chain(minifat_start, nminifat)
    chain(mini_start, nmini)
    for k in range(nfat):
        fat[fat_start + k] = FATSECT
    fat_bytes = b"".join(struct.pack("<I", e) for e in fat)
    if len(fat_bytes) % SECTOR:
        fat_bytes += b"\xff" * (SECTOR - len(fat_bytes) % SECTOR)

    # --- 5. header ---
    hdr = bytearray(SECTOR)
    hdr[0:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    struct.pack_into("<H", hdr, 24, 0x003E)             # minor ver
    struct.pack_into("<H", hdr, 26, 0x0003)             # major ver (512B sectors)
    struct.pack_into("<H", hdr, 28, 0xFFFE)             # byte order
    struct.pack_into("<H", hdr, 30, 0x0009)             # sector shift = 512
    struct.pack_into("<H", hdr, 32, 0x0006)             # mini sector shift = 64
    struct.pack_into("<I", hdr, 44, nfat)               # num FAT sectors
    struct.pack_into("<I", hdr, 48, dir_start)          # first dir sector
    struct.pack_into("<I", hdr, 56, MINI_CUTOFF)        # mini stream cutoff
    struct.pack_into("<I", hdr, 60, minifat_start if nminifat else ENDOFCHAIN)
    struct.pack_into("<I", hdr, 64, nminifat)           # num mini FAT sectors
    struct.pack_into("<I", hdr, 68, ENDOFCHAIN)         # first DIFAT sector
    struct.pack_into("<I", hdr, 72, 0)                  # num DIFAT sectors
    # DIFAT (109 entries) bat dau o offset 76
    difat = [FREESECT] * 109
    for k in range(nfat):
        difat[k] = fat_start + k
    for k in range(109):
        struct.pack_into("<I", hdr, 76 + 4 * k, difat[k])

    # --- 6. ghep file: header + sector theo dung thu tu ---
    out = bytes(hdr) + bytes(dir_bytes) + minifat_bytes + bytes(mini_data) + fat_bytes
    return out


# --- cac stream chuan cua mot OLE object MathType ---
def _comp_obj_stream(prog_id="Equation.DSMT4", user_type="MathType 6.0 Equation"):
    out = bytearray()
    out += struct.pack("<I", 0xFFFFFFFE)                # reserved1
    out += struct.pack("<I", 0x00000700)               # version
    out += struct.pack("<I", 0xFFFFFFFF) + b"\x00" * 16  # reserved + clsid (toi gian)
    def lp(s):
        b = s.encode("ascii", "replace") + b"\x00"
        return struct.pack("<I", len(b)) + b
    out += lp(user_type)
    out += lp(prog_id)
    out += struct.pack("<I", 0x71B239F4)               # unicode marker
    return bytes(out)


def _ole_stream():
    s = bytearray(20)
    struct.pack_into("<I", s, 0, 0x02000001)           # version
    return bytes(s)


# --- Dinh danh CO DINH cua MathType (lay tu cong thuc that, giong nhau moi cong thuc) ---
# Nho cac hang nay, object sinh ra mo duoc bang MathType ma KHONG can file mau (--ref).
MATHTYPE_CLSID   = bytes.fromhex("03ce020000000000c000000000000046")   # 0002CE03-...
MATHTYPE_OLE     = bytes.fromhex("0100000208000000000000000000000000000000")
MATHTYPE_COMPOBJ = bytes.fromhex(
    "0100feff030a0000ffffffff03ce020000000000c0000000000000461600000"
    "04d6174685479706520372e30204571756174696f6e000c0000004d61746854"
    "797065204546000f0000004571756174696f6e2e44534d543400f439b271000"
    "00000000000000000000000")


def build_mathtype_ole(equation_native, prog_id="Equation.DSMT4", template=None):
    """Tra ve noi dung file oleObjectN.bin (CFB) chua cong thuc MathType.
    Mac dinh dung dinh danh MathType that (CLSID 0002CE03 + CompObj + Ole) nen
    Word route dung sang MathType. template (tu read_ole_template) neu muon ghi de."""
    if template:
        ole_s  = template.get("ole")     or MATHTYPE_OLE
        comp_s = template.get("compobj") or MATHTYPE_COMPOBJ
        clsid  = template.get("clsid")   or MATHTYPE_CLSID
    else:
        ole_s, comp_s, clsid = MATHTYPE_OLE, MATHTYPE_COMPOBJ, MATHTYPE_CLSID
    streams = [
        ("\x01Ole", ole_s),
        ("\x01CompObj", comp_s),
        ("Equation Native", equation_native),
    ]
    return build_cfb(streams, root_clsid=clsid)


def read_ole_template(src):
    """Doc vo OLE tu mot cong thuc MathType THAT (.bin hoac bytes):
    lay clsid goc, stream \\x01Ole, \\x01CompObj de tai su dung."""
    import olefile, uuid
    ole = olefile.OleFileIO(io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src)
    clsid_str = ole.root.clsid or "00000000-0000-0000-0000-000000000000"
    try:
        clsid = uuid.UUID(clsid_str).bytes_le
    except Exception:
        clsid = b"\x00" * 16
    ole_s  = ole.openstream("\x01Ole").read()      if ole.exists("\x01Ole") else None
    comp_s = ole.openstream("\x01CompObj").read()  if ole.exists("\x01CompObj") else None
    eqn    = ole.openstream("Equation Native").read() if ole.exists("Equation Native") else None
    ole.close()
    return {"clsid": clsid, "ole": ole_s, "compobj": comp_s, "equation_native": eqn,
            "clsid_str": clsid_str}


if __name__ == "__main__":
    import olefile, io
    from mtef_encode import (equation, text_char, sup, frac, encode_body,
                             wrap_equation_native)

    ast = equation([text_char("a"), sup([text_char("2")]), text_char("+"),
                    frac([text_char("1")], [text_char("2")])])
    eqn_native = wrap_equation_native(encode_body(ast))
    blob = build_mathtype_ole(eqn_native)
    print("oleObject.bin:", len(blob), "bytes")

    # KIEM THU: doc lai bang olefile, so sanh byte 'Equation Native'
    ole = olefile.OleFileIO(io.BytesIO(blob))
    print("streams:", ole.listdir())
    got = ole.openstream("Equation Native").read()
    print("Equation Native readback ==", got == eqn_native,
          f"({len(got)} bytes)")
    print("has \\x01CompObj:", ole.exists("\x01CompObj"))
    print("has \\x01Ole     :", ole.exists("\x01Ole"))
    ole.close()
