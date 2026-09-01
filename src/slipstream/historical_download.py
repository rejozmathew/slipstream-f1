"""Whole-session historical source precedence and provenance."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .adapters.f1_historical import F1HistoricalClient, write_canonical_recording
from .adapters.openf1 import OpenF1Client, write_recording
from .events import NormalizedEvent, parse_timestamp
from .library import SessionDescriptor
from .replay import replay
from .state import RaceState


class HistoricalSessionDownloader:
    """Select exactly one timing source: official F1, then OpenF1 fallback."""

    def __init__(
        self,
        *,
        official: F1HistoricalClient | None = None,
        fallback: OpenF1Client | None = None,
    ) -> None:
        self.official = official or F1HistoricalClient()
        self.fallback = fallback or OpenF1Client()

    def download(self, descriptor: SessionDescriptor, data_root: Path) -> Path:
        key = descriptor.key
        provenance: dict[str, Any] = {
            "session_key": key,
            "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "precedence": ["f1-signalr-public", "f1-static-public", "openf1"],
        }
        try:
            events = self.official.capture_events(
                key,
                year=descriptor.year,
                session_identity={
                    "meeting_name": descriptor.meeting_name,
                    "session_name": descriptor.session_name,
                    "session_type": descriptor.session_type,
                    "session_kind": descriptor.session_kind,
                    "layout_family": descriptor.layout_family,
                    "circuit": descriptor.circuit,
                    "location": descriptor.location,
                    "date_start": descriptor.date_start,
                    "date_end": descriptor.date_end,
                    "gmt_offset": descriptor.gmt_offset,
                },
            )
            state = replay(list(events))
            _validate_official_recording(descriptor, events, state)
            path = data_root / f"f1-static-{key}.json"
            write_canonical_recording(path, events)
            provenance.update(
                source="f1-static-public",
                capabilities={
                    "historical_replay": True,
                    "live_timing": False,
                    "positions": False,
                    "intervals": True,
                    "sector_timing": True,
                    "location_xy": False,
                    "race_control": True,
                    "weather": True,
                    "authenticated": False,
                },
            )
        except Exception as official_error:  # noqa: BLE001 - whole-source fallback
            recording = self.fallback.capture_session(int(key))
            path = data_root / f"openf1-{key}.json"
            write_recording(path, recording)
            provenance.update(
                source="openf1",
                official_unavailable=f"{type(official_error).__name__}: {official_error}",
                capabilities=recording.get("source_capabilities", {}),
            )
        manifest = data_root / ".slipstream" / "sources" / f"{key}.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        temporary = manifest.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(provenance, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        temporary.replace(manifest)
        return path


def _validate_official_recording(
    descriptor: SessionDescriptor,
    events: tuple[NormalizedEvent, ...],
    state: RaceState,
) -> None:
    if not events or str(state.session.key or "") != str(descriptor.key):
        raise ValueError("official F1 source produced no usable canonical session")
    timestamps = [parse_timestamp(event.occurred_at) for event in events]
    if timestamps != sorted(timestamps):
        raise ValueError("official F1 source produced non-chronological events")
    if (
        state.session.session_kind != descriptor.session_kind
        or state.session.layout_family != descriptor.layout_family
        or not state.session.name
        or not state.session.meeting_name
    ):
        raise ValueError("official F1 source did not preserve known session identity")

    timing = [event for event in events if event.kind == "timing"]
    if len(state.drivers) < 10 or not timing:
        raise ValueError("official F1 source produced an implausible timing field")
    if not any(
        event.payload.get("position") is not None
        or event.payload.get("lap") is not None
        or event.payload.get("last_lap") is not None
        for event in timing
    ):
        raise ValueError("official F1 source produced no usable timing stream")

    if descriptor.session_kind != "race":
        return
    lap_values = {
        int(event.payload["lap"])
        for event in events
        if event.kind == "session" and isinstance(event.payload.get("lap"), int)
    }
    if len(lap_values) < 2 or state.session.total_laps is None:
        raise ValueError("official F1 race has no usable lap progression")
    if max(lap_values) < state.session.total_laps:
        raise ValueError("official F1 race does not reach its declared final lap")
    final = [
        driver
        for driver in state.drivers.values()
        if driver.classification in {"FINISHED", "DNF", "DNS", "DSQ"}
    ]
    if state.session.status != "FINISHED" or len(final) != len(state.drivers):
        raise ValueError("official F1 race has no coherent final classification boundary")
