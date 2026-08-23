# Changelog

## Unreleased — Milestone 3.5 review candidate

### Added

- A product-level live lifecycle covering pre-event, connecting, live, stale, reconnecting, finalizing, complete, replay-ready, and unavailable states.
- Normalized live-session recording with atomic replay-library promotion after a completion drain.
- Independent per-viewer live delay with cursor-aligned factual state and analytics.
- Server-authored Qualifying phase/clock, scoped benchmark, stable-roster advancement, final Q1/Q2/Q3 facts, completed-lap history, teammate comparison, and session-aware focused views.
- Explicit resumable `STOPPED` versus persistent terminal lifecycle; the prior `NO_RECENT_PROGRESS` product heuristic is disabled for M3.5.
- Sparse-packet-resistant timing-derived track progress with explicit capability limits for precise live X/Y.
- Explicit driver lifecycle/terminal semantics and cursor-safe replay/live session-mode handling.
- Deterministic `race-intelligence-v2.1` sidecar with RaceRead, race-phase comparability, dry-rule state, projection gates, TO_FINISH evidence, Driver Read, completed-lap Battle histories, and server-owned recommendation stabilization.
- Factual `raceRead` Strategy presentation plus admitted Pirelli baseline context; legacy projection-heavy wire fields remain compatibility-only and are not read by product surfaces.
- Strong persistent TV track-status treatment and focused Driver/Battle maps.
- Explicit Historical/Official context and backtest availability contracts.

### Corrected

- Removed replay transport affordances from live viewing and made return-to-LIVE explicit.
- Kept Qualifying policy profiles season/field-size explicit rather than hard-coding a single elimination count.
- Ensured late post-completion packets extend finalization instead of being lost at the first chequered signal.
- Kept full lap history out of high-frequency `RaceState` snapshots.
- Removed frontend recreation of Battle/analytics truth.
- Added source-dependent red-flag handling: public Live uses explicit suspension/restart evidence, while OpenF1 historical replay avoids a persistent latch when the source has no explicit actual restart.
- Kept the selected session stable through `FINALIZING → REPLAY_READY`, including hard refresh, while later Live sessions are only advertised until explicitly selected.
- Restricted Qualifying TV to Tower plus renderable Track and Practice TV to Tower-only; removed Cut Line/Sectors and placeholder Practice rotations.
- Suppressed Net Pit Loss-dependent outputs until that model exists.
- Removed believable fabricated Historical, Pirelli, and backtest values from legacy spike modules.
- Aligned Python and TypeScript dry-tyre, lifecycle, window, held-recommendation, RaceRead, and distribution shapes.

This entry records implementation work only. Milestone 3.5 is not accepted until independent review.
