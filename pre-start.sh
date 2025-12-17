#!/bin/bash
# ComfyUI Manager pre-start script
# Place this at /root/user-scripts/pre-start.sh
#
# This script installs and starts the ComfyUI Manager, which will
# handle starting/stopping ComfyUI based on user activity.

set -e

echo "########################################"
echo "[INFO] ComfyUI Manager Setup"
echo "########################################"

# Set up Python environment (same as entrypoint)
export PYTHONPYCACHEPREFIX="/root/.cache/pycache"
export PIP_USER=true
export PATH="${PATH}:/root/.local/bin"
export PIP_ROOT_USER_ACTION=ignore

# Install manager dependencies if not already installed
if ! python3 -c "import flask_sock" 2>/dev/null; then
    echo "[INFO] Installing ComfyUI Manager dependencies..."
    pip install flask flask-sock requests websocket-client
fi

# Find manager location - check both possible paths
MANAGER_DIR="/root/ComfyUI/comfyui-manager"
if [ ! -f "${MANAGER_DIR}/app.py" ]; then
    MANAGER_DIR="/root/comfyui-manager"
fi

if [ ! -f "${MANAGER_DIR}/app.py" ]; then
    echo "[ERROR] ComfyUI Manager not found!"
    echo "[ERROR] Checked: /root/ComfyUI/comfyui-manager/ and /root/comfyui-manager/"
    echo "[INFO] Falling back to standard ComfyUI startup..."
    return 0
fi

echo "[INFO] Found ComfyUI Manager at: ${MANAGER_DIR}"

# Set manager environment variables
export COMFYUI_PATH="/root/ComfyUI"
export COMFYUI_PORT=8188
export COMFYUI_HOST="127.0.0.1"
export MANAGER_PORT=5000
export IDLE_TIMEOUT="${IDLE_TIMEOUT:-600}"
export COMFYUI_ARGS="--listen --port 8188 ${CLI_ARGS}"

echo "[INFO] Starting ComfyUI Manager..."
echo "[INFO] - Manager UI: http://localhost:5000/manager/"
echo "[INFO] - ComfyUI: http://localhost:5000/comfy/"
echo "[INFO] - Idle timeout: ${IDLE_TIMEOUT}s"
echo "########################################"

# Start the manager (this blocks, so the entrypoint's ComfyUI command never runs)
cd "${MANAGER_DIR}"
exec python3 app.py
