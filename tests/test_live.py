import asyncio
import json

import pytest
from aiohttp import web

from slipstream.live import (
    CAPABILITIES,
    PUBLIC_TOPICS,
    RECORD_SEPARATOR,
    LiveSourceError,
    PublicLiveRecorder,
    decode_signalr_text,
    recording_header,
)


def test_public_capabilities_exclude_authenticated_feeds() -> None:
    assert CAPABILITIES["live_timing"] is True
    assert CAPABILITIES["authenticated"] is False
    assert CAPABILITIES["location_xy"] is False
    assert CAPABILITIES["circuit_shape"] is False
    assert CAPABILITIES["weather"] is True
    assert CAPABILITIES["local_time"] is True
    assert "TimingData" in PUBLIC_TOPICS
    assert "RaceControlMessages" in PUBLIC_TOPICS
    assert "CarData.z" not in PUBLIC_TOPICS
    assert "Position.z" not in PUBLIC_TOPICS
    assert "TeamRadio" not in PUBLIC_TOPICS


def test_decodes_initial_and_incremental_signalr_rows() -> None:
    text = RECORD_SEPARATOR.join(
        (
            json.dumps(
                {
                    "type": 3,
                    "invocationId": "0",
                    "result": {"SessionStatus": {"Status": "Started"}},
                }
            ),
            json.dumps(
                {
                    "type": 1,
                    "target": "feed",
                    "arguments": [
                        "TimingData",
                        {"Lines": {"4": {"Position": "1"}}},
                        "00:01:02.345",
                    ],
                }
            ),
            json.dumps({"type": 6}),
            "",
        )
    )

    rows, ping = decode_signalr_text(text, received_at="2026-08-11T04:00:00Z")

    assert ping is True
    assert rows == [
        {
            "received_at": "2026-08-11T04:00:00Z",
            "stream": "SessionStatus",
            "source_timestamp": None,
            "payload": {"Status": "Started"},
            "initial": True,
        },
        {
            "received_at": "2026-08-11T04:00:00Z",
            "stream": "TimingData",
            "source_timestamp": "00:01:02.345",
            "payload": {"Lines": {"4": {"Position": "1"}}},
            "initial": False,
        },
    ]


def test_close_frame_is_an_error() -> None:
    with pytest.raises(LiveSourceError, match="maintenance"):
        decode_signalr_text(
            json.dumps({"type": 7, "error": "maintenance"}) + RECORD_SEPARATOR,
            received_at="2026-08-11T04:00:00Z",
        )


def test_recording_header_is_versioned_and_source_specific() -> None:
    header = recording_header(captured_at="2026-08-11T04:00:00Z")
    assert header["format"] == "slipstream.f1-signalr-recording.v1"
    assert header["source"] == "f1-signalr-public"
    assert header["topics"] == list(PUBLIC_TOPICS)


def test_one_upstream_connection_per_recorder() -> None:
    recorder = PublicLiveRecorder()
    recorder._running = True
    with pytest.raises(LiveSourceError, match="already owns"):
        asyncio.run(recorder.record(None))  # type: ignore[arg-type]


def test_recorder_negotiates_subscribes_and_writes_jsonl(tmp_path) -> None:
    async def scenario() -> None:
        upstream_connections = 0
        subscription: dict[str, object] = {}

        async def options_handler(request: web.Request) -> web.Response:
            assert request.query["negotiateVersion"] == "1"
            return web.Response(
                headers={"Set-Cookie": "AWSALBCORS=test-cookie; Path=/"}
            )

        async def negotiate_handler(request: web.Request) -> web.Response:
            assert request.query["negotiateVersion"] == "1"
            return web.json_response({"connectionToken": "local-token"})

        async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
            nonlocal upstream_connections, subscription
            upstream_connections += 1
            assert request.query["id"] == "local-token"
            socket = web.WebSocketResponse()
            await socket.prepare(request)

            handshake = await socket.receive_str()
            assert json.loads(handshake.rstrip(RECORD_SEPARATOR)) == {
                "protocol": "json",
                "version": 1,
            }
            await socket.send_str("{}" + RECORD_SEPARATOR)
            subscription = json.loads(
                (await socket.receive_str()).rstrip(RECORD_SEPARATOR)
            )
            await socket.send_str(
                json.dumps(
                    {
                        "type": 3,
                        "invocationId": "0",
                        "result": {"SessionStatus": {"Status": "Started"}},
                    }
                )
                + RECORD_SEPARATOR
                + json.dumps(
                    {
                        "type": 1,
                        "target": "feed",
                        "arguments": [
                            "TrackStatus",
                            {"Status": "1", "Message": "AllClear"},
                            "00:00:05.000",
                        ],
                    }
                )
                + RECORD_SEPARATOR
            )
            await asyncio.sleep(0.2)
            return socket

        app = web.Application()
        app.router.add_route("OPTIONS", "/signalrcore/negotiate", options_handler)
        app.router.add_post("/signalrcore/negotiate", negotiate_handler)
        app.router.add_get("/signalrcore", websocket_handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        output = tmp_path / "live.jsonl"
        try:
            count = await PublicLiveRecorder(
                negotiate_url=f"http://127.0.0.1:{port}/signalrcore/negotiate",
                connect_url=f"http://127.0.0.1:{port}/signalrcore",
            ).record(output, idle_timeout=1, duration=0.1)
        finally:
            await runner.cleanup()

        assert count == 2
        assert upstream_connections == 1
        assert subscription["target"] == "Subscribe"
        assert subscription["arguments"] == [list(PUBLIC_TOPICS)]
        lines = [json.loads(line) for line in output.read_text().splitlines()]
        assert lines[0]["format"] == "slipstream.f1-signalr-recording.v1"
        assert [line["stream"] for line in lines[1:]] == [
            "SessionStatus",
            "TrackStatus",
        ]

    asyncio.run(scenario())
