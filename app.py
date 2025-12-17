import os
import sys
import time
import signal
import subprocess
import threading
import logging
from flask import Flask, request, Response, render_template, jsonify
import requests

from config import (
    COMFYUI_PATH, COMFYUI_PORT, COMFYUI_HOST, COMFYUI_ARGS,
    MANAGER_PORT, IDLE_TIMEOUT, STARTUP_TIMEOUT
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)


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

            # ComfyUI listens on 0.0.0.0 so we can access it, but we proxy most requests
            cmd = [sys.executable, "main.py", "--listen", "0.0.0.0", "--port", str(COMFYUI_PORT)]
            if COMFYUI_ARGS:
                cmd.extend(COMFYUI_ARGS.split() if isinstance(COMFYUI_ARGS, str) else COMFYUI_ARGS)

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
        url = f"http://127.0.0.1:{COMFYUI_PORT}/system_stats"

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


# --- Manager Routes (under /manager/) ---

@app.route("/manager/")
def manager_dashboard():
    """Render manager dashboard."""
    return render_template("index.html", comfyui_port=COMFYUI_PORT)


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


# Serve manager static files
@app.route("/manager/static/<path:path>")
def manager_static(path):
    """Serve manager static files."""
    return app.send_static_file(path)


# --- Landing page that checks status and redirects ---

@app.route("/")
def landing():
    """Landing page - starts ComfyUI and redirects to it."""
    if not manager.is_running():
        status = manager.get_status()
        if status["state"] == "stopped":
            logger.info("Auto-starting ComfyUI on landing page visit")
            manager.start()
            # Show starting page
            return Response(
                f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Starting ComfyUI...</title>
                    <meta http-equiv="refresh" content="3">
                    <style>
                        body {{
                            font-family: system-ui;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            height: 100vh;
                            margin: 0;
                            background: #1a1a2e;
                            color: #eee;
                        }}
                        .loader {{ text-align: center; }}
                        .spinner {{
                            width: 50px;
                            height: 50px;
                            border: 4px solid #333;
                            border-top-color: #4ade80;
                            border-radius: 50%;
                            animation: spin 1s linear infinite;
                            margin: 0 auto 20px;
                        }}
                        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
                        a {{ color: #4ade80; }}
                    </style>
                </head>
                <body>
                    <div class="loader">
                        <div class="spinner"></div>
                        <h2>Starting ComfyUI...</h2>
                        <p>This page will refresh automatically.</p>
                        <p><a href="/manager/">Go to Manager</a></p>
                    </div>
                </body>
                </html>
                """,
                status=200,
                content_type="text/html"
            )
        elif status["state"] == "starting":
            # Still starting, show wait page
            return Response(
                f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Starting ComfyUI...</title>
                    <meta http-equiv="refresh" content="2">
                    <style>
                        body {{
                            font-family: system-ui;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            height: 100vh;
                            margin: 0;
                            background: #1a1a2e;
                            color: #eee;
                        }}
                        .loader {{ text-align: center; }}
                        .spinner {{
                            width: 50px;
                            height: 50px;
                            border: 4px solid #333;
                            border-top-color: #4ade80;
                            border-radius: 50%;
                            animation: spin 1s linear infinite;
                            margin: 0 auto 20px;
                        }}
                        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
                        a {{ color: #4ade80; }}
                    </style>
                </head>
                <body>
                    <div class="loader">
                        <div class="spinner"></div>
                        <h2>ComfyUI is starting...</h2>
                        <p>Please wait, this page will redirect when ready.</p>
                        <p><a href="/manager/">Go to Manager</a></p>
                    </div>
                </body>
                </html>
                """,
                status=200,
                content_type="text/html"
            )

    # ComfyUI is running, redirect to it directly
    manager.reset_idle_timer()
    # Redirect to ComfyUI's actual port
    host = request.host.split(':')[0]  # Get hostname without port
    return Response(
        f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Redirecting to ComfyUI...</title>
            <meta http-equiv="refresh" content="0; url=http://{host}:{COMFYUI_PORT}/">
            <style>
                body {{
                    font-family: system-ui;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    background: #1a1a2e;
                    color: #eee;
                }}
                a {{ color: #4ade80; }}
            </style>
        </head>
        <body>
            <div>
                <p>Redirecting to <a href="http://{host}:{COMFYUI_PORT}/">ComfyUI</a>...</p>
            </div>
        </body>
        </html>
        """,
        status=200,
        content_type="text/html"
    )


# --- Activity tracking endpoint (called by ComfyUI frontend) ---

@app.route("/manager/api/ping", methods=["POST", "GET"])
def api_ping():
    """Reset idle timer - can be called periodically by frontend."""
    manager.reset_idle_timer()
    return jsonify({"success": True})


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
    logger.info(f"ComfyUI will run on port: {COMFYUI_PORT}")
    logger.info(f"Idle timeout: {IDLE_TIMEOUT}s")
    logger.info(f"")
    logger.info(f"Access URLs:")
    logger.info(f"  Landing page: http://localhost:{MANAGER_PORT}/")
    logger.info(f"  Manager UI:   http://localhost:{MANAGER_PORT}/manager/")
    logger.info(f"  ComfyUI:      http://localhost:{COMFYUI_PORT}/ (when running)")

    app.run(host="0.0.0.0", port=MANAGER_PORT, threaded=True)
