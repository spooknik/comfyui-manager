import { app } from "../../scripts/app.js";

/**
 * ComfyUI Manager - Keepalive Extension
 *
 * Pings the manager to keep ComfyUI alive while the browser tab is open.
 * Also auto-restarts ComfyUI if it was shut down while the tab was idle.
 */

const PING_INTERVAL = 60000; // Ping every 60 seconds
const MANAGER_PORT = 5000;

let pingInterval = null;
let notificationEl = null;

function getManagerPingUrl() {
    // Manager runs on port 5000, same host as ComfyUI
    const host = window.location.hostname;
    return `http://${host}:${MANAGER_PORT}/manager/api/ping`;
}

function showNotification(message, type = 'info') {
    // Remove existing notification
    if (notificationEl) {
        notificationEl.remove();
    }

    notificationEl = document.createElement('div');
    notificationEl.style.cssText = `
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        padding: 12px 24px;
        border-radius: 8px;
        font-family: system-ui, sans-serif;
        font-size: 14px;
        z-index: 99999;
        transition: opacity 0.3s;
        ${type === 'info'
            ? 'background: #1e40af; color: white;'
            : 'background: #166534; color: white;'}
    `;
    notificationEl.textContent = message;
    document.body.appendChild(notificationEl);
}

function hideNotification() {
    if (notificationEl) {
        notificationEl.style.opacity = '0';
        setTimeout(() => {
            if (notificationEl) {
                notificationEl.remove();
                notificationEl = null;
            }
        }, 300);
    }
}

async function ping(isVisibilityChange = false) {
    // Only ping if the tab is visible
    if (document.hidden) {
        return;
    }

    try {
        const url = getManagerPingUrl();
        const response = await fetch(url, {
            method: 'POST',
            mode: 'cors',
            signal: AbortSignal.timeout(5000)
        });
        const data = await response.json();

        // If ComfyUI was stopped and is now starting, show notification
        if (data.state === 'starting') {
            showNotification('ComfyUI is starting up... Please wait.');
            // Poll more frequently until it's running
            pollUntilRunning();
        } else if (data.state === 'running') {
            hideNotification();
        }

        console.log('[ComfyUI Manager] Ping sent, state:', data.state);
    } catch (e) {
        // Manager might not be running
        console.log('[ComfyUI Manager] Ping failed (manager may not be running)');
    }
}

async function pollUntilRunning() {
    const url = getManagerPingUrl();
    const checkState = async () => {
        try {
            const response = await fetch(url, {
                method: 'POST',
                mode: 'cors',
                signal: AbortSignal.timeout(5000)
            });
            const data = await response.json();

            if (data.state === 'running') {
                showNotification('ComfyUI is ready!', 'success');
                setTimeout(hideNotification, 2000);
                return true;
            } else if (data.state === 'starting') {
                return false; // Keep polling
            } else {
                hideNotification();
                return true; // Stop polling on error/stopped
            }
        } catch (e) {
            return true; // Stop polling on error
        }
    };

    // Poll every 2 seconds until running
    const poll = async () => {
        const done = await checkState();
        if (!done) {
            setTimeout(poll, 2000);
        }
    };
    poll();
}

function startPinging() {
    ping();
    if (!pingInterval) {
        pingInterval = setInterval(ping, PING_INTERVAL);
    }
}

function stopPinging() {
    if (pingInterval) {
        clearInterval(pingInterval);
        pingInterval = null;
    }
}

// Handle tab visibility changes
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        stopPinging();
    } else {
        // Ping immediately when tab becomes visible again
        startPinging();
    }
});

// Register with ComfyUI
app.registerExtension({
    name: "comfyui.manager.keepalive",
    async setup() {
        startPinging();
        console.log('[ComfyUI Manager] Keepalive extension loaded');
    }
});
