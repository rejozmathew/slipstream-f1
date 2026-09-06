"""Atomic canonical recording for a public live session."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .events import NormalizedEvent, parse_timestamp

IN_PROGRESS_SUFFIX = ".in-progress.jsonl"


class NormalizedLiveRecorder:
    """Append canonical events without exposing a partial replay artifact."""

    def __init__(self, directory: Path, session_key: str) -> None:
        self.directory = directory
        self.session_key = str(session_key)
        self.temporary_path = directory / f"live-{self.session_key}{IN_PROGRESS_SUFFIX}"
        self.final_path = directory / f"live-{self.session_key}.json"
        self._events: list[NormalizedEvent] = []
        self._event_keys: set[str] = set()
        self._finalized = False
        self._recover()

    @property
    def events(self) -> tuple[NormalizedEvent, ...]:
        return tuple(self._events)

    def append(
        self, events: tuple[NormalizedEvent, ...]
    ) -> tuple[NormalizedEvent, ...]:
        if not events:
            return ()
        if self._finalized:
            raise RuntimeError("normalized live recording is already finalized")
        seen = set()
        accepted = []
        for event in events:
            key = self._event_key(event)
            if key not in self._event_keys and key not in seen:
                accepted.append(event)
                seen.add(key)
        fresh = tuple(accepted)
        if not fresh:
            return ()
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.temporary_path.open("a", encoding="utf-8", newline="\n") as output:
            for event in fresh:
                self._events.append(event)
                self._event_keys.add(self._event_key(event))
                output.write(json.dumps(asdict(event), separators=(",", ":")) + "\n")
            output.flush()
        return fresh

    def _recover(self) -> None:
        if self.final_path.exists():
            from .replay import load_events
            from .session import classify_session
            from .session_completion import session_completion

            saved = load_events(self.final_path)
            identity = {}
            for event in saved:
                self._validate_recovered_event(event)
                if event.kind == "session":
                    identity.update(event.payload)
            kind = classify_session(
                identity.get("session_type"), identity.get("name")
            ).kind.value
            if not session_completion(saved, session_kind=kind).complete:
                # Recover legacy prematurely-published files without changing
                # the original until genuine completion publishes atomically.
                self._events.extend(saved)
                self._event_keys.update(self._event_key(event) for event in saved)
        if not self.temporary_path.exists():
            return
        try:
            lines = self.temporary_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as error:
            raise RuntimeError(
                f"cannot recover normalized live recording {self.temporary_path}: {error}"
            ) from error
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                raw: Any = json.loads(line)
                if not isinstance(raw, dict):
                    raise TypeError("event must be a JSON object")
                event = NormalizedEvent.from_mapping(raw)
                self._validate_recovered_event(event)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                raise RuntimeError(
                    "cannot recover normalized live recording "
                    f"{self.temporary_path} at line {line_number}: {error}"
                ) from error
            key = self._event_key(event)
            if key in self._event_keys:
                continue
            self._events.append(event)
            self._event_keys.add(key)

    def _validate_recovered_event(self, event: NormalizedEvent) -> None:
        if not isinstance(event.occurred_at, str) or not isinstance(event.source, str):
            raise TypeError("event timestamps and source must be strings")
        if not isinstance(event.payload, dict):
            raise TypeError("event payload must be an object")
        if event.kind == "session":
            recorded_key = event.payload.get("key")
            if recorded_key is not None and str(recorded_key) != self.session_key:
                raise ValueError(
                    f"session event belongs to {recorded_key}, expected {self.session_key}"
                )

    @staticmethod
    def _event_key(event: NormalizedEvent) -> str:
        # Receipt time is transport provenance, not canonical event identity.
        # A reconnect may redeliver the same source fact at a later receipt time.
        return json.dumps(
            {
                "kind": event.kind,
                "occurred_at": parse_timestamp(event.occurred_at).isoformat(),
                "source": event.source,
                "payload": event.payload,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def finalize(self) -> Path:
        """Atomically publish the existing normalized-list replay format."""
        if self._finalized:
            return self.final_path
        ordered = sorted(
            enumerate(self._events),
            key=lambda item: (parse_timestamp(item[1].occurred_at), item[0]),
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
