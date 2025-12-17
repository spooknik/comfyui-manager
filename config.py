import os

# ComfyUI settings
COMFYUI_PATH = os.environ.get("COMFYUI_PATH", "/app/ComfyUI")
COMFYUI_PORT = int(os.environ.get("COMFYUI_PORT", "8188"))
COMFYUI_HOST = os.environ.get("COMFYUI_HOST", "127.0.0.1")
COMFYUI_ARGS = os.environ.get("COMFYUI_ARGS", "").split() if os.environ.get("COMFYUI_ARGS") else []

# Manager settings
MANAGER_PORT = int(os.environ.get("MANAGER_PORT", "5000"))
IDLE_TIMEOUT = int(os.environ.get("IDLE_TIMEOUT", "600"))  # 10 minutes default
STARTUP_TIMEOUT = int(os.environ.get("STARTUP_TIMEOUT", "120"))  # 2 minutes to start
