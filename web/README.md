# Slipstream F1 web

The browser consumer for canonical `RaceState` API v1. It renders a timing tower, race-control messages, tyre/stint state, and timing-derived approximate track positions.

Development requires Node.js 22.13 or newer.

```powershell
npm install
npm run dev
npm test
```

The default API origin is `http://127.0.0.1:8000`. Override it at build time with `NEXT_PUBLIC_SLIPSTREAM_API`. Representative replay data keeps the layout usable when the backend is offline.

The current vinext beta depends on `image-size`, which has two open denial-of-service advisories and no patched release. This application does not accept image uploads or process untrusted images; keep the dependency under review and do not add such a path until the advisory is resolved.
