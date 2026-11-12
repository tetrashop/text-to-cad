from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess
import uuid
import os
import requests
import re

# 1. تعریف اپلیکیشن FastAPI (حل مشکل NameError)
app = FastAPI(title="Text-to-CAD Pro AI Engine")

# 2. فعال‌سازی CORS برای اجازه دادن به Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. خواندن کلید API از تنظیمات Render (Environment Variables)
API_KEY = os.getenv("OPENROUTER_API_KEY")
API_URL = "https://openrouter.ai/api/v1/chat/completions"

FALLBACK_MODELS = [
    "openrouter/free",
    "cohere/north-mini-code:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-26b-a4b-it:free"
]

class PromptRequest(BaseModel):
    text: str

@app.get("/")
def read_root():
    return {"status": "Text-to-CAD Backend is running perfectly!"}

@app.post("/generate")
def generate_from_text(req: PromptRequest):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API Key is missing in Render Environment Variables.")

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
    
    for model_name in FALLBACK_MODELS:
        try:
            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://text-to-cad.vercel.app",
                "X-Title": "Text-to-CAD Render"
            }
            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": 0.1
            }
            
            response = requests.post(API_URL, headers=headers, json=payload, timeout=45)
            
            if response.status_code in [404, 429, 403, 502]:
                last_error = f"Model {model_name} unavailable: {response.status_code}"
                continue
                
            if response.status_code != 200:
                raise Exception(f"API Error {response.status_code}: {response.text}")
                
            ai_reply = response.json()['choices'][0]['message']['content']
            
            scad_code = re.sub(r'```(?:openscad)?\n?(.*?)```', r'\1', ai_reply, flags=re.DOTALL).strip()
            
            if not scad_code or "error" in scad_code.lower():
                raise Exception("AI returned invalid or empty code.")

            file_id = str(uuid.uuid4())
            # در محیط Docker، پوشه /tmp همیشه در دسترس و قابل نوشتن است
            scad_path = f"/tmp/{file_id}.scad"
            stl_path = f"/tmp/{file_id}.stl"
            
            with open(scad_path, "w") as f:
                f.write(scad_code)
                
            # استفاده از دستور اختصاصی که در Dockerfile ساختیم
            process = subprocess.run(["openscad-headless", "-o", stl_path, scad_path], capture_output=True, text=True)
            
            if process.returncode != 0:
                raise Exception(process.stderr)
            
            return FileResponse(stl_path, media_type="application/octet-stream", filename="model.stl")

        except Exception as e:
            last_error = str(e)
            continue
            
    raise HTTPException(status_code=500, detail=f"All AI models failed. Last error: {last_error}")
