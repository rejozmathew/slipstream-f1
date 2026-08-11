"""Unauthenticated Formula 1 SignalR Core recording.

This module deliberately records provider messages without normalizing them.
The live normalizer will be built from recordings captured during an actual
race weekend, rather than guessed from third-party examples.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import aiohttp

RECORD_SEPARATOR = "\x1e"
RECORDING_FORMAT = "slipstream.f1-signalr-recording.v1"
NEGOTIATE_URL = "https://livetiming.formula1.com/signalrcore/negotiate"
CONNECT_URL = "wss://livetiming.formula1.com/signalrcore"

# Streams observed to remain public in 2026. CarData.z, Position.z, team
# radio, and other enhanced feeds are intentionally absent because they now
# require authentication.
PUBLIC_TOPICS = (
    "DriverList",
    "ExtrapolatedClock",
    "Heartbeat",
    "LapCount",
    "RaceControlMessages",
    "SessionData",
    "SessionInfo",
    "SessionStatus",
    "TimingAppData",
    "TimingData",
    "TopThree",
    "TrackStatus",
    "WeatherData",
)

CAPABILITIES = {
    "historical_replay": False,
    "live_timing": True,
    "positions": True,
    "intervals": True,
    "location_xy": False,
    "circuit_shape": False,
    "race_control": True,
    "weather": True,
    "local_time": True,
    "authenticated": False,
}


class LiveSourceError(RuntimeError):
    """Raised when the public live transport cannot produce a recording."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def recording_header(*, captured_at: str | None = None) -> dict[str, Any]:
    """Return the first JSONL record for a public live capture."""
    return {
        "format": RECORDING_FORMAT,
        "schema_version": 1,
        "source": "f1-signalr-public",
        "captured_at": captured_at or utc_now(),
        "source_capabilities": CAPABILITIES,
        "topics": list(PUBLIC_TOPICS),
    }


def decode_signalr_text(
    text: str, *, received_at: str
) -> tuple[list[dict[str, Any]], bool]:
    """Decode SignalR Core JSON records into stable raw recording rows.

    Returns ``(rows, ping_received)``. Invocation results are initial
    snapshots; ``feed`` invocations are incremental provider messages.
    """
    rows: list[dict[str, Any]] = []
    ping_received = False
    for segment in text.split(RECORD_SEPARATOR):
        if not segment.strip():
            continue
        try:
            message = json.loads(segment)
        except json.JSONDecodeError as error:
            raise LiveSourceError("SignalR returned invalid JSON") from error
        if not isinstance(message, dict):
            continue
        message_type = message.get("type")
        if message_type == 1 and str(message.get("target", "")).lower() == "feed":
            arguments = message.get("arguments")
            if not isinstance(arguments, list) or len(arguments) < 2:
                continue
            stream = arguments[0]
            if not isinstance(stream, str):
                continue
            rows.append(
                {
                    "received_at": received_at,
                    "stream": stream,
                    "source_timestamp": (
                        arguments[2]
                        if len(arguments) > 2 and isinstance(arguments[2], str)
                        else None
                    ),
                    "payload": arguments[1],
                    "initial": False,
                }
            )
        elif message_type == 3:
            result = message.get("result")
            if isinstance(result, dict):
                rows.extend(
                    {
                        "received_at": received_at,
                        "stream": stream,
                        "source_timestamp": None,
                        "payload": payload,
                        "initial": True,
                    }
                    for stream, payload in result.items()
                )
        elif message_type == 6:
            ping_received = True
        elif message_type == 7:
            detail = message.get("error") or "no reason supplied"
            raise LiveSourceError(f"SignalR closed the connection: {detail}")
    return rows, ping_received


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    """Write a complete live recording. Primarily useful for test fixtures."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as output:
        for row in rows:
            output.write(json.dumps(row, separators=(",", ":")) + "\n")


class PublicLiveRecorder:
    """Record the public F1 live feed through one upstream connection."""

    def __init__(
        self,
        *,
        negotiate_url: str = NEGOTIATE_URL,
        connect_url: str = CONNECT_URL,
        topics: tuple[str, ...] = PUBLIC_TOPICS,
    ) -> None:
        self.negotiate_url = negotiate_url
        self.connect_url = connect_url
        self.topics = topics
        self._running = False

    async def record(
        self,
        path: Path,
        *,
        idle_timeout: float = 90.0,
        duration: float | None = None,
    ) -> int:
        """Connect, write a versioned JSONL recording, and return row count."""
        if self._running:
            raise LiveSourceError("This recorder already owns an upstream connection")
        if idle_timeout <= 0:
            raise ValueError("idle_timeout must be greater than zero")
        if duration is not None and duration <= 0:
            raise ValueError("duration must be greater than zero")

        self._running = True
        websocket: aiohttp.ClientWebSocketResponse | None = None
        session: aiohttp.ClientSession | None = None
        count = 0
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": "slipstream-f1/0.1"},
            )
            token = await self._negotiate(session)
            connect_query = urlencode({"id": token})
            websocket = await session.ws_connect(
                f"{self.connect_url}?{connect_query}", heartbeat=20
            )
            await websocket.send_str(
                json.dumps({"protocol": "json", "version": 1}) + RECORD_SEPARATOR
            )
            handshake = await asyncio.wait_for(websocket.receive(), idle_timeout)
            self._validate_handshake(handshake)
            await websocket.send_str(
                json.dumps(
                    {
                        "type": 1,
                        "target": "Subscribe",
                        "arguments": [list(self.topics)],
                        "invocationId": "0",
                    }
                )
                + RECORD_SEPARATOR
            )
            started = asyncio.get_running_loop().time()

            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8", newline="\n") as output:
                output.write(
                    json.dumps(recording_header(), separators=(",", ":")) + "\n"
                )
                output.flush()
                while (
                    duration is None
                    or asyncio.get_running_loop().time() - started < duration
                ):
                    remaining = idle_timeout
                    if duration is not None:
                        remaining = min(
                            remaining,
                            max(
                                0.01,
                                duration
                                - (asyncio.get_running_loop().time() - started),
                            ),
                        )
                    try:
                        message = await asyncio.wait_for(websocket.receive(), remaining)
                    except TimeoutError as error:
                        if (
                            duration is not None
                            and asyncio.get_running_loop().time() - started >= duration
                        ):
                            break
                        raise LiveSourceError(
                            f"No live data received for {idle_timeout:g} seconds"
                        ) from error
                    if message.type == aiohttp.WSMsgType.TEXT:
                        rows, ping = decode_signalr_text(
                            message.data, received_at=utc_now()
                        )
                        if ping:
                            await websocket.send_str(
                                json.dumps({"type": 6}) + RECORD_SEPARATOR
                            )
                        for row in rows:
                            output.write(json.dumps(row, separators=(",", ":")) + "\n")
                            count += 1
                        if rows:
                            output.flush()
                    elif message.type in {
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    }:
                        raise LiveSourceError("The live connection closed unexpectedly")
            return count
        finally:
            if websocket is not None:
                await websocket.close()
            if session is not None:
                await session.close()
            self._running = False

    async def _negotiate(self, session: aiohttp.ClientSession) -> str:
        params = {"negotiateVersion": "1"}
        async with session.options(self.negotiate_url, params=params) as response:
            if response.status >= 400:
                raise LiveSourceError(
                    f"Live negotiation preflight failed with HTTP {response.status}"
                )
        async with session.post(self.negotiate_url, params=params) as response:
            if response.status >= 400:
                raise LiveSourceError(
                    f"Live negotiation failed with HTTP {response.status}"
                )
            payload = await response.json()
        token = payload.get("connectionToken") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise LiveSourceError("Live negotiation returned no connection token")
        return token

    @staticmethod
    def _validate_handshake(message: aiohttp.WSMessage) -> None:
        if message.type != aiohttp.WSMsgType.TEXT:
            raise LiveSourceError("SignalR closed before completing its handshake")
        for segment in message.data.split(RECORD_SEPARATOR):
            if not segment.strip():
                continue
            try:
                payload = json.loads(segment)
            except json.JSONDecodeError as error:
                raise LiveSourceError(
                    "SignalR returned an invalid handshake"
                ) from error
            if isinstance(payload, dict) and payload.get("error"):
                raise LiveSourceError(f"SignalR handshake failed: {payload['error']}")
