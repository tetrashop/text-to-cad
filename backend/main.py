from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import subprocess
import uuid
import os
import requests
import re

API_KEY = os.getenv("OPENROUTER_API_KEY", "sk-or-v1-YOUR_KEY_HERE")
API_URL = "https://openrouter.ai/api/v1/chat/completions"

# لیست بهترین مدل‌های رایگان فعلی OpenRouter (اگر یکی 404 داد، بعدی امتحان می‌شود)
FALLBACK_MODELS = [
    "openrouter/free",                      # روتر خودکار (توصیه می‌شود)
    "cohere/north-mini-code:free",          # بهینه‌شده برای کدنویسی
    "nvidia/nemotron-3-ultra-550b-a55b:free", # مدل قدرتمند Nvidia
    "google/gemma-4-26b-a4b-it:free"        # مدل سریع گوگل
]

class PromptRequest(BaseModel):
    text: str

@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "index.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>خطا: فایل index.html پیدا نشد.</h1>"

@app.post("/generate")
def generate_from_text(req: PromptRequest):
    system_prompt = """
    You are an expert OpenSCAD developer. Your ONLY task is to convert the user's Persian description into valid OpenSCAD code.
    Rules:
    1. Output ONLY the OpenSCAD code. Do NOT wrap it in markdown code blocks. Do NOT output any explanations.
    2. Always use `$fn=100;` at the beginning for smooth curves.
    3. Use `translate([x,y,z])` to position objects precisely.
    4. Use `difference()` to subtract volumes and `union()` to merge them.
    5. Pay close attention to the Z-axis.
    """
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": req.text}
    ]
    
    last_error = ""
    
    # تلاش با مدل‌های مختلف
    for model_name in FALLBACK_MODELS:
        print(f"\n--- تلاش با مدل: {model_name} ---")
        
        try:
            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "Text-to-CAD Local"
            }
            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": 0.1
            }
            
            # درخواست به هوش مصنوعی
            response = requests.post(API_URL, headers=headers, json=payload, timeout=45)
            
            # اگر مدل 404 یا 429 بود، برو سراغ مدل بعدی
            if response.status_code in [404, 429, 403, 502]:
                last_error = f"Model {model_name} unavailable: {response.status_code}"
                print(f"❌ {last_error}")
                continue # برو سراغ حلقه بعدی (مدل بعدی)
                
            if response.status_code != 200:
                raise Exception(f"API Error {response.status_code}: {response.text}")
                
            ai_reply = response.json()['choices'][0]['message']['content']
            
            # استخراج کد OpenSCAD
            scad_code = re.sub(r'```(?:openscad)?\n?(.*?)```', r'\1', ai_reply, flags=re.DOTALL).strip()
            
            if not scad_code or "error" in scad_code.lower():
                raise Exception("AI returned invalid or empty code.")

            # ذخیره و اجرای OpenSCAD
            file_id = str(uuid.uuid4())
            temp_dir = os.path.join(os.getcwd(), "temp_files")
            os.makedirs(temp_dir, exist_ok=True)
            
            scad_path = os.path.join(temp_dir, f"{file_id}.scad")
            stl_path = os.path.join(temp_dir, f"{file_id}.stl")
            
            with open(scad_path, "w") as f:
                f.write(scad_code)
                
            process = subprocess.run(["openscad", "-o", stl_path, scad_path], capture_output=True, text=True)
            
            if process.returncode != 0:
                raise Exception(process.stderr)
            
            # اگر موفق بود، فایل STL را برمی‌گردانیم
            print(f"✅ مدل با موفقیت توسط {model_name} ساخته شد.")
            return FileResponse(stl_path, media_type="application/octet-stream", filename="model.stl")

        except Exception as e:
            last_error = str(e)
            print(f"❌ خطا در این مدل: {last_error}")
            continue # برو سراغ مدل بعدی در لیست
            
    # اگر تمام مدل‌ها شکست خوردند
    raise HTTPException(status_code=500, detail=f"All AI models failed. Last error: {last_error}")
