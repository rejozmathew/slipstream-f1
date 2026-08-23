"""Atomic canonical recording for a public live session."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .events import NormalizedEvent

IN_PROGRESS_SUFFIX = ".in-progress.jsonl"


class NormalizedLiveRecorder:
    """Append canonical events without exposing a partial replay artifact."""

    def __init__(self, directory: Path, session_key: str) -> None:
        self.directory = directory
        self.session_key = str(session_key)
        self.temporary_path = directory / f"live-{self.session_key}{IN_PROGRESS_SUFFIX}"
        self.final_path = directory / f"live-{self.session_key}.json"
        self._events: list[NormalizedEvent] = []
        self._finalized = False

    def append(self, events: tuple[NormalizedEvent, ...]) -> None:
        if self._finalized:
            raise RuntimeError("normalized live recording is already finalized")
        if not events:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.temporary_path.open("a", encoding="utf-8", newline="\n") as output:
            for event in events:
                self._events.append(event)
                output.write(json.dumps(asdict(event), separators=(",", ":")) + "\n")
            output.flush()

    def finalize(self) -> Path:
        """Atomically publish the existing normalized-list replay format."""
        if self._finalized:
            return self.final_path
        ordered = sorted(
            enumerate(self._events), key=lambda item: (item[1].occurred_at, item[0])
        )
        staging = self.final_path.with_suffix(".json.tmp")
        staging.write_text(
            json.dumps([asdict(event) for _, event in ordered], separators=(",", ":")),
            encoding="utf-8",
        )
        staging.replace(self.final_path)
        self.temporary_path.unlink(missing_ok=True)
        self._finalized = True
        return self.final_path
