import os
import sys
from urllib.parse import urlparse


def check_model_exists(url):
    """Check if a model file exists in ComfyUI models directories"""
    try:
        filename = os.path.basename(urlparse(url).path)
        if not filename:
            return False
        
        # Search in all model directories
        models_base = "/workspace/ComfyUI/models"
        if not os.path.exists(models_base):
            return False
            
        for root, dirs, files in os.walk(models_base):
            if filename in files:
                return True
        return False
    except Exception:
        return False


def check_missing_models(config_file):
    """Check for missing models from config file and return True if any are missing"""
    try:
        if not os.path.exists(config_file):
            print(f"Config file not found: {config_file}", file=sys.stderr)
            return True
            
        import json
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        missing_count = 0
        
        # Handle different config formats
        if isinstance(config, dict):
            # Standard format: {"category": ["url1", "url2"]}
            for category, urls in config.items():
                if isinstance(urls, list):
                    for url in urls:
                        if isinstance(url, str) and url.startswith('http'):
                            if not check_model_exists(url):
                                print(f"Missing model: {url}")
                                missing_count += 1
                elif isinstance(urls, str) and urls.startswith('http'):
                    # Single URL as string
                    if not check_model_exists(urls):
                        print(f"Missing model: {urls}")
                        missing_count += 1
        elif isinstance(config, list):
            # Array format: ["url1", "url2"]
            for url in config:
                if isinstance(url, str) and url.startswith('http'):
                    if not check_model_exists(url):
                        print(f"Missing model: {url}")
                        missing_count += 1
        
        return missing_count > 0
        
    except Exception as e:
        print(f"Error checking models: {e}", file=sys.stderr)
        return True


def get_installed_models():
    """Get a list of installed models from models_config.json"""
    models = {}

    try:
        import json
        import urllib.request
        
        model_config = None
        
        # Check if MODELS_CONFIG_URL is set and try to fetch from URL first
        models_config_url = os.getenv("MODELS_CONFIG_URL")
        if models_config_url and models_config_url.startswith("http"):
            try:
                print(f"Fetching model config from URL: {models_config_url}")
                with urllib.request.urlopen(models_config_url) as response:
                    model_config = json.loads(response.read().decode())
                print("Successfully loaded model config from custom URL")
            except Exception as e:
                print(f"Failed to fetch model config from URL {models_config_url}: {e}")
                print("Falling back to local config files...")
        
        # If URL fetch failed or no URL provided, check local files
        if not model_config:
            config_paths = [
                "/workspace/models_config.json",
                "./models_config.json",
                os.path.join(os.path.dirname(__file__), "models_config.json"),
            ]

            for path in config_paths:
                if os.path.exists(path):
                    with open(path, "r") as file:
                        model_config = json.load(file)
                    print(f"Loaded model config from local file: {path}")
                    break

        if not model_config:
            print("Warning: models_config.json not found in expected locations")
            return {}

        # Check if ComfyUI/models directory exists before trying to check file existence
        comfyui_models_dir = "/workspace/ComfyUI/models"
        if not os.path.exists(comfyui_models_dir):
            print(
                f"Note: {comfyui_models_dir} doesn't exist yet. Will show models from config only."
            )

        # Process each model category
        for category, urls in model_config.items():
            if urls:  # Only process non-empty categories
                model_files = []
                for url in urls:
                    # Extract filename from URL
                    filename = url.split("/")[-1]

                    # Add model information
                    model_files.append(
                        {
                            "name": filename,
                            "path": f"/workspace/ComfyUI/models/{category}/{filename}",
                            "url": url,
                        }
                    )

                if model_files:
                    # Sort by name
                    model_files.sort(key=lambda x: x["name"].lower())
                    models[category] = model_files
    except Exception as e:
        print(f"Error parsing models from models_config.json: {e}")

    # Sort categories alphabetically
    return dict(sorted(models.items()))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check-missing":
        if len(sys.argv) != 3:
            print("Usage: python getInstalledModels.py --check-missing <config_file>", file=sys.stderr)
            sys.exit(1)
        
        config_file = sys.argv[2]
        has_missing = check_missing_models(config_file)
        sys.exit(1 if has_missing else 0)
