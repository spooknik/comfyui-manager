/**
 * ComfyUI Manager - Activity Ping Extension
 *
 * This script pings the manager to keep ComfyUI alive while the browser tab is open.
 * Place this file in: ComfyUI/web/extensions/comfyui-manager-ping.js
 */

(function() {
    const PING_INTERVAL = 60000; // Ping every 60 seconds
    const MANAGER_PING_URL = '/manager/api/ping';

    let pingInterval = null;

    async function ping() {
        // Only ping if the tab is visible
        if (document.hidden) {
            return;
        }

        try {
            await fetch(MANAGER_PING_URL, {
                method: 'POST',
                // Short timeout - don't block if manager is unreachable
                signal: AbortSignal.timeout(5000)
            });
        } catch (e) {
            // Silently ignore errors - manager might not be running
            // (e.g., if ComfyUI is running standalone without the manager)
        }
    }

    function startPinging() {
        // Initial ping
        ping();

        // Set up interval
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

    // Start when the page loads
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', startPinging);
    } else {
        startPinging();
    }

    console.log('[ComfyUI Manager] Activity ping extension loaded');
})();
