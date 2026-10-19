# Render Web Service - nhập Environment Variables thủ công

Bản này dành cho **Web Service Render hiện có**. Không cần tạo Blueprint mới và không đổi sang Docker.

## Deploy

- Giữ service Render hiện tại và URL hiện tại.
- Ghi đè source này vào repository GitHub cũ / branch đang kết nối với Render.
- Render: **Manual Deploy -> Deploy latest commit** (hoặc để Auto Deploy chạy).
- Nếu build cache gây lỗi: **Clear build cache & deploy**.

## Environment Variables nên nhập trên Render

### CORS (bắt buộc nếu frontend khác origin)

```text
CORS_ALLOWED_ORIGINS=https://web1.vercel.app,https://web2.vercel.app
CORS_ALLOW_LOCALHOST=false
```

- Nhiều origin ngăn cách bằng dấu phẩy.
- Không thêm dấu `/` ở cuối origin.
- Để test local có thể đặt `CORS_ALLOW_LOCALHOST=true`.

### MathType / MathJax

```text
MATHTYPE_RENDER_ENGINE=hybrid
MATHTYPE_RENDER_DPI=200
MATHTYPE_FULL_PT=13
MATHTYPE_MATHJAX_FONT=mathjax-termes
MATHTYPE_MATHJAX_TIMEOUT=30
MATHTYPE_MATHJAX_PERSISTENT=true
MATHTYPE_NODE_HEAP_MB=256
```

Các biến tùy chọn khác (code đã có giá trị mặc định):

```text
MATHTYPE_RENDER_PAD_PX=1
MATHTYPE_BASELINE_EXTRA_PT=0.65
MATHTYPE_OBJECT_WIDTH_SCALE=1.0
MATHTYPE_OBJECT_HEIGHT_SCALE=1.0
MATHTYPE_PREVIEW_STYLE=mathtype
```

## Lưu ý về Node/MathJax

Service hiện tại vẫn dùng Render native Python như trước. Nếu môi trường runtime không có Node/MathJax khả dụng, backend vẫn có cơ chế fallback renderer cũ. Không cần đổi kiểu service chỉ để áp dụng CORS whitelist.
