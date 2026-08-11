# Roadmap

Slipstream has completed its historical-replay foundation. The roadmap now focuses on turning the experimental public live recorder into a reliable normalized live source without weakening replay behavior or requiring authenticated data.

## Current baseline

The following is implemented and tested:

- historical OpenF1 session, weekend, and season acquisition
- versioned raw recording and lightweight catalog formats
- deterministic normalization into immutable `RaceState` snapshots
- race, qualifying, sprint, and practice replay
- session discovery for the current and two preceding seasons
- browser downloads for finished catalog sessions
- exact historical circuit outlines loaded independently of timing recordings
- timing-derived car placement and optional historical source X/Y
- weather, rain sensor, track status, race control, and circuit-local time
- per-viewer WebSocket play, pause, seek, speed, and delay
- terminal, REST API v1, WebSocket, and browser outputs
- one-container deployment for Docker, Unraid, and other container hosts
- golden-file and focused regression coverage

## Next milestone: normalized public live timing

The next release line should prove the live path during a real session before generalizing it.

1. Capture at least one complete real-session public SignalR recording.
2. Document which topics and fields are actually available without authentication.
3. Normalize the validated public messages into the existing event model and `RaceState`.
4. Feed live state through the same API and browser presentation used by replay.
5. Add reconnect behavior while preserving one upstream connection per instance.
6. Add a bounded in-memory event buffer for per-viewer broadcast delay.
7. Make live/stale/unavailable states explicit in the UI and API.
8. Add golden replay tests derived from the project’s own public capture.
9. Extract a common source lifecycle only after historical and live implementations demonstrate it.

The live source must degrade by capability. Missing protected GPS or telemetry must never prevent public timing from operating.

## Enhanced-source integration

After public live timing is stable:

- define an adapter boundary for authenticated or paid sources;
- keep credentials in runtime configuration only;
- expose authenticated status and per-field capabilities explicitly;
- add live source X/Y without changing browser logic that consumes `positionMode`;
- test fallback from source X/Y to timing estimates to unavailable placement;
- ensure one selected upstream source owns the instance connection.

No authenticated capture, token, cookie, or protected payload belongs in the repository.

## Product work

Potential product features after live timing is dependable:

- configurable battle groups, including two-on-two comparisons;
- gap and position progression over a selected time window;
- replay bookmarks and shareable session/time links;
- recording retention and storage visibility;
- hardware and LED clients using API v1;
- API conformance fixtures for third-party clients.

## Release quality

Before declaring a stable 1.0 contract:

- validate the live source across multiple session types and race weekends;
- publish explicit recording migration rules;
- define API deprecation and compatibility windows;
- add backup/restore documentation for `/data`;
- add observability for upstream state, reconnects, and recording health;
- test upgrades and rollbacks using immutable container tags.

## Non-goals for the current milestone

Slipstream is not currently a strategy simulator, fantasy platform, news product, predictive analytics system, or full authenticated telemetry archive. Those areas should not complicate the historical replay and public live timing core.
