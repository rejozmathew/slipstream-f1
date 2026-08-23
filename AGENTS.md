# Working agreement

Before changing code:

- Read `ARCHITECTURE.md` for current system boundaries.
- Read `docs/protocol.md` before changing state, API, WebSocket, or recording contracts.
- Keep documentation proportional to an early open-source project and update it when behavior changes.

Architecture rules:

- Preserve immutable `RaceState` as the canonical boundary for every output.
- Put provider-specific acquisition and translation in adapters; never expose raw provider fields through state or API v1.
- Treat optional raw SignalR capture as diagnostic evidence; the canonical normalized live event recording is the product replay artifact.
- Maintain one upstream live connection per application instance.
- Declare capabilities explicitly and keep public and authenticated capabilities separate.
- Do not extract a common source interface until a real-session live implementation validates the shared lifecycle.
- Keep replay cursors, speed, seek, and delay per viewer.
- Author persistent reversible sporting/control state at the source boundary only when that source supplies explicit entry and exit semantics. Never use `TRACK CLEAR`, lap/sector progress, gaps, or timing resumption as a sporting restart.
- Treat `STOPPED` as non-terminal and explicit `RETIRED`/DNF/DNS/DSQ/withdrawal as terminal. Do not restore `NO_RECENT_PROGRESS` in M3.5.
- Use stable session/source capability for column presence. Missing row values render `—`; capability-wide absence omits the element instead of exposing raw `UNKNOWN`/`UNAVAILABLE` enums.
- React renders server-authored Race/Qualifying/Strategy semantics. Legacy projection fields may remain on the wire but M3.5 product components must not read them.
- Preserve the one-process, one-container production model. Do not add a runtime Node or Nginx service without an explicit architectural reason.

Local application preview:

- Run the Python backend on `127.0.0.1:8000`.
- Run the Vite UI with `cd web` then `npm run dev`; the repository fixes it to
  `127.0.0.1:3344` and proxies `/api/v1` to the backend.
- Open `http://localhost:3344`. Do not run `slipstream serve` on port `3344`
  and do not accept Vite's default `5173` port.
- These two development processes do not change the one-process production
  architecture; Docker serves the built UI and API together on one port.

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

## Local subagent delegation

The primary Codex agent owns architecture, implementation decisions, substantial
source-code changes, difficult cross-system debugging, and final acceptance.

Use local subagents proactively for bounded work when delegation is cheaper than
doing the intermediate work in the primary context.

- `local_explorer`: use for read-heavy repository exploration, locating code,
  tracing execution/data flow, mapping configuration, and gathering evidence.
- `local_validator`: use for tests, lint, type checks, builds, reproduction,
  logs, and bounded external verification needed to validate a change.
- `local_reviewer`: use after implementation for an independent read-only review
  focused on correctness, regressions, security, edge cases, and missing tests.
- `local_researcher`: use for bounded current web research, official documentation,
  release/version checks, APIs, compatibility research, and source gathering.

Prefer local agents for noisy intermediate work that can be summarized back to
the primary agent.

Do not delegate architecture, ambiguous product decisions, major code changes,
or final acceptance to a local agent.

Avoid spawning multiple local agents concurrently unless the tasks are genuinely
independent; they share the same local model/GPU.

