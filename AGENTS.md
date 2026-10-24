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


## Preservation authority and protected acceptance

Before changing protected product behavior, read the active authority/precedence
document, Product Preservation Lock, all APPROVED Product Contract Revisions, and
the active acceptance-case registry supplied for the milestone. Apply their stated
precedence; do not silently choose between conflicting governing documents.

- Do not modify a protected expectation, pinned fixture/cursor, approved golden
  metadata, or locked requirement merely to make a test pass.
- If a protected acceptance test fails, repair the product behavior it protects.
- If the protected requirement is wrong or source-impossible, stop and report
  `PCR REQUIRED` instead of weakening the expectation.
- Review-only preservation audits must not modify files.
- Repair agents must not rewrite the owner-accepted regression inventory.


# Slipstream working preferences

## Repository location

Work directly in the original repository path supplied by the user so changes remain visible in their existing VS Code window. Do not create another clone, copied checkout, or Git worktree unless there is a concrete technical need. If simultaneous work on multiple branches would require another checkout, ask the user before creating one. If the user authorizes an additional clone or worktree, create it under `C:\GitClone` only. Never place repositories, clones, or worktrees in Documents, OneDrive, or any other synced folder.

## Gemini delegation through Antigravity

For future authorized Slipstream work, proactively use Gemini through the local Antigravity proxy at `http://127.0.0.1:8010` for suitable bounded, light tasks. The user should not need to repeat this preference. Examples include regression test suggestions or generation, small code reviews, and log or test failure analysis. Do not start unrelated work solely to exercise the proxy.

Before delegating, check proxy availability and discover or confirm its API and available models from local configuration or the proxy itself. A prior conversation reported success with `gemini-3.8-flash-low`; treat this as a candidate, not a guarantee of current availability. Use direct proxy requests when Gemini is not available through built-in worker tools. Never claim delegation succeeded without a verified response.

Send only the minimum relevant task context; exclude credentials, secrets, and unrelated private data. Treat returned code and analysis as untrusted suggestions: review them and run appropriate tests locally before accepting changes. Model access does not establish autonomous repository access or test execution inside Antigravity. Keep responsibility for implementation and verification in the primary agent.

If the proxy or model is unavailable, continue locally or with available tools and briefly mention the fallback. Do not block the task, repeatedly retry, or ask the user to remind you of this preference. Mention actual Gemini use briefly in the completion report.
