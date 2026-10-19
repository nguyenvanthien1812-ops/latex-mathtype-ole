# CORS whitelist cho frontend Vercel

Backend da doi tu `Access-Control-Allow-Origin: *` sang danh sach domain duoc phep.

## Cau hinh tren Render

Them Environment Variable:

```text
CORS_ALLOWED_ORIGINS=https://web1.vercel.app,https://web2.vercel.app
```

Quy tac:

- Moi origin cach nhau bang dau phay.
- Khong them dau `/` o cuoi domain.
- Can ghi day du `https://`.
- Neu co custom domain, them domain do vao danh sach.
- Sau khi sua bien moi truong, deploy/restart service Render.

Vi du:

```text
CORS_ALLOWED_ORIGINS=https://latex-online-2026.vercel.app,https://de-thi-online.vercel.app
```

## Vercel Preview Deployment

Neu moi lan deploy Preview Vercel tao mot hostname moi, whitelist exact domain se khong tu dong cho phep hostname moi. De an toan, nen:

1. Dung Production Domain on dinh cua tung project trong whitelist; hoac
2. Gan custom domain on dinh cho frontend.

Khong nen cho phep toan bo `*.vercel.app` neu muc tieu la chi cho mot so website cu the goi API.

## Test

Origin hop le se nhan header:

```text
Access-Control-Allow-Origin: https://web1.vercel.app
```

Origin khong nam trong whitelist se khong nhan header `Access-Control-Allow-Origin`, vi vay trinh duyet se chan request.

## Test local (tuy chon)

Neu can frontend local Vite/React goi backend Render, dat them:

```text
CORS_ALLOW_LOCALHOST=true
```

Production nen de `false`.
