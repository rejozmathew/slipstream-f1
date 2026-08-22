# Changelog

## Unreleased — Milestone 3.5 review candidate

### Added

- Explicit driver lifecycle/terminal semantics and cursor-safe replay/live session-mode handling.
- Deterministic `race-intelligence-v2.1` sidecar with RaceRead, race-phase comparability, dry-rule state, projection gates, TO_FINISH evidence, Driver Read, completed-lap Battle histories, and server-owned recommendation stabilization.
- Full Race Strategy hierarchy plus focused Driver, Battle, and authored TV surfaces.
- Strong persistent TV track-status treatment and focused Driver/Battle maps.
- Explicit Historical/Official context and backtest availability contracts.

### Corrected

- Kept full lap history out of high-frequency `RaceState` snapshots.
- Removed frontend recreation of Battle/analytics truth.
- Suppressed Net Pit Loss-dependent outputs until that model exists.
- Removed believable fabricated Historical, Pirelli, and backtest values from legacy spike modules.
- Aligned Python and TypeScript dry-tyre, lifecycle, window, held-recommendation, RaceRead, and distribution shapes.

This entry records implementation work only. Milestone 3.5 is not accepted until independent review.
