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

The production UI never substitutes representative preview timing when the API is unavailable. It preserves the last confirmed snapshot and shows initialization/retry or connection status. The design prototype is a separate reference under `design/`; it is not a runtime data source.

Open `http://localhost:3344`; Vite uses that fixed port and proxies to the Python backend on port 8000. Desktop, phone and TV use one `useSlipstreamSession` controller. Presentation changes preserve cursor, speed, delay, pause and replay return point. Commands from controls, keyboard and remote use the same capability guard. Live pause holds the source cursor, resumes with accrued delay and automatically resumes at the five-minute limit with a visible notice. Live has no seek or speed selection.

Story, pair gaps, qualifying settlement and results come from backend analytics. Reconnects and seeks advance a navigation generation so earlier events are not announced again. See [session experience](../docs/session-experience.md), [protocol](../docs/protocol.md) and [story](../docs/story.md).

## Checks

```sh
npm run lint
npm run typecheck
npm test
```

`npm test` builds the static application and runs the browser test files, including transport, rendered components and redesign behavior. Automated checks do not replace visual, remote-device or viewing-distance acceptance.
