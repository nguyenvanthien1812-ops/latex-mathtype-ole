r"""
app.py -- Flask API cho backend Word Equation / MathType OLE.

Phu hop bo backend MathType + MathJax V8.2 tren Render Free.

Endpoints:
  GET  /                       -> giao dien test neu co templates/index.html
  GET  /healthz                -> health check nhe
  GET  /api/renderer-info      -> xem cau hinh renderer hien tai
  GET|POST /api/warmup         -> danh thuc MathJax/renderer truoc khi xuat Word
  GET  /api/mathjax-check      -> kiem tra MathJax truc tiep, KHONG fallback
  POST /api/convert-text       -> JSON/form {"text": "..."} -> DOCX MathType
  POST /api/convert-docx       -> multipart field "file" -> DOCX MathType
  POST /api/convert-markdown   -> JSON {markdown, formula_mode} -> DOCX

Production:
  gunicorn app:app
"""

from __future__ import annotations

import io
import logging
import os
import time
import traceback
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS

from backend import convert_markdown, convert_text, convert_upload


# -----------------------------------------------------------------------------
# Cau hinh chung
# -----------------------------------------------------------------------------

DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document"
)
MAX_UPLOAD_MB = max(1, int(os.getenv("MAX_UPLOAD_MB", "25")))
ROOT_DIR = Path(__file__).resolve().parent

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mathtype-backend")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
app.config["JSON_AS_ASCII"] = False

# Chi cho phep cac frontend duoc liet ke goi API tu trinh duyet.
# Cau hinh tren Render, vi du:
# CORS_ALLOWED_ORIGINS=https://web1.vercel.app,https://web2.vercel.app
# Luu y: Origin KHONG co dau / o cuoi.
def _cors_allowed_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
    origins = [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]

    # Localhost chi duoc mo khi chu dong bat bien nay.
    allow_localhost = os.getenv("CORS_ALLOW_LOCALHOST", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }
    if allow_localhost:
        origins.extend([
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ])

    # Loai bo trung lap nhung giu nguyen thu tu.
    return list(dict.fromkeys(origins))


CORS_ALLOWED_ORIGINS = _cors_allowed_origins()

CORS(
    app,
    resources={r"/*": {"origins": CORS_ALLOWED_ORIGINS}},
    expose_headers=["X-Stats", "X-Elapsed-Ms", "Content-Disposition"],
    allow_headers="*",
    methods=["GET", "POST", "OPTIONS"],
    supports_credentials=False,
    max_age=86400,
    vary_header=True,
    always_send=False,
)

if CORS_ALLOWED_ORIGINS:
    logger.info("CORS allowed origins: %s", ", ".join(CORS_ALLOWED_ORIGINS))
else:
    logger.warning(
        "CORS_ALLOWED_ORIGINS is empty: browser cross-origin requests will be blocked"
    )


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _stats_value(stats: dict[str, Any] | None, key: str) -> int:
    try:
        return int((stats or {}).get(key, 0))
    except (TypeError, ValueError):
        return 0


def _send_docx(
    data: bytes,
    stats: dict[str, Any] | None,
    filename: str,
    started: float,
):
    """Tra DOCX kem thong ke chuyen cong thuc."""
    response = send_file(
        io.BytesIO(data),
        as_attachment=True,
        download_name=filename,
        mimetype=DOCX_MIME,
        max_age=0,
    )
    response.headers["X-Stats"] = (
        f"{_stats_value(stats, 'converted')},"
        f"{_stats_value(stats, 'failed')}"
    )
    response.headers["X-Elapsed-Ms"] = str(_elapsed_ms(started))
    response.headers["Cache-Control"] = "no-store"
    return response


def _error_response(message: str, status: int = 500, **extra: Any):
    payload: dict[str, Any] = {"ok": False, "error": message}
    payload.update(extra)
    return jsonify(payload), status


def _log_exception(context: str, exc: BaseException) -> None:
    logger.error("%s: %s\n%s", context, exc, traceback.format_exc())


def _renderer_info() -> dict[str, Any]:
    try:
        from render import render_info

        info = render_info()
        if isinstance(info, dict):
            return info
        return {"value": str(info)}
    except Exception as exc:
        return {"error": repr(exc)}


# -----------------------------------------------------------------------------
# Trang chu va health/debug
# -----------------------------------------------------------------------------

@app.get("/")
def index():
    """Hien giao dien test neu project co templates/index.html."""
    template = ROOT_DIR / "templates" / "index.html"
    if template.exists():
        return render_template("index.html")
    return jsonify(
        ok=True,
        service="MathType OLE backend",
        health="/healthz",
        warmup="/api/warmup",
        mathjax_check="/api/mathjax-check",
    )


@app.get("/healthz")
def healthz():
    """Health check that nhe, khong khoi dong MathJax."""
    return jsonify(ok=True, service="mathtype-backend")


@app.get("/api/renderer-info")
def api_renderer_info():
    return jsonify(
        ok=True,
        env={
            "engine": os.getenv("MATHTYPE_RENDER_ENGINE", "hybrid"),
            "dpi": os.getenv("MATHTYPE_RENDER_DPI", "200"),
            "full_pt": os.getenv("MATHTYPE_FULL_PT", "13"),
            "mathjax_font": os.getenv(
                "MATHTYPE_MATHJAX_FONT", "mathjax-termes"
            ),
            "mathjax_timeout": os.getenv("MATHTYPE_MATHJAX_TIMEOUT", "30"),
        },
        renderer=_renderer_info(),
    )


@app.route("/api/warmup", methods=["GET", "POST"])
def api_warmup():
    """Nap renderer truoc khi xuat Word.

    Neu engine la hybrid/mathjax, ham nay goi MathJax truc tiep de Node, font va
    CairoSVG duoc nap som. Warmup that bai van tra HTTP 200 de frontend co the
    tiep tuc; endpoint /api/mathjax-check moi tra 500 khi MathJax loi.
    """
    started = time.perf_counter()
    engine = os.getenv("MATHTYPE_RENDER_ENGINE", "hybrid").strip().lower()

    try:
        if engine in {"mathjax", "all", "hybrid", "auto"}:
            from mathjax_renderer import mathjax_info, render_mathjax

            image, width_pt, height_pt, depth_pt = render_mathjax(
                latex=(
                    r"\begin{cases}"
                    r"5x-2y=8\\"
                    r"2x+5y=9"
                    r"\end{cases}"
                ),
                full_pt=float(os.getenv("MATHTYPE_FULL_PT", "13")),
                dpi=int(os.getenv("MATHTYPE_RENDER_DPI", "200")),
                pad_px=1,
            )
            return jsonify(
                ok=True,
                elapsed_ms=_elapsed_ms(started),
                engine=engine,
                direct_mathjax=True,
                image_px={"width": image.width, "height": image.height},
                metrics_pt={
                    "width": round(width_pt, 2),
                    "height": round(height_pt, 2),
                    "depth": round(depth_pt, 2),
                },
                mathjax=mathjax_info(),
                renderer=_renderer_info(),
            )

        from render import render_formula

        image, width_pt, height_pt, depth_pt = render_formula(r"x^2+1")
        return jsonify(
            ok=True,
            elapsed_ms=_elapsed_ms(started),
            engine=engine,
            direct_mathjax=False,
            image_px={"width": image.width, "height": image.height},
            metrics_pt={
                "width": round(width_pt, 2),
                "height": round(height_pt, 2),
                "depth": round(depth_pt, 2),
            },
            renderer=_renderer_info(),
        )

    except Exception as exc:
        _log_exception("Warmup renderer failed", exc)
        # HTTP 200 de frontend khong bi chan hoan toan; backend van co fallback.
        return jsonify(
            ok=False,
            elapsed_ms=_elapsed_ms(started),
            engine=engine,
            warning=repr(exc),
            renderer=_renderer_info(),
        ), 200


@app.get("/api/mathjax-check")
def api_mathjax_check():
    """Kiem tra truc tiep MathJax, tuyet doi khong fallback sang Matplotlib."""
    started = time.perf_counter()

    try:
        from mathjax_renderer import mathjax_info, render_mathjax

        latex = request.args.get(
            "latex",
            (
                r"\begin{cases}"
                r"5x-2y=8\\"
                r"2x+5y=9"
                r"\end{cases}"
            ),
        )
        image, width_pt, height_pt, depth_pt = render_mathjax(
            latex=latex,
            full_pt=float(os.getenv("MATHTYPE_FULL_PT", "13")),
            dpi=int(os.getenv("MATHTYPE_RENDER_DPI", "200")),
            pad_px=1,
        )

        return jsonify(
            ok=True,
            elapsed_ms=_elapsed_ms(started),
            latex=latex,
            image_px={"width": image.width, "height": image.height},
            metrics_pt={
                "width": round(width_pt, 2),
                "height": round(height_pt, 2),
                "depth": round(depth_pt, 2),
            },
            mathjax=mathjax_info(),
        )

    except Exception as exc:
        _log_exception("Direct MathJax check failed", exc)
        return _error_response(
            repr(exc),
            status=500,
            elapsed_ms=_elapsed_ms(started),
            renderer=_renderer_info(),
        )


# -----------------------------------------------------------------------------
# Convert endpoints
# -----------------------------------------------------------------------------

@app.post("/api/convert-text")
def api_convert_text():
    started = time.perf_counter()

    if request.is_json:
        body = request.get_json(silent=True) or {}
        text = str(body.get("text", ""))
    else:
        text = request.form.get("text", "")

    if not text.strip():
        return _error_response("Văn bản trống.", status=400)

    try:
        data, stats = convert_text(text, log=logger.info)
        return _send_docx(
            data,
            stats,
            "cong_thuc_mathtype.docx",
            started,
        )
    except Exception as exc:
        _log_exception("convert-text failed", exc)
        return _error_response(
            f"Lỗi chuyển đổi: {exc}",
            status=500,
            elapsed_ms=_elapsed_ms(started),
        )


@app.post("/api/convert-docx")
def api_convert_docx():
    started = time.perf_counter()
    uploaded = request.files.get("file")

    if uploaded is None or not uploaded.filename:
        return _error_response("Chưa chọn file .docx.", status=400)
    if not uploaded.filename.lower().endswith(".docx"):
        return _error_response("Chỉ nhận file .docx.", status=400)

    try:
        source = uploaded.read()
        if not source:
            return _error_response("File Word trống.", status=400)

        data, stats = convert_upload(source, log=logger.info)
        base = os.path.splitext(os.path.basename(uploaded.filename))[0]
        return _send_docx(
            data,
            stats,
            f"{base}_mathtype.docx",
            started,
        )
    except Exception as exc:
        _log_exception("convert-docx failed", exc)
        return _error_response(
            f"Lỗi chuyển đổi: {exc}",
            status=500,
            elapsed_ms=_elapsed_ms(started),
        )


@app.post("/api/convert-markdown")
def api_convert_markdown():
    started = time.perf_counter()
    body = request.get_json(silent=True) or {}

    markdown_text = str(body.get("markdown", ""))
    formula_mode = str(body.get("formula_mode", "mathtype")).lower().strip()
    if formula_mode not in {"latex", "omml", "mathtype"}:
        formula_mode = "mathtype"

    if not markdown_text.strip():
        return _error_response("Nội dung trống.", status=400)

    try:
        data, stats = convert_markdown(
            markdown_text,
            formula_mode=formula_mode,
            log=logger.info,
        )
        return _send_docx(
            data,
            stats,
            f"tai_lieu_{formula_mode}.docx",
            started,
        )
    except Exception as exc:
        _log_exception("convert-markdown failed", exc)
        return _error_response(
            f"Lỗi chuyển đổi: {exc}",
            status=500,
            elapsed_ms=_elapsed_ms(started),
        )


# -----------------------------------------------------------------------------
# Error handlers
# -----------------------------------------------------------------------------

@app.errorhandler(413)
def too_large(_error):
    return _error_response(
        f"File vượt quá giới hạn {MAX_UPLOAD_MB} MB.",
        status=413,
    )


@app.errorhandler(404)
def not_found(_error):
    return _error_response("Không tìm thấy endpoint.", status=404)


@app.errorhandler(500)
def internal_error(error):
    logger.error("Unhandled Flask error: %s", error)
    return _error_response("Lỗi nội bộ backend.", status=500)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
