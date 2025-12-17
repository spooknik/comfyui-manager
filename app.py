import os
import sys
import time
import signal
import subprocess
import threading
import logging
from flask import Flask, request, Response, redirect, render_template, jsonify
from flask_sock import Sock
import requests
from websocket import create_connection, WebSocketConnectionClosedException

from config import (
    COMFYUI_PATH, COMFYUI_PORT, COMFYUI_HOST, COMFYUI_ARGS,
    MANAGER_PORT, IDLE_TIMEOUT, STARTUP_TIMEOUT
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
sock = Sock(app)


class ComfyUIManager:
    def __init__(self):
        self.process = None
        self.state = "stopped"  # stopped, starting, running
        self.start_time = None
        self.last_activity = None
        self.lock = threading.Lock()
        self._monitor_thread = None
        self._start_idle_monitor()

    def _start_idle_monitor(self):
        """Start background thread to monitor idle time and auto-stop."""
        def monitor():
            while True:
                time.sleep(30)
                with self.lock:
                    if self.state == "running" and self.last_activity:
                        idle_time = time.time() - self.last_activity
                        if idle_time >= IDLE_TIMEOUT:
                            logger.info(f"Idle timeout reached ({IDLE_TIMEOUT}s), stopping ComfyUI")
                            self._stop_internal()

        self._monitor_thread = threading.Thread(target=monitor, daemon=True)
        self._monitor_thread.start()

    def start(self):
        """Start ComfyUI process."""
        with self.lock:
            if self.state != "stopped":
                return True

            self.state = "starting"
            logger.info("Starting ComfyUI...")

            cmd = [sys.executable, "main.py", "--listen", COMFYUI_HOST, "--port", str(COMFYUI_PORT)]
            cmd.extend(COMFYUI_ARGS)

            try:
                self.process = subprocess.Popen(
                    cmd,
                    cwd=COMFYUI_PATH,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                # Start log reader thread
                threading.Thread(target=self._read_logs, daemon=True).start()

            except Exception as e:
                logger.error(f"Failed to start ComfyUI: {e}")
                self.state = "stopped"
                return False

        return True

    def _read_logs(self):
        """Read and log ComfyUI output."""
        if self.process and self.process.stdout:
            for line in self.process.stdout:
                logger.info(f"[ComfyUI] {line.rstrip()}")

            # Process ended
            with self.lock:
                if self.state != "stopped":
                    logger.warning("ComfyUI process ended unexpectedly")
                    self.state = "stopped"
                    self.process = None

    def wait_for_ready(self, timeout=None):
        """Wait for ComfyUI to be ready to accept requests."""
        timeout = timeout or STARTUP_TIMEOUT
        start = time.time()
        url = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}/system_stats"

        while time.time() - start < timeout:
            try:
                resp = requests.get(url, timeout=2)
                if resp.status_code == 200:
                    with self.lock:
                        self.state = "running"
                        self.start_time = time.time()
                        self.last_activity = time.time()
                    logger.info("ComfyUI is ready")
                    return True
            except requests.RequestException:
                pass
            time.sleep(1)

        logger.error(f"ComfyUI failed to start within {timeout}s")
        self.stop()
        return False

    def stop(self):
        """Stop ComfyUI process."""
        with self.lock:
            self._stop_internal()

    def _stop_internal(self):
        """Internal stop (must be called with lock held)."""
        if self.process is None:
            self.state = "stopped"
            return

        logger.info("Stopping ComfyUI...")
        self.state = "stopped"

        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("ComfyUI didn't stop gracefully, killing...")
                self.process.kill()
                self.process.wait()
        except Exception as e:
            logger.error(f"Error stopping ComfyUI: {e}")

        self.process = None
        self.start_time = None
        logger.info("ComfyUI stopped")

    def reset_idle_timer(self):
        """Reset the idle timer on activity."""
        with self.lock:
            self.last_activity = time.time()

    def is_running(self):
        """Check if ComfyUI is running."""
        with self.lock:
            return self.state == "running"

    def get_status(self):
        """Get current status information."""
        with self.lock:
            now = time.time()
            uptime = int(now - self.start_time) if self.start_time else 0
            idle_time = int(now - self.last_activity) if self.last_activity else 0
            time_until_stop = max(0, IDLE_TIMEOUT - idle_time) if self.state == "running" else 0

            return {
                "state": self.state,
                "uptime": uptime,
                "idle_time": idle_time,
                "time_until_stop": time_until_stop,
                "idle_timeout": IDLE_TIMEOUT
            }


# Global manager instance
manager = ComfyUIManager()


# --- Manager Routes ---

@app.route("/")
def index():
    """Redirect root to manager dashboard."""
    return redirect("/manager/")


@app.route("/manager/")
def manager_dashboard():
    """Render manager dashboard."""
    return render_template("index.html")


@app.route("/manager/api/status")
def api_status():
    """Get current status as JSON."""
    return jsonify(manager.get_status())


@app.route("/manager/api/start", methods=["POST"])
def api_start():
    """Manually start ComfyUI."""
    if manager.is_running():
        return jsonify({"success": True, "message": "Already running"})

    if manager.start():
        if manager.wait_for_ready():
            return jsonify({"success": True, "message": "Started"})
        return jsonify({"success": False, "message": "Failed to start"}), 500

    return jsonify({"success": False, "message": "Failed to start"}), 500


@app.route("/manager/api/stop", methods=["POST"])
def api_stop():
    """Manually stop ComfyUI."""
    manager.stop()
    return jsonify({"success": True, "message": "Stopped"})


# --- ComfyUI Proxy Routes ---

def ensure_comfyui_running():
    """Ensure ComfyUI is running, start if needed."""
    if not manager.is_running():
        status = manager.get_status()
        if status["state"] == "stopped":
            logger.info("Auto-starting ComfyUI on request")
            manager.start()
            if not manager.wait_for_ready():
                return False
    manager.reset_idle_timer()
    return True


@app.route("/comfy/", defaults={"path": ""})
@app.route("/comfy/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def proxy_comfyui(path):
    """Proxy requests to ComfyUI."""
    if not ensure_comfyui_running():
        return Response("ComfyUI failed to start", status=503)

    # Build target URL
    target_url = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}/{path}"
    if request.query_string:
        target_url += f"?{request.query_string.decode()}"

    # Forward the request
    try:
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers={k: v for k, v in request.headers if k.lower() not in ['host', 'content-length']},
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=300
        )

        # Build response
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(k, v) for k, v in resp.raw.headers.items() if k.lower() not in excluded_headers]

        return Response(resp.content, resp.status_code, headers)

    except requests.RequestException as e:
        logger.error(f"Proxy error: {e}")
        return Response(f"Proxy error: {e}", status=502)


# --- WebSocket Proxy ---

@sock.route("/ws")
def ws_proxy(ws):
    """Proxy WebSocket connections to ComfyUI."""
    if not ensure_comfyui_running():
        ws.close()
        return

    # Get client ID from query string if present
    client_id = request.args.get("clientId", "")
    ws_url = f"ws://{COMFYUI_HOST}:{COMFYUI_PORT}/ws"
    if client_id:
        ws_url += f"?clientId={client_id}"

    try:
        comfy_ws = create_connection(ws_url, timeout=10)
    except Exception as e:
        logger.error(f"Failed to connect to ComfyUI WebSocket: {e}")
        ws.close()
        return

    stop_event = threading.Event()

    def forward_to_comfy():
        """Forward messages from client to ComfyUI."""
        try:
            while not stop_event.is_set():
                try:
                    data = ws.receive(timeout=1)
                    if data is None:
                        break
                    manager.reset_idle_timer()
                    comfy_ws.send(data)
                except TimeoutError:
                    continue
        except Exception as e:
            logger.debug(f"Client->ComfyUI forward ended: {e}")
        finally:
            stop_event.set()

    def forward_to_client():
        """Forward messages from ComfyUI to client."""
        try:
            while not stop_event.is_set():
                try:
                    comfy_ws.settimeout(1)
                    data = comfy_ws.recv()
                    if data is None:
                        break
                    manager.reset_idle_timer()
                    ws.send(data)
                except TimeoutError:
                    continue
                except WebSocketConnectionClosedException:
                    break
        except Exception as e:
            logger.debug(f"ComfyUI->Client forward ended: {e}")
        finally:
            stop_event.set()

    # Start forwarding threads
    t1 = threading.Thread(target=forward_to_comfy, daemon=True)
    t2 = threading.Thread(target=forward_to_client, daemon=True)
    t1.start()
    t2.start()

    # Wait for either thread to finish
    stop_event.wait()

    # Cleanup
    try:
        comfy_ws.close()
    except:
        pass


def shutdown_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info("Shutdown signal received")
    manager.stop()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    logger.info(f"Starting ComfyUI Manager on port {MANAGER_PORT}")
    logger.info(f"ComfyUI path: {COMFYUI_PATH}")
    logger.info(f"Idle timeout: {IDLE_TIMEOUT}s")

    app.run(host="0.0.0.0", port=MANAGER_PORT, threaded=True)
