#!/bin/bash

# Set strict error handling
set -e

# Function to check GPU availability with timeout
check_gpu() {
    local timeout=30
    local interval=2
    local elapsed=0
    
    while [ $elapsed -lt $timeout ]; do
        if nvidia-smi > /dev/null 2>&1; then
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
    if ! command -v uv &> /dev/null; then
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
        awk '!seen[$0]++' "$log_file" > "${log_file}.tmp"
        # Replace original with cleaned version
        mv "${log_file}.tmp" "$log_file"
    fi
}

# Clean the log file before starting the log viewer
clean_log_file

# Function to start the log viewer
start_log_viewer() {
    cd /workspace
    CUDA_VISIBLE_DEVICES="" python /log_viewer.py &
    echo "Started log viewer on port 8189 - Monitor setup at http://localhost:8189"
    cd /
}

# Install uv for faster package installation
install_uv

# Function to clone ComfyUI and install dependencies
install_comfyui() {
    echo "Cloning ComfyUI repository..." | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/comfyanonymous/ComfyUI /workspace/ComfyUI 2>&1 | tee -a /workspace/logs/comfyui.log
    
    # Install dependencies
    cd /workspace/ComfyUI
    echo "Installing PyTorch dependencies..." | tee -a /workspace/logs/comfyui.log
    uv pip install --no-cache torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu124 2>&1 | tee -a /workspace/logs/comfyui.log
    echo "Installing ComfyUI requirements..." | tee -a /workspace/logs/comfyui.log
    uv pip install --no-cache -r requirements.txt 2>&1 | tee -a /workspace/logs/comfyui.log
    
    # Create model directories
    mkdir -p /workspace/ComfyUI/models/{checkpoints,vae,unet,diffusion_models,text_encoders,loras,upscale_models,clip,controlnet,clip_vision,ipadapter,style_models}
    mkdir -p /workspace/ComfyUI/input
    mkdir -p /workspace/ComfyUI/output
    
    # Clone custom nodes
    mkdir -p /workspace/ComfyUI/custom_nodes
    cd /workspace/ComfyUI/custom_nodes
    
    echo "Cloning custom nodes..." | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/ltdrdata/ComfyUI-Manager.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI-Manager | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI-VideoHelperSuite | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/kijai/ComfyUI-KJNodes.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI-KJNodes | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/city96/ComfyUI-GGUF.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI-GGUF | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/ltdrdata/ComfyUI-Inspire-Pack.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI-Inspire-Pack | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/pythongosssss/ComfyUI-Custom-Scripts.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI-Custom-Scripts | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/rgthree/rgthree-comfy.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh rgthree-comfy | tee -a /workspace/logs/comfyui.log
    git clone --depth=1 https://github.com/cubiq/ComfyUI_essentials.git 2>&1 | tee -a /workspace/logs/comfyui.log && du -sh ComfyUI_essentials | tee -a /workspace/logs/comfyui.log
    
    echo "Total size of custom nodes:" | tee -a /workspace/logs/comfyui.log && du -sh . | tee -a /workspace/logs/comfyui.log
    
    # Install custom nodes requirements
    echo "Installing custom node requirements..." | tee -a /workspace/logs/comfyui.log
    find . -name "requirements.txt" -exec uv pip install --no-cache -r {} \; 2>&1 | tee -a /workspace/logs/comfyui.log
    
    cd /workspace
}

# Function to clone custom nodes
install_custom_nodes() {
    # ... existing code for cloning custom nodes ...
}

# Function to install custom node requirements
install_custom_node_requirements() {
    # ... existing code for installing requirements ...
}

# Function to download models
download_models() {
    # ... existing code for downloading models ...
}

# Function to initialize GPU
initialize_gpu() {
    echo "Initializing GPU..."
    if ! check_gpu; then
        echo "WARNING: GPU initialization failed. Services may not function properly."
    else
        reset_gpu
    fi
}

# Function to start Jupyter
start_jupyter() {
    CUDA_VISIBLE_DEVICES="" jupyter lab --allow-root --no-browser --ip=0.0.0.0 --port=8888 --NotebookApp.token="" --NotebookApp.password="" --notebook-dir=/workspace &
}

# Function to start ComfyUI
start_comfyui() {
    cd /workspace/ComfyUI
    python3 -c "import torch; torch.cuda.empty_cache()" || true
    echo "====================================================================" | tee -a /workspace/logs/comfyui.log
    echo "============ ComfyUI STARTING $(date) ============" | tee -a /workspace/logs/comfyui.log
    echo "====================================================================" | tee -a /workspace/logs/comfyui.log
    echo "Starting ComfyUI on port 8188..." | tee -a /workspace/logs/comfyui.log
    python main.py --listen 0.0.0.0 --port=8188 2>&1 | tee -a /workspace/logs/comfyui.log &
    COMFY_PID=$!
    echo "ComfyUI started with PID: $COMFY_PID" | tee -a /workspace/logs/comfyui.log
}

# This script now only defines functions for install/start logic.
# It does not auto-run any install/start logic when sourced or run. 