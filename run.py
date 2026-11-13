# -*- coding: utf-8 -*-
"""Entry point.

  python run.py                 -> opens the control panel in your browser (setup + start/stop)
  python run.py --headless      -> no panel, runs the bot using data/config.json (for servers)
  python run.py --port 9000     -> use another panel port
"""
import argparse
import signal
import sys
import threading
import webbrowser

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from app import __version__, config            # noqa: E402
from app.panel import serve                    # noqa: E402
from app.worker import Engine                  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true", help="run without the web panel")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    cfg = config.load()
    if not config.CONFIG_PATH.exists():
        config.save(cfg)
    engine = Engine()
    print(f"Security Feed Bot for Bale v{__version__}")

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *a: stop.set())
    try:
        signal.signal(signal.SIGTERM, lambda *a: stop.set())
    except (AttributeError, ValueError):
        pass

    if args.headless:
        if not (cfg["bale_token"] and cfg["channel_id"]):
            print("ERROR: token/channel are empty. Run `python run.py` once and fill the panel first.")
            return 1
        engine.start()
        print("Bot is running in headless mode. Press Ctrl+C to stop.")
    else:
        port = args.port or cfg["panel_port"]
        try:
            server = serve(engine, port)
        except OSError:
            print(f"ERROR: port {port} is busy. Use: python run.py --port 9000")
            return 1
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{port}/"
        print(f"Control panel: {url}   (press Ctrl+C to quit)")
        if cfg["auto_start"] and cfg["bale_token"] and cfg["channel_id"]:
            engine.start()
            print("Auto-start: bot is running.")
        if not args.no_browser:
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    while not stop.is_set():
        stop.wait(1)
    print("Shutting down...")
    if engine.running:
        engine.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
