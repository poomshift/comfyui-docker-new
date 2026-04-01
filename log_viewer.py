import asyncio
import io
import json
import os
import threading
import zipfile
from datetime import datetime

import uvicorn
from fastapi import (
    BackgroundTasks,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from constants.websocketEventManager import websocket_connections
from dto.downloadRequest import DownloadRequest
from utils.getCurrentLogs import get_current_logs
from utils.getInstalledCustomNodes import get_installed_custom_nodes
from utils.getInstalledModels import get_installed_models
from workers.download_file import (
    download_from_civitai_async,
    download_from_googledrive_async,
    download_from_huggingface_async,
)
from workers.tailLogsFile import tail_log_file, tlf_worker

# Initialize FastAPI with disable docs url (swagger and redoc)
app = FastAPI(
    title="ComfyUI Log Viewer",
    description="ComfyUI Runpod Log Viewer and Model Downloader",
    docs_url=None,
    redoc_url=None,
)

# using static file to serve css,js and images
app.mount("/static", StaticFiles(directory="./static"), name="static")

# using template path instead of HTML string
templates = Jinja2Templates(directory="templates")


def create_output_zip():
    """Create a zip file of the ComfyUI output directory"""
    output_dir = os.path.join("/workspace", "ComfyUI", "output")
    memory_file = io.BytesIO()

    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(output_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, output_dir)
                zf.write(file_path, arcname)

    memory_file.seek(0)
    return memory_file


# WebSocket endpoint for real-time log updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    /ws endpoint for real time communication
    """
    await websocket.accept()
    websocket_connections.append(websocket)
    print(f"WebSocket connected. Total connections: {len(websocket_connections)}")

    try:
        # Send initial logs
        await websocket.send_text(
            json.dumps({"type": "msg", "msg": "websocket connected"})
        )

        # Keep the connection alive
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_connections.remove(websocket)
        print(
            f"WebSocket disconnected. Remaining connections: {len(websocket_connections)}"
        )


@app.get("/api/custom-nodes")
async def api_custom_nodes():
    """API endpoint to get installed custom nodes"""
    return get_installed_custom_nodes()


@app.get("/api/models")
async def api_models():
    """API endpoint to get installed models"""
    return get_installed_models()


@app.get("/logs")
async def get_logs():
    return {"logs": get_current_logs()}


@app.get("/download/outputs")
async def download_outputs():
    """
    endpoint for download every outputs in zip file.
    """
    try:
        memory_file = create_output_zip()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        return StreamingResponse(
            io.BytesIO(memory_file.read()),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=comfyui_outputs_{timestamp}.zip"
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/download/{url_type}", status_code=204)
async def download(
    request: DownloadRequest, url_type: str, background_tasks: BackgroundTasks
):
    """
    download model endpoints with path params url_type is civitai, huggingface and googledrive
    """
    if not request.url:
        raise HTTPException(status_code=400, detail="URL is required")

    if url_type == "civitai":

        task = asyncio.create_task(
            download_from_civitai_async(
                request.url, request.api_key, request.model_type
            )
        )

    elif url_type == "huggingface":

        task = asyncio.create_task(
            download_from_huggingface_async(request.url, request.model_type)
        )
    elif url_type == "googledrive":

        custom_filename = (
            request.filename if request.filename and request.filename.strip() else None
        )
        task = asyncio.create_task(
            download_from_googledrive_async(
                request.url, request.model_type, custom_filename
            )
        )

    background_tasks.add_task(lambda: task)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    main webpage with parse some value into html jinja2 template
    """

    # get log from log file
    logs = get_current_logs()

    # Get installed custom nodes and models
    custom_nodes = get_installed_custom_nodes()
    models = get_installed_models()

    # Count total models
    total_models = sum(len(models[category]) for category in models)

    # Detect if we're running in RunPod by checking environment variables
    is_runpod = "RUNPOD_POD_ID" in os.environ

    # Get the RunPod proxy host and port
    if is_runpod:
        # In RunPod, we use the public FQDN provided by RunPod for the proxy
        # Format: https://{pod_id}-{port}.proxy.runpod.net
        pod_id = os.environ.get("RUNPOD_POD_ID", "")
        proxy_port = "8188"  # ComfyUI port
        jupyter_port = "8888"  # JupyterLab port
        proxy_host = f"{pod_id}-{proxy_port}.proxy.runpod.net"
        jupyter_host = f"{pod_id}-{jupyter_port}.proxy.runpod.net"
        proxy_url = f"https://{proxy_host}"
        jupyter_url = f"https://{jupyter_host}"
    else:
        # For local development or other environments
        proxy_host = request.url.hostname
        proxy_port = "8188"
        jupyter_port = "8888"
        proxy_url = f"http://{proxy_host}:{proxy_port}"
        jupyter_url = f"http://{proxy_host}:{jupyter_port}"

        # return template instead of html string
    return templates.TemplateResponse(
        request=request,
        name="web.html",
        context={
            "request": request,
            "logs": logs,
            "proxy_url": proxy_url,
            "jupyter_url": jupyter_url,
            "is_runpod": is_runpod,
            "custom_nodes": custom_nodes,
            "models": models,
            "total_models": total_models,
        },
    )


if __name__ == "__main__":

    print("Starting log monitoring thread...")

    # using new event loop + thread to handle read logs like tail -f (always read latest log)
    loop = asyncio.new_event_loop()

    log_thread = threading.Thread(
        target=tlf_worker,
        args=(
            tail_log_file,
            loop,
        ),
        daemon=True,
    )
    log_thread.start()

    print("Starting FastAPI log viewer on port 8189...")

    uvicorn.run(app, host="0.0.0.0", port=8189, log_level="info")
