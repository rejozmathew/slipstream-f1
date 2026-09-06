"""Serve a fresh download/open regression using an external saved recording.

The actual download job, publication, replay and browser contracts run locally.
Only acquisition is substituted with the supplied recording; no upstream fetch.
The data directory must not already exist. Never point it at application data.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import uvicorn


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--recording", type=Path, required=True)
    parser.add_argument("--web", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18350)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    recording = json.loads(args.recording.read_text(encoding="utf-8"))
    args.data.mkdir(parents=True, exist_ok=False)
    (args.data / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    for feature in ("REFRESH", "SEED", "BACKFILL"):
        os.environ[f"SLIPSTREAM_PIRELLI_{feature}"] = "0"

    from slipstream.api import create_app

    def capture(key):
        if int(recording["session_key"]) != key:
            raise ValueError("Only the supplied regression session can be downloaded")
        time.sleep(0.3)
        return recording

    def no_context(*_args, **_kwargs):
        raise OSError("Optional acquisition disabled for download/open regression")

    app = create_app(
        args.data,
        capture_session=capture,
        public_live=False,
        prepare_weekend_context=no_context,
        now=lambda: datetime(2026, 9, 6, tzinfo=UTC),
        web_dir=args.web,
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
