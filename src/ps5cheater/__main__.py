"""Command line and app entry point."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import urllib.request
import webbrowser

from .db import Database
from .paths import data_dir

DEFAULT_PORT = 8765


def already_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as reply:
            return json.load(reply).get("app") == "ps5-cheater"
    except (OSError, ValueError):
        return False


def serve(port: int, open_browser: bool) -> None:
    from aiohttp import web

    from .server import create_app

    url = f"http://127.0.0.1:{port}"
    if already_running(port):
        if open_browser:
            webbrowser.open(url)
        return
    app = create_app(Database(data_dir() / "cheats.db"), port)
    if open_browser:
        threading.Timer(0.6, webbrowser.open, (url,)).start()
    print(f"PS5 Cheater running at {url}", file=sys.stderr, flush=True)
    web.run_app(app, host="127.0.0.1", port=port, print=None)


def main() -> None:
    parser = argparse.ArgumentParser(prog="ps5-cheater", description=__doc__)
    parser.add_argument("command", nargs="?", default="app", choices=["app", "serve", "mcp"],
                        help="app opens the browser, serve does not, mcp speaks MCP over stdio")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING,
        handlers=[logging.FileHandler(data_dir() / "ps5-cheater.log", encoding="utf-8")],
    )
    if args.command == "mcp":
        from .mcp_server import build_server

        build_server(Database(data_dir() / "cheats.db")).run("stdio")
    else:
        serve(args.port, args.command == "app")


if __name__ == "__main__":
    main()
