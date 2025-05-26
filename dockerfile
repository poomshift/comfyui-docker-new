FROM nvidia/cuda:12.4.0-devel-ubuntu22.04 as builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="${PATH}:/root/.local/bin:/root/.cargo/bin"

# Install system dependencies 
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    python3.10 \
    python3.10-venv \
    python3-pip \
    build-essential \
    libgl1-mesa-dev \
    libglib2.0-0 \
    wget \
    ffmpeg \
    aria2 \
    rsync \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv package installer
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Create and activate virtual environment
RUN python3.10 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory to root
WORKDIR /

# Install Jupyter with uv
RUN uv pip install jupyter jupyterlab nodejs opencv-python requests runpod flask flask-socketio websocket-client psutil gputil

# Setup Jupyter configuration
RUN jupyter notebook --generate-config && \
    echo "c.NotebookApp.allow_root = True" >> /root/.jupyter/jupyter_notebook_config.py && \
    echo "c.NotebookApp.ip = '0.0.0.0'" >> /root/.jupyter/jupyter_notebook_config.py && \
    echo "c.NotebookApp.token = ''" >> /root/.jupyter/jupyter_notebook_config.py && \
    echo "c.NotebookApp.password = ''" >> /root/.jupyter/jupyter_notebook_config.py && \
    echo "c.NotebookApp.allow_origin = '*'" >> /root/.jupyter/jupyter_notebook_config.py && \
    echo "c.NotebookApp.allow_remote_access = True" >> /root/.jupyter/jupyter_notebook_config.py

# Create workspace directory
RUN mkdir -p /workspace

# Copy scripts to root
COPY download_models.py update.sh start.sh log_viewer.py banner.jpg /


# Set environment variables for configuration 
ENV UPDATE_ON_START=false \
    MODELS_CONFIG_URL="https://raw.githubusercontent.com/poomshift/comfyui-docker-new/refs/heads/main/models_config.json" \
    SKIP_MODEL_DOWNLOAD=false \
    FORCE_MODEL_DOWNLOAD=false

# Make scripts executable
RUN chmod +x /*.sh /download_models.py

# Expose ports
EXPOSE 8188 8888 8189

WORKDIR /
CMD ["./start.sh"]

