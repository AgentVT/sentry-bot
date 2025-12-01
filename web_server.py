#!/usr/bin/env python3
"""
SentryBot Web Interface
Provides a web dashboard and REST API for monitoring SentryBot status
"""

from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
import threading
import logging
import json
from typing import Optional

# HTML template for the dashboard
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SentryBot Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 40px;
            max-width: 600px;
            width: 100%;
        }
        h1 {
            color: #333;
            margin-bottom: 30px;
            text-align: center;
            font-size: 2.5em;
        }
        .status-card {
            background: #f8f9fa;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 20px;
            transition: transform 0.2s;
        }
        .status-card:hover {
            transform: translateY(-5px);
        }
        .status-label {
            font-size: 0.9em;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 10px;
        }
        .status-value {
            font-size: 2em;
            font-weight: bold;
            color: #333;
        }
        .state-STANDBY { color: #28a745; }
        .state-INITIALIZING { color: #ffc107; }
        .state-POWERING_ON { color: #fd7e14; }
        .state-UNAUTHORIZED { color: #dc3545; }
        .state-WARNING { color: #e83e8c; }
        .state-ALARM { color: #dc3545; }
        .state-POWERING_DOWN { color: #6c757d; }
        .motion-detected {
            display: inline-block;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            margin-left: 10px;
            animation: pulse 2s infinite;
        }
        .motion-yes {
            background: #dc3545;
        }
        .motion-no {
            background: #28a745;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .timestamp {
            color: #999;
            font-size: 0.9em;
            text-align: center;
            margin-top: 20px;
        }
        .refresh-indicator {
            text-align: center;
            color: #666;
            font-size: 0.85em;
            margin-top: 15px;
        }
        .error {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            border: 1px solid #f5c6cb;
        }
        .loading {
            text-align: center;
            color: #666;
            font-size: 1.2em;
            padding: 40px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🛡️ SentryBot</h1>
        <div id="content" class="loading">Loading...</div>
    </div>

    <script>
        function formatTimestamp(timestamp) {
            const date = new Date(timestamp * 1000);
            return date.toLocaleString();
        }

        function getStateEmoji(state) {
            const emojis = {
                'STANDBY': '🟢',
                'INITIALIZING': '🟡',
                'POWERING_ON': '🟠',
                'UNAUTHORIZED': '🔴',
                'WARNING': '⚠️',
                'ALARM': '🚨',
                'POWERING_DOWN': '⬇️'
            };
            return emojis[state] || '❓';
        }

        async function updateStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();

                const motionClass = data.motion_detected ? 'motion-yes' : 'motion-no';
                const motionText = data.motion_detected ? 'YES' : 'NO';

                const html = `
                    <div class="status-card">
                        <div class="status-label">System State</div>
                        <div class="status-value state-${data.state}">
                            ${getStateEmoji(data.state)} ${data.state.replace('_', ' ')}
                        </div>
                    </div>
                    <div class="status-card">
                        <div class="status-label">Motion Detected</div>
                        <div class="status-value">
                            ${motionText}
                            <span class="motion-detected ${motionClass}"></span>
                        </div>
                    </div>
                    <div class="timestamp">
                        Last updated: ${formatTimestamp(data.timestamp)}
                    </div>
                    <div class="refresh-indicator">
                        Auto-refreshing every 2 seconds
                    </div>
                `;

                document.getElementById('content').innerHTML = html;
            } catch (error) {
                document.getElementById('content').innerHTML = `
                    <div class="error">
                        <strong>Error:</strong> Unable to connect to SentryBot.
                        Make sure the system is running.
                    </div>
                `;
                console.error('Error fetching status:', error);
            }
        }

        // Update immediately
        updateStatus();

        // Update every 2 seconds
        setInterval(updateStatus, 2000);
    </script>
</body>
</html>
"""


class WebServer:
    """Web server for SentryBot monitoring"""

    def __init__(self, sentrybot_instance, config: dict):
        self.sentrybot = sentrybot_instance
        self.config = config
        self.app = Flask(__name__)
        CORS(self.app)  # Enable CORS for API access

        # Disable Flask's default logging to avoid clutter
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        self._setup_routes()
        self.server_thread: Optional[threading.Thread] = None

    def _setup_routes(self):
        """Setup Flask routes"""

        @self.app.route('/')
        def dashboard():
            """Main dashboard page"""
            return render_template_string(DASHBOARD_HTML)

        @self.app.route('/api/status')
        def api_status():
            """REST API endpoint for status"""
            try:
                status = self.sentrybot.get_state()
                return jsonify(status)
            except Exception as e:
                logging.error(f"Error getting status: {e}")
                return jsonify({
                    'error': 'Failed to get status',
                    'state': 'UNKNOWN',
                    'timestamp': 0,
                    'motion_detected': False
                }), 500

        @self.app.route('/api/config')
        def api_config():
            """REST API endpoint for configuration (sanitized)"""
            # Don't expose full file paths for security
            safe_config = {
                'pir_pin': self.config.get('pir_pin'),
                'led_type': self.config.get('led_type'),
                'voice_enabled': self.config.get('voice_enabled'),
                'warning_delay': self.config.get('warning_delay'),
                'alarm_delay': self.config.get('alarm_delay')
            }
            return jsonify(safe_config)

    def start(self):
        """Start web server in background thread"""
        host = self.config.get('host', '0.0.0.0')
        port = self.config.get('port', 5000)

        def run_server():
            logging.info(f"Starting web server on http://{host}:{port}")
            print(f"Web dashboard available at http://{host}:{port}")
            self.app.run(
                host=host,
                port=port,
                debug=False,
                use_reloader=False,
                threaded=True
            )

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()

    def stop(self):
        """Stop web server"""
        # Flask doesn't have a built-in stop method when running in a thread
        # The daemon thread will automatically stop when main program exits
        logging.info("Web server stopping...")


def main():
    """Standalone web server for testing"""
    from sentrybot import SentryBot

    # Load config
    with open('config.json', 'r') as f:
        config = json.load(f)

    # Create mock SentryBot for testing
    class MockSentryBot:
        def get_state(self):
            import time
            import random
            states = ['STANDBY', 'POWERING_ON', 'UNAUTHORIZED', 'WARNING', 'ALARM']
            return {
                'state': random.choice(states),
                'timestamp': time.time(),
                'motion_detected': random.choice([True, False])
            }

    bot = MockSentryBot()
    web_config = config.get('web_server', {'host': '0.0.0.0', 'port': 5000})
    server = WebServer(bot, web_config)
    server.start()

    print("Web server running. Press Ctrl+C to stop.")
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping web server...")


if __name__ == "__main__":
    main()
