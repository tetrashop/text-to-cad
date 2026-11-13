from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import subprocess
import uuid
import os
import requests
import re

app = FastAPI(title="Text-to-CAD Pro Dual Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("OPENROUTER_API_KEY")
API_URL = "https://openrouter.ai/api/v1/chat/completions"

VISION_MODELS = [
    "qwen/qwen-2-vl-7b-instruct:free",
    "openrouter/free" 
]

class PromptRequest(BaseModel):
    text: Optional[str] = None
    image_base64: Optional[str] = None
    mode: Optional[str] = "mechanical"

@app.get("/")
def read_root():
    return {"status": "Text-to-CAD Dual Engine is running!"}

# --- تابع کمکی برای اجرای کد CadQuery به صورت ایزوله (Sandbox) ---
def execute_cadquery(code: str, stl_path: str) -> bool:
    try:
        # کد را در یک فایل موقت پایتون می‌نویسیم
        file_id = str(uuid.uuid4())
        py_path = f"/tmp/{file_id}.py"
        
        # به کد AI دستور خروجی گرفتن را اضافه می‌کنیم
        full_code = f"""
import cadquery as cq
{code}
try:
    cq.exporters.export(result, "{stl_path}")
except NameError:
    print("Error: The AI did not define a 'result' variable.")
    exit(1)
"""
        with open(py_path, "w") as f:
            f.write(full_code)
            
        # اجرای کد پایتون در یک پروسه جداگانه برای جلوگیری از کرش سرور اصلی
        process = subprocess.run(["python", py_path], capture_output=True, text=True, timeout=30)
        
        if process.returncode != 0:
            print("CadQuery Execution Failed:", process.stderr)
            return False
            
        return os.path.exists(stl_path)
    except Exception as e:
        print("CadQuery Sandbox Error:", str(e))
        return False

@app.post("/generate")
def generate_from_text(req: PromptRequest):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API Key is missing.")

    # --- 1. تنظیم پرامپت‌ها ---
    if req.mode == "architectural":
        # پرامپت معماری (برای OpenSCAD)
        system_prompt = """
        You are an expert Architectural CAD modeler. Convert 2D floor plans into 3D OpenSCAD models.
        RULES:
        1. Create a base floor.
        2. Create walls and use `linear_extrude(height=30)` to raise them.
        3. Leave rooms EMPTY.
        4. **DOORS/WINDOWS:** Use `difference()` to subtract cubes from the walls.
        5. Output ONLY OpenSCAD code. Use `$fn=100`.
        """
        use_cadquery = False
    else:
        # پرامپت مکانیک (ابتدا CadQuery را امتحان می‌کنیم)
        system_prompt = """
        You are an expert Mechanical Engineer using Python and CadQuery. Convert drawings into valid CadQuery Python scripts.
        RULES:
        1. ALWAYS `import cadquery as cq`.
        2. The final solid MUST be assigned to a variable named `result`.
        3. Use `.cut()` for holes, `.union()` for merging.
        4. Use `translate` or `.translate()` to position objects.
        5. Output ONLY the Python code. Do NOT wrap in markdown.
        """
        use_cadquery = True

    # --- 2. آماده‌سازی پیام برای AI ---
    user_content = []
    if req.text:
        user_content.append({"type": "text", "text": req.text})
    if req.image_base64:
        user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{req.image_base64}"}})
        
    if not user_content:
        user_content.append({"type": "text", "text": "Generate a 10x10x10 cube."})

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
    
    last_error = ""
    
    # --- 3. درخواست از هوش مصنوعی ---
    for model_name in VISION_MODELS:
        try:
            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://text-to-cad.vercel.app",
                "X-Title": "Text-to-CAD Dual"
            }
            payload = {"model": model_name, "messages": messages, "temperature": 0.1}
            
            response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
            
            if response.status_code in [404, 429, 403, 502]:
                last_error = f"Model {model_name} unavailable."
                continue
                
            if response.status_code != 200:
                raise Exception("API Error")
                
            ai_reply = response.json()['choices'][0]['message']['content']
            # پاکسازی کد از مارک‌داون
            clean_code = re.sub(r'```(?:python|openscad)?\n?(.*?)```', r'\1', ai_reply, flags=re.DOTALL).strip()
            
            file_id = str(uuid.uuid4())
            stl_path = f"/tmp/{file_id}.stl"

            # --- 4. سیستم دوگانه (Dual-Engine) ---
            if use_cadquery:
                # تلاش اول: CadQuery
                success = execute_cadquery(clean_code, stl_path)
                if success:
                    return FileResponse(stl_path, media_type="application/octet-stream", filename="model.stl")
                
                # اگر CadQuery شکست خورد، لاگ می‌کنیم و به سراغ OpenSCAD می‌رویم (Fallback)
                print("CadQuery failed. Falling back to OpenSCAD...")
                # تغییر پرامپت به OpenSCAD برای تلاش دوم
                messages[0]["content"] = "You are an OpenSCAD expert. Output ONLY OpenSCAD code. Use difference() for holes."
                messages.append({"role": "assistant", "content": ai_reply})
                messages.append({"role": "user", "content": "The previous code failed. Please write this as OpenSCAD code instead."})
                
                response2 = requests.post(API_URL, headers=headers, json={"model": model_name, "messages": messages}, timeout=60)
                if response2.status_code == 200:
                    ai_reply2 = response2.json()['choices'][0]['message']['content']
                    scad_code = re.sub(r'```(?:openscad)?\n?(.*?)```', r'\1', ai_reply2, flags=re.DOTALL).strip()
                    
                    scad_path = f"/tmp/{file_id}.scad"
                    with open(scad_path, "w") as f: f.write(scad_code)
                    
                    process = subprocess.run(["openscad-headless", "-o", stl_path, scad_path], capture_output=True, text=True)
                    if process.returncode == 0:
                        return FileResponse(stl_path, media_type="application/octet-stream", filename="model.stl")
                    else:
                        last_error = process.stderr

            else:
                # مسیر مستقیم OpenSCAD (برای معماری)
                scad_path = f"/tmp/{file_id}.scad"
                with open(scad_path, "w") as f: f.write(clean_code)
                
                process = subprocess.run(["openscad-headless", "-o", stl_path, scad_path], capture_output=True, text=True)
                if process.returncode != 0:
                    raise Exception(process.stderr)
                    
                return FileResponse(stl_path, media_type="application/octet-stream", filename="model.stl")

        except Exception as e:
            last_error = str(e)
            print(f"Error with {model_name}: {last_error}")
            continue
            
    raise HTTPException(status_code=500, detail=f"Both engines failed. Last error: {last_error}")
