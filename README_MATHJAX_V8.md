# MathType backend V8 – MathJax preview

- MathType OLE vẫn được tạo bằng MTEF Python và vẫn nhấp đúp sửa được.
- Ảnh WMF hiển thị trong Word được render bằng MathJax SVG, font mặc định `mathjax-termes` (gần Times New Roman).
- Nếu MathJax lỗi, backend tự động dùng renderer Matplotlib cũ.

## Render

Tạo Web Service mới hoặc đổi service hiện tại sang **Docker**. Dockerfile đã cài cả Python, Node 22, MathJax và CairoSVG.

Biến môi trường mặc định:

```text
MATHTYPE_RENDER_ENGINE=mathjax
MATHTYPE_MATHJAX_FONT=mathjax-termes
MATHTYPE_FULL_PT=13
MATHTYPE_RENDER_DPI=300
MATHTYPE_BASELINE_EXTRA_PT=0.65
```

Có thể đổi font MathJax thành:

```text
MATHTYPE_MATHJAX_FONT=mathjax-stix2
```


## V8.1 - che do hybrid nhanh hon

Mac dinh: `MATHTYPE_RENDER_ENGINE=hybrid`. MathJax chi render he phuong trinh,
ma tran, tich phan, tong/tich va mot so cau truc phuc tap. Cong thuc thong thuong
dung MathText de nhanh hon. DPI mac dinh trong Docker la 240.

Co the chon:
- `hybrid`: can bang dep/toc do (khuyen dung)
- `mathjax`: MathJax cho tat ca cong thuc (dep nhat, cham nhat)
- `matplotlib`: renderer cu cho tat ca (nhanh nhat)
