import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from conftest import GAME
from ps5cheater.console import NETWORK_BLOCKED, ConsoleError
from ps5cheater.server import create_app


@pytest.fixture
async def client(db):
    app = create_app(db, 0)
    test = TestClient(TestServer(app))
    await test.start_server()
    test.headers = {"Host": f"127.0.0.1:{test.port}"}
    app._state["port"] = test.port
    yield test
    await test.close()


async def get(client, path):
    return await client.get(path, headers=client.headers)


async def post(client, path, data, **headers):
    return await client.post(path, json=data, headers={**client.headers, **headers})


async def test_status_reports_mock_console(client):
    data = await (await get(client, "/api/status")).json()
    assert data["paired"] and data["console"]["name"] == "PS5-MOCK"
    assert data["mcp"]["enabled"] is False


async def test_blocked_network_is_reported_not_crashed(client, monkeypatch):
    def blocked(_):
        raise ConsoleError(NETWORK_BLOCKED)

    monkeypatch.setattr("ps5cheater.console.probe", blocked)
    reply = await get(client, "/api/status")
    assert reply.status == 200
    data = await reply.json()
    assert data["network_error"] == NETWORK_BLOCKED and data["console"] is None


async def test_static_page_is_served(client):
    page = await (await get(client, "/")).text()
    assert "PS5 Cheater" in page


async def test_other_sites_are_rejected(client):
    bad_origin = await post(client, "/api/run", {}, Origin="https://evil.example")
    assert bad_origin.status == 403
    bad_host = await client.get("/api/status", headers={"Host": "evil.example"})
    assert bad_host.status == 403


async def test_form_posts_are_rejected(client):
    reply = await client.post("/api/run", data="a=b", headers=client.headers)
    assert reply.status == 415


async def test_run_streams_events_in_order(client, db):
    db.set_setting("timing:tail", 0)
    reply = await post(client, "/api/run", {"game": GAME, "cheats": ["full-armor", "full-armor"]})
    events = [json.loads(line) for line in (await reply.text()).splitlines()]
    assert [e["type"] for e in events] == ["connecting", "cheat", "cheat", "waiting", "done"]
    assert events[-1]["frame"]


async def test_run_with_unknown_cheat_gets_a_clear_error(client):
    reply = await post(client, "/api/run", {"game": GAME, "cheats": ["nope"]})
    assert reply.status == 400
    assert "nope" in (await reply.json())["error"]


async def test_game_and_cheat_crud(client):
    game = await (await post(client, "/api/games", {"title": "New Game"})).json()
    added = await post(client, f"/api/games/{game['id']}/cheats", {"name": "Boost", "sequence": ["UP", "L2"]})
    assert added.status == 201
    cheats = await (await get(client, f"/api/games/{game['id']}/cheats")).json()
    assert cheats[0]["sequence"] == ["UP", "L2"]


async def test_timing_limits(client):
    assert (await post(client, "/api/settings", {"hold": 9})).status == 400
    assert (await post(client, "/api/settings", {"hold": 0.1})).status == 200


async def test_pin_must_have_eight_digits(client):
    reply = await post(client, "/api/pair/link", {"pin": "123"})
    assert reply.status == 400
