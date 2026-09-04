# Unraid deployment

Slipstream uses one image, one container, and one internal TCP port. The technical slug is `slipstream-f1`.

## Docker template

Create one Unraid container with:

| Template field | Value |
| --- | --- |
| Name | `Slipstream` |
| Repository | `ghcr.io/rejozmathew/slipstream-f1:latest` |
| WebUI | `http://[IP]:[PORT:3344]` |
| Container port | `3344` TCP |
| Host port | `3344` by default; choose another free host port if needed |
| Container path | `/data`, read/write |
| Host path | `/mnt/user/appdata/slipstream-f1` |
| Variable | `SLIPSTREAM_MODE=full` |
| Variable | `SLIPSTREAM_CATALOG_YEARS=3` |
| Network | `bridge` by default; adapt to your server if needed |

The image runs as its built-in non-root `slipstream` user (UID 10001). Prepare the host appdata directory so UID 10001 can write to it, and retain the image's built-in user. A host bind mount supplies its own permissions; it does not inherit the image directory's ownership. Validate a clean writable directory before relying on the installation.

Start the container and open `http://UNRAID-IP:3344` (or the selected host port).

`full` is the normal, recommended installation: browser UI + REST API + WebSocket. `api-only` serves headless REST API + WebSocket without the bundled browser UI and is useful for custom clients/integrations. The browser depends on the API/WebSocket, so a browser-only runtime mode is not supported.

`SLIPSTREAM_CATALOG_YEARS` is the number of recent Formula 1 seasons included in Slipstream's session catalog and defaults to `3`. On first startup, Slipstream refreshes lightweight metadata for the current and two preceding seasons; it does not automatically download timing for every session. Pirelli history remains fixed internally at ten seasons and is not an administrator-facing horizon setting.

## Persistent application data

The standard read/write mapping is:

```text
/mnt/user/appdata/slipstream-f1 -> /data
```

`/data` is Slipstream's persistent application-data root and may contain:

- catalog metadata;
- downloaded replay/session data;
- `.slipstream` operational state;
- Pirelli state;
- future persistent database/settings.

Application code stays inside the image under `/app`. `/data` is not the application installation directory. Preserve and back up the entire host data root across container updates.

Use the browser's **Download replay** action for finished sessions, or run (use `slipstream-f1` as the container name for the Compose installation):

```sh
docker exec Slipstream python -m slipstream fetch 9165 --output /data/session-9165.json
docker exec Slipstream python -m slipstream fetch-weekend 1219 --output-dir /data
docker exec Slipstream python -m slipstream fetch-season 2023 --output-dir /data
```

Add `--include-location` only when you want the much larger historical source X/Y data.

## Draft Community Applications template

[deploy/unraid/slipstream-f1.xml](../deploy/unraid/slipstream-f1.xml) is a DockerMan v2 draft for private testing. It pre-fills the image, WebUI, port, appdata mapping, runtime mode, and catalog years above. Its mode selector offers `full` and `api-only`, with `full` selected initially.

The draft follows the [official Community Apps field reference](https://ca.unraid.net/submit/help/xml-field-reference) and [DockerMan implementation conventions](https://github.com/unraid/webgui/blob/master/emhttp/plugins/dynamix.docker.manager/include/CreateDocker.php). XML parsing alone does not validate DockerMan compatibility. This template has not been validated by an actual DockerMan-compatible schema or imported and exercised on Unraid, and is **not CA-submission-ready**.

Before submission, privately import the template on Unraid, inspect the generated container command and defaults, then verify catalog access, browser routes in full mode, absent browser routes in api-only mode, and persistent writes on a clean data root using the built-in image user.

## Nginx Proxy Manager or another proxy

Slipstream does not require a proxy. If you use one, configure a single upstream:

```text
Forward host: Slipstream (slipstream-f1 for Compose), or the Unraid host address
Forward port: 3344 (or the mapped host port)
WebSocket support: enabled
```

No separate `/api` location, gateway container, proxy-network environment variable, or bundled Nginx configuration is required. Select a Docker network in the Unraid template only when your proxy topology needs it.

## Updating

For `latest`, use Unraid's **Force Update** action or pull the image and recreate the container. Keep the same `/data` mapping.

The release workflow also publishes immutable `run-N` and `sha-COMMIT` tags. Pin one of those for a controlled deployment. Rollback means selecting the earlier tag and recreating the same container; persistent application data remains unchanged.

## Moving from the older multi-container layout

After the new `slipstream-f1` container is healthy:

1. confirm it uses the existing appdata directory;
2. point any reverse proxy at the single container;
3. stop and remove the old `slipstream-f1-backend`, `slipstream-f1-web`, and gateway containers;
4. remove their unused images from the Unraid Docker page if desired.

An image shown as orphaned or unused means no current container references it. Removing an old unused image does not delete the persistent-data directory, but confirm the active container and `/data` mapping first.

## Compose alternative

Copy `deploy/unraid/compose.yaml` and `deploy/unraid/refresh.sh` into `/mnt/user/appdata/slipstream-f1`. The Compose file is self-contained: it uses the official image, `3344:3344`, full mode, a three-season catalog, and `/mnt/user/appdata/slipstream-f1:/data`. It retains the built-in image user, always pulls the image, restarts unless stopped, and checks `http://127.0.0.1:3344/api/v1/catalog`. No `.env` file is required. Edit the YAML directly when the host needs different values.

```sh
docker compose up -d --wait
```

To refresh later:

```sh
sh /mnt/user/appdata/slipstream-f1/refresh.sh
```

The public Compose example contains no server name, private Docker network, reverse-proxy network, hostname, token, or credential.
