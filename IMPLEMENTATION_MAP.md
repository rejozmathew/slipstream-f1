# Implementation map

This map describes the Milestone 3.5 clean-restart implementation based on commit `16fa0b5a65a9611a8a408516fa786611bff09bca`. It is an engineering map, not an acceptance claim.

## Canonical pipeline

```text
OpenF1 replay or public live evidence
  -> NormalizedEvent
  -> RaceState (factual current state)
  + SessionEvidence / WeekendContext (history sidecars, cursor-bounded)
  -> AnalyticsSnapshot race-intelligence-v2.1 (deterministic derived state)
  -> REST / WebSocket / React / TV
```

React renders canonical contracts and does not recreate analytics truth. Historical replay remains the regression harness. Missing evidence stays `UNKNOWN`; unavailable source/context and deliberately unimplemented models are labelled explicitly.

## Backend ownership

| Area | Primary implementation |
| --- | --- |
| Normalization and lifecycle | `src/slipstream/adapters/`, `state.py`, `replay.py` |
| Replay/live session mode | `library.py`, `live.py`, `server.py`, `playback.py` |
| Lap and session evidence | `evidence.py`, `weekend.py` |
| Race intelligence | `analytics.py`, `race_intelligence.py`, `strategy_rules.py` |
| Optional context contracts | `context_types.py`, `historical.py`, `pirelli.py` |
| Backtest boundary | `backtest.py` — truthfully `NOT_IMPLEMENTED`; no metrics are published |
| API contract | `server.py`, `docs/protocol.md` |

`RaceState` remains factual and lightweight. Full lap history stays in `SessionEvidence`. `AnalyticsSnapshot` is independently versioned and cursor-safe.

## Product surfaces

| Surface | Ownership |
| --- | --- |
| Session / Timing | canonical `RaceState` |
| Strategy | server `raceRead`, race/driver strategy, gates and provenance |
| Driver | canonical driver facts plus server Driver Read and strategy |
| Battle | server candidates, completed-lap history and stabilized recommendation |
| TV Mode | authored rendering of the same contracts; no separate TV truth model |

Strategy and Battle are Race/Sprint-only. Track markers use canonical team colours; focused maps de-emphasize non-target cars without hiding factual field context.

## Context boundaries

- `WeekendContext` accepts only earlier sessions from the same `meeting_key` and before the evidence cutoff.
- Prior-season same-circuit `HistoricalContext` is separately labelled context only and never blended into current-meeting truth. With no compatible ingested artifact it is `ABSENT`; 2025→2026 comparability is `LIMITED`.
- `OfficialPreRaceContext` is a separately attributed artifact. Automated Pirelli parsing is not implemented; the legacy sample-returning spike now returns no context.
- `NetPitLoss` and deterministic archive backtesting are `NOT_IMPLEMENTED`. Dependent rejoin/free-stop/quantified-undercut fields and quality metrics are not fabricated.

## Verification map

Focused tests live in:

- `tests/test_lifecycle.py`, `tests/test_live.py`
- `tests/test_race_intelligence.py`
- `tests/test_strategy_v21_contract.py`, `tests/test_strategy_v21_battle.py`
- `tests/test_packet_e_contracts.py`
- `web/tests/domain.test.mjs`, `web/tests/rendered-html.test.mjs`

See `docs/analytics/race-intelligence-v2.1.md` for normative formulas and evidence gates, `docs/protocol.md` for wire contracts, and `ROADMAP.md` for later milestones. M4 authentication/control-plane work remains out of scope.
