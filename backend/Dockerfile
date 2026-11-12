FROM python:3.11-slim

# نصب OpenSCAD و پیش‌نیازهای گرافیکی مجازی (Xvfb) برای اجرای Headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    openscad \
    xvfb \
    xauth \
    libgl1 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# ساخت یک اسکریپت کمکی برای اینکه OpenSCAD بدون نیاز به نمایشگر فیزیکی اجرا شود
RUN printf '%s\n' \
    '#!/usr/bin/env sh' \
    'set -eu' \
    'if command -v xvfb-run >/dev/null 2>&1 && command -v xauth >/dev/null 2>&1; then' \
    '  exec xvfb-run -a /usr/bin/openscad "$@"' \
    'fi' \
    'export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-minimal}"' \
    'exec /usr/bin/openscad "$@"' \
    > /usr/local/bin/openscad-headless \
    && chmod +x /usr/local/bin/openscad-headless

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render از متغیر PORT استفاده می‌کند
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
