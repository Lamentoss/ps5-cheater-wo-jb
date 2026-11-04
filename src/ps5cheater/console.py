"""PS5 discovery, pairing and the Remote Play session."""
from __future__ import annotations

import asyncio
import errno
import io
import ipaddress
import logging
import os
import select
import socket
import time

SETTLE_SECONDS = 3.0
HEARTBEAT_SECONDS = 0.1
READY_TIMEOUT = 15
CONNECT_TIMEOUT = 40
FRAME_TIMEOUT = 8

_LOG = logging.getLogger(__name__)


class ConsoleError(Exception):
    """A console problem with a message that is safe to show to the user."""


NETWORK_BLOCKED = (
    "This computer cannot reach the console. On macOS, click Allow when asked about the local "
    "network, or turn on PS5 Cheater in System Settings, Privacy & Security, Local Network, "
    "then reopen the app. Also check that both devices share a network and that no VPN blocks it."
)


def network_message(error: OSError) -> str:
    blocked = (errno.EHOSTUNREACH, errno.ENETUNREACH, errno.EPERM, errno.EACCES)
    return NETWORK_BLOCKED if error.errno in blocked else str(error)


def mock_enabled() -> bool:
    return os.environ.get("PS5CHEATER_MOCK") == "1"


def _quiet_library() -> None:
    # Audio resampler errors are irrelevant: audio is never played.
    logging.getLogger("pyremoteplay.receiver").setLevel(logging.CRITICAL)


def scan(timeout: float = 3.0) -> list[dict]:
    """Find consoles by sending a discovery message on every local broadcast network.

    The library's global broadcast fails when a VPN owns the default route.
    """
    if mock_enabled():
        return [{"ip": "192.0.2.50", "name": "PS5-MOCK", "type": "PS5", "status": "Ok",
                 "system_version": "00000000"}]
    import netifaces
    from pyremoteplay.const import DDP_PORTS, TYPE_PS5
    from pyremoteplay.ddp import get_ddp_search_message, parse_ddp_response

    message = get_ddp_search_message().encode()
    sockets = []
    for interface in netifaces.interfaces():
        for address in netifaces.ifaddresses(interface).get(netifaces.AF_INET, []):
            broadcast = address.get("broadcast")
            if not broadcast or not ipaddress.ip_address(address["addr"]).is_private:
                continue
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                sock.bind((address["addr"], 0))
                sock.sendto(message, (broadcast, DDP_PORTS[TYPE_PS5]))
            except OSError:
                sock.close()
                continue
            sockets.append(sock)

    found: dict[str, dict] = {}
    deadline = time.monotonic() + timeout
    while sockets and time.monotonic() < deadline:
        ready, _, _ = select.select(sockets, [], [], 0.2)
        for sock in ready:
            data, sender = sock.recvfrom(2048)
            reply = parse_ddp_response(data, sender[0])
            if reply:
                found[sender[0]] = {
                    "ip": sender[0],
                    "name": reply.get("host-name"),
                    "type": reply.get("host-type"),
                    "status": reply.get("status"),
                    "system_version": reply.get("system-version"),
                }
    for sock in sockets:
        sock.close()
    return list(found.values())


def _device(ip: str):
    from pyremoteplay import RPDevice

    return RPDevice(ip)


def probe(ip: str) -> dict | None:
    """Return the reachable state of one console, or None."""
    if mock_enabled():
        return scan()[0]
    device = _device(ip)
    try:
        status = device.get_status()
    except OSError as error:
        raise ConsoleError(network_message(error)) from error
    if not status:
        return None
    return {
        "ip": ip,
        "name": status.get("host-name"),
        "type": status.get("host-type"),
        "status": status.get("status"),
        "system_version": status.get("system-version"),
        "running_app": status.get("running-app-name"),
        "users": device.get_users(),
    }


def login_url() -> str:
    from pyremoteplay.oauth import get_login_url

    return get_login_url()


def add_account(redirect_url: str) -> str:
    """Store the PSN account from a redirect URL and return its online ID."""
    if mock_enabled():
        return "mock-user"
    from pyremoteplay import RPDevice
    from pyremoteplay.oauth import get_user_account
    from pyremoteplay.profile import format_user_account

    data = get_user_account(redirect_url.strip())
    profile = format_user_account(data) if data else None
    if profile is None:
        raise ConsoleError(
            "Sony did not accept that address. Sign in again and copy the full address "
            "of the page that opens after login."
        )
    profiles = RPDevice.get_profiles()
    profiles.update_user(profile)
    profiles.save()
    return profile.name


def accounts() -> list[str]:
    if mock_enabled():
        return ["mock-user"]
    from pyremoteplay import RPDevice

    return list(RPDevice.get_profiles().usernames)


def link(ip: str, user: str, pin: str) -> None:
    """Pair a stored account with a console using the code it displays."""
    pin = pin.replace(" ", "")
    if not (pin.isdigit() and len(pin) == 8):
        raise ConsoleError("The pairing code must be exactly 8 digits.")
    if mock_enabled():
        return
    from pyremoteplay import RPDevice

    device = _device(ip)
    if not probe(ip):
        raise ConsoleError(f"The console at {ip} is not reachable.")
    device.get_status()
    if not device.register(user, pin, profiles=RPDevice.get_profiles()):
        raise ConsoleError(
            "The console rejected the pairing. Codes expire quickly: request a new one and retry."
        )


async def _heartbeat(device) -> None:
    """Send controller state continuously.

    The console treats a silent controller as idle, and the library only sends
    state when a stick moves. Reference clients send at least every 200 ms.
    """
    from pyremoteplay.stream_packets import FeedbackHeader

    controller, session = device.controller, device.session
    while not session.is_stopped:
        stream = session.stream
        if stream and session.is_ready:
            stream.send_feedback(
                FeedbackHeader.Type.STATE, controller._sequence_state,
                state=controller.stick_state,
            )
            controller._sequence_state += 1
        await asyncio.sleep(HEARTBEAT_SECONDS)


class ConsoleSession:
    """One Remote Play connection; every button of a run goes through it."""

    def __init__(self, ip: str):
        self.ip = ip
        self.device = None
        self.receiver = None
        self._task = None

    async def open(self) -> None:
        from pyremoteplay.receiver import QueueReceiver

        _quiet_library()
        deadline = time.monotonic() + CONNECT_TIMEOUT
        while True:
            self.receiver = QueueReceiver(max_video_frames=2, max_audio_frames=1)
            device = _device(self.ip)
            if not await device.async_get_status():
                raise ConsoleError(f"The console at {self.ip} is not reachable.")
            users = device.get_users()
            if not users:
                raise ConsoleError("This console is not paired yet. Finish the Connect steps.")
            if not device.create_session(users[0], receiver=self.receiver):
                raise ConsoleError("Could not create a Remote Play session.")
            # autostart would open a throwaway network test stream first, which
            # the console rejects; it shows up as a connect/disconnect blip.
            if await device.session.start(autostart=False):
                device.session._start_stream(test=False)
                if await device.async_wait_for_session(READY_TIMEOUT):
                    break
                device.disconnect()
                if time.monotonic() >= deadline:
                    raise ConsoleError("The Remote Play session did not become ready.")
                continue
            error = device.session.error or "Could not connect."
            device.session.stop()
            if "Standby" in error:
                raise ConsoleError("The console was in rest mode. It is waking up: try again shortly.")
            if "Another Remote Play session" not in error:
                raise ConsoleError(error)
            if time.monotonic() >= deadline:
                raise ConsoleError(
                    "Another Remote Play session is active. Close it and try again."
                )
            await asyncio.sleep(2)
        self.device = device
        device.controller.start()
        self._task = asyncio.create_task(_heartbeat(device))
        # Buttons pressed before the console registers the controller are lost.
        await asyncio.sleep(SETTLE_SECONDS)

    async def press(self, button: str, hold: float) -> None:
        session = self.device.session if self.device else None
        if session is None or session.is_stopped or not session.is_ready:
            raise ConsoleError("The Remote Play connection dropped.")
        await self.device.controller.async_button(button, "tap", hold)

    async def snapshot(self) -> bytes | None:
        """Return the latest frame as PNG bytes, or None if no video arrived."""
        deadline = time.monotonic() + FRAME_TIMEOUT
        while time.monotonic() < deadline:
            frame = self.receiver.get_latest_video_frame()
            if frame is not None:
                image = await asyncio.to_thread(frame.to_image)
                buffer = io.BytesIO()
                await asyncio.to_thread(image.save, buffer, "PNG")
                return buffer.getvalue()
            await asyncio.sleep(0.1)
        return None

    async def close(self) -> None:
        if self.device:
            self.device.disconnect()
            self.device = None
        if self._task:
            self._task.cancel()
            self._task = None


class MockSession:
    """Stands in for a console in development and tests."""

    def __init__(self, ip: str):
        self.ip = ip
        self.pressed: list[str] = []

    async def open(self) -> None:
        await asyncio.sleep(0.3)

    async def press(self, button: str, hold: float) -> None:
        self.pressed.append(button)
        await asyncio.sleep(hold)

    async def snapshot(self) -> bytes:
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (640, 360), (24, 28, 38))
        ImageDraw.Draw(image).text((20, 20), "Mock console frame", fill=(226, 232, 240))
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        return buffer.getvalue()

    async def close(self) -> None:
        pass


def new_session(ip: str):
    return MockSession(ip) if mock_enabled() else ConsoleSession(ip)
