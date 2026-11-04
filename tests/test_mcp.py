from conftest import GAME
from ps5cheater.mcp_server import build_server


async def call(server, tool, **arguments):
    return await server.call_tool(tool, arguments)


async def test_tools_are_registered(db):
    names = {tool.name for tool in await build_server(db).list_tools()}
    assert {"list_games", "list_cheats", "add_cheat", "run_cheats", "capture_screen"} <= names


async def test_agent_can_add_a_new_game(db):
    server = build_server(db)
    await call(server, "add_game", title="Agent Game")
    await call(server, "add_cheat", game_id="agent-game", name="Jump", sequence=["UP", "CROSS"])
    assert db.list_cheats("agent-game")[0]["slug"] == "jump"


async def test_run_returns_summary_and_screen(db):
    db.set_setting("timing:tail", 0)
    content = await call(build_server(db), "run_cheats", game_id=GAME, cheat_slugs=["full-armor"])
    blocks = content[0] if isinstance(content, tuple) else content
    assert any(getattr(block, "type", "") == "image" for block in blocks)
    assert any("full-armor" in getattr(block, "text", "") for block in blocks)


async def test_capture_screen_returns_an_image(db):
    content = await call(build_server(db), "capture_screen")
    blocks = content[0] if isinstance(content, tuple) else content
    assert blocks[0].type == "image"
