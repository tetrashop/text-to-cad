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

app = FastAPI(title="Text-to-CAD Pro Vision Engine")

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
    return {"status": "Text-to-CAD Pro Backend is running!"}

@app.post("/generate")
def generate_from_text(req: PromptRequest):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API Key is missing.")

    if req.mode == "architectural":
        system_prompt = """
        You are an expert Architectural CAD modeler. Convert 2D floor plans into 3D OpenSCAD models.
        RULES:
        1. Create a base floor.
        2. Create walls and use `linear_extrude(height=30)` to raise them.
        3. Leave rooms EMPTY.
        4. **DOORS/WINDOWS:** Use `difference()` to subtract cubes from the walls to create doorways. Do NOT leave them solid.
        5. Output ONLY OpenSCAD code. Use `$fn=100`.
        """
    else:
        system_prompt = """
        You are an expert Mechanical Engineer. Convert drawings into OpenSCAD code.
        RULES:
        1. Use `translate([x,y,z])` for positioning.
        2. Use `difference()` for holes, `union()` for merging.
        3. Output ONLY OpenSCAD code. Use `$fn=100`.
        """
    
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
    
    for model_name in VISION_MODELS:
        # سیستم خودترمیم (تا ۳ بار تلاش مجدد در صورت خطای کد OpenSCAD)
        for attempt in range(3):
            try:
                headers = {
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://text-to-cad.vercel.app",
                    "X-Title": "Text-to-CAD Pro"
                }
                payload = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": 0.1
                }
                
                response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
                
                if response.status_code in [404, 429, 403, 502]:
                    last_error = f"Model {model_name} unavailable: {response.status_code}"
                    break # برو سراغ مدل بعدی
                    
                if response.status_code != 200:
                    raise Exception(f"API Error {response.status_code}")
                    
                ai_reply = response.json()['choices'][0]['message']['content']
                scad_code = re.sub(r'```(?:openscad)?\n?(.*?)```', r'\1', ai_reply, flags=re.DOTALL).strip()
                
                if not scad_code:
                    raise Exception("Empty code.")

                file_id = str(uuid.uuid4())
                scad_path = f"/tmp/{file_id}.scad"
                stl_path = f"/tmp/{file_id}.stl"
                
                with open(scad_path, "w") as f:
                    f.write(scad_code)
                    
                process = subprocess.run(["openscad-headless", "-o", stl_path, scad_path], capture_output=True, text=True)
                
                if process.returncode != 0:
                    # سیستم خودترمیم: خطای OpenSCAD را به هوش مصنوعی می‌دهیم تا کد را اصلاح کند
                    raise Exception(process.stderr)
                
                return FileResponse(stl_path, media_type="application/octet-stream", filename="model.stl")

            except Exception as e:
                last_error = str(e)
                print(f"Attempt {attempt+1} failed: {last_error}")
                # اگر AI کدی تولید کرده بود اما خطا داشت، خطا را به آن برمی‌گردانیم
                if 'ai_reply' in locals() and ai_reply:
                    messages.append({"role": "assistant", "content": ai_reply})
                    messages.append({"role": "user", "content": f"Your OpenSCAD code failed with this error: {last_error}. Please fix the code and output ONLY the corrected code."})
                else:
                    break # اگر اصلا کدی تولید نشد، برو سراغ مدل بعدی
            
    raise HTTPException(status_code=500, detail=f"All models failed. Last error: {last_error}")
