# Working agreement

Before changing code:

- Read `ARCHITECTURE.md` for current system boundaries.
- Read `docs/protocol.md` before changing state, API, WebSocket, or recording contracts.
- Keep documentation proportional to an early open-source project and update it when behavior changes.

Architecture rules:

- Preserve immutable `RaceState` as the canonical boundary for every output.
- Put provider-specific acquisition and translation in adapters; never expose raw provider fields through state or API v1.
- Treat the public live recorder as raw evidence, not as an integrated live source.
- Maintain one upstream live connection per application instance.
- Declare capabilities explicitly and keep public and authenticated capabilities separate.
- Do not extract a common source interface until a real-session live implementation validates the shared lifecycle.
- Keep replay cursors, speed, seek, and delay per viewer.
- Preserve the one-process, one-container production model. Do not add a runtime Node or Nginx service without an explicit architectural reason.

Safety and licensing:

- Never commit recordings, `.env` files, tokens, cookies, credentials, or authenticated captures.
- Do not copy AGPL code, including code or fixtures from slowlydev/f1-dash.
- Keep protected GPS, telemetry, and radio topics opt-in behind an authenticated adapter; never request them silently.

Verification:

- Add focused tests for behavioral changes.
- Update golden files when normalized or terminal-visible state intentionally changes.
- Add capability/fallback coverage when a field can be available, unavailable, unsupported, or stale.
- Keep public routes and event envelopes versioned as documented in `docs/protocol.md`.
- Run Python lint/tests and web lint/build tests for changes that cross the container boundary.
