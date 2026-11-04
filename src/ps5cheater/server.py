"""Local web app: JSON API plus the static single page interface."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import signal

from aiohttp import web

from . import __version__, console, runner
from .console import ConsoleError
from .db import Database, ValidationError
from .mcp_server import McpHttp
from .paths import STATIC_DIR

APP_ID = "ps5-cheater"
ALLOWED_TIMINGS = {"hold": (0.03, 0.5), "gap": (0.03, 0.5), "between": (0.0, 3.0), "tail": (0.0, 10.0)}


@web.middleware
async def local_only(request: web.Request, handler):
    """Block other websites and DNS rebinding from reaching the console through a browser."""
    port = request.app["port"]
    allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if request.host not in allowed:
        raise web.HTTPForbidden(text="This app is only available from this computer.")
    origin = request.headers.get("Origin")
    if origin and origin.removeprefix("http://") not in allowed:
        raise web.HTTPForbidden(text="Requests from other sites are not accepted.")
    try:
        return await handler(request)
    except (ValidationError, ConsoleError) as error:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": str(error)}), content_type="application/json"
        ) from None


async def body(request: web.Request) -> dict:
    if request.content_type != "application/json":
        raise web.HTTPUnsupportedMediaType(text="JSON expected.")
    try:
        data = await request.json()
    except ValueError:
        raise ValidationError("Invalid JSON.") from None
    if not isinstance(data, dict):
        raise ValidationError("A JSON object is expected.")
    return data


def db_of(request: web.Request) -> Database:
    return request.app["db"]


async def index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def health(_: web.Request) -> web.Response:
    return web.json_response({"app": APP_ID, "version": __version__})


async def status(request: web.Request) -> web.Response:
    db = db_of(request)
    ip = db.get_setting("console_ip")
    state, network_error = None, None
    try:
        state = await asyncio.to_thread(console.probe, ip) if ip else None
    except ConsoleError as error:
        network_error = str(error)
    accounts = await asyncio.to_thread(console.accounts)
    return web.json_response({
        "version": __version__,
        "network_error": network_error,
        "mock": console.mock_enabled(),
        "console": state,
        "console_ip": ip,
        "accounts": accounts,
        "paired": bool(state and (state.get("users") or console.mock_enabled())),
        "running": request.app["engine"].lock.locked(),
        "active_game": db.get_setting("active_game"),
        "mcp": request.app["mcp"].info(),
        "timings": runner.timings(db),
    })


async def scan(request: web.Request) -> web.Response:
    found = await asyncio.to_thread(console.scan)
    db = db_of(request)
    if len(found) == 1:
        db.set_setting("console_ip", found[0]["ip"])
    return web.json_response({"consoles": found})


async def select_console(request: web.Request) -> web.Response:
    ip = str((await body(request)).get("ip", "")).strip()
    state = await asyncio.to_thread(console.probe, ip) if ip else None
    if not state:
        raise ConsoleError(f"No console answered at {ip or 'that address'}.")
    db_of(request).set_setting("console_ip", ip)
    return web.json_response({"console": state})


async def pair_url(_: web.Request) -> web.Response:
    return web.json_response({"url": await asyncio.to_thread(console.login_url)})


async def pair_account(request: web.Request) -> web.Response:
    url = str((await body(request)).get("redirect_url", ""))
    return web.json_response({"account": await asyncio.to_thread(console.add_account, url)})


async def pair_link(request: web.Request) -> web.Response:
    data = await body(request)
    ip = request.app["engine"].console_ip()
    users = await asyncio.to_thread(console.accounts)
    user = str(data.get("account") or (users[0] if users else ""))
    if not user:
        raise ConsoleError("Sign in to PlayStation Network first.")
    await asyncio.to_thread(console.link, ip, user, str(data.get("pin", "")))
    return web.json_response({"paired": True})


async def games(request: web.Request) -> web.Response:
    return web.json_response(db_of(request).list_games())


async def add_game(request: web.Request) -> web.Response:
    data = await body(request)
    game = db_of(request).add_game(
        str(data.get("title", "")), str(data.get("platform", "PS5")), str(data.get("notes", "")),
        str(data.get("source", "")),
    )
    return web.json_response(game, status=201)


async def delete_game(request: web.Request) -> web.Response:
    return web.json_response({"deleted": db_of(request).delete_game(request.match_info["game"])})


async def cheats(request: web.Request) -> web.Response:
    return web.json_response(
        db_of(request).list_cheats(request.match_info["game"], request.query.get("q", ""))
    )


async def add_cheat(request: web.Request) -> web.Response:
    data = await body(request)
    cheat = db_of(request).add_cheat(
        request.match_info["game"], str(data.get("name", "")), data.get("sequence", ""),
        str(data.get("category") or "General"), str(data.get("warning", "")),
    )
    return web.json_response(cheat, status=201)


async def delete_cheat(request: web.Request) -> web.Response:
    deleted = db_of(request).delete_cheat(request.match_info["game"], request.match_info["slug"])
    return web.json_response({"deleted": deleted})


async def import_pack(request: web.Request) -> web.Response:
    return web.json_response(db_of(request).import_pack(await body(request)), status=201)


async def export_pack(request: web.Request) -> web.Response:
    return web.json_response(db_of(request).export_pack(request.match_info["game"]))


async def history(request: web.Request) -> web.Response:
    return web.json_response(db_of(request).recent_runs())


async def settings(request: web.Request) -> web.Response:
    data = await body(request)
    db = db_of(request)
    if "active_game" in data:
        db.set_setting("active_game", data["active_game"])
    for key, (low, high) in ALLOWED_TIMINGS.items():
        if key in data:
            value = float(data[key])
            if not low <= value <= high:
                raise ValidationError(f"{key} must be between {low} and {high} seconds.")
            db.set_setting(f"timing:{key}", value)
    if "mcp_enabled" in data:
        await request.app["mcp"].set_enabled(bool(data["mcp_enabled"]))
    return web.json_response({"ok": True})


async def run(request: web.Request) -> web.StreamResponse:
    data = await body(request)
    game_id = str(data.get("game", ""))
    slugs = data.get("cheats")
    if not isinstance(slugs, list) or not slugs:
        raise ValidationError("Add at least one cheat first.")
    engine = request.app["engine"]
    engine.db.get_cheats(game_id, [str(slug) for slug in slugs])
    if engine.lock.locked():
        raise ConsoleError("Another run is in progress.")

    response = web.StreamResponse(headers={"Content-Type": "application/x-ndjson"})
    await response.prepare(request)

    async def emit(**event) -> None:
        await response.write((json.dumps(event) + "\n").encode())

    try:
        result = await engine.run(game_id, [str(slug) for slug in slugs], bool(data.get("capture", True)), emit)
        await emit(type="done", frame=result["frame"])
    except ConsoleError as error:
        await emit(type="error", message=str(error))
    await response.write_eof()
    return response


async def snapshot(request: web.Request) -> web.Response:
    frame = await request.app["engine"].snapshot()
    return web.json_response({"frame": base64.b64encode(frame).decode()})


async def quit_app(_: web.Request) -> web.Response:
    asyncio.get_running_loop().call_later(0.2, os.kill, os.getpid(), signal.SIGTERM)
    return web.json_response({"ok": True})


async def on_startup(app: web.Application) -> None:
    if app["db"].get_setting("mcp_enabled", False):
        await app["mcp"].set_enabled(True)


async def on_cleanup(app: web.Application) -> None:
    await app["mcp"].stop()


def create_app(db: Database, port: int) -> web.Application:
    app = web.Application(middlewares=[local_only], client_max_size=4 * 1024 * 1024)
    app["db"] = db
    app["port"] = port
    app["engine"] = runner.Engine(db)
    app["mcp"] = McpHttp(db)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get("/", index)
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/status", status)
    app.router.add_post("/api/scan", scan)
    app.router.add_post("/api/console", select_console)
    app.router.add_get("/api/pair/url", pair_url)
    app.router.add_post("/api/pair/account", pair_account)
    app.router.add_post("/api/pair/link", pair_link)
    app.router.add_get("/api/games", games)
    app.router.add_post("/api/games", add_game)
    app.router.add_delete("/api/games/{game}", delete_game)
    app.router.add_get("/api/games/{game}/cheats", cheats)
    app.router.add_post("/api/games/{game}/cheats", add_cheat)
    app.router.add_delete("/api/games/{game}/cheats/{slug}", delete_cheat)
    app.router.add_get("/api/games/{game}/export", export_pack)
    app.router.add_post("/api/import", import_pack)
    app.router.add_get("/api/history", history)
    app.router.add_post("/api/settings", settings)
    app.router.add_post("/api/run", run)
    app.router.add_post("/api/snapshot", snapshot)
    app.router.add_post("/api/quit", quit_app)
    app.router.add_static("/static", STATIC_DIR)
    return app
