"""Whole-session historical source precedence and provenance."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .adapters.f1_historical import F1HistoricalClient, write_canonical_recording
from .adapters.openf1 import OpenF1Client, write_recording
from .library import SessionDescriptor
from .replay import replay


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
            events = self.official.capture_events(key, year=descriptor.year)
            state = replay(list(events))
            if (
                not events
                or str(state.session.key or "") != str(key)
                or not any(event.kind == "timing" for event in events)
            ):
                raise ValueError("official F1 source produced an unusable session recording")
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
