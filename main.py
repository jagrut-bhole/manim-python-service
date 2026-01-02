from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from validator import validate_code, extract_scene_name
from executor import execute_manim_code, cleanup_temp_dir
from s3_uploader import S3Uploader 

load_dotenv()

app = FastAPI(title="Manim Renderer Service")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize S3 uploader
s3_uploader = S3Uploader() 

class RenderRequest(BaseModel):
    code: str
    quality: str = "l"

from typing import Optional

class RenderResponse(BaseModel):
    success: bool
    message: str
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[float] = None
    error: Optional[str] = None

@app.get("/")
def root():
    return {"service": "Manim Renderer", "status": "running"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/execute", response_model=RenderResponse)
async def execute_code(request: RenderRequest):
    """Execute Manim code and upload to S3"""
    
    # Validate
    is_valid, error_msg = validate_code(request.code)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    scene_name = extract_scene_name(request.code)
    if not scene_name:
        raise HTTPException(status_code=400, detail="Scene class not found")
    
    print(f"Executing scene: {scene_name}")
    
    # Execute
    result = execute_manim_code(
        code=request.code,
        scene_name=scene_name,
        quality=request.quality
    )
    
    if not result['success']:
        raise HTTPException(status_code=500, detail=result['error'])
    
    video_path = result['video_path']
    thumbnail_path = result.get('thumbnail_path')
    temp_dir = result['temp_dir']
    
    try:
        # Upload to S3
        print("Uploading to S3...")
        upload_result = s3_uploader.upload_video_and_thumbnail(
            video_path=video_path,
            thumbnail_path=thumbnail_path
        )
        
        print(f"Upload complete! Video: {upload_result['video_url']}")
        
        return RenderResponse(
            success=True,
            message="Video rendered and uploaded successfully",
            video_url=upload_result['video_url'],
            thumbnail_url=upload_result.get('thumbnail_url'),
            duration=result.get('duration', 0)
        )
        
    except Exception as e:
        print(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
        
    finally:
        # Cleanup
        cleanup_temp_dir(temp_dir)


# Async rendering with webhook callback
class AsyncRenderRequest(BaseModel):
    code: str
    quality: str = "l"
    animation_id: str
    webhook_url: str

import httpx
from fastapi import BackgroundTasks

async def process_render_job(
    code: str, 
    quality: str, 
    animation_id: str, 
    webhook_url: str
):
    """Background task to render video and call webhook when done"""
    
    result_data = {
        "animation_id": animation_id,
        "success": False,
        "video_url": None,
        "thumbnail_url": None,
        "duration": None,
        "error": None
    }
    
    try:
        # Validate code
        is_valid, error_msg = validate_code(code)
        if not is_valid:
            result_data["error"] = error_msg
            await send_webhook(webhook_url, result_data)
            return
        
        scene_name = extract_scene_name(code)
        if not scene_name:
            result_data["error"] = "Scene class not found"
            await send_webhook(webhook_url, result_data)
            return
        
        print(f"[Async] Executing scene: {scene_name} for animation {animation_id}")
        
        # Execute manim
        result = execute_manim_code(
            code=code,
            scene_name=scene_name,
            quality=quality
        )
        
        if not result['success']:
            result_data["error"] = result['error']
            await send_webhook(webhook_url, result_data)
            return
        
        video_path = result['video_path']
        thumbnail_path = result.get('thumbnail_path')
        temp_dir = result['temp_dir']
        
        try:
            # Upload to S3
            print(f"[Async] Uploading to S3 for animation {animation_id}...")
            upload_result = s3_uploader.upload_video_and_thumbnail(
                video_path=video_path,
                thumbnail_path=thumbnail_path
            )
            
            result_data["success"] = True
            result_data["video_url"] = upload_result['video_url']
            result_data["thumbnail_url"] = upload_result.get('thumbnail_url')
            result_data["duration"] = result.get('duration', 0)
            
            print(f"[Async] Upload complete for animation {animation_id}!")
            
        except Exception as e:
            print(f"[Async] Upload error: {e}")
            result_data["error"] = f"Upload failed: {str(e)}"
            
        finally:
            cleanup_temp_dir(temp_dir)
            
    except Exception as e:
        print(f"[Async] Render job error: {e}")
        result_data["error"] = str(e)
    
    # Send webhook callback
    await send_webhook(webhook_url, result_data)


async def send_webhook(webhook_url: str, data: dict):
    """Send webhook callback to Next.js app"""
    try:
        print(f"[Webhook] Sending callback to {webhook_url}")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                webhook_url,
                json=data,
                headers={
                    "Content-Type": "application/json",
                    "x-webhook-secret": os.getenv("WEBHOOK_SECRET", "")
                }
            )
            print(f"[Webhook] Response: {response.status_code}")
    except Exception as e:
        print(f"[Webhook] Failed to send callback: {e}")


@app.post("/execute-async")
async def execute_code_async(request: AsyncRenderRequest, background_tasks: BackgroundTasks):
    """Start async video rendering - returns immediately, calls webhook when done"""
    
    print(f"[Async] Received render request for animation {request.animation_id}")
    
    # Add the render job to background tasks
    background_tasks.add_task(
        process_render_job,
        request.code,
        request.quality,
        request.animation_id,
        request.webhook_url
    )
    
    return {
        "success": True,
        "message": "Render job started",
        "animation_id": request.animation_id
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        timeout_keep_alive=900,  # 15 minutes keep-alive
        timeout_notify=900  # 15 minutes timeout
    )