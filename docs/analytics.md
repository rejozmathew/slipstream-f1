# Analytics, Race Intelligence & Strategy Charter

Slipstream keeps factual `RaceState` separate from deterministic `AnalyticsSnapshot`. Server analytics are cursor-safe, source-neutral, provenance-bearing, and allowed to return `UNKNOWN`. Clients render them and do not recreate the calculations.

## Model registry

- [race-intelligence-v2.1](analytics/race-intelligence-v2.1.md) — current Milestone 3.5 model and normative formulas/gates.
- [race-intelligence-v1](analytics/race-intelligence-v1.md) — superseded historical model reference.

See the [CHANGELOG](../CHANGELOG.md) for release history.

## Qualifying intelligence

`qualifying-intelligence-v1` is a deterministic `AnalyticsSnapshot.qualifying` sidecar. The server—not React—authors phase, session clock, benchmark scope, verified advancement boundary, per-driver best/delta/elimination state, teammate comparison, and completed-lap history at the inclusive replay or delayed-live cursor.

Phase is accepted only from normalized `SessionData`/session evidence as `Q1`–`Q3` or `SQ1`–`SQ3`. With factual phase, the benchmark is the best lap in that segment. With phase unknown, the benchmark is the fastest qualifying lap known anywhere in the session at that cursor and is explicitly marked session-wide. `benchmarkDelta` is the driver's scope-best minus that benchmark; absent or unparseable laps remain `null`.

Current advancement state requires an explicit season, stable roster field size, and phase rule profile. M3.5 verifies the normal 20-car 2024 and 2025 profiles (Q1/SQ1 top 15; Q2/SQ2 top 10) and preserves the separately verified 2026 profile. A partial timing snapshot never changes the advancement count. If stable roster/profile evidence is insufficient, elimination-zone treatment is omitted. Being below the current boundary is not factual elimination; `ELIMINATED` requires source/final-result evidence.

Lap-history entries are source-neutral completed-lap observations with `sequence <= snapshot.sequence`. Rewinding therefore removes future laps. Historical OpenF1 final Q1/Q2/Q3 result arrays are normalized only at official session end, so they are physically unreachable one event before that point. Phase, tyre NEW/USED, and validity remain `UNKNOWN` unless normalized evidence established them. No run boundary, predictive safe/at-risk label, minisector, or telemetry claim is inferred.

## Driver activity and lifecycle

Activity is separate from lifecycle. Explicit timing/app data can establish `ON_TRACK` or `IN_PIT`; missing recent progress does not establish another product state in M3.5. `STOPPED` remains non-terminal. Explicit `RETIRED`, DNF, DNS, DSQ, and withdrawal are terminal and sparse later timing cannot resurrect a driver.


## Published Pirelli strategy

The official pre-race baseline and its deterministic comparison with factual current-race evidence are specified in [Published Pirelli strategy](pirelli-strategy.md). `publishedStrategy` is separate from the legacy internal `raceStrategy` model: product race surfaces use the published baseline and server-authored relation/window state, while existing calculations remain compatibility/internal data until separately accepted.

Pirelli discovery is event-aware and purpose-aware. Exact official event tags admit candidates without weakening alias thresholds; Race and Sprint releases populate only their target session scope, while meeting-bound WEEKEND nominations may be reused by either. Every normalized fact carries its contributing artifact IDs, and each artifact version independently satisfies the replay cutoff.

The server compares only `ORDERED` options. It retains all compatible option IDs and windows, marks observed transitions `COMPLETED`, derives remaining window state from the replay lap, and suppresses live/future windows in FINAL state. `ANY_ORDER` remains non-directional published context. Missing or ambiguous prose, tyre-bank artifacts, or applicability remains absent/`UNKNOWN` rather than being completed in React.
