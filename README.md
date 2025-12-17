# ComfyUI Auto Start/Stop Manager

A lightweight Flask-based service that manages ComfyUI lifecycle based on user activity.

## Features

- **Auto-start**: ComfyUI starts automatically when you visit the web UI
- **Auto-stop**: ComfyUI stops after 10 minutes of inactivity (configurable)
- **Single port**: All traffic proxied through port 5000
- **Web dashboard**: Monitor status, uptime, and manually control ComfyUI
- **Docker ready**: Includes Dockerfile and docker-compose.yml

## Quick Start

### Docker (Recommended)

1. Clone or copy this project
2. Edit `docker-compose.yml` to mount your model directories
3. Run:

```bash
docker-compose up -d
```

4. Access the manager at `http://localhost:5000`

### Local Development

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set environment variables:

```bash
export COMFYUI_PATH=/path/to/ComfyUI
export IDLE_TIMEOUT=600  # optional, default 10 minutes
```

3. Run:

```bash
python app.py
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `COMFYUI_PATH` | `/app/ComfyUI` | Path to ComfyUI installation |
| `COMFYUI_PORT` | `8188` | Internal ComfyUI port |
| `COMFYUI_HOST` | `127.0.0.1` | ComfyUI listen address |
| `COMFYUI_ARGS` | (empty) | Extra arguments for ComfyUI |
| `MANAGER_PORT` | `5000` | Manager web UI port |
| `IDLE_TIMEOUT` | `600` | Seconds before auto-stop (10 min) |
| `STARTUP_TIMEOUT` | `120` | Max seconds to wait for startup |

## URLs

- `/` - Redirects to manager dashboard
- `/manager/` - Manager dashboard
- `/manager/api/status` - JSON status endpoint
- `/manager/api/start` - POST to start ComfyUI
- `/manager/api/stop` - POST to stop ComfyUI
- `/comfy/` - ComfyUI web interface (auto-starts if stopped)
- `/ws` - WebSocket proxy for ComfyUI

## How It Works

1. The manager runs on port 5000 and proxies all requests to ComfyUI on port 8188
2. When you visit `/comfy/`, the manager auto-starts ComfyUI if it's stopped
3. Every request to ComfyUI resets the idle timer
4. After 10 minutes of no activity, ComfyUI is automatically stopped
5. Use the dashboard at `/manager/` to monitor status and manually control ComfyUI

## License

MIT
