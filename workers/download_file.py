import asyncio
import os
import subprocess

from constants.websocketEventManager import broadcast_to_websockets


async def download_from_civitai_async(url, api_key=None, model_type="loras"):
    """Download a model from Civitai using aria2c (async)"""
    # Handle model_type with or without 'models/' prefix
    if model_type.startswith("models/"):
        model_path = model_type
    else:
        model_path = os.path.join("models", model_type)

    await broadcast_to_websockets(
        {"type": "download", "data": {"status": "downloading", "source": "civitai"}}
    )

    model_dir = os.path.join("/workspace", "ComfyUI", model_path)
    os.makedirs(model_dir, exist_ok=True)

    cmd = [
        "aria2c",
        "--console-log-level=error",
        "-c",
        "-x",
        "1",
        "-s",
        "1",
        "--file-allocation=none",
        "--max-tries=5",
        "--retry-wait=10",
        "--connect-timeout=30",
        "--timeout=600",
        "--auto-file-renaming=false",
        "--allow-overwrite=true",
    ]

    if api_key:
        cmd.extend(["--header", f"Authorization: Bearer {api_key}"])

    cmd.extend([url, "-d", model_dir])

    try:
        # Use asyncio.create_subprocess_exec for non-blocking execution
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        print(stdout.decode())
        print(stderr.decode())

        if process.returncode == 0:
            await broadcast_to_websockets(
                {"type": "download", "data": {"status": "success", "source": "civitai"}}
            )
            return {"success": True, "message": "Download completed"}
        else:
            await broadcast_to_websockets(
                {
                    "type": "download",
                    "data": {
                        "status": "failed",
                        "source": "civitai",
                        "detail": stdout.decode(),
                    },
                }
            )
            return {"success": False, "message": f"Download failed: {stdout.decode()}"}
    except Exception as e:

        await broadcast_to_websockets(
            {
                "type": "download",
                "data": {"status": "failed", "source": "civitai", "detail": str(e)},
            }
        )

        return {"success": False, "message": f"Error during download: {str(e)}"}


async def download_from_huggingface_async(url, model_type="loras"):
    """Download a model from Hugging Face using aria2c (async)"""
    # Handle model_type with or without 'models/' prefix
    if model_type.startswith("models/"):
        model_path = model_type
    else:
        model_path = os.path.join("models", model_type)

    model_dir = os.path.join("/workspace", "ComfyUI", model_path)
    os.makedirs(model_dir, exist_ok=True)

    await broadcast_to_websockets(
        {"type": "download", "data": {"status": "downloading", "source": "huggingface"}}
    )

    try:
        filename = url.split("/")[-1]
        cmd = [
            "aria2c",
            "--console-log-level=error",
            "-c",
            "-x",
            "16",
            "-s",
            "16",
            "-k",
            "1M",
            "--file-allocation=none",
            "--optimize-concurrent-downloads=true",
            "--max-connection-per-server=16",
            "--min-split-size=1M",
            "--max-tries=5",
            "--retry-wait=10",
            "--connect-timeout=30",
            "--timeout=600",
            url,
            "-d",
            model_dir,
            "-o",
            filename,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        print(stdout.decode())
        print(stderr.decode())

        if process.returncode == 0:
            await broadcast_to_websockets(
                {
                    "type": "download",
                    "data": {"status": "success", "source": "huggingface"},
                }
            )
            return {"success": True, "message": "Download completed"}
        else:
            await broadcast_to_websockets(
                {
                    "type": "download",
                    "data": {
                        "status": "failed",
                        "source": "huggingface",
                        "detail": stdout.decode(),
                    },
                }
            )
            return {"success": False, "message": f"Download failed: {stdout.decode()}"}
    except Exception as e:

        await broadcast_to_websockets(
            {
                "type": "download",
                "data": {"status": "failed", "source": "huggingface", "detail": str(e)},
            }
        )

        return {"success": False, "message": f"Error during download: {str(e)}"}


async def download_from_googledrive_async(
    url, model_type="loras", custom_filename=None
):
    """Download a model from Google Drive using gdown (async)"""
    # Handle model_type with or without 'models/' prefix
    if model_type.startswith("models/"):
        model_path = model_type
    else:
        model_path = os.path.join("models", model_type)

    model_dir = os.path.join("/workspace", "ComfyUI", model_path)
    os.makedirs(model_dir, exist_ok=True)

    await broadcast_to_websockets(
        {"type": "download", "data": {"status": "downloading", "source": "gdrive"}}
    )

    try:
        # Extract file ID from URL if it's a full URL
        file_id = url
        if "drive.google.com" in url:
            if "/file/d/" in url:
                file_id = url.split("/file/d/")[1].split("/")[0]
            elif "id=" in url:
                file_id = url.split("id=")[1].split("&")[0]

        # Check if gdown is installed, if not install it
        try:
            process = await asyncio.create_subprocess_exec(
                "pip",
                "show",
                "gdown",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode, "pip show gdown"
                )
        except:
            process = await asyncio.create_subprocess_exec(
                "pip",
                "install",
                "gdown",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

        # Download the file
        if custom_filename:
            cmd = [
                "gdown",
                "--id",
                file_id,
                "-O",
                os.path.join(model_dir, custom_filename),
            ]
        else:
            cmd = ["gdown", "--id", file_id, "-O", model_dir]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        print(stdout.decode())
        print(stderr.decode())

        if process.returncode == 0:
            await broadcast_to_websockets(
                {"type": "download", "data": {"status": "success", "source": "gdrive"}}
            )
            return {"success": True, "message": "Download completed"}
        else:
            await broadcast_to_websockets(
                {
                    "type": "download",
                    "data": {
                        "status": "failed",
                        "source": "gdrive",
                        "detail": stderr.decode(),
                    },
                }
            )
            return {"success": False, "message": f"Download failed: {stderr.decode()}"}
    except Exception as e:

        await broadcast_to_websockets(
            {
                "type": "download",
                "data": {"status": "failed", "source": "gdrive", "detail": str(e)},
            }
        )

        return {"success": False, "message": f"Error during download: {str(e)}"}
