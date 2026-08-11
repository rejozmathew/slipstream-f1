# Unraid deployment

Slipstream uses one image, one container, and one internal TCP port (`3444`). It does not require a gateway container or a bundled Nginx service.

## Unraid Docker template

Create one container with these values:

- Repository: the published `ghcr.io/.../slipstream-f1:latest` package shown on GitHub
- Container port: `3444` TCP
- Host port: any free port; `3444` is the friendly default
- Container path: `/data`
- Host path: an appdata recordings directory of your choice
- Optional variable: `SLIPSTREAM_MODE=full` (or `api-only`)
- Network: choose the network appropriate for your server when creating the template

Start the container and open `http://UNRAID-IP:HOST-PORT`.

The application refreshes the lightweight recent-season catalog at startup. Historical replay files and downloaded sessions remain under `/data`, outside the image.

## Compose alternative

The files under `deploy/unraid` are provided for users who prefer Compose. Copy `compose.yaml`, `.env.example`, and `refresh.sh` to an appdata folder, rename `.env.example` to `.env`, and set only the published image path and any host choices you want to override.

```sh
docker compose up -d --wait
```

Download data with the same container:

```sh
docker compose run --rm --user 0 slipstream fetch 9165 --output /data/session.json
docker compose run --rm --user 0 slipstream fetch-weekend 1219 --output-dir /data
docker compose run --rm --user 0 slipstream fetch-season 2023 --output-dir /data
```

To refresh after a release:

```sh
sh /mnt/user/appdata/slipstream-f1/refresh.sh
```

## Existing reverse proxy

A reverse proxy is optional and remains a server-owner choice. If you use one, route a single hostname to `slipstream-f1:3444` (or to the chosen host port) and enable WebSocket forwarding. No separate `/api` destination is needed. Slipstream does not change or configure the proxy.
