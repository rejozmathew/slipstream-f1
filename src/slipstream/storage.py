"""Narrow replay artifact deletion with durable-context preservation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .library import _read_descriptor


@dataclass(frozen=True)
class ReplayDeletion:
    session_key: str
    removed: tuple[str, ...]


def delete_replay_artifacts(data_root: Path, session_key: str) -> ReplayDeletion:
    """Delete only rebuildable timing/session evidence for one exact session."""

    key = str(session_key)
    removed: list[str] = []
    for path in sorted(data_root.rglob("*.json")):
        if ".slipstream" in path.parts:
            continue
        descriptor = _read_descriptor(path)
        if descriptor is None or descriptor.key != key or descriptor.path is None:
            continue
        path.unlink(missing_ok=True)
        removed.append(str(path.relative_to(data_root)))
    for path in (data_root / f"live-{key}.in-progress.jsonl",):
        if path.is_file():
            path.unlink()
            removed.append(str(path.relative_to(data_root)))
    raw_root = data_root / ".slipstream" / "raw-timing" / key
    if raw_root.is_dir():
        for path in sorted(raw_root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        raw_root.rmdir()
        removed.append(str(raw_root.relative_to(data_root)))
    return ReplayDeletion(key, tuple(removed))
