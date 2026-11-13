FROM python:3.11-slim

# 1. نصب OpenSCAD و پیش‌نیازهای گرافیکی مجازی برای معماری
RUN apt-get update && apt-get install -y --no-install-recommends \
    openscad \
    xvfb \
    xauth \
    libgl1 \
    libglib2.0-0 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# ساخت اسکریپت کمکی Headless
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

# 2. نصب کتابخانه‌های پایتون (اضافه شدن CadQuery)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD uvicorn main:app --host 0.0.0.0 --port $PORT
