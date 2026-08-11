# Docker deployment

Slipstream is packaged as one Linux container that includes the compiled browser application and the Python service. Node is used only while building the image. At runtime there is one process, one container, and one internal port: `3444`.

## Windows and macOS

1. Install Docker Desktop and start it.
2. Clone the repository, open a terminal in the repository folder, and run:

   ```sh
   docker compose up -d --build
   ```

3. Open `http://localhost:3444`.

Docker Desktop runs the Linux image automatically. No Python or Node installation is needed on the host.

## Linux

Install Docker Engine with the Compose plugin, clone the repository, and run the same command:

```sh
docker compose up -d --build
```

## Choose another host port

Port `3444` is only the default host address. Map any free host port to container port `3444`:

```sh
SLIPSTREAM_PORT=7444 docker compose up -d --build
```

On PowerShell:

```powershell
$env:SLIPSTREAM_PORT = "7444"
docker compose up -d --build
```

Then open `http://localhost:7444`.

## Run a published image directly

Replace the image placeholder with the package path shown on the GitHub repository:

```sh
docker run -d --name slipstream-f1 --restart unless-stopped -p 3444:3444 -v slipstream-recordings:/data ghcr.io/your-github-owner/slipstream-f1:latest
```

To expose only the API and WebSocket, add `-e SLIPSTREAM_MODE=api-only`.

A reverse proxy is optional. If one is used, send one hostname to container port `3444` and enable WebSocket forwarding. Slipstream does not bundle or configure a proxy.
