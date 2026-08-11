# Unraid deployment

The current Slipstream deployment is one image, one container, and one internal TCP port. Older instructions that used separate backend, web, and Nginx gateway containers are obsolete.

## Recommended Docker template

Create one Unraid container with:

| Template field | Value |
| --- | --- |
| Name | `slipstream-f1` |
| Repository | `ghcr.io/OWNER/slipstream-f1:latest` |
| Container port | `3444` TCP |
| Host port | Any free port; `3444` is the default suggestion |
| Container path | `/data` |
| Host path | An appdata directory chosen for Slipstream recordings |
| Variable | `SLIPSTREAM_MODE=full` (optional; this is the default) |
| Network | Choose the network appropriate for your server/template |

Replace `OWNER` with the GitHub account or organization publishing the package.

The image runs as a non-root user. Ensure the selected appdata directory is writable. If the share uses Unraid’s standard `nobody:users` ownership, configure the container as UID/GID `99:100`; otherwise use the ownership appropriate for that share.

Start the container and open:

```text
http://UNRAID-IP:HOST-PORT
```

On first startup Slipstream refreshes a lightweight catalog for the current and two preceding seasons. That catalog supplies dates and track shapes but does not automatically download timing for every session.

## Historical recordings

Downloaded sessions remain under the mapped `/data` directory across image updates. Use the browser’s **Download replay** action for finished sessions, or run:

```sh
docker exec slipstream-f1 python -m slipstream fetch 9165 --output /data/session-9165.json
docker exec slipstream-f1 python -m slipstream fetch-weekend 1219 --output-dir /data
docker exec slipstream-f1 python -m slipstream fetch-season 2023 --output-dir /data
```

Add `--include-location` only when you want the much larger historical source X/Y data.

## Nginx Proxy Manager or another proxy

Slipstream does not require a proxy. If you use one, configure it yourself with a single upstream:

```text
Forward host: slipstream-f1 (or the Unraid host address)
Forward port: 3444 (or the mapped host port)
WebSocket support: enabled
```

No separate `/api` location, gateway container, proxy-network environment variable, or bundled Nginx configuration is required. Select a Docker network in the Unraid template only when your proxy topology needs it.

## Updating

For `latest`, use Unraid’s **Force Update** action or pull the image and recreate the container. Keep the same `/data` mapping.

The release workflow also publishes immutable `run-N` and `sha-COMMIT` tags. Pin one of those for a controlled deployment. Rollback means selecting the earlier tag and recreating the same container; recordings remain unchanged.

## Moving from the older multi-container layout

After the new `slipstream-f1` container is healthy:

1. confirm it uses the existing recordings/appdata directory;
2. point any reverse proxy at the single container;
3. stop and remove the old `slipstream-f1-backend`, `slipstream-f1-web`, and gateway containers;
4. remove their unused images from the Unraid Docker page if desired.

An image shown as orphaned or unused means no current container references it. Removing an old unused image does not delete the recordings directory, but confirm the active container and `/data` mapping first.

## Compose alternative

Users who prefer Compose can copy `deploy/unraid/compose.yaml`, `.env.example`, and `refresh.sh` into an appdata directory. Rename `.env.example` to `.env` and set the published image plus host-specific port, storage, UID, and GID values.

```sh
docker compose up -d --wait
```

To refresh later:

```sh
sh /mnt/user/appdata/slipstream-f1/refresh.sh
```

The public Compose example intentionally contains no server name, private Docker network, reverse-proxy network, hostname, token, or credential.
