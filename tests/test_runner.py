import asyncio
import errno

import pytest

from conftest import GAME
from ps5cheater import runner
from ps5cheater.console import ConsoleError


class Session:
    instances = []

    def __init__(self, ip):
        self.events = []
        Session.instances.append(self)

    async def open(self):
        self.events.append("open")

    async def press(self, button, hold):
        self.events.append(button)

    async def snapshot(self):
        self.events.append("snapshot")
        return b"png"

    async def close(self):
        self.events.append("close")


@pytest.fixture
def session(monkeypatch, db):
    Session.instances = []
    monkeypatch.setattr(runner, "new_session", Session)
    db.set_setting("timing:tail", 0)
    db.set_setting("timing:between", 0)
    db.set_setting("timing:gap", 0)
    return Session


SLUGS = ["full-armor", "weapon-set-3", "spawn-rhino-tank", "remove-wanted-level"]


async def test_whole_cart_uses_one_connection(db, session):
    events = []

    async def emit(**event):
        events.append(event["type"])

    result = await runner.Engine(db).run(GAME, SLUGS, True, emit)
    assert len(session.instances) == 1
    pressed = session.instances[0].events
    assert pressed[0] == "open" and pressed[-1] == "close"
    assert pressed.count("open") == pressed.count("close") == 1
    assert pressed[-2] == "snapshot"
    assert len(pressed) == 3 + sum(len(c["sequence"]) for c in db.get_cheats(GAME, SLUGS))
    assert events == ["connecting", "cheat", "cheat", "cheat", "cheat", "waiting"]
    assert result["frame"]


async def test_session_closes_when_a_press_fails(db, session, monkeypatch):
    async def broken(self, button, hold):
        raise ConsoleError("dropped")

    monkeypatch.setattr(session, "press", broken)
    with pytest.raises(ConsoleError):
        await runner.Engine(db).run(GAME, SLUGS)
    assert session.instances[0].events[-1] == "close"
    assert db.recent_runs()[0]["status"] == "failed"


async def test_blocked_network_gets_a_helpful_message(db, session, monkeypatch):
    async def blocked(self):
        raise OSError(errno.EHOSTUNREACH, "No route to host")

    monkeypatch.setattr(session, "open", blocked)
    with pytest.raises(ConsoleError, match="Local Network"):
        await runner.Engine(db).run(GAME, SLUGS)
    assert session.instances[0].events == ["close"]


async def test_only_one_run_at_a_time(db, session):
    engine = runner.Engine(db)
    release = asyncio.Event()

    async def blocked(**event):
        await release.wait()

    first = asyncio.create_task(engine.run(GAME, SLUGS, False, blocked))
    await asyncio.sleep(0)
    with pytest.raises(ConsoleError):
        await engine.run(GAME, SLUGS)
    release.set()
    await first


async def test_no_console_selected(db, session):
    db.set_setting("console_ip", None)
    with pytest.raises(ConsoleError):
        await runner.Engine(db).run(GAME, SLUGS)
    assert db.recent_runs() == []
