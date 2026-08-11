"""Command-line entry point."""

import argparse
import asyncio
import re
import sys
from datetime import UTC, timedelta
from pathlib import Path

from .adapters.openf1 import OpenF1Client, OpenF1Error, write_recording
from .catalog import recent_seasons, sync_catalog
from .playback import ReplayController
from .replay import load_events, replay
from .terminal import render


def main() -> None:
    parser = argparse.ArgumentParser(prog="slipstream")
    commands = parser.add_subparsers(dest="command", required=True)
    replay_command = commands.add_parser(
        "replay", help="Render a replay or source recording"
    )
    replay_command.add_argument("path", type=Path)
    replay_limit = replay_command.add_mutually_exclusive_group()
    replay_limit.add_argument(
        "--at", help="Render state at an ISO 8601 session timestamp"
    )
    replay_limit.add_argument(
        "--events", type=int, help="Render state after the first N events"
    )
    replay_command.add_argument(
        "--play", action="store_true", help="Play events using session time"
    )
    replay_command.add_argument(
        "--speed", type=float, choices=(0.5, 1.0, 2.0, 10.0), default=1.0
    )
    fetch_command = commands.add_parser(
        "fetch", help="Download a historical OpenF1 session"
    )
    fetch_command.add_argument("session_key", type=int)
    fetch_command.add_argument("--output", type=Path)
    fetch_command.add_argument(
        "--include-location",
        action="store_true",
        help="Include high-volume public historical per-car X/Y samples",
    )
    weekend_command = commands.add_parser(
        "fetch-weekend", help="Download every session in a Grand Prix weekend"
    )
    weekend_command.add_argument("meeting_key", type=int)
    weekend_command.add_argument("--output-dir", type=Path, default=Path("recordings"))
    weekend_command.add_argument("--force", action="store_true")
    weekend_command.add_argument("--include-location", action="store_true")
    season_command = commands.add_parser(
        "fetch-season", help="Download every available session in a season"
    )
    season_command.add_argument("year", type=int)
    season_command.add_argument("--output-dir", type=Path, default=Path("recordings"))
    season_command.add_argument("--force", action="store_true")
    season_command.add_argument("--include-location", action="store_true")
    catalog_command = commands.add_parser(
        "sync-catalog",
        help="Cache recent session dates and circuit outlines without timing data",
    )
    catalog_command.add_argument(
        "--years", type=int, default=3, help="Number of recent seasons to cache"
    )
    catalog_command.add_argument(
        "--output", type=Path, default=Path("recordings/catalog.json")
    )
    catalog_command.add_argument("--max-age-hours", type=float, default=24.0)
    serve_command = commands.add_parser(
        "serve", help="Serve one replay or a recording directory over API v1"
    )
    serve_command.add_argument("path", type=Path)
    serve_command.add_argument("--host", default="127.0.0.1")
    serve_command.add_argument("--port", type=int, default=8000)
    serve_command.add_argument(
        "--catalog-years",
        type=int,
        default=0,
        help="Refresh this many recent seasons before serving a directory",
    )
    serve_command.add_argument("--catalog-max-age-hours", type=float, default=24.0)
    live_command = commands.add_parser(
        "live", help="Record the unauthenticated public F1 live stream"
    )
    live_command.add_argument("--output", type=Path)
    live_command.add_argument("--duration", type=float)
    live_command.add_argument("--idle-timeout", type=float, default=90.0)
    args = parser.parse_args()
    if args.command == "fetch":
        output = args.output or Path("recordings") / f"openf1-{args.session_key}.json"
        recording = OpenF1Client().capture_session(
            args.session_key, include_location=args.include_location
        )
        write_recording(output, recording)
        print(f"Saved OpenF1 session {args.session_key} to {output}")
        return
    if args.command in {"fetch-weekend", "fetch-season"}:
        client = OpenF1Client()
        sessions = client.get(
            "sessions",
            **(
                {"meeting_key": args.meeting_key}
                if args.command == "fetch-weekend"
                else {"year": args.year}
            ),
        )
        _fetch_session_library(
            client,
            sessions,
            output_dir=args.output_dir,
            force=args.force,
            include_location=args.include_location,
        )
        return
    if args.command == "sync-catalog":
        years = recent_seasons(args.years)
        catalog = sync_catalog(
            args.output,
            years,
            max_age=timedelta(hours=args.max_age_hours),
        )
        print(
            f"Cached {len(catalog['sessions'])} sessions across "
            f"{len(catalog['meetings'])} weekends in {args.output}"
        )
        return
    if args.command == "serve":
        import uvicorn

        from .api import create_app

        if args.catalog_years and args.path.is_dir():
            try:
                sync_catalog(
                    args.path / "catalog.json",
                    recent_seasons(args.catalog_years),
                    max_age=timedelta(hours=args.catalog_max_age_hours),
                )
            except OpenF1Error as error:
                print(
                    f"Catalog refresh unavailable; serving the existing local library: {error}",
                    file=sys.stderr,
                )

        uvicorn.run(create_app(args.path), host=args.host, port=args.port)
        return
    if args.command == "live":
        from datetime import datetime

        from .live import LiveSourceError, PublicLiveRecorder

        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output = args.output or Path("recordings") / f"f1-live-{timestamp}.jsonl"
        try:
            count = asyncio.run(
                PublicLiveRecorder().record(
                    output, idle_timeout=args.idle_timeout, duration=args.duration
                )
            )
        except LiveSourceError as error:
            parser.exit(1, f"Live source unavailable: {error}\n")
        print(f"Saved {count} public live messages to {output}")
        return
    events = load_events(args.path)
    if args.play:
        if args.events is not None:
            parser.error("--play cannot be combined with --events")
        controller = ReplayController(events)
        if args.at is not None:
            controller.seek(args.at)

        def display(state: object) -> None:
            print("\x1b[2J\x1b[H", end="")
            print(render(state), end="", flush=True)  # type: ignore[arg-type]

        try:
            controller.play(speed=args.speed, on_state=display)
        except KeyboardInterrupt:
            controller.pause()
        return
    print(render(replay(events, at=args.at, event_limit=args.events)), end="")


def _fetch_session_library(
    client: OpenF1Client,
    sessions: list[dict[str, object]],
    *,
    output_dir: Path,
    force: bool,
    include_location: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(sessions, key=lambda item: str(item.get("date_start") or ""))
    for index, session in enumerate(ordered, start=1):
        session_key = int(session["session_key"])
        year = int(session.get("year") or str(session.get("date_start"))[:4])
        meeting_key = int(session.get("meeting_key") or 0)
        session_name = str(session.get("session_name") or "session")
        slug = re.sub(r"[^a-z0-9]+", "-", session_name.lower()).strip("-")
        output = output_dir / f"{year}-{meeting_key}-{session_key}-{slug}.json"
        if output.exists() and not force:
            print(f"[{index}/{len(ordered)}] Already downloaded: {output.name}")
            continue
        print(f"[{index}/{len(ordered)}] Downloading {session_name} ({session_key})")
        write_recording(
            output,
            client.capture_session(session_key, include_location=include_location),
        )
