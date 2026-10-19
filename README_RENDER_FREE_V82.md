# V8.2 - toi uu Render Free

- Render Free: 512 MB RAM, 0.1 CPU, spin-down sau 15 phut.
- DPI mac dinh: 200.
- MathJax chi dung cho cases/matrix/integral va cau truc phuc tap; sum/prod dung MathText nhanh.
- Gunicorn timeout: 300 giay, 1 worker, 2 threads.
- Endpoint moi: GET/POST /api/warmup.

Frontend nen xu ly theo thu tu:
1. GET /healthz voi timeout 120 giay.
2. GET /api/warmup voi timeout 120 giay.
3. POST /api/convert-markdown voi timeout 300 giay.

Khong co package-lock.json.
