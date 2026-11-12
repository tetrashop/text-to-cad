FROM python:3.11-slim

# نصب OpenSCAD و پیش‌نیازهای گرافیکی آن در محیط لینوکس
RUN apt-get update && apt-get install -y \
    openscad \
    libgl1-mesa-glx \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# تنظیم پوشه کاری
WORKDIR /app

# کپی و نصب پکیج‌های پایتون
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی کردن بقیه فایل‌ها
COPY . .

# اجرای برنامه (Render از متغیر PORT استفاده می‌کند)
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
