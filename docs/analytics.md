# Race Intelligence & Strategy Charter

Slipstream keeps factual `RaceState` separate from deterministic `AnalyticsSnapshot`. Server analytics are cursor-safe, source-neutral, provenance-bearing, and allowed to return `UNKNOWN`. Clients render them and do not recreate the calculations.

## Model registry

- [race-intelligence-v2.1](analytics/race-intelligence-v2.1.md) — current Milestone 3.5 model and normative formulas/gates.
- [race-intelligence-v1](analytics/race-intelligence-v1.md) — superseded historical model reference.

See the [CHANGELOG](../CHANGELOG.md) for release history.
