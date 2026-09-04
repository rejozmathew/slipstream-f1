# Docker deployment

Slipstream is distributed as one Linux container. The image uses Node only to compile the React application; the runtime contains one Python process serving the browser, REST API, and WebSocket on internal port `3444`.

It runs under Docker Desktop on Windows and macOS, Docker Engine on Linux, and compatible container platforms.

## Run the published image

```sh
docker run -d \
  --name slipstream-f1 \
  --restart unless-stopped \
  -p 3444:3444 \
  -v slipstream-recordings:/data \
  ghcr.io/rejozmathew/slipstream-f1:latest
```

Open `http://localhost:3444`.

The named volume stores `catalog.json` and downloaded session recordings. Deleting and recreating the container does not delete the volume.

## Build from a checkout

The repository Compose file builds a local image and uses a named volume:

```sh
docker compose up -d --build
```

Use this path for development or when you want to build an unmerged checkout. No host Python or Node installation is needed.

## Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| Container port | `3444` | Internal HTTP and WebSocket port; do not change it in normal deployments |
| `SLIPSTREAM_PORT` | `3444` | Host-side port used by the repository Compose file |
| `SLIPSTREAM_RECORDINGS_DIR` | Docker volume | Optional host directory mounted at `/data` by Compose |
| `SLIPSTREAM_MODE` | `full` | `full` serves browser and API; `api-only` omits browser routes |
| `SLIPSTREAM_CATALOG_YEARS` | `3` | Replay-catalog seasons; an explicit `serve --catalog-years` value overrides it |
| `SLIPSTREAM_PIRELLI_SEED` | `1` | Validate and idempotently import the bundled normalized Pirelli seed on writable startup |
| `SLIPSTREAM_PIRELLI_SEED_PATH` | bundled artifact | Optional replacement normalized seed path |
| `SLIPSTREAM_PIRELLI_BACKFILL` | `1` | Quietly attempt one missing historical Pirelli meeting at a time |
| `SLIPSTREAM_PIRELLI_REFRESH` | `1` | Keep the sparse current-weekend Pirelli acquisition path enabled |

The Pirelli historical horizon is a fixed ten-season product policy, not an end-user setting. The seed is application distribution data copied with the Python package, not a runtime recording. Import and historical catch-up write only to the mounted `/data` volume. A seed validation/import or catch-up failure is logged but does not block application startup, the API, live timing, or replay. Historical discovery uses a private lightweight metadata cache and does not expand the browser's three-season catalog. No `.env` file is required for either supplied Compose file.

Choose another host port by changing only the published side:

```sh
docker run -d --name slipstream-f1 -p 7444:3444 -v slipstream-recordings:/data ghcr.io/rejozmathew/slipstream-f1:latest
```

With Compose on Linux or macOS:

```sh
SLIPSTREAM_PORT=7444 docker compose up -d --build
```

With PowerShell:

```powershell
$env:SLIPSTREAM_PORT = "7444"
docker compose up -d --build
```

## Storage and permissions

The image runs as a non-root user. A fresh named volume inherits writable ownership from the image. For a bind mount, make sure the chosen host directory is writable by the container user or explicitly run the container with a UID/GID appropriate for that host.

Recordings can be large, especially when `--include-location` is enabled. The catalog is small and does not contain timing data.

Do not store credentials or authenticated captures under a repository checkout. `/data` is operational storage and should be backed up according to the host’s normal container-volume practice.

## Download sessions

The browser can download any finished session listed by the catalog. CLI acquisition is also available inside the running container:

```sh
docker exec slipstream-f1 python -m slipstream fetch 9165 --output /data/session-9165.json
docker exec slipstream-f1 python -m slipstream fetch-weekend 1219 --output-dir /data
docker exec slipstream-f1 python -m slipstream fetch-season 2023 --output-dir /data
```

For the repository Compose service:

```sh
docker compose run --rm slipstream fetch 9165 --output /data/session-9165.json
```

Add `--include-location` only when source X/Y history is worth the additional download and storage.

## API-only mode

API-only mode keeps REST and WebSocket routes while returning no browser application:

```sh
docker run -d \
  --name slipstream-f1 \
  -e SLIPSTREAM_MODE=api-only \
  -p 3444:3444 \
  -v slipstream-recordings:/data \
  ghcr.io/rejozmathew/slipstream-f1:latest
```

## Updates and rollback

For a published-image deployment:

1. pull the desired tag;
2. stop and remove the existing container;
3. recreate it with the same port, environment, and `/data` volume.

The volume survives container replacement. `latest` follows the newest successful `main` build. Release workflows also publish immutable `run-N` and `sha-COMMIT` tags; use one of those when controlled rollback matters.

For a source-build deployment:

```sh
git pull --ff-only
docker compose up -d --build
```

## Reverse proxy

A reverse proxy is optional. Route one hostname to container port `3444` and enable WebSocket forwarding. The website, `/api/v1/*`, and `/api/v1/stream` must remain on the same upstream origin.

Slipstream does not bundle Nginx, open multiple application ports, join a particular Docker network, or configure TLS. Those remain host-level decisions.

## Health check

The supplied Compose files check `GET /api/v1/catalog`. A healthy response proves the process is accepting requests and its replay library initialized. It does not prove that a live upstream source is connected.
