# Slipstream F1

Slipstream F1 is an open-source, self-hosted Formula 1 historical timing and replay application. It turns source data into one canonical `RaceState` and presents that state through a browser pit wall, a versioned REST/WebSocket API, and a terminal renderer.

The usable product today is historical replay. A public live-feed recorder also exists, but live messages are not yet normalized into `RaceState` or shown as live timing in the application.

## What works today

| Capability | Current status |
| --- | --- |
| Recent-season session catalog | Loads the current season and two preceding seasons by default |
| Historical session download | Finished practice, qualifying, sprint, and race sessions can be downloaded from the browser or CLI |
| Replay timing | Race, Qualifying, and Practice layouts driven by canonical timing, lap, tyre, stint, sector, pit, and race-control facts |
| Focused views | Contextual Driver Focus with on-demand normalized lap evidence, plus factual any-two-driver Battle |
| Race intelligence | As-of-time Strategy, clean-lap pace/degradation, pit history, Driver context, and stabilized Recommended Battle with explicit provenance |
| Weekend context | Compact prior-session evidence prepares asynchronously and never blocks replay startup |
| Display modes | Responsive portrait/landscape session layouts and an authored browser TV Mode |
| Presentation settings | Device-local dark background, accent, Race split, Timing Tower mode, module layout, and TV rotation preferences |
| Track display | Preloaded historical circuit outline, independent of timing downloads |
| Car placement | Timing-derived estimate by default; optional historical source X/Y when downloaded |
| Conditions | Weather observations, rain sensor state, whole-track status, and circuit-local time |
| Playback | Per-browser play, pause, speed, timeline seek, and relative seek |
| Outputs | Browser, API v1, WebSocket snapshots, and terminal output |
| Deployment | One container, one process, and one internal port |

Not yet implemented: authentication/SQLite, Sync Groups and device pairing, normalized live timing in the browser/API, authenticated live sources, complete remaining-tyre inventory, live per-car X/Y, external strategy-intelligence providers, or hardware clients. A schedule entry may be labelled `LIVE` because its official time window is active; that does not mean a live timing source is connected.

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

The formulas, evidence thresholds, confidence rules, UNKNOWN behavior, Battle Score, and current limitations are documented in [docs/analytics.md](docs/analytics.md).
- Capabilities are explicit, especially where public and authenticated sources differ.
- Public API routes and event envelopes are versioned from the beginning.
- Secrets, cookies, environment files, authenticated captures, and recordings never belong in Git.
- AGPL code, including f1-dash source, must not be copied into this MIT-licensed implementation.

## Documentation

- [Architecture](ARCHITECTURE.md) — current data flows, module boundaries, and invariants
- [Protocol](docs/protocol.md) — RaceState, API v1, WebSocket commands, and file formats
- [Roadmap](ROADMAP.md) — shipped baseline and the next milestones
- [Source notes](docs/sources.md) — reference and license boundaries
- [Working agreement](AGENTS.md) — contributor rules

Slipstream F1 is unofficial and unaffiliated with Formula 1, FIA, or any team. Related marks may be trademarks of their respective owners.
