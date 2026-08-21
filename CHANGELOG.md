# Changelog

## [v2.2.0] - 2026-08-21
### Added
- **Analytics v2.2**: Introduced strict race phase proxying, Strategy Archetypes, and terminal status propagation.
- **RaceRead**: Created a clean projection layer independent of RaceState for React/frontend consumption.
- **TV Mode**: Added a full-field compact 1080p TV tower and a semantic status rail.
- **Contract Integrity**: Mirrored TypeScript definitions with backend models to resolve shape mismatches.

## [v2.1.0] - 2026-08-18
### Added
- **Phase A-C**: Core analytical model upgrades for dry-tyre rules, race-horizon disposition, strategy validity, and stability gates.
- **Phase D**: Dedicated StrategyView and SessionStrategySnapshot.
- **Phase E**: Server-side calculation migration for Battle View and Driver Focus; race-family gating.
- **Phase F**: Bounded spikes for HistoricalContext and OfficialPreRaceContext acquisition (e.g. Pirelli).
- **Phase G**: Automated Backtesting Harness script with hit-rate/error metrics.
- **Phase H**: Model registry refactor of analytics documentation.

### Changed
- PaceDeltaChart MAD scaling and battle hysteresis moved to server.
- Suppressed `freeStopMargin` and `projectedRejoinPosition` pending `NetPitLoss` model.
- Removed Sprint durations from Grand Prix pit loss metrics.
