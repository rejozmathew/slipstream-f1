# Analytics, Race Intelligence & Strategy Charter

Slipstream keeps factual `RaceState` separate from deterministic `AnalyticsSnapshot`. Server analytics are cursor-safe, source-neutral, provenance-bearing, and allowed to return `UNKNOWN`. Clients render them and do not recreate the calculations.

## Model registry

- [race-intelligence-v2.1](analytics/race-intelligence-v2.1.md) — current Milestone 3.5 model and normative formulas/gates.
- [race-intelligence-v1](analytics/race-intelligence-v1.md) — superseded historical model reference.

See the [CHANGELOG](../CHANGELOG.md) for release history.

## Qualifying intelligence

`qualifying-intelligence-v1` is a deterministic `AnalyticsSnapshot.qualifying` sidecar. The server—not React—authors phase, session clock, benchmark, current cut boundary, per-driver benchmark delta/activity/cut state, and completed-lap attempts at the inclusive replay or delayed-live cursor.

Phase is accepted only from normalized `SessionData`/session evidence as `Q1`–`Q3` or `SQ1`–`SQ3`. The benchmark is the best parseable current driver lap only after phase is established. `benchmarkDelta` is `driver_best_seconds - benchmark_seconds`; absent or unparseable laps remain `null`.

Current cut state requires an explicit season, field-size, and phase rule profile. M3.5 verifies 2023/20-car and 2026/22-car Q1/SQ1 and Q2/SQ2 boundaries; other sizes/segments return `UNKNOWN`. Being below the current boundary is not elimination. `ELIMINATED` requires factual source elimination evidence.

Attempts are source-neutral completed-lap observations with `sequence <= snapshot.sequence`. Rewinding therefore removes future attempts. Phase, tyre NEW/USED, and validity remain `UNKNOWN` unless the normalized observation established them. No run boundary, predictive safe/at-risk label, minisector, or telemetry claim is inferred.

## Driver activity and no-recent-progress

Activity is separate from lifecycle. Explicit timing/app data can establish `ON_TRACK` or `IN_PIT`. During a progressing Race, `NO_RECENT_PROGRESS` is derived when a non-terminal, non-pit driver's own last proven completed lap trails the canonical session/leader lap by at least two. This is a conservative circulation-gap presentation state, not STOPPED, DNF, or retirement. Any later completed-lap progress immediately restores `ON_TRACK`; completed/final sessions do not newly derive it.


## Published Pirelli strategy

The official pre-race baseline and its deterministic comparison with factual current-race evidence are specified in [Published Pirelli strategy](pirelli-strategy.md). `publishedStrategy` is separate from the legacy internal `raceStrategy` model: product race surfaces use the published baseline and server-authored relation/window state, while existing calculations remain compatibility/internal data until separately accepted.

Pirelli discovery is event-aware and purpose-aware. Exact official event tags admit candidates without weakening alias thresholds; Race and Sprint releases populate only their target session scope, while meeting-bound WEEKEND nominations may be reused by either. Every normalized fact carries its contributing artifact IDs, and each artifact version independently satisfies the replay cutoff.

The server compares only `ORDERED` options. It retains all compatible option IDs and windows, marks observed transitions `COMPLETED`, derives remaining window state from the replay lap, and suppresses live/future windows in FINAL state. `ANY_ORDER` remains non-directional published context. Missing or ambiguous prose, tyre-bank artifacts, or applicability remains absent/`UNKNOWN` rather than being completed in React.
