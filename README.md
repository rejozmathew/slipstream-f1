# Slipstream F1

An open-source, self-hosted Formula 1 timing-state service. Historical OpenF1 data can be replayed into one canonical `RaceState`, inspected in the terminal, and served to the local browser pit wall with timing, historical circuit geometry, approximate car positions, weather, track conditions, and circuit-local time.

```powershell
python -m pip install -e ".[dev]"
slipstream fetch 9165 --output recordings/9165.json
# Optional, high-volume public historical X/Y samples for source-positioned car dots.
slipstream fetch 9165 --include-location --output recordings/9165-with-location.json
slipstream fetch-weekend 1219 --output-dir recordings
slipstream fetch-season 2023 --output-dir recordings
slipstream sync-catalog --years 3 --output recordings/catalog.json
slipstream replay recordings/9165.json
# Reconstruct a session instant, or play its original clock at 10x.
slipstream replay recordings/9165.json --at 2023-09-17T13:30:00Z
slipstream replay recordings/9165.json --play --speed 10
python -m pytest
```

To run the replay-backed browser pit wall locally:

```powershell
slipstream serve recordings --catalog-years 3
cd web
npm install
npm run dev
```

Open `http://localhost:3000`. The browser reads the versioned state endpoint at `http://127.0.0.1:8000/api/v1/state` and falls back to representative replay data when the backend is offline.
When the WebSocket endpoint is available, each browser gets an independent replay clock with play/pause, 1×–120× speed, an elapsed-time scrubber, ±30-second jumps, and broadcast-delay presets. A recording directory becomes a browser library grouped by season, race weekend, and session; practice, sprint, qualifying, and race recordings use the same canonical state.

`sync-catalog` is intentionally much lighter than downloading timing recordings. It caches the complete session schedule and linked circuit outlines for the most recent three seasons, so every weekend and date appears immediately and track geometry is ready before a session is selected. The Unraid backend refreshes this cache at startup when it is older than 24 hours. Sessions without a local timing recording remain visible and clearly say `NOT DOWNLOADED`; finished sessions can be downloaded directly from that notice and become replayable without restarting the server. Downloads are serialized so one instance does not fan out concurrent upstream acquisition.

If the cached schedule contains a session active at the current time, it becomes the default selection and is marked `LIVE`. Without a connected live timing adapter, the page says so instead of inventing timing data; the live timeline is capped at the current time and cannot seek into the future.

Phase 3 includes an early public-live recorder. It intentionally writes raw SignalR messages first; live normalization will be based on a capture from an actual session.

```powershell
slipstream live --output recordings/live.jsonl
# For a bounded transport check:
slipstream live --duration 60 --idle-timeout 30
```

The public collector requests timing, driver, session, track-status, race-control, lap-count, and weather streams. Auth-gated GPS, car telemetry, and team radio are not requested. The upstream currently rejects negotiation outside its allowed live window in this development environment, so race-weekend validation remains open.

The default source is free/public historical OpenF1. `fetch` stores provider responses without changing them; `replay` passes them through the OpenF1 adapter into canonical state. Production recordings are local operational data and excluded from Git.

For sessions whose OpenF1 meeting record links circuit information, `fetch` and `sync-catalog` preserve the ordered historical X/Y circuit path. The browser draws the real circuit outline from those coordinates. Circuit coordinates describe the track, not the cars. Normal recordings label car dots as timing-derived; `--include-location` also downloads the much larger public historical per-car X/Y stream and enables source-positioned historical placement. OpenF1 describes these samples as approximate and unsuitable for fine lateral placement. If neither form of car position exists, the map keeps the circuit visible and explains that an enhanced/authenticated position source is not connected. Live X/Y remains a future source capability.

- One upstream connection per instance; downstream clients later consume its canonical state.
- `RaceState` is the normalized boundary between source adapters and all outputs.
- Authenticated sources remain easy to add through adapters, without secrets in Git.
- Do not copy AGPL-licensed f1-dash code; this repository is implemented independently.
- Public API/event compatibility starts at version 1; see [docs/protocol.md](docs/protocol.md).

Replay supports inclusive timestamp seek, single-event stepping in the Python core, pause/resume, and clock speeds of `0.5x`, `1x`, `2x`, and `10x`. `Ctrl+C` pauses terminal playback.

See [ARCHITECTURE.md](ARCHITECTURE.md) and [ROADMAP.md](ROADMAP.md).
Direct reference checks and license boundaries are recorded in [docs/sources.md](docs/sources.md).
Docker publishing and the Unraid Compose stack are documented in [docs/unraid.md](docs/unraid.md).

Slipstream F1 is unofficial and unaffiliated with Formula 1, FIA, or any team. Related marks may be trademarks of their respective owners.
