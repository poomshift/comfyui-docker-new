#!/bin/bash

# default environment variable

export UPDATE_ON_START=${UPDATE_ON_START:-"false"}
export MODELS_CONFIG_URL=${MODELS_CONFIG_URL:-"https://raw.githubusercontent.com/poomshift/comfyui-docker-new/refs/heads/main/models_config.json"}
export SKIP_MODEL_DOWNLOAD=${SKIP_MODEL_DOWNLOAD:-"false"}
export FORCE_MODEL_DOWNLOAD=${FORCE_MODEL_DOWNLOAD:-"false"}
export LOG_PATH=${LOG_PATH:-"/notebooks/backend.log"}

export TORCH_FORCE_WEIGHTS_ONLY_LOAD=1

# Set strict error handling
set -e

# Function to check GPU availability with timeout
check_gpu() {
    local timeout=30
    local interval=2
    local elapsed=0

    while [ $elapsed -lt $timeout ]; do
        if nvidia-smi >/dev/null 2>&1; then
            echo "GPU detected and ready"
            return 0
        fi
        sleep $interval
        elapsed=$((elapsed + interval))
        echo "Waiting for GPU... ($elapsed/$timeout seconds)"
    done

    echo "WARNING: GPU not detected after $timeout seconds"
    return 1
}

# Function to reset GPU state
reset_gpu() {
    echo "Resetting GPU state..."
    nvidia-smi --gpu-reset 2>/dev/null || true
    sleep 2
}

# Install uv if not already installed
install_uv() {
    if ! command -v uv &>/dev/null; then
        echo "Installing uv package installer..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.cargo/bin:$PATH"
    else
        echo "uv already installed, skipping..."
    fi
}

# Ensure CUDA environment is properly set
export CUDA_VISIBLE_DEVICES=0
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
export CUDA_LAUNCH_BLOCKING=1

# Create necessary directories
mkdir -p /workspace/logs
mkdir -p /workspace/ComfyUI

# Create log file if it doesn't exist
touch /workspace/logs/comfyui.log

# Clean up the log file to remove any duplicate lines
clean_log_file() {
    local log_file="/workspace/logs/comfyui.log"
    if [ -f "$log_file" ] && [ -s "$log_file" ]; then
        echo "Cleaning log file to remove duplicates..."
        # Create a temporary file with unique lines only
        awk '!seen[$0]++' "$log_file" >"${log_file}.tmp"
        # Replace original with cleaned version
        mv "${log_file}.tmp" "$log_file"
    fi
}

# Clean the log file before starting the log viewer
clean_log_file

# Start log viewer early to monitor the installation process
cd /notebooks
# CUDA_VISIBLE_DEVICES="" python /log_viewer.py &
CUDA_VISIBLE_DEVICES="" nohup python /notebooks/log_viewer.py &>$LOG_PATH &
echo "Started log viewer on port 8189 - Monitor setup at http://localhost:8189"
cd /

# Install uv for faster package installation
install_uv

# Function to check internet connectivity
check_internet() {
    local max_attempts=5
    local attempt=1
    local timeout=5

    while [ $attempt -le $max_attempts ]; do
        echo "Checking internet connectivity (attempt $attempt/$max_attempts)..."
        if ping -c 1 -W $timeout 8.8.8.8 >/dev/null 2>&1; then
            echo "Internet connection is available."
            return 0
        fi
        echo "No internet connection. Waiting before retry..."
        sleep 10
        attempt=$((attempt + 1))
    done

    echo "WARNING: No internet connection after $max_attempts attempts."
    return 1
}

# Function to download config with retry
download_config() {
    local url=$1
    local output=$2
    local max_attempts=5
    local attempt=1
    local timeout=30

    while [ $attempt -le $max_attempts ]; do
        echo "Downloading config (attempt $attempt/$max_attempts)..."
        if wget --timeout=$timeout --tries=3 -O "$output" "$url" 2>/dev/null; then
            echo "Successfully downloaded config file."
            return 0
        fi
        echo "Download failed. Waiting before retry..."
        sleep 10
        attempt=$((attempt + 1))
    done

    echo "WARNING: Failed to download config after $max_attempts attempts."
    return 1
}

# Check for models_config.json and download it first thing
CONFIG_FILE="/workspace/models_config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Creating models_config.json..." | tee -a /workspace/logs/comfyui.log
    if [ -n "$MODELS_CONFIG_URL" ]; then
        if ! download_config "$MODELS_CONFIG_URL" "$CONFIG_FILE"; then
            echo "Failed to download from URL. Creating default config..." | tee -a /workspace/logs/comfyui.log
            echo '{
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
            }' >"$CONFIG_FILE"
        fi
    else
        echo "No MODELS_CONFIG_URL provided. Creating default configuration..." | tee -a /workspace/logs/comfyui.log
        echo '{
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
        }' >"$CONFIG_FILE"
    fi
else
    echo "models_config.json already exists, using existing file" | tee -a /workspace/logs/comfyui.log
fi

# Create dirs and download ComfyUI if it doesn't exist
if [ ! -e "/workspace/ComfyUI/main.py" ]; then
    echo "ComfyUI not found or incomplete, installing..." | tee -a /workspace/logs/comfyui.log

    # Remove incomplete directory if it exists
    rm -rf /workspace/ComfyUI

    # Create workspace and log directories
    mkdir -p /workspace/logs

    # Create log file
    touch /workspace/logs/comfyui.log

    echo "Cloning ComfyUI..." | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/comfyanonymous/ComfyUI /workspace/ComfyUI 2>&1 | tee -a /workspace/logs/comfyui.log

    # Install dependencies
    cd /workspace/ComfyUI
    echo "Installing PyTorch dependencies..." | tee -a /workspace/logs/comfyui.log
    uv pip install --no-cache torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu128 2>&1 | tee -a /workspace/logs/comfyui.log
    echo "Installing ComfyUI requirements..." | tee -a /workspace/logs/comfyui.log
    uv pip install --no-cache -r requirements.txt 2>&1 | tee -a /workspace/logs/comfyui.log

    # Install SageAttention 2.2.0 from prebuilt wheel (no compilation needed)
    echo "Installing SageAttention 2.2.0 from prebuilt wheel..." | tee -a /workspace/logs/comfyui.log
    uv pip install https://huggingface.co/Kijai/PrecompiledWheels/resolve/main/sageattention-2.2.0-cp312-cp312-linux_x86_64.whl 2>&1 | tee -a /workspace/logs/comfyui.log
    echo "SageAttention 2.2.0 installation complete" | tee -a /workspace/logs/comfyui.log

    cd /workspace/ComfyUI

    # Create model directories
    mkdir -p /workspace/ComfyUI/models/{checkpoints,vae,unet,diffusion_models,text_encoders,loras,upscale_models,clip,controlnet,clip_vision,ipadapter,style_models}
    mkdir -p /workspace/ComfyUI/custom_nodes
    mkdir -p /workspace/ComfyUI/input
    mkdir -p /workspace/ComfyUI/output

    # Clone custom nodes
    mkdir -p /workspace/ComfyUI/custom_nodes
    cd /workspace/ComfyUI/custom_nodes

    echo "Cloning custom nodes..." | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/ltdrdata/ComfyUI-Manager.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI-Manager | tee -a /workspace/logs/comfyui.log
    #git clone --depth=1 https://github.com/ltdrdata/ComfyUI-Impact-Pack.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI-Impact-Pack | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/cubiq/ComfyUI_essentials.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI_essentials | tee -a /workspace/logs/comfyui.log
    #git clone --depth=1 https://github.com/ltdrdata/ComfyUI-Inspire-Pack.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI-Inspire-Pack | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/Fannovel16/comfyui_controlnet_aux.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh comfyui_controlnet_aux | tee -a /workspace/logs/comfyui.log
    #git clone --depth=1 https://github.com/nicofdga/DZ-FaceDetailer.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh DZ-FaceDetailer | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/cubiq/ComfyUI_IPAdapter_plus.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI_IPAdapter_plus | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/ssitu/ComfyUI_UltimateSDUpscale.git --recursive 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI_UltimateSDUpscale | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI-VideoHelperSuite | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/Acly/comfyui-inpaint-nodes.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh comfyui-inpaint-nodes | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/kijai/ComfyUI-KJNodes.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI-KJNodes | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/city96/ComfyUI-GGUF.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI-GGUF | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/rgthree/rgthree-comfy.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh rgthree-comfy | tee -a /workspace/logs/comfyui.log
    #git clone --depth=1 https://github.com/AlekPet/ComfyUI_Custom_Nodes_AlekPet.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI_Custom_Nodes_AlekPet | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/justUmen/Bjornulf_custom_nodes.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh Bjornulf_custom_nodes | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/pythongosssss/ComfyUI-Custom-Scripts.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI-Custom-Scripts | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI-Frame-Interpolation | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI-SeedVR2_VideoUpscaler | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/ShmuelRonen/ComfyUI-VideoUpscale_WithModel.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI-VideoUpscale_WithModel | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/kijai/ComfyUI-WanVideoWrapper.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI-WanVideoWrapper | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/chflame163/ComfyUI_LayerStyle.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI_LayerStyle | tee -a /workspace/logs/comfyui.log
    
    echo "Total size of custom nodes:" | tee -a /workspace/logs/comfyui.log && du -sh . | tee -a /workspace/logs/comfyui.log

    # Install custom nodes requirements
    echo "Installing custom node requirements..." | tee -a /workspace/logs/comfyui.log
    find . -name "requirements.txt" -exec uv pip install --no-cache -r {} \; 2>&1 | tee -a /workspace/logs/comfyui.log

    mkdir -p /workspace/ComfyUI/user/default/ComfyUI-Manager
    wget https://gist.githubusercontent.com/vjumpkung/b2993de3524b786673552f7de7490b08/raw/b7ae0b4fe0dad5c930ee290f600202f5a6c70fa8/uv_enabled_config.ini -O /workspace/ComfyUI/user/default/ComfyUI-Manager/config.ini 2>&1 | tee -a /workspace/logs/comfyui.log

    cd /workspace
else
    echo "ComfyUI already exists, skipping clone" | tee -a /workspace/logs/comfyui.log
    # Create ComfyUI model directories if they don't exist yet
    echo "Ensuring ComfyUI model directories exist..." | tee -a /workspace/logs/comfyui.log
    mkdir -p /workspace/ComfyUI/models/{checkpoints,vae,unet,diffusion_models,text_encoders,loras,upscale_models,clip,controlnet,clip_vision,ipadapter,style_models}
    mkdir -p /workspace/ComfyUI/custom_nodes
    mkdir -p /workspace/ComfyUI/input
    mkdir -p /workspace/ComfyUI/output

    
    # Install Dependencies
    cd /workspace/ComfyUI
    echo "Installing PyTorch dependencies..." | tee -a /workspace/logs/comfyui.log
    uv pip install --no-cache torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu128 2>&1 | tee -a /workspace/logs/comfyui.log
    echo "Installing ComfyUI requirements..." | tee -a /workspace/logs/comfyui.log
    uv pip install --no-cache -r requirements.txt 2>&1 | tee -a /workspace/logs/comfyui.log

    # Install SageAttention 2.2.0 from prebuilt wheel (no compilation needed)
    echo "Installing SageAttention 2.2.0 from prebuilt wheel..." | tee -a /workspace/logs/comfyui.log
    uv pip install https://huggingface.co/Kijai/PrecompiledWheels/resolve/main/sageattention-2.2.0-cp312-cp312-linux_x86_64.whl 2>&1 | tee -a /workspace/logs/comfyui.log
    echo "SageAttention 2.2.0 installation complete" | tee -a /workspace/logs/comfyui.log

    cd /workspace/ComfyUI

    # Install Custom Nodes Dependencies
    cd /workspace/ComfyUI/custom_nodes
    echo "Installing custom node requirements..." | tee -a /workspace/logs/comfyui.log
    find . -name "requirements.txt" -exec uv pip install --no-cache -r {} \; 2>&1 | tee -a /workspace/logs/comfyui.log
fi

# Create log file if it doesn't exist
touch /workspace/logs/comfyui.log

# Function to check if a model exists
check_model() {
    local url=$1
    local filename=$(basename "$url")
    # Search for the file in all model directories
    find /workspace/ComfyUI/models -type f -name "$filename" | grep -q .
    return $?
}

# Initialize GPU - Do this before downloading models to ensure GPU is ready
echo "Initializing GPU..."
if ! check_gpu; then
    echo "WARNING: GPU initialization failed. Services may not function properly."
else
    reset_gpu
fi

# Check if models from config exist
if [ -n "$CONFIG_FILE" ] && [ -f "$CONFIG_FILE" ]; then
    echo "Checking for missing models..." | tee -a /workspace/logs/comfyui.log
    if python /utils/getInstalledModels.py --check-missing "$CONFIG_FILE"; then
        echo "All required models present..." | tee -a /workspace/logs/comfyui.log
    elif [ "$SKIP_MODEL_DOWNLOAD" != "true" ]; then
        echo "Some required models are missing. Downloading models..." | tee -a /workspace/logs/comfyui.log
        python /notebooks/download_models.py 2>&1 | tee -a $LOG_PATH
    else
        echo "Models missing but download skipped..." | tee -a /workspace/logs/comfyui.log
    fi
else
    echo "No valid models_config.json found. Skipping model checks..."
fi

# Start services with proper sequencing
echo "Starting services..."

# Start Jupyter with GPU isolation
CUDA_VISIBLE_DEVICES="" jupyter lab --allow-root --no-browser --ip=0.0.0.0 --port=8888 --NotebookApp.token="" --NotebookApp.password="" --notebook-dir=/workspace &

# Give other services time to initialize
sleep 5

# Start ComfyUI with full GPU access
cd /workspace/ComfyUI


# Clear any existing CUDA cache
python -c "import torch; torch.cuda.empty_cache()" || true
# Add a clear marker in the log file
echo "====================================================================" | tee -a /workspace/logs/comfyui.log
echo "============ ComfyUI STARTING $(date) ============" | tee -a /workspace/logs/comfyui.log
echo "====================================================================" | tee -a /workspace/logs/comfyui.log
# Start ComfyUI with proper logging
echo "Starting ComfyUI on port 8188..." | tee -a /workspace/logs/comfyui.log
# Use unbuffer to ensure output is line-buffered for better real-time logging
python main.py --listen 0.0.0.0 --use-sage-attention --port 8188 2>&1 | tee -a /workspace/logs/comfyui.log &
# Record the PID of the ComfyUI process
COMFY_PID=$!
echo "ComfyUI started with PID: $COMFY_PID" | tee -a /workspace/logs/comfyui.log

# Wait for all processes
wait
