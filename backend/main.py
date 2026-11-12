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

# مدل‌های بینا (Vision) رایگان و قدرتمند در OpenRouter
VISION_MODELS = [
    "qwen/qwen-2-vl-7b-instruct:free",
    "openrouter/free" 
]

class PromptRequest(BaseModel):
    text: Optional[str] = None
    image_base64: Optional[str] = None

@app.get("/")
def read_root():
    return {"status": "Text-to-CAD Vision Backend is running!"}

@app.post("/generate")
def generate_from_text(req: PromptRequest):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API Key is missing.")

    system_prompt = """
    You are an expert Mechanical Engineer and OpenSCAD developer. 
    Your task is to analyze the provided engineering drawing (image) or text description and convert it into valid OpenSCAD code.
    Rules:
    1. Carefully read dimensions, annotations, and views (front, top, side) in the image.
    2. Output ONLY the OpenSCAD code. Do NOT wrap it in markdown code blocks. Do NOT output explanations.
    3. Always use `$fn=100;` at the beginning for smooth curves.
    4. Use `translate([x,y,z])` to position objects.
    5. Use `difference()` for holes and `union()` for combining parts.
    6. If the image is a 2D profile, use `linear_extrude()` or `rotate_extrude()`.
    """
    
    # ساخت پیام برای هوش مصنوعی
    user_content = []
    if req.text:
        user_content.append({"type": "text", "text": req.text})
    
    if req.image_base64:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{req.image_base64}"}
        })
        
    if not user_content:
        user_content.append({"type": "text", "text": "Please generate a simple 10x10x10 cube."})

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
    
    last_error = ""
    
    for model_name in VISION_MODELS:
        try:
            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://text-to-cad.vercel.app",
                "X-Title": "Text-to-CAD Vision"
            }
            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": 0.1
            }
            
            response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
            
            if response.status_code in [404, 429, 403, 502]:
                last_error = f"Model {model_name} unavailable: {response.status_code}"
                continue
                
            if response.status_code != 200:
                raise Exception(f"API Error {response.status_code}: {response.text}")
                
            ai_reply = response.json()['choices'][0]['message']['content']
            scad_code = re.sub(r'```(?:openscad)?\n?(.*?)```', r'\1', ai_reply, flags=re.DOTALL).strip()
            
            if not scad_code:
                raise Exception("AI returned empty code.")

            file_id = str(uuid.uuid4())
            scad_path = f"/tmp/{file_id}.scad"
            stl_path = f"/tmp/{file_id}.stl"
            
            with open(scad_path, "w") as f:
                f.write(scad_code)
                
            process = subprocess.run(["openscad-headless", "-o", stl_path, scad_path], capture_output=True, text=True)
            
            if process.returncode != 0:
                raise Exception(process.stderr)
            
            return FileResponse(stl_path, media_type="application/octet-stream", filename="model.stl")

        except Exception as e:
            last_error = str(e)
            continue
            
    raise HTTPException(status_code=500, detail=f"All AI models failed. Last error: {last_error}")
