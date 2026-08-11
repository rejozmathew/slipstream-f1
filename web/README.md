# Browser pit wall

The browser is a React application built with Vite. During production image creation it compiles to static files; FastAPI serves those files, the REST API, and the WebSocket from one origin.

```sh
npm install
npm run dev
```

The Vite development server proxies `/api` and WebSocket requests to `http://127.0.0.1:8000`. Set `VITE_SLIPSTREAM_API` only when deliberately testing against another non-secret API origin. Client-prefixed build variables are public and must never contain secrets.

```sh
npm run lint
npm test
```
