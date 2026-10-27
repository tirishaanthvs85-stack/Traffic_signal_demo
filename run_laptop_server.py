"""
run_laptop_server.py - Launches the AI Traffic Signal Laptop Working Model.
Serves the web dashboard locally and opens it directly in your browser.
"""
import os
import sys
import webbrowser
import http.server
import socketserver

# Ensure Windows stdout handles UTF-8 characters gracefully
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PORT = 8080
DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "laptop_model")

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

def start_server():
    os.chdir(DIRECTORY)
    # Attempt to bind to PORT, try subsequent ports if busy
    port = PORT
    httpd = None
    for p in range(PORT, PORT + 20):
        try:
            httpd = socketserver.TCPServer(("", p), Handler)
            port = p
            break
        except OSError:
            continue

    if not httpd:
        print("[ERROR] Could not bind to any port between 8080 and 8100.")
        # Fallback to direct file open
        index_path = os.path.join(DIRECTORY, "index.html")
        webbrowser.open(f"file://{index_path}")
        return

    url = f"http://localhost:{port}/index.html"
    print("=" * 65)
    print("🚦 NEURA-TRAFFIC AI 4.0 // LAPTOP WORKING MODEL")
    print(f"📡 Web Server active at: {url}")
    print("💻 Opening working model in your default web browser...")
    print("=" * 65)
    print("Press Ctrl+C to shut down the server when finished.")

    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server. Goodbye!")
        httpd.server_close()

if __name__ == "__main__":
    start_server()
