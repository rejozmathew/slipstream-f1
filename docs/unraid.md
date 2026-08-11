# Unraid deployment

Slipstream publishes separate backend and browser images to GitHub Container Registry. The default `gateway` profile adds a small Nginx container so the UI, API, and WebSocket work at one address without requiring an existing reverse proxy. Historical recordings remain in Unraid appdata and are not built into any image.

## First deployment

1. Create `/mnt/user/appdata/slipstream-f1`, copy `deploy/unraid/compose.yaml`, `nginx.conf`, and `.env.example` into it, then rename `.env.example` to `.env`. Set `SLIPSTREAM_IMAGE_OWNER` to the GitHub account or organization that publishes the images. Keep this machine-specific `.env` private and never commit it.
2. Create `/mnt/user/appdata/slipstream-f1/recordings`.
   On first backend startup, Slipstream creates `/data/catalog.json` with session dates and circuit outlines for the latest three seasons. It refreshes that small cache after 24 hours; this does not download timing recordings.
   The supplied Compose file runs the backend as Unraid's standard `nobody:users` identity (`99:100`) so the page can save requested replays into this directory. Change `SLIPSTREAM_PUID` and `SLIPSTREAM_PGID` only if your share uses different ownership.
3. From the stack directory, download a session, complete weekend, or season into the persistent volume:

   ```sh
   docker compose run --rm --user 0 backend fetch 9165 --output /data/session.json
   docker compose run --rm --user 0 backend fetch-weekend 1219 --output-dir /data
   docker compose run --rm --user 0 backend fetch-season 2023 --output-dir /data
   ```

   A full season can take time and storage because every practice, sprint, qualifying, and race session is captured. Existing files are skipped unless `--force` is supplied.

   You can refresh only the lightweight schedule/track cache without downloading timing data:

   ```sh
   docker compose run --rm --user 0 backend sync-catalog --years 3 --output /data/catalog.json
   ```

4. Start or restart the stack after adding recordings:

   ```sh
   docker compose up -d --wait
   ```

5. Open `http://UNRAID-IP:3000`. Change `SLIPSTREAM_PORT` in the private `.env` if that port is already in use.

If the GHCR packages are private, sign in once on Unraid with a GitHub personal access token that has `read:packages`. Public packages need no registry credentials.

## Refresh after a release

Every push to `main` runs tests and publishes `latest`, `run-N`, and immutable `sha-...` tags. To update Unraid manually:

```sh
cd /mnt/user/appdata/slipstream-f1
docker compose pull backend web
docker compose up -d --remove-orphans
```

For automatic refresh, copy `refresh.sh` into the stack directory and schedule `sh /mnt/user/appdata/slipstream-f1/refresh.sh` with the Unraid User Scripts plugin. A five- or ten-minute schedule is sufficient; the script only recreates services when the pulled image changes.

For controlled releases, set `SLIPSTREAM_TAG` to a tested `run-N` or `sha-...` tag instead of `latest`, then run the same refresh script. Rollback is the same operation with the prior immutable tag.

## Existing reverse proxy

The bundled gateway is optional. On a server that already has Nginx Proxy Manager or another capable reverse proxy, clear the profile in the private `.env`:

```dotenv
COMPOSE_PROFILES=
```

When creating the two containers in Unraid, place `slipstream-f1-web` and `slipstream-f1-backend` on the Docker network used by that proxy. This network is a deployment choice and is intentionally not named in the public configuration.

Route the proxy host's default `/` location to `slipstream-f1-web:3000` and add a custom `/api/` location pointing to `slipstream-f1-backend:8000`. Enable WebSocket support because `/api/v1/stream` is a WebSocket endpoint. The proxy should terminate TLS; only it should be internet-facing.
