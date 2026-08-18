# Changelog

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
