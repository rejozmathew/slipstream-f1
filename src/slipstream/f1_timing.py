"""Shared normalization for official F1 TimingData provider state."""

from __future__ import annotations

from typing import Any

from .events import NormalizedEvent


def merge_f1_provider_value(current: Any, patch: Any) -> Any:
    """Deep-merge sparse F1 patches without dropping explicit false values."""

    if isinstance(current, dict) and isinstance(patch, dict):
        merged = dict(current)
        for key, value in patch.items():
            merged[str(key)] = merge_f1_provider_value(merged.get(str(key)), value)
        return merged
    if isinstance(current, list) and isinstance(patch, dict):
        merged = list(current)
        for raw_index, value in patch.items():
            if not str(raw_index).isdigit():
                continue
            index = int(raw_index)
            while len(merged) <= index:
                merged.append({})
            merged[index] = merge_f1_provider_value(merged[index], value)
        return merged
    return patch


def normalize_f1_timing(
    merged: dict[str, Any],
    patch: Any,
    occurred_at: str,
    *,
    source: str,
    timing_app_data: dict[str, Any] | None = None,
    qualifying_phase: str = "UNKNOWN",
) -> list[NormalizedEvent]:
    """Normalize merged F1 TimingData while respecting sparse patch intent."""

    lines = merged.get("Lines") if isinstance(merged.get("Lines"), dict) else {}
    patch_lines = (
        patch.get("Lines")
        if isinstance(patch, dict) and isinstance(patch.get("Lines"), dict)
        else {}
    )
    app_lines = (
        timing_app_data.get("Lines", {}) if isinstance(timing_app_data, dict) else {}
    )
    events: list[NormalizedEvent] = []
    selected_lines = (
        lines
        if not patch_lines
        else {key: lines[key] for key in patch_lines if key in lines}
    )
    for raw_number, item in selected_lines.items():
        if not isinstance(item, dict):
            continue
        number = str(item.get("RacingNumber") or raw_number)
        line_patch = (
            patch_lines.get(raw_number)
            if isinstance(patch_lines.get(raw_number), dict)
            else {}
        )
        sectors = _ordered_values(item.get("Sectors"))
        updates: dict[str, Any] = {
            "position": _number(item.get("Position"), integer=True),
            "lap": _number(item.get("NumberOfLaps"), integer=True),
            "gap_to_leader": _value(item.get("GapToLeader")),
            "interval_to_ahead": _value(item.get("IntervalToPositionAhead")),
            "last_lap": _value(item.get("LastLapTime")),
            "best_lap": _value(item.get("BestLapTime")),
            "pit_count": _number(item.get("NumberOfPitStops"), integer=True) or 0,
            "qualifying_eliminated": (
                _truthy(item.get("KnockedOut")) if "KnockedOut" in item else None
            ),
            "sector_1": _number(_value(sectors[0])) if len(sectors) > 0 else None,
            "sector_2": _number(_value(sectors[1])) if len(sectors) > 1 else None,
            "sector_3": _number(_value(sectors[2])) if len(sectors) > 2 else None,
        }
        track_position = _timing_track_position(sectors, line_patch)
        if track_position is not None:
            updates["track_position"] = track_position
        last_lap_value = _value(item.get("LastLapTime"))
        if (
            last_lap_value
            and isinstance(updates.get("lap"), int)
            and ("LastLapTime" in line_patch or (not patch_lines and line_patch == {}))
        ):
            app_line = (
                app_lines.get(raw_number, {}) if isinstance(app_lines, dict) else {}
            )
            stints = (
                _ordered_values(app_line.get("Stints"))
                if isinstance(app_line, dict)
                else []
            )
            stint = stints[-1] if stints and isinstance(stints[-1], dict) else {}
            new_value = stint.get("New")
            updates["lap_observation"] = {
                "lap": int(updates["lap"]),
                "started_at": occurred_at,
                "duration": _duration_seconds(last_lap_value),
                "sector_1": updates.get("sector_1"),
                "sector_2": updates.get("sector_2"),
                "sector_3": updates.get("sector_3"),
                "compound": stint.get("Compound"),
                "stint_number": None,
                "tyre_age": _number(stint.get("TotalLaps"), integer=True),
                "qualifying_phase": qualifying_phase,
                "tyre_usage": (
                    "NEW"
                    if _truthy(new_value)
                    else "USED"
                    if new_value is not None
                    else "UNKNOWN"
                ),
                "lap_validity": "UNKNOWN",
                "quality": "unknown",
                "contamination_reasons": [],
            }

        retired = _truthy(item.get("Retired")) if "Retired" in item else None
        stopped = _truthy(item.get("Stopped")) if "Stopped" in item else None
        in_pit = _truthy(item.get("InPit")) if "InPit" in item else None
        if retired is not None:
            updates["source_retired"] = retired
        if stopped is not None:
            updates["source_stopped"] = stopped
        if retired is True:
            updates.update(source_condition="RETIRED_INDICATED", activity="UNKNOWN")
        elif stopped is True:
            updates.update(source_condition="STOPPED", activity="UNKNOWN")
        elif in_pit is True:
            updates.update(source_condition="IN_PIT", activity="IN_PIT")
        elif (
            _truthy(item.get("PitOut"))
            or in_pit is False
            or "NumberOfLaps" in line_patch
            or retired is False
            or stopped is False
            or (not patch_lines and item.get("NumberOfLaps") is not None)
        ):
            updates.update(source_condition="RUNNING", activity="ON_TRACK")

        updates = {key: value for key, value in updates.items() if value is not None}
        events.append(
            NormalizedEvent(
                "timing",
                occurred_at,
                source,
                {"number": number, **updates},
                received_at=occurred_at,
            )
        )
    return events


def finalize_f1_classifications(
    timing_data: dict[str, Any], occurred_at: str, *, source: str
) -> list[NormalizedEvent]:
    """Project final results only after an authoritative finished cursor.

    Retired/Stopped remain retractable during a session. They are interpreted
    as result evidence only when the caller has observed provider completion;
    explicit result fields always take precedence.
    """

    lines = timing_data.get("Lines")
    if not isinstance(lines, dict):
        return []
    events: list[NormalizedEvent] = []
    for raw_number, line in lines.items():
        if not isinstance(line, dict):
            continue
        raw = str(
            line.get("Classification")
            or line.get("ResultStatus")
            or line.get("Status")
            or ""
        ).upper()
        classification = {"DISQUALIFIED": "DSQ", "OUT": "DNF"}.get(
            raw, raw if raw in {"FINISHED", "DNF", "DNS", "DSQ"} else None
        )
        if classification is None and (
            _truthy(line.get("Retired")) or _truthy(line.get("Stopped"))
        ):
            classification = "DNF"
        if classification is None and line.get("Position") is not None:
            classification = "FINISHED"
        if classification is None:
            continue
        events.append(
            NormalizedEvent(
                "timing",
                occurred_at,
                source,
                {
                    "number": str(line.get("RacingNumber") or raw_number),
                    "classification": classification,
                },
                received_at=occurred_at,
            )
        )
    return events


def _ordered_values(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return []
    return [value[key] for key in sorted(value, key=_sort_key)]


def _value(value: object) -> Any:
    return value.get("Value") if isinstance(value, dict) else value


def _number(value: object, *, integer: bool = False) -> int | float | None:
    value = _value(value)
    if value in {None, ""}:
        return None
    try:
        return int(float(value)) if integer else float(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _duration_seconds(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        minutes, seconds = value.split(":", 1)
        return int(minutes) * 60 + float(seconds)
    except (TypeError, ValueError):
        return None


def _timing_track_position(
    merged_sectors: list[Any], line_patch: dict[str, Any]
) -> float | None:
    """Estimate lap fraction from official TimingData mini-sector progress.

    TimingData marks completed/current mini-sectors in sparse patches. The
    merged sector structure supplies the track-specific mini-sector count,
    while a lap update is the authoritative start/finish-line position.
    Reset-only segment patches carry no new position evidence.
    """

    if "NumberOfLaps" in line_patch:
        return 0.0

    patch_sectors = line_patch.get("Sectors")
    if not isinstance(patch_sectors, (dict, list)):
        return None
    sector_sizes = [
        len(_ordered_values(sector.get("Segments")))
        for sector in merged_sectors
        if isinstance(sector, dict)
    ]
    total_segments = sum(sector_sizes)
    if total_segments <= 0:
        return None

    latest: int | None = None
    for sector_index, sector_patch in _indexed_values(patch_sectors):
        if sector_index >= len(sector_sizes) or not isinstance(sector_patch, dict):
            continue
        sector_size = sector_sizes[sector_index]
        for segment_index, segment in _indexed_values(
            sector_patch.get("Segments")
        ):
            if (
                segment_index < sector_size
                and isinstance(segment, dict)
                and _number(segment.get("Status"), integer=True) not in {None, 0}
            ):
                latest = sum(sector_sizes[:sector_index]) + segment_index + 1
    return latest / total_segments if latest is not None else None


def _indexed_values(value: object) -> list[tuple[int, Any]]:
    if isinstance(value, list):
        return list(enumerate(value))
    if not isinstance(value, dict):
        return []
    return [
        (int(key), item)
        for key, item in value.items()
        if str(key).isdigit()
    ]


def _sort_key(value: object) -> tuple[int, object]:
    text = str(value)
    return (0, int(text)) if text.isdigit() else (1, text)
