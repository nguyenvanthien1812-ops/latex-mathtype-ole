# LaTeX → MathType (Word) — web service

Chuyển công thức LaTeX bọc trong `$...$` thành **đối tượng MathType OLE** thật trong
file Word: mở trong Word thì công thức hiển thị sẵn, double-click sửa được bằng MathType.

Hỗ trợ 2 dạng đầu vào:
- **Dán văn bản** có `$...$` → tải về `.docx`.
- **Tải file Word** `.docx` chứa `$...$` → tải về bản đã chuyển.

Không cần MathType khi chuyển; định danh MathType (CLSID `0002CE03` + CompObj) đã nhúng sẵn.

## Chạy thử ở máy
```bash
pip install -r requirements.txt
python app.py
# mở http://localhost:5000
```

## Cấu trúc
```
app.py            Flask web service (2 endpoint + giao diện)
templates/index.html   giao diện test (có xem trước MathJax)
backend.py        convert_text(...) / convert_upload(...)
api.py            API cấp thấp cho tích hợp khác
docx_convert.py   tìm $...$ trong docx, nhúng MathType OLE
latex2mtef.py     LaTeX → cây MtAST
mtef_encode.py    AST → bytes MTEF v5 (+ preamble/header chuẩn DSMT7)
cfb.py            ghi Compound File (OLE2) + định danh MathType
wmf.py            bọc ảnh xem trước thành WMF (Word vẽ được)
render.py         render công thức (matplotlib mathtext)
record.py         enum/lớp dữ liệu MTEF
tests/            test không cần Word (6/6)
gui.py, cli.py    bản desktop (tùy chọn; cần requirements-desktop.txt)
```

## Endpoint
| Method | Path | Vào | Ra |
|--------|------|-----|-----|
| GET  | `/`                  | — | giao diện |
| POST | `/api/convert-text`  | JSON `{"text": "..."}` | `.docx` |
| POST | `/api/convert-docx`  | multipart, field `file` | `.docx` |
| GET  | `/healthz`           | — | `ok` |

Header `X-Stats: "converted,failed"` trên mỗi phản hồi file.

## Đưa lên GitHub
```bash
git init
git add .
git commit -m "LaTeX to MathType Word service"
git branch -M main
git remote add origin https://github.com/<bạn>/<repo>.git
git push -u origin main
```

## Deploy lên Render
**Cách 1 — Blueprint (có sẵn `render.yaml`):**
1. Render Dashboard → **New** → **Blueprint**.
2. Kết nối repo GitHub vừa push. Render đọc `render.yaml` và tạo web service.
3. Bấm **Apply**. Chờ build xong → mở URL `https://<tên>.onrender.com`.

**Cách 2 — tạo Web Service thủ công:**
1. **New** → **Web Service** → chọn repo.
2. Runtime: **Python 3**.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `gunicorn app:app --timeout 120 --workers 2`
5. Thêm env (tùy chọn): `MPLBACKEND=Agg`, `PYTHON_VERSION=3.11.9`.
6. **Create Web Service**.

Gói free của Render sẽ "ngủ" khi không dùng; request đầu tiên sau khi ngủ mất ~30–60s để khởi động lại.

## Ghi chú
- Ảnh xem trước render bằng matplotlib mathtext rồi bọc WMF; nếu công thức quá lạ,
  ảnh có thể giản lược nhưng đối tượng MathType (mở bằng double-click) vẫn đúng.
- Giới hạn upload mặc định 25MB (`MAX_CONTENT_LENGTH` trong `app.py`).
- Phase 2 (chưa làm): ma trận, dấu phụ `\hat \vec \dot`, `$$...$$` (display math).
```
```
