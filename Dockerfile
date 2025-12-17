# ComfyUI Manager with Auto Start/Stop
# This Dockerfile builds on an existing ComfyUI image or installs ComfyUI

ARG BASE_IMAGE=pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime
FROM ${BASE_IMAGE}

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Clone ComfyUI (or copy from local)
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

# Install ComfyUI dependencies
WORKDIR /app/ComfyUI
RUN pip install --no-cache-dir -r requirements.txt

# Install manager dependencies
WORKDIR /app/manager
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy manager application
COPY app.py config.py ./
COPY templates/ templates/
COPY static/ static/

# Environment variables
ENV COMFYUI_PATH=/app/ComfyUI
ENV COMFYUI_PORT=8188
ENV COMFYUI_HOST=127.0.0.1
ENV MANAGER_PORT=5000
ENV IDLE_TIMEOUT=600

# Expose only the manager port
EXPOSE 5000

# Run the manager
CMD ["python", "app.py"]
