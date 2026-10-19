FROM node:22-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=10000 \
    MATHTYPE_RENDER_ENGINE=hybrid \
    MATHTYPE_MATHJAX_FONT=mathjax-termes \
    MATHTYPE_FULL_PT=13 \
    MATHTYPE_RENDER_DPI=200

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip \
      libcairo2 libpango-1.0-0 libgdk-pixbuf-2.0-0 shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund

COPY requirements.txt ./
RUN python3 -m venv /opt/venv \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 2 --timeout 300 --graceful-timeout 30 --keep-alive 10"]
