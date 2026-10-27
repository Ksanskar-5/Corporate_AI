#!/usr/bin/env python3
"""
main.py — Desktop Launcher for Corporate AI Assistant
Starts the local FastAPI service and renders the desktop interface
using pywebview (native macOS WebKit window) with automatic browser fallback.
"""

import sys
import os
import time
import socket
import threading
import webbrowser

# Add project root to sys.path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import uvicorn
from src.app.server import app

PORT = 8765
HOST = "127.0.0.1"


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def run_server():
    """Runs FastAPI in background thread."""
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    server.run()


def main():
    print("=" * 65)
    print("      CORPORATE AI — MODERN ENTERPRISE DESKTOP APP")
    print("=" * 65)
    print(f"Backend Service : http://{HOST}:{PORT}")
    print("Engine          : WebKit (macOS Native pywebview)")

    # Start FastAPI server in background thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Wait for server to become active
    retries = 20
    while retries > 0 and not is_port_open(HOST, PORT):
        time.sleep(0.2)
        retries -= 1

    url = f"http://{HOST}:{PORT}"

    # Check if user requested pure browser mode via CLI
    if "--web" in sys.argv:
        print(f"\nOpening in default browser: {url}")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down server.")
            sys.exit(0)

    # Launch native desktop window via pywebview
    try:
        import webview

        print("\nLaunching native macOS desktop window...")
        window = webview.create_window(
            title="Corporate AI — Privacy-Preserving Enterprise Copilot",
            url=url,
            width=1240,
            height=820,
            min_size=(980, 640),
            background_color="#090D16",
            text_select=True,
        )
        webview.start()
    except Exception as e:
        print(f"\n[Note] Native window launcher: {e}")
        print(f"Opening in default browser window: {url}")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down.")
            sys.exit(0)


if __name__ == "__main__":
    main()
