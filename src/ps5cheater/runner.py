"""Run a list of cheats over one Remote Play connection."""
from __future__ import annotations

import asyncio
import base64
from typing import Awaitable, Callable

from .console import ConsoleError, network_message, new_session
from .db import Database

DEFAULTS = {"hold": 0.08, "gap": 0.08, "between": 0.3, "tail": 2.0}
Emit = Callable[..., Awaitable[None]]


def timings(db: Database) -> dict:
    return {key: db.get_setting(f"timing:{key}", value) for key, value in DEFAULTS.items()}


async def _ignore(**_) -> None:
    pass


class Engine:
    """Serialises console access: a console accepts a single session."""

    def __init__(self, db: Database):
        self.db = db
        self.lock = asyncio.Lock()

    def console_ip(self) -> str:
        ip = self.db.get_setting("console_ip")
        if not ip:
            raise ConsoleError("No console selected. Search the network on the Connect page.")
        return ip

    async def run(self, game_id: str, slugs: list[str], capture: bool = True,
                  emit: Emit = _ignore) -> dict:
        """Open once, press every cheat in order, wait, then close once."""
        cheats = self.db.get_cheats(game_id, slugs)
        if not cheats:
            raise ConsoleError("Add at least one cheat first.")
        if self.lock.locked():
            raise ConsoleError("Another run is in progress.")
        settings = timings(self.db)
        ip = self.console_ip()
        async with self.lock:
            run_id = self.db.start_run(game_id, slugs)
            session = new_session(ip)
            result: dict = {"status": "done", "cheats": slugs, "frame": None}
            try:
                await emit(type="connecting")
                await session.open()
                for index, cheat in enumerate(cheats):
                    await emit(type="cheat", index=index, slug=cheat["slug"])
                    for button in cheat["sequence"]:
                        await session.press(button, settings["hold"])
                        await asyncio.sleep(settings["gap"])
                    if index < len(cheats) - 1:
                        await asyncio.sleep(settings["between"])
                await emit(type="waiting", seconds=settings["tail"])
                await asyncio.sleep(settings["tail"])
                if capture:
                    frame = await session.snapshot()
                    if frame:
                        result["frame"] = base64.b64encode(frame).decode()
                self.db.finish_run(run_id, "done")
                return result
            except ConsoleError as error:
                self.db.finish_run(run_id, "failed", str(error))
                raise
            except OSError as error:
                message = network_message(error)
                self.db.finish_run(run_id, "failed", message)
                raise ConsoleError(message) from error
            except asyncio.CancelledError:
                self.db.finish_run(run_id, "cancelled")
                raise
            finally:
                await session.close()

    async def snapshot(self) -> bytes:
        """Connect, grab the screen and disconnect."""
        if self.lock.locked():
            raise ConsoleError("Another run is in progress.")
        async with self.lock:
            session = new_session(self.console_ip())
            try:
                await session.open()
                frame = await session.snapshot()
            except OSError as error:
                raise ConsoleError(network_message(error)) from error
            finally:
                await session.close()
        if not frame:
            raise ConsoleError("No video arrived from the console.")
        return frame
