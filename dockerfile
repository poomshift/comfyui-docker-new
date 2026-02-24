FROM nvidia/cuda:12.8.0-base-ubuntu24.04
ARG PYTHON_VERSION="3.12"
ARG CONTAINER_TIMEZONE=UTC
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:/root/.local/bin:/root/.cargo/bin:${PATH}"

# Everything in one layer to minimize overlay mounts
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    git \
    build-essential \
    libgl1-mesa-dev \
    libglib2.0-0 \
    wget \
    ffmpeg \
    aria2 \
    rsync \
    curl \
    ca-certificates \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update --yes \
    && apt-get install --yes --no-install-recommends \
    python3-pip \
    "python${PYTHON_VERSION}" \
    "python${PYTHON_VERSION}-venv" \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && python${PYTHON_VERSION} -m venv /opt/venv \
    && echo "en_US.UTF-8 UTF-8" > /etc/locale.gen \
    && apt-get autoremove -y \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/* \
    && uv pip install --no-cache \
    jupyter \
    jupyterlab \
    nodejs \
    requests \
    fastapi \
    uvicorn \
    websockets \
    pydantic \
    jinja2 \
    gdown \
    onnxruntime-gpu \
    pip \
    "numpy<2" \
    triton \
    && uv cache clean \
    && jupyter notebook --generate-config \
    && echo "c.NotebookApp.allow_root = True" >> /root/.jupyter/jupyter_notebook_config.py \
    && echo "c.NotebookApp.ip = '0.0.0.0'" >> /root/.jupyter/jupyter_notebook_config.py \
    && echo "c.NotebookApp.token = ''" >> /root/.jupyter/jupyter_notebook_config.py \
    && echo "c.NotebookApp.password = ''" >> /root/.jupyter/jupyter_notebook_config.py \
    && echo "c.NotebookApp.allow_origin = '*'" >> /root/.jupyter/jupyter_notebook_config.py \
    && echo "c.NotebookApp.allow_remote_access = True" >> /root/.jupyter/jupyter_notebook_config.py

WORKDIR /notebooks
RUN mkdir -p /workspace /notebooks/dto /notebooks/static /notebooks/utils /notebooks/workers
COPY start.sh log_viewer.py download_models.py ./
COPY ./constants/ ./constants/
COPY ./dto/ ./dto/
COPY ./static/ ./static/
COPY ./workers/ ./workers/
COPY ./utils/ ./utils/
COPY ./templates/ ./templates/
COPY models_config.json /workspace
RUN chmod +x *.sh

EXPOSE 8188 8888 8189
CMD ["./start.sh"]
