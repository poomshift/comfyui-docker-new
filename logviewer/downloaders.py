import os
import subprocess

def download_from_civitai(url, api_key=None, model_type="loras"):
    """Download a model from Civitai using aria2c"""
    if model_type.startswith('models/'):
        model_path = model_type
    else:
        model_path = os.path.join('models', model_type)
    model_dir = os.path.join('/workspace', 'ComfyUI', model_path)
    os.makedirs(model_dir, exist_ok=True)
    download_url = url
    if api_key:
        download_url = f"{url}?token={api_key}"
    cmd = [
        'aria2c',
        '--console-log-level=error',
        '-c',
        '-x', '16',
        '-s', '16',
        '-k', '1M',
        '--file-allocation=none',
        '--optimize-concurrent-downloads=true',
        '--max-connection-per-server=16',
        '--min-split-size=1M',
        '--max-tries=5',
        '--retry-wait=10',
        '--connect-timeout=30',
        '--timeout=600',
        download_url,
        '-d', model_dir
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return {"success": True, "message": "Download completed successfully"}
        else:
            return {"success": False, "message": f"Download failed: {result.stderr}"}
    except Exception as e:
        return {"success": False, "message": f"Error during download: {str(e)}"}

def download_from_huggingface(url, model_type="loras"):
    """Download a model from Hugging Face using aria2c"""
    if model_type.startswith('models/'):
        model_path = model_type
    else:
        model_path = os.path.join('models', model_type)
    model_dir = os.path.join('/workspace', 'ComfyUI', model_path)
    os.makedirs(model_dir, exist_ok=True)
    try:
        filename = url.split('/')[-1]
        cmd = [
            'aria2c',
            '--console-log-level=error',
            '-c',
            '-x', '16',
            '-s', '16',
            '-k', '1M',
            '--file-allocation=none',
            '--optimize-concurrent-downloads=true',
            '--max-connection-per-server=16',
            '--min-split-size=1M',
            '--max-tries=5',
            '--retry-wait=10',
            '--connect-timeout=30',
            '--timeout=600',
            url,
            '-d', model_dir,
            '-o', filename
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return {"success": True, "message": "Download completed successfully"}
        else:
            return {"success": False, "message": f"Download failed: {result.stderr}"}
    except Exception as e:
        return {"success": False, "message": f"Error during download: {str(e)}"}

def download_from_googledrive(url, model_type="loras", custom_filename=None):
    """Download a model from Google Drive using gdown"""
    if model_type.startswith('models/'):
        model_path = model_type
    else:
        model_path = os.path.join('models', model_type)
    model_dir = os.path.join('/workspace', 'ComfyUI', model_path)
    os.makedirs(model_dir, exist_ok=True)
    try:
        file_id = url
        if 'drive.google.com' in url:
            if '/file/d/' in url:
                file_id = url.split('/file/d/')[1].split('/')[0]
            elif 'id=' in url:
                file_id = url.split('id=')[1].split('&')[0]
        output_path = os.path.join(model_dir, custom_filename) if custom_filename else model_dir
        try:
            subprocess.run(['pip', 'show', 'gdown'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError:
            subprocess.run(['pip', 'install', 'gdown'], check=True)
        if custom_filename:
            cmd = ['gdown', '--id', file_id, '-O', os.path.join(model_dir, custom_filename)]
        else:
            cmd = ['gdown', '--id', file_id, '-O', model_dir]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return {"success": True, "message": "Download completed successfully"}
        else:
            return {"success": False, "message": f"Download failed: {result.stderr}"}
    except Exception as e:
        return {"success": False, "message": f"Error during download: {str(e)}"} 