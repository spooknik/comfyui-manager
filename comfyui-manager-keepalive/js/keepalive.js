import { app } from "../../scripts/app.js";

/**
 * ComfyUI Manager - Keepalive Extension
 *
 * Pings the manager to keep ComfyUI alive while the browser tab is open.
 */

const PING_INTERVAL = 60000; // Ping every 60 seconds
const MANAGER_PORT = 5000;

let pingInterval = null;

function getManagerPingUrl() {
    // Manager runs on port 5000, same host as ComfyUI
    const host = window.location.hostname;
    return `http://${host}:${MANAGER_PORT}/manager/api/ping`;
}

async function ping() {
    // Only ping if the tab is visible
    if (document.hidden) {
        return;
    }

    try {
        const url = getManagerPingUrl();
        await fetch(url, {
            method: 'POST',
            mode: 'cors',
            signal: AbortSignal.timeout(5000)
        });
        console.log('[ComfyUI Manager] Ping sent');
    } catch (e) {
        // Silently ignore errors - manager might not be running
        console.log('[ComfyUI Manager] Ping failed (manager may not be running)');
    }
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
