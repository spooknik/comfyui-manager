#!/bin/bash
# Custom entrypoint that runs ComfyUI Manager instead of ComfyUI directly
# Place this at /root/user-scripts/entrypoint-manager.sh

set -e

echo "########################################"
echo "[INFO] ComfyUI Manager Entrypoint"
echo "########################################"

# Run user's set-proxy script
cd /root
if [ -f "/root/user-scripts/set-proxy.sh" ] ; then
    echo "[INFO] Running set-proxy script..."
    chmod +x /root/user-scripts/set-proxy.sh
    source /root/user-scripts/set-proxy.sh
fi

# Copy ComfyUI from cache to workdir if it doesn't exist
cd /root
if [ ! -f "/root/ComfyUI/main.py" ] ; then
    mkdir -p /root/ComfyUI
    if cp --archive --update=none "/default-comfyui-bundle/ComfyUI/." "/root/ComfyUI/" ; then
        echo "[INFO] Setting up ComfyUI..."
        echo "[INFO] Using image-bundled ComfyUI (copied to workdir)."
    else
        echo "[ERROR] Failed to copy ComfyUI bundle to '/root/ComfyUI'" >&2
        exit 1
    fi
else
    echo "[INFO] Using existing ComfyUI in user storage..."
fi

# Run user's pre-start script
cd /root
if [ -f "/root/user-scripts/pre-start.sh" ] ; then
    echo "[INFO] Running pre-start script..."
    chmod +x /root/user-scripts/pre-start.sh
    source /root/user-scripts/pre-start.sh
fi

# Set up Python environment
export PYTHONPYCACHEPREFIX="/root/.cache/pycache"
export PIP_USER=true
export PATH="${PATH}:/root/.local/bin"
export PIP_ROOT_USER_ACTION=ignore

# Install manager dependencies if not already installed
if ! python3 -c "import flask" 2>/dev/null; then
    echo "[INFO] Installing ComfyUI Manager dependencies..."
    pip install flask flask-sock requests websocket-client
fi

# Set manager environment variables
export COMFYUI_PATH="/root/ComfyUI"
export COMFYUI_PORT=8188
export COMFYUI_HOST="127.0.0.1"
export MANAGER_PORT=5000
export IDLE_TIMEOUT="${IDLE_TIMEOUT:-600}"
export COMFYUI_ARGS="${CLI_ARGS}"

echo "[INFO] Starting ComfyUI Manager..."
echo "[INFO] - Manager UI: http://localhost:5000/manager/"
echo "[INFO] - ComfyUI: http://localhost:5000/comfy/"
echo "[INFO] - Idle timeout: ${IDLE_TIMEOUT}s"
echo "########################################"

cd /root/comfyui-manager
python3 app.py
