# Race Intelligence & Strategy Charter

Slipstream keeps factual `RaceState` separate from deterministic `AnalyticsSnapshot`. Server analytics are cursor-safe, source-neutral, provenance-bearing, and allowed to return `UNKNOWN`. Clients render them and do not recreate the calculations.

## Model registry

- [race-intelligence-v2.1](analytics/race-intelligence-v2.1.md) — current Milestone 3.5 model and normative formulas/gates.
- [race-intelligence-v1](analytics/race-intelligence-v1.md) — superseded historical model reference.

See the [CHANGELOG](../CHANGELOG.md) for release history.


## Published Pirelli strategy

The official pre-race baseline and its deterministic comparison with factual current-race evidence are specified in [Published Pirelli strategy](pirelli-strategy.md). `publishedStrategy` is separate from the legacy internal `raceStrategy` model: product race surfaces use the published baseline and server-authored relation/window state, while existing calculations remain compatibility/internal data until separately accepted.
