FROM vastai/pytorch:cuda-12.8.1-auto

ARG BUILD_SHA=unknown

USER root
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PROJECT_DIR=/opt/ltx-suite \
    COMFYUI_DIR=/opt/workspace-internal/ComfyUI \
    WORKSPACE_DIR=/workspace \
    DATA_DIRECTORY=/workspace \
    OPEN_BUTTON_PORT=1111 \
    OPEN_BUTTON_TOKEN=1 \
    PORTAL_CONFIG="localhost:1111:11111:/:Instance Portal|localhost:8188:18188:/:ComfyUI" \
    OLLAMA_HOST=127.0.0.1:11434 \
    OLLAMA_KEEP_ALIVE=0s \
    LTX_BUILD_SHA=${BUILD_SHA}

LABEL org.opencontainers.image.revision=${BUILD_SHA}

RUN apt-get update && apt-get install -y --no-install-recommends \
      git git-lfs ffmpeg curl ca-certificates aria2 unzip jq procps \
      build-essential pkg-config libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/* \
    && git lfs install

WORKDIR /opt/workspace-internal
ARG COMFYUI_REF=v0.24.0
RUN git clone --depth 1 --branch ${COMFYUI_REF} https://github.com/Comfy-Org/ComfyUI.git
WORKDIR /opt/workspace-internal/ComfyUI
RUN /venv/main/bin/python -m pip install --upgrade pip setuptools wheel \
    && /venv/main/bin/python -m pip install -r requirements.txt

WORKDIR /opt/ltx-suite
COPY requirements-runtime.txt /opt/ltx-suite/requirements-runtime.txt
RUN /venv/main/bin/python -m pip install -r /opt/ltx-suite/requirements-runtime.txt
COPY config /opt/ltx-suite/config
COPY scripts/install_nodes.py /opt/ltx-suite/scripts/install_nodes.py
RUN /venv/main/bin/python /opt/ltx-suite/scripts/install_nodes.py \
      --manifest /opt/ltx-suite/config/nodes.json \
      --custom-nodes /opt/workspace-internal/ComfyUI/custom_nodes \
      --python /venv/main/bin/python

# Local LLM server used by the supplied Goon Machine workflow.
RUN curl -fsSL https://ollama.com/install.sh | sh

COPY . /opt/ltx-suite
COPY docker/ltx-suite.conf /etc/supervisor/conf.d/ltx-suite.conf
RUN chmod +x /opt/ltx-suite/docker/start.sh \
    && test -s /etc/supervisor/conf.d/ltx-suite.conf \
    && /venv/main/bin/python /opt/ltx-suite/scripts/validate_project.py

EXPOSE 1111/tcp 8188/tcp

# Preserve the Vast.ai base ENTRYPOINT. The ltx-suite process is started by
# supervisord from docker/ltx-suite.conf after the Instance Portal stack comes up.
CMD []
