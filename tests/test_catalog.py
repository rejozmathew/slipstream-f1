import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from slipstream.api import create_app
from slipstream.catalog import CATALOG_FORMAT, recent_seasons, sync_catalog
from slipstream.library import ReplayLibrary


class FakeOpenF1Client:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def get(
        self, endpoint: str, *, allow_not_found: bool = False, **params: object
    ) -> list[dict[str, object]]:
        del allow_not_found
        year = int(params["year"])
        self.calls.append((endpoint, year))
        if endpoint == "meetings":
            return [
                {
                    "meeting_key": year * 10,
                    "meeting_name": f"Example Grand Prix {year}",
                    "location": "Example City",
                    "circuit_key": 42,
                    "circuit_short_name": "Example Ring",
                    "date_start": f"{year}-06-01T00:00:00Z",
                    "date_end": f"{year}-06-03T23:59:59Z",
                    "year": year,
                    "circuit_info_url": f"https://circuits.test/42/{year}",
                }
            ]
        return [
            {
                "session_key": year * 100,
                "meeting_key": year * 10,
                "session_name": "Race",
                "session_type": "Race",
                "circuit_short_name": "Example Ring",
                "location": "Example City",
                "date_start": f"{year}-06-03T12:00:00Z",
                "date_end": f"{year}-06-03T14:00:00Z",
                "gmt_offset": "02:00:00",
                "year": year,
            }
        ]

    def get_object_url(
        self, url: str, *, allow_not_found: bool = False
    ) -> dict[str, object]:
        del allow_not_found
        year = int(url.rsplit("/", 1)[-1])
        return {
            "circuitKey": 42,
            "circuitName": "Example Ring",
            "year": year,
            "rotation": 12,
            "x": [0, 10, 5, 0],
            "y": [0, 0, 10, 0],
        }


def test_recent_seasons_and_catalog_cache_preload_shapes(tmp_path: Path) -> None:
    now = datetime(2026, 8, 11, tzinfo=UTC)
    years = recent_seasons(3, now=now)
    client = FakeOpenF1Client()
    path = tmp_path / "catalog.json"

    catalog = sync_catalog(path, years, client=client, now=now)
    cached = sync_catalog(
        path,
        years,
        client=client,
        now=now + timedelta(hours=1),
    )

    assert years == [2024, 2025, 2026]
    assert len(catalog["sessions"]) == 3
    assert len(catalog["meetings"]) == 3
    assert catalog["meetings"]["20260"]["circuit"]["path"] == [
        [0.0, 0.0],
        [10.0, 0.0],
        [5.0, 10.0],
        [0.0, 0.0],
    ]
    assert cached == catalog
    assert len(client.calls) == 6


def test_catalog_only_live_session_is_default_and_cannot_seek_to_future(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 11, 12, 30, tzinfo=UTC)
    payload = {
        "format": CATALOG_FORMAT,
        "schema_version": 1,
        "source": "openf1",
        "updated_at": "2026-08-11T12:00:00Z",
        "years": [2026],
        "meetings": {
            "1": {
                "meeting_key": 1,
                "meeting_name": "Live Grand Prix",
                "location": "Live City",
                "circuit_short_name": "Live Ring",
                "circuit": {
                    "key": "42",
                    "name": "Live Ring",
                    "year": 2026,
                    "rotation": 0,
                    "path": [[0, 0], [10, 0], [5, 10]],
                    "source": "https://circuits.test/42/2026",
                    "availability": {"path": "available"},
                },
            }
        },
        "sessions": [
            {
                "session_key": 100,
                "meeting_key": 1,
                "session_name": "Race",
                "session_type": "Race",
                "circuit_short_name": "Live Ring",
                "location": "Live City",
                "date_start": "2026-08-11T12:00:00Z",
                "date_end": "2026-08-11T14:00:00Z",
                "gmt_offset": "02:00:00",
                "year": 2026,
            }
        ],
    }
    (tmp_path / "catalog.json").write_text(json.dumps(payload), encoding="utf-8")

    with TestClient(create_app(tmp_path, now=lambda: now, public_live=False)) as client:
        catalog = client.get("/api/v1/catalog").json()
        state = client.get("/api/v1/state").json()
        replay = client.get("/api/v1/replay").json()
        capabilities = client.get("/api/v1/capabilities").json()

    assert catalog["defaultSessionKey"] == "100"
    assert catalog["sessions"][0]["isLive"] is True
    assert catalog["sessions"][0]["available"] is False
    assert catalog["sessions"][0]["circuitShapeAvailable"] is True
    assert state["data"]["session"]["status"] == "UNKNOWN"
    assert state["data"]["session"]["local_time"] == "2026-08-11T14:30:00+02:00"
    assert state["data"]["circuit"]["path"] == [[0.0, 0.0], [10.0, 0.0], [5.0, 10.0]]
    assert replay["endTime"] == "2026-08-11T12:30:00Z"
    assert replay["durationSeconds"] == 1800
    assert replay["available"] is False
    assert replay["positionMode"] == "unavailable"
    assert capabilities["capabilities"]["live_timing"] is False


def test_preloaded_circuit_enriches_an_older_local_recording(tmp_path: Path) -> None:
    catalog = {
        "format": CATALOG_FORMAT,
        "schema_version": 1,
        "source": "openf1",
        "updated_at": "2026-08-11T12:00:00Z",
        "years": [2025],
        "meetings": {
            "20": {
                "meeting_key": 20,
                "meeting_name": "Cached Grand Prix",
                "circuit_short_name": "Cached Ring",
                "circuit": {
                    "key": "7",
                    "name": "Cached Ring",
                    "year": 2025,
                    "rotation": 0,
                    "path": [[0, 0], [20, 0], [10, 20]],
                    "source": "https://circuits.test/7/2025",
                    "availability": {"path": "available"},
                },
            }
        },
        "sessions": [
            {
                "session_key": 200,
                "meeting_key": 20,
                "session_name": "Race",
                "session_type": "Race",
                "circuit_short_name": "Cached Ring",
                "location": "Cached City",
                "date_start": "2025-06-01T12:00:00Z",
                "date_end": "2025-06-01T14:00:00Z",
                "year": 2025,
            }
        ],
    }
    recording = [
        {
            "kind": "session",
            "occurred_at": "2025-06-01T12:00:00Z",
            "source": "test",
            "payload": {
                "key": "200",
                "name": "Race",
                "meeting_name": "Cached Grand Prix",
                "session_type": "Race",
                "circuit": "Cached Ring",
                "location": "Cached City",
                "started_at": "2025-06-01T12:00:00Z",
                "ended_at": "2025-06-01T14:00:00Z",
                "status": "STARTED",
            },
        },
        {
            "kind": "circuit",
            "occurred_at": "2025-06-01T12:00:00Z",
            "source": "test",
            "payload": {"availability": {"path": "unavailable"}},
        },
    ]
    (tmp_path / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    (tmp_path / "recording.json").write_text(
        json.dumps(recording), encoding="utf-8"
    )

    library = ReplayLibrary(tmp_path)
    resource = library.get("200")

    assert resource.replay_available is True
    assert resource.final_state.circuit.name == "Cached Ring"
    assert resource.final_state.circuit.path == (
        (0.0, 0.0),
        (20.0, 0.0),
        (10.0, 20.0),
    )
    assert resource.descriptor.capabilities["circuit_shape"] is True
