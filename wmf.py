r"""
wmf.py -- Boc mot anh raster (PIL Image) thanh Placeable WMF.

Word ve duoc WMF trong <w:object> (PNG thi khong), nen anh xem truoc phai la
WMF/EMF giong cong thuc MathType that. Ham raster_to_wmf nhung anh raster vao
mot record META_STRETCHDIB.
"""
import struct


def raster_to_wmf(img):
    """img: PIL.Image (RGB). Tra ve bytes WMF (placeable)."""
    img = img.convert("RGB")
    w, h = img.size
    px = img.load()

    # --- DIB (bottom-up, 24bpp, moi hang padding 4 byte) ---
    rowsize = (w * 3 + 3) & ~3
    pixels = bytearray()
    for y in range(h - 1, -1, -1):
        row = bytearray()
        for x in range(w):
            r, g, b = px[x, y]
            row += bytes((b, g, r))
        row += b"\x00" * (rowsize - w * 3)
        pixels += row
    bih = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(pixels), 0, 0, 0, 0)
    dib = bih + bytes(pixels)

    def record(func, params):
        if len(params) % 2:
            params += b"\x00"
        size_words = 3 + len(params) // 2          # rdSize(2w) + rdFunction(1w) + params
        return struct.pack("<IH", size_words, func) + params

    # SetWindowOrg(0,0), SetWindowExt(w,h), StretchDIBits, EOF
    rec_org = record(0x020B, struct.pack("<hh", 0, 0))             # y,x
    rec_ext = record(0x020C, struct.pack("<hh", h, w))            # height,width
    sdib_params = (struct.pack("<I", 0x00CC0020) +               # SRCCOPY
                   struct.pack("<H", 0) +                         # ColorUsage
                   struct.pack("<HHHH", h, w, 0, 0) +             # Src H,W,Y,X
                   struct.pack("<HHHH", h, w, 0, 0) +             # Dst H,W,y,x
                   dib)
    rec_dib = record(0x0F43, sdib_params)
    rec_eof = record(0x0000, b"")
    records = rec_org + rec_ext + rec_dib + rec_eof

    max_record = max(len(rec_org), len(rec_ext), len(rec_dib), len(rec_eof)) // 2
    # METAHEADER (18 byte)
    total_words = 9 + len(records) // 2
    metaheader = struct.pack("<HHHIHIH", 1, 9, 0x0300, total_words, 0, max_record, 0)

    # Placeable header (22 byte)
    left, top, right, bottom, inch = 0, 0, w, h, 96
    ph = struct.pack("<IHhhhhHIH", 0x9AC6CDD7, 0, left, top, right, bottom, inch, 0, 0)
    # checksum = XOR cua 10 WORD dau (20 byte dau, khong tinh o checksum)
    chk = 0
    for i in range(0, 20, 2):
        chk ^= struct.unpack("<H", ph[i:i + 2])[0]
    ph = ph[:20] + struct.pack("<H", chk)

    return ph + metaheader + records


if __name__ == "__main__":
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (120, 80), "white")
    d = ImageDraw.Draw(im); d.line((10, 40, 110, 40), fill="black", width=3)
    d.text((20, 10), "-15", fill="black"); d.text((30, 50), "27", fill="black")
    open("/home/claude/test.wmf", "wb").write(raster_to_wmf(im))
    print("wrote test.wmf")
