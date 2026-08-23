# Slipstream F1

Slipstream F1 is an open-source, self-hosted Formula 1 timing, live-viewing, and replay application. It turns source data into one canonical `RaceState` and presents that state through a browser pit wall, a versioned REST/WebSocket API, and a terminal renderer.

The product supports historical replay and a conservative public live-timing slice. One server-owned public SignalR connection normalizes proven timing, session, track-status, race-control, and weather topics through the same `NormalizedEvent` → `RaceState` path used by replay. Each viewer may apply an independent display delay while factual state and analytics remain on the same delayed cursor.

## What works today

| Capability | Current status |
| --- | --- |
| Recent-season session catalog | Loads the current season and two preceding seasons by default |
| Historical session download | Finished practice, qualifying, sprint, and race sessions can be downloaded from the browser or CLI |
| Public live timing | Explicit pre-event, connecting, live, stale/reconnecting, finalizing, complete, and replay-ready lifecycle |
| Live recording | Normalized live events are finalized atomically and become an immediately selectable replay |
| Viewer delay | Independent 0/5/10/15/30-second live delay with one-click return to LIVE; no live seek/pause/speed controls |
| Replay timing | Race, Qualifying, and Practice layouts driven by canonical timing, lap, tyre, stint, sector, pit, and race-control facts |
| Qualifying intelligence | Server-authored phase/clock, scoped benchmark, verified elimination zone, final Q1/Q2/Q3 facts, teammate comparison, lap history, and session-aware Driver Focus |
| Focused views | Contextual Driver Focus with on-demand normalized lap evidence, plus factual any-two-driver Battle |
| Race intelligence | As-of-time Strategy, clean-lap pace/degradation, pit history, Driver context, and stabilized Recommended Battle with explicit provenance |
| Weekend context | Compact prior-session evidence prepares asynchronously and never blocks replay startup |
| Published strategy | Official Pirelli pre-race options plus deterministic cursor-safe Race Now/driver comparison |
| Display modes | Responsive portrait/landscape session layouts and an authored browser TV Mode |
| Presentation settings | Device-local dark background, accent, Race split, Timing Tower mode, module layout, and TV rotation preferences |
| Track display | Preloaded historical circuit outline, independent of timing downloads |
| Car placement | Timing-derived estimate by default; optional historical source X/Y when downloaded |
| Conditions | Weather observations, rain sensor state, whole-track status, and circuit-local time |
| Playback | Per-browser play, pause, speed, timeline seek, and relative seek |
| Outputs | Browser, API v1, WebSocket snapshots, and terminal output |
| Deployment | One container, one process, and one internal port |

Not yet implemented: deterministic archived-session backtesting, general historical pre-race context, Net Pit Loss, authentication/SQLite, Sync Groups and device pairing, expanded/authenticated live-source coverage, complete remaining-tyre inventory, live per-car X/Y, external strategy-intelligence providers, or hardware clients. Schedule status, transport status, sporting status, and marshal state remain separate; driver inactivity is not treated as factual retirement.

## Run it with Docker

The published image works with Docker Desktop on Windows or macOS, Docker Engine on Linux, and container platforms such as Unraid.

```sh
docker run -d \
  --name slipstream-f1 \
  --restart unless-stopped \
  -p 3444:3444 \
  -v slipstream-recordings:/data \
  ghcr.io/OWNER/slipstream-f1:latest
```

Replace `OWNER` with the GitHub account or organization publishing the image, then open `http://localhost:3444`.

To build the current checkout instead:

```sh
docker compose up -d --build
```

Port `3444` is only the friendly default. Map any unused host port to container port `3444`. The default Docker volume keeps the catalog and downloaded recordings across upgrades.

The container serves one origin:

```text
/                 browser pit wall
/api/v1/*         versioned REST API
/api/v1/stream    WebSocket replay stream
```

Set `SLIPSTREAM_MODE=api-only` to disable browser routes. Slipstream does not bundle Nginx or configure a reverse proxy.

See [Docker deployment](docs/docker.md) and [Unraid deployment](docs/unraid.md) for storage, updates, ports, and reverse-proxy notes.

## Getting historical sessions

At startup the container refreshes a lightweight catalog for the latest three seasons. The catalog includes weekend/session dates and circuit geometry; it does not contain timing data.

Select a finished session in the browser and choose **Download replay**, or use the CLI:

```sh
slipstream fetch 9165 --output recordings/9165.json
slipstream fetch-weekend 1219 --output-dir recordings
slipstream fetch-season 2023 --output-dir recordings
```

Add `--include-location` to `fetch`, `fetch-weekend`, or `fetch-season` when you want the much larger historical per-car X/Y dataset. Without it, Slipstream estimates lap progress from timing and maps that estimate onto the exact circuit outline.

Recordings are operational data. They are excluded from Git and are not baked into the image.

## Local development

Python 3.11+ and Node 22+ are required outside Docker.

```powershell
python -m pip install -e ".[dev]"
slipstream sync-catalog --years 3 --output recordings/catalog.json
slipstream serve recordings --catalog-years 3 --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd web
npm install
npm run dev
```

Pirelli newsroom strategy evidence refreshes server-side and is stored under the operational data root. Set `SLIPSTREAM_PIRELLI_REFRESH=0` to disable acquisition. Native machine-readable PDF tyre-bank rows are optional; install `.[pirelli-pdf]` for that capability. Missing tyre-bank data never blocks Strategy.

Open `http://localhost:3344`. The Vite development server is fixed to port
`3344` and proxies API and WebSocket requests to the Slipstream backend at
`http://127.0.0.1:8000`. Keep both terminals running. Do not run
`slipstream serve` on port `3344`; that port belongs to the Vite UI during
local development.

Run the checks with:

```powershell
python -m ruff check src tests
python -m pytest
cd web
npm run typecheck
npm run lint
npm test
```

## Design commitments

- `RaceState` is the normalized boundary used by every presentation and transport.
- Analytics is a separate versioned, replay-synchronized sidecar; it never becomes a second factual dashboard model.
- Playback assets are session-scoped while compact analytics context is strictly limited to earlier sessions in the same `meeting_key` and is cutoff-safe; prior weekends and prior circuit editions are not direct V1 inputs.
- Source-specific fields stay inside adapters; upstream payloads do not leak into the public API.
- One application instance owns at most one upstream live connection.
- Persistent sporting/control latches are source-capability dependent: public Live may use explicit suspension/restart semantics, while historical OpenF1 does not invent a restart endpoint it cannot observe.
- Explicit terminal driver states remain terminal; `STOPPED` remains resumable and M3.5 does not derive `NO_RECENT_PROGRESS`.
- Stable source/session capability controls whole-column presence; row-level missing values use `—` rather than shifting the layout or exposing raw capability enums.

The formulas, evidence thresholds, confidence rules, UNKNOWN behavior, Battle Score, and current limitations are documented in [docs/analytics.md](docs/analytics.md).
- Capabilities are explicit, especially where public and authenticated sources differ.
- Public API routes and event envelopes are versioned from the beginning.
- Secrets, cookies, environment files, authenticated captures, and recordings never belong in Git.
- AGPL code, including f1-dash source, must not be copied into this MIT-licensed implementation.

## Documentation

- [Architecture](ARCHITECTURE.md) — current data flows, module boundaries, and invariants
- [Protocol](docs/protocol.md) — RaceState, API v1, WebSocket commands, and file formats
- [Session experience](docs/session-experience.md) — live lifecycle, viewer delay, replay finalization, Qualifying, and availability semantics
- [Published Pirelli strategy](docs/pirelli-strategy.md) — evidence admission, derivation, missing-data semantics, and corpus metrics
- [Roadmap](ROADMAP.md) — shipped baseline and the next milestones
- [Source notes](docs/sources.md) — reference and license boundaries
- [Working agreement](AGENTS.md) — contributor rules

Slipstream F1 is unofficial and unaffiliated with Formula 1, FIA, or any team. Related marks may be trademarks of their respective owners.
