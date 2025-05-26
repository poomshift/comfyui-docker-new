from fastapi import APIRouter, Request, BackgroundTasks, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
import os
from .utils import (
    get_installed_custom_nodes,
    get_installed_models,
    get_current_logs,
    tail_log_file,
    create_output_zip,
    log_buffer, log_lock
)
from .downloaders import (
    download_from_civitai,
    download_from_huggingface,
    download_from_googledrive
)
from .templates import HTML_TEMPLATE
from datetime import datetime
import io

router = APIRouter()

templates = Jinja2Templates(directory="logviewer")  # Not used, but placeholder if you want to use Jinja2

@router.get("/api/custom-nodes")
def api_custom_nodes():
    return get_installed_custom_nodes()

@router.get("/api/models")
def api_models():
    return get_installed_models()

@router.get("/logs")
def get_logs():
    return {"logs": get_current_logs()}

@router.post("/refresh_logs")
def refresh_logs():
    with log_lock:
        log_buffer.clear()
    # Reload logs from file
    log_file = os.path.join('logs', 'comfyui.log')
    if os.path.exists(log_file):
        with open(log_file, 'r') as file:
            content = file.readlines()
            processed_content = []
            content = content[-500:] if len(content) > 500 else content
            prev_line = None
            for line in content:
                stripped_line = line.strip()
                if stripped_line and stripped_line != prev_line:
                    processed_content.append(stripped_line)
                prev_line = stripped_line
            with log_lock:
                log_buffer.extend(processed_content)
    return {"success": True, "message": "Logs refreshed successfully"}

@router.get("/download/outputs")
def download_outputs():
    try:
        memory_file = create_output_zip()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return StreamingResponse(
            memory_file,
            media_type='application/zip',
            headers={
                "Content-Disposition": f"attachment; filename=comfyui_outputs_{timestamp}.zip"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/download/civitai")
def download_civitai(data: dict):
    url = data.get('url')
    api_key = data.get('api_key')
    model_type = data.get('model_type', 'loras')
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    result = download_from_civitai(url, api_key, model_type)
    return result

@router.post("/download/huggingface")
def download_huggingface(data: dict):
    url = data.get('url')
    model_type = data.get('model_type', 'loras')
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    result = download_from_huggingface(url, model_type)
    return result

@router.post("/download/googledrive")
def download_googledrive(data: dict):
    url = data.get('url')
    model_type = data.get('model_type', 'loras')
    filename = data.get('filename')
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    custom_filename = filename if filename and filename.strip() else None
    result = download_from_googledrive(url, model_type, custom_filename)
    return result

@router.get("/banner.jpg")
def serve_banner():
    possible_paths = [
        '/banner.jpg',
        './banner.jpg',
        os.path.join(os.path.dirname(__file__), '..', 'banner.jpg')
    ]
    for banner_path in possible_paths:
        if os.path.exists(banner_path):
            return FileResponse(banner_path, media_type='image/jpeg')
    raise HTTPException(status_code=404, detail="Banner not found")

@router.get("/")
def index(request: Request):
    logs = get_current_logs()
    custom_nodes = get_installed_custom_nodes()
    models = get_installed_models()
    total_models = sum(len(models[category]) for category in models)
    is_runpod = 'RUNPOD_POD_ID' in os.environ
    if is_runpod:
        pod_id = os.environ.get('RUNPOD_POD_ID', '')
        proxy_port = '8188'
        jupyter_port = '8888'
        proxy_host = f"{pod_id}-{proxy_port}.proxy.runpod.net"
        jupyter_host = f"{pod_id}-{jupyter_port}.proxy.runpod.net"
        proxy_url = f"https://{proxy_host}"
        jupyter_url = f"https://{jupyter_host}"
    else:
        proxy_host = request.client.host
        proxy_port = '8188'
        jupyter_port = '8888'
        proxy_url = f"http://{proxy_host}:{proxy_port}"
        jupyter_url = f"http://{proxy_host}:{jupyter_port}"
    html = HTML_TEMPLATE.replace("{{ logs }}", logs)
    html = html.replace("{{ proxy_url }}", proxy_url)
    html = html.replace("{{ jupyter_url }}", jupyter_url)
    html = html.replace("{{ total_models }}", str(total_models))
    # For custom_nodes and models, you may want to use a template engine for full rendering
    return HTMLResponse(content=html, status_code=200) 