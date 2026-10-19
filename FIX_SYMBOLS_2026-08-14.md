# Fix ký hiệu LaTeX / MathType - 2026-08-14

Các thay đổi nhỏ, không đổi font/kiểu hiển thị hiện tại:

- Preview: chuẩn hóa `\\ge -> \\geq`, `\\le -> \\leq`, `\\ne -> \\neq` để Matplotlib MathText không in nguyên lệnh LaTeX.
- MathType editable: thêm `\\perp` (và alias `\\bot`) vào MTEF, tránh mất dấu vuông góc sau khi double-click.
- Bổ sung `\\parallel`, `\\mid` cho các ký hiệu hình học thường gặp.
- Giá trị tuyệt đối: `|...|` và `\\lvert ... \\rvert` được mã hóa bằng MathType `tmBAR` fence thay vì hai ký tự text rời, giúp vạch đứng tự nhiên hơn khi mở/sửa.
- Giữ nguyên cấu hình font preview và kiểu `mathtype` hiện tại.
- Thêm regression tests trong `tests/test_symbol_fixes.py`.
