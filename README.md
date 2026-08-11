# Slipstream F1

Slipstream F1 is an open-source, self-hosted Formula 1 timing and replay application. It normalizes historical OpenF1 data into one canonical `RaceState` used by the terminal, versioned API, WebSocket stream, and browser pit wall.

## Run with Docker

Docker is the primary deployment path. The same single image runs on Windows Docker Desktop, macOS, Linux, Unraid, and other container platforms.

```sh
docker compose up -d --build
```

Open `http://localhost:3444`. The default port is a small nod to car 3 and car 44; change only the host side if it is occupied, for example `SLIPSTREAM_PORT=7444 docker compose up -d --build`.

The one container serves:

```text
/                 browser pit wall
/api/v1/*         versioned REST API
/api/v1/stream    WebSocket replay stream
```

Recordings persist in a Docker named volume by default. Set `SLIPSTREAM_RECORDINGS_DIR` to use a host folder, or `SLIPSTREAM_MODE=api-only` to disable browser routes. There is no bundled reverse proxy or Nginx service.

See [docs/docker.md](docs/docker.md) for Windows, macOS, and Linux deployment, and [docs/unraid.md](docs/unraid.md) for Unraid.

## Develop locally

```powershell
python -m pip install -e ".[dev]"
slipstream fetch 9165 --output recordings/9165.json
slipstream replay recordings/9165.json
python -m pytest
```

To run the API and Vite development server separately:

```powershell
slipstream serve recordings --catalog-years 3
cd web
npm install
npm run dev
```

Open the Vite address shown in the terminal. Its development proxy connects `/api/v1/*` and the WebSocket to the local service on port 8000.

Useful acquisition commands:

```powershell
slipstream fetch 9165 --include-location --output recordings/9165-with-location.json
slipstream fetch-weekend 1219 --output-dir recordings
slipstream fetch-season 2023 --output-dir recordings
slipstream sync-catalog --years 3 --output recordings/catalog.json
slipstream live --output recordings/live.jsonl
```

The lightweight catalog caches recent session dates and exact historical circuit outlines without downloading timing data. Finished sessions can then be downloaded from the browser. Standard recordings estimate car progress from timing; `--include-location` adds the larger public historical X/Y dataset when available.

The default source is free/public. Authenticated sources can be added later through adapters, and capability flags keep consumers independent of provider names. One instance owns one upstream connection. Recordings, environment files, tokens, cookies, and authenticated captures stay out of Git.

`RaceState` is the normalized boundary between sources and every output. API and event compatibility begins at version 1; see [docs/protocol.md](docs/protocol.md). Do not copy AGPL-licensed f1-dash code; this implementation is independent.

See [ARCHITECTURE.md](ARCHITECTURE.md), [ROADMAP.md](ROADMAP.md), and [docs/sources.md](docs/sources.md).

Slipstream F1 is unofficial and unaffiliated with Formula 1, FIA, or any team. Related marks may be trademarks of their respective owners.
