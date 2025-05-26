#!/usr/bin/env python3
import os
import json
import requests
import subprocess
from pathlib import Path
import logging
import sys

# Prevent duplicate logging
logging.getLogger().handlers = []

# Set up logging to file only, since stdout is already captured by tee in start.sh
log_file_path = '/workspace/logs/comfyui.log'
file_handler = logging.FileHandler(log_file_path)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)

# Also log to stdout for visibility
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(stdout_handler)

def download_file(url, output_path):
    """
    Download a file using aria2c with optimized settings for faster downloads.
    Args:
        url (str): The URL to download from.
        output_path (Path): The directory to save the file in.
    Returns:
        bool: True if download succeeded, False otherwise.
    """
    filename = url.split('/')[-1]
    logger.info(f"Starting download of {filename} from {url}")
    
    cmd = [
        'aria2c',
        '--console-log-level=warn',  # Reduce verbosity to warnings only
        '-c',  # Continue downloading if partial file exists
        '-x', '16',  # Increase concurrent connections to 16
        '-s', '16',  # Split file into 16 parts
        '-k', '1M',  # Minimum split size
        '--file-allocation=none',  # Disable file allocation for faster start
        '--optimize-concurrent-downloads=true',  # Optimize concurrent downloads
        '--max-connection-per-server=16',  # Maximum connections per server
        '--min-split-size=1M',  # Minimum split size
        '--max-tries=5',  # Maximum retries
        '--retry-wait=10',  # Wait between retries
        '--connect-timeout=30',  # Connection timeout
        '--timeout=600',  # Timeout for stalled downloads
        '--summary-interval=30',  # Show summary every 30 seconds
        url,
        '-d', str(output_path),
        '-o', filename  # Specify output filename
    ]
    
    try:
        logger.info(f"Running download command for {filename}")
        # Run process with simple call instead of monitoring output
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"Successfully downloaded {filename}")
            return True
        else:
            error_msg = result.stderr or result.stdout
            logger.error(f"Failed to download {filename}: {error_msg}")
            return False
    except Exception as e:
        logger.error(f"Unexpected error while downloading {url}: {e}")
        return False

def get_config(config_path):
    """
    Load configuration from file or URL.
    Args:
        config_path (str): Path or URL to the config file.
    Returns:
        dict or None: The loaded config, or None on failure.
    """
    try:
        # Check if it's a URL
        if config_path.startswith(('http://', 'https://')):
            response = requests.get(config_path)
            response.raise_for_status()
            return response.json()
        else:
            # Load from local file
            with open(config_path, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config from {config_path}: {e}")
        return None

def ensure_directories(base_path):
    """
    Ensure all required directories exist under the given base path.
    Args:
        base_path (Path): The base directory for model folders.
    """
    directories = [
        'models/checkpoints',
        'models/vae',
        'models/unet',
        'models/diffusion_models',
        'models/text_encoders',
        'models/loras',
        'models/upscale_models',
        'models/clip',
        'models/controlnet',
        'models/clip_vision',
        'models/ipadapter',
        'models/style_models',
        'input',
        'output'
    ]
    
    for dir_path in directories:
        full_path = base_path / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured directory exists: {full_path}")

def main():
    """
    Main entry point for downloading models as specified in the config file.
    Handles environment variables, directory setup, and download logic.
    """
    # Environment variables
    config_path = os.getenv('MODELS_CONFIG_URL', '/workspace/models_config.json')
    skip_download = os.getenv('SKIP_MODEL_DOWNLOAD', '').lower() == 'true'
    force_download = os.getenv('FORCE_MODEL_DOWNLOAD', '').lower() == 'true'
    
    # Skip if explicitly told to skip
    if skip_download:
        logger.info("Model download skipped due to SKIP_MODEL_DOWNLOAD=true")
        return
    
    # Check if ComfyUI is fully set up
    comfyui_path = '/workspace/ComfyUI'
    if not os.path.exists(os.path.join(comfyui_path, 'main.py')):
        logger.info("ComfyUI main.py not found. Skipping model downloads until ComfyUI is installed.")
        return
        
    # Check if key model directories exist
    model_dirs = [
        os.path.join(comfyui_path, 'models'),
        os.path.join(comfyui_path, 'models/checkpoints'),
        os.path.join(comfyui_path, 'models/loras')
    ]
    
    for dir_path in model_dirs:
        if not os.path.exists(dir_path):
            logger.info(f"Model directory {dir_path} not found. Skipping model downloads.")
            return
        
    # Base path for ComfyUI
    base_path = Path('/workspace/ComfyUI')
    
    # Ensure directories exist
    ensure_directories(base_path)
    
    # Check if config path is a URL or local file
    if config_path.startswith(('http://', 'https://')):
        logger.info(f"Using models_config.json from URL: {config_path}")
    else:
        local_config_path = Path(config_path)
        if local_config_path.exists():
            logger.info(f"Using local models_config.json: {config_path}")
            config_path = str(local_config_path.absolute())
        else:
            logger.error(f"Local config file not found at {config_path}")
            default_config = {
                "checkpoints": [],
                "vae": [],
                "unet": [],
                "diffusion_models": [],
                "text_encoders": [],
                "loras": [],
                "upscale_models": [],
                "clip": [],
                "controlnet": [],
                "clip_vision": [],
                "ipadapter": [],
                "style_models": []
            }
            logger.info("Using default empty configuration")
            with open('/workspace/models_config.json', 'w') as f:
                json.dump(default_config, f, indent=4)
            config_path = '/workspace/models_config.json'
    
    # Fetch configuration
    config = get_config(config_path)
    if not config:
        logger.error("Failed to get configuration, exiting.")
        return
    
    # Log the number of models to download
    total_models = sum(len(urls) for urls in config.values() if isinstance(urls, list))
    logger.info(f"Found {total_models} models in configuration")
    
    # Download models from each category
    for category, urls in config.items():
        if not isinstance(urls, list):
            logger.warning(f"Skipping '{category}' as it's not a list of URLs")
            continue
            
        category_path = base_path / 'models' / category
        category_path.mkdir(parents=True, exist_ok=True)
        
        for url in urls:
            # Extract filename from URL
            filename = url.split('/')[-1]
            
            # Skip if file exists and force_download is False
            if (category_path / filename).exists() and not force_download:
                logger.info(f"Skipping {filename}, file already exists")
                continue
            
            logger.info(f"Downloading {filename} to {category_path}")
            if download_file(url, category_path):
                logger.info(f"Successfully downloaded {filename}")
            else:
                logger.error(f"Failed to download {filename}")

if __name__ == '__main__':
    main()