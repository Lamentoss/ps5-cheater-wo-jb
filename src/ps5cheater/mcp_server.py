"""MCP server exposing the cheat database and the console to AI agents."""
from __future__ import annotations

import asyncio
import base64
import sys
import threading

from mcp.server.fastmcp import FastMCP, Image
from mcp.server.transport_security import TransportSecuritySettings

from . import console, runner
from .db import Database

MCP_PORT = 8766
INSTRUCTIONS = (
    "Controls a jailbreak-free PS5 through Remote Play by pressing in-game cheat codes. "
    "Call get_status first, then list_games and list_cheats. run_cheats presses every code in "
    "order over one connection and returns the final screen, so check it for confirmation. "
    "Disconnecting pauses most games, and the game must be in gameplay before a run, so use "
    "capture_screen when unsure. For single-player use only."
)


def build_server(db: Database, port: int = MCP_PORT, allowed_hosts=None) -> FastMCP:
    engine = runner.Engine(db)
    hosts = allowed_hosts or [f"127.0.0.1:{port}", f"localhost:{port}"]
    server = FastMCP(
        "ps5-cheater", instructions=INSTRUCTIONS, host="127.0.0.1", port=port,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=hosts,
            allowed_origins=[f"http://{host}" for host in hosts],
        ),
    )

    @server.tool()
    def get_status() -> dict:
        """Report the selected console, whether it is reachable, and whether it is paired."""
        ip = db.get_setting("console_ip")
        state = console.probe(ip) if ip else None
        return {"console_ip": ip, "console": state, "paired": bool(state and state.get("users")),
                "active_game": db.get_setting("active_game")}

    @server.tool()
    def scan_network(select_if_single: bool = True) -> list[dict]:
        """Search the local network for consoles."""
        found = console.scan()
        if select_if_single and len(found) == 1:
            db.set_setting("console_ip", found[0]["ip"])
        return found

    @server.tool()
    def list_games() -> list[dict]:
        """List games in the local database with their cheat counts."""
        return db.list_games()

    @server.tool()
    def list_cheats(game_id: str, query: str = "") -> list[dict]:
        """List cheats for a game, optionally filtered by name, slug or category."""
        return db.list_cheats(game_id, query)

    @server.tool()
    def add_game(title: str, platform: str = "PS5", notes: str = "", source: str = "") -> dict:
        """Add a game, or update it if it already exists. source is where the codes came from."""
        return db.add_game(title, platform, notes, source)

    @server.tool()
    def add_cheat(game_id: str, name: str, sequence: list[str], category: str = "General",
                  warning: str = "") -> dict:
        """Add a cheat. sequence uses UP DOWN LEFT RIGHT L1 R1 L2 R2 CROSS CIRCLE SQUARE TRIANGLE."""
        return db.add_cheat(game_id, name, sequence, category, warning)

    @server.tool()
    def delete_cheat(game_id: str, slug: str) -> bool:
        """Delete one cheat."""
        return db.delete_cheat(game_id, slug)

    @server.tool()
    def import_pack(pack: dict) -> dict:
        """Import a cheat pack: {"game": {"title": ...}, "cheats": [{"name", "sequence"}]}."""
        return db.import_pack(pack)

    @server.tool()
    async def capture_screen() -> Image:
        """Return the current console screen. Connecting and disconnecting pauses most games."""
        return Image(data=await engine.snapshot(), format="png")

    @server.tool()
    async def run_cheats(game_id: str, cheat_slugs: list[str]) -> list:
        """Press the cheats in order over one connection, wait, capture the screen, disconnect."""
        result = await engine.run(game_id, cheat_slugs)
        summary = f"Sent {len(cheat_slugs)} cheat(s): {', '.join(cheat_slugs)}."
        if result["frame"]:
            return [summary, Image(data=base64.b64decode(result["frame"]), format="png")]
        return [summary + " No screen capture arrived."]

    return server


class McpHttp:
    """Optional local HTTP endpoint, switched on from the app."""

    def __init__(self, db: Database, port: int = MCP_PORT):
        self.db = db
        self.port = port
        self._uvicorn = None
        self._thread = None

    def info(self) -> dict:
        frozen = getattr(sys, "frozen", False)
        return {
            "enabled": self._uvicorn is not None,
            "url": f"http://127.0.0.1:{self.port}/mcp",
            "command": sys.executable,
            "args": ["mcp"] if frozen else ["-m", "ps5cheater", "mcp"],
        }

    async def set_enabled(self, enabled: bool) -> None:
        self.db.set_setting("mcp_enabled", enabled)
        if enabled and self._uvicorn is None:
            import uvicorn

            app = build_server(self.db, self.port).streamable_http_app()
            config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
            self._uvicorn = uvicorn.Server(config)
            self._thread = threading.Thread(target=self._uvicorn.run, daemon=True)
            self._thread.start()
        elif not enabled:
            await self.stop()

    async def stop(self) -> None:
        if self._uvicorn is None:
            return
        self._uvicorn.should_exit = True
        await asyncio.to_thread(self._thread.join, 5)
        self._uvicorn = None
        self._thread = None
