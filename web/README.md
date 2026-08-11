# Browser pit wall

The browser is a React application built with Vite. It consumes only Slipstream’s versioned REST/WebSocket contract; it never calls OpenF1 or the Formula 1 live endpoint directly.

## Production

The Docker build compiles `web/` to static files. FastAPI serves those files from `/` and serves API v1 from the same origin. There is no Node process in the runtime image.

The page selects presentation behavior from catalog capabilities and `positionMode`:

- `precise_xy`: display source historical X/Y samples;
- `timing_estimate`: map timing-derived progress onto the circuit;
- `unavailable`: show the circuit and an explicit position-unavailable message.

A schedule-active session can be labelled `LIVE` even though normalized live timing is not yet connected. The page must keep that distinction visible.

## Development

Start the Python API from the repository root:

```sh
slipstream serve recordings --catalog-years 3
```

Then start Vite:

```sh
cd web
npm install
npm run dev
```

Vite proxies `/api` and WebSocket requests to `http://127.0.0.1:8000`. Set `VITE_SLIPSTREAM_API` only when deliberately testing another non-secret API origin. Any `VITE_*` value is compiled into client code and must be treated as public.

The UI contains representative preview state so layout work remains possible when the API is unavailable. That preview must be labelled by transport state and must never be mistaken for connected timing.

## Checks

```sh
npm run lint
npm test
```

`npm test` builds the static application and verifies its production contract and API/WebSocket references.
