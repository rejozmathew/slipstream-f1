"""Plain terminal rendering for the first executable milestone."""

from .state import RaceState


def render(state: RaceState) -> str:
    session = state.session
    title = (
        " - ".join(x for x in (session.meeting_name, session.name) if x)
        or "Unknown session"
    )
    show_best_lap = session.session_type in {
        "Practice",
        "Qualifying",
        "Sprint Qualifying",
    }
    lap_heading = "BEST LAP" if show_best_lap else "LAST LAP"
    session_lap = (
        f"{session.lap if session.lap is not None else '-'}/{session.total_laps or '-'}"
    )
    lines = [
        f"Slipstream | {title}",
        f"Status: {session.status} | Lap: {session_lap} | Track: {session.track_status or '-'} | Updated: {state.updated_at or 'never'}",
    ]
    conditions = _render_conditions(state)
    if conditions:
        lines.append(conditions)
    lines.extend(
        [
            "",
            f"{'POS':<4} {'DRV':<4} {'DRIVER':<18} {'LAP':>3} {'GAP':>10} {'INT':>10} {'TYRE':<12} {'AGE':>3} {'STINT':>5} {'PIT':>3} {'TRACK':>5} {lap_heading:>10} STATUS",
            "-" * 122,
        ]
    )
    drivers = sorted(
        state.drivers.values(),
        key=lambda d: (d.position is None, d.position or 999, d.number),
    )
    for d in drivers:
        displayed_lap = d.best_lap or d.last_lap if show_best_lap else d.last_lap
        displayed_gap = "LEADER" if d.position == 1 else d.gap_to_leader or "-"
        displayed_interval = "-" if d.position == 1 else d.interval_to_ahead or "-"
        displayed_track = (
            f"{d.track_position:.3f}" if d.track_position is not None else "-"
        )
        lines.append(
            f"{d.position or '-'!s:<4} {d.code or d.number:<4} {(d.name or d.number):<18} "
            f"{d.lap if d.lap is not None else '-'!s:>3} {displayed_gap:>10} "
            f"{displayed_interval:>10} {(d.compound or '-'):<12} "
            f"{d.tyre_age if d.tyre_age is not None else '-'!s:>3} "
            f"{d.stint_laps if d.stint_laps is not None else '-'!s:>5} {d.pit_count:>3} "
            f"{displayed_track:>5} {(displayed_lap or '-'):>10} {d.status}"
        )
    if state.race_control:
        lines.extend(["", "Race control:"])
        lines.extend(
            f"- {x.occurred_at} {x.category}: {x.message}"
            for x in state.race_control[-3:]
        )
    return "\n".join(lines) + "\n"


def _render_conditions(state: RaceState) -> str | None:
    weather = state.weather
    available = any(value == "available" for value in weather.availability.values())
    if not state.session.local_time and not available:
        return None

    parts = [f"Local: {state.session.local_time or '-'}"]
    if weather.air_temperature is not None:
        parts.append(f"Air: {weather.air_temperature:.1f}°C")
    if weather.track_temperature is not None:
        parts.append(f"Track temp: {weather.track_temperature:.1f}°C")
    if weather.rainfall is not None:
        parts.append("Rain: YES" if weather.rainfall else "Rain: NO")
    if weather.humidity is not None:
        parts.append(f"Humidity: {weather.humidity:.0f}%")
    if weather.wind_speed is not None:
        direction = (
            f" @ {weather.wind_direction}°"
            if weather.wind_direction is not None
            else ""
        )
        parts.append(f"Wind: {weather.wind_speed:.1f} m/s{direction}")
    return " | ".join(parts)
