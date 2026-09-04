# Implementation map

This map describes the Milestone 3.5 source-unification merge candidate. It maps current engineering ownership and does not override [Architecture](ARCHITECTURE.md) or the normative [Protocol](docs/protocol.md).

## Canonical path

```text
F1 public Live / F1 static history / OpenF1 fallback
    ↓
provider adapter
    ↓
NormalizedEvent
    ├──→ RaceState
    ├──→ SessionEvidence
    └──→ normalized replay

RaceState + SessionEvidence + admitted context
    ↓
AnalyticsSnapshot
    ↓
REST / WebSocket / React / TV
```

React renders canonical contracts and does not recreate analytics or provider truth. Missing evidence remains unavailable or `UNKNOWN`; source and context absence are labelled explicitly.

## Backend ownership

| Area | Primary implementation |
| --- | --- |
| Catalog and session discovery | `catalog.py`, `library.py`, `session.py` |
| Official historical timing | `adapters/f1_historical.py`, `historical_download.py` |
| Shared F1 timing semantics | `f1_timing.py`, `live.py` |
| OpenF1 fallback and CLI capture | `adapters/openf1.py` |
| Canonical events and state | `events.py`, `state.py`, `lifecycle.py` |
| Replay | `replay.py`, `playback.py` |
| Live session and recording | `live.py`, `live_recording.py` |
| Lap, pit, and session evidence | `evidence.py` |
| Weekend context | `weekend.py`, `context_types.py` |
| Analytics orchestration | `analytics.py` |
| RaceRead and race intelligence | `race_intelligence.py`, `strategy_rules.py` |
| Qualifying intelligence | `qualifying.py` |
| Pirelli seed, acquisition, backfill, normalization, admission, and storage | `pirelli/` plus bundled `data/pirelli-seed-v1.json.gz` |
| Published Pirelli comparison | `published_strategy.py` |
| Backtest boundary | `backtest.py` — explicitly `NOT_IMPLEMENTED` |
| API and serialization | `api.py`, `serialization.py` |
| Replay deletion | `storage.py` plus `WeekendContextCoordinator.forget` |
| Browser | `web/` |

`RaceState` remains factual and lightweight. Full lap and pit history stays in `SessionEvidence`. `AnalyticsSnapshot` is independently versioned and cursor-safe.

## Historical source precedence

```text
finalized normalized Live
  > official F1 static reconstruction
  > whole-session OpenF1 fallback
```

Selection is explicit for the whole timing session; provider fields are not spliced together. Direct `slipstream fetch`, `fetch-weekend`, and `fetch-season` remain OpenF1-specific CLI capture commands.

Official F1 `.jsonStream` prefixes are SessionTime. Reconstruction establishes stream zero from a consensus of provider UTC anchors; it does not assume scheduled session start is stream zero. A missing or inconsistent timebase fails the official reconstruction closed.

## F1 public/static topics

The official static path requests the low-volume product topics:

- `SessionInfo`, `DriverList`, and `TimingData`;
- `TimingAppData`, `PitLaneTimeCollection`, and `LapCount`;
- `SessionStatus`, `SessionData`, and `ExtrapolatedClock`;
- `TrackStatus`, `RaceControlMessages`, and `WeatherData`.

The public Live subscription allow-list also contains `Heartbeat` and `TopThree`. A subscribed provider stream becomes product truth only where the adapter maps it to normalized events. Protected telemetry, team radio, and authenticated GPS are excluded.

## Product surfaces

| Surface | Main truth |
| --- | --- |
| Session and Timing Tower | `RaceState`; Race Strategy mode adds `publishedStrategy.actualStrategy` and last factual stop |
| Driver current state | `RaceState.drivers[number]`; Race Driver Focus puts actual strategy before Pirelli reference |
| Driver lap and pit history | `SessionEvidence` through `/api/v1/driver-history` |
| Strategy | full admitted Pirelli baseline plus current-race `publishedStrategy` evidence and factual `raceRead` |
| Qualifying | server-authored `qualifying` analytics |
| Battle | actual two-driver strategy plus server-authored completed-lap evidence; Pirelli remains secondary context |
| Track Map | circuit geometry plus capability- and lifecycle-filtered positions |
| TV Mode | compact rendering of the same actual-strategy, Pirelli, state, and analytics semantics |

Race and Sprint may expose Strategy and Battle. Qualifying uses its own timing and Driver Focus. Qualifying TV is Tower plus Track only when positions are renderable; Practice TV is Tower-only.

## Important implemented semantics

- `STOPPED` and `RETIRED_INDICATED` are current source conditions and can recover when the provider retracts them.
- Final `FINISHED`, `DNF`, `DNS`, `DSQ`, or authoritative `RETIRED` classification is cursor-safe and terminal.
- Historical F1 SessionTime is anchored to provider UTC evidence, not scheduled start.
- `PitLaneTimeCollection.Duration` supplies complete pit-lane transit only.
- Pit-lane durations outside `0 < duration <= 300s` are rejected, not clamped.
- Live delay reconstructs `RaceState` and `AnalyticsSnapshot` at one private delayed cursor.
- The Live protocol accepts 0–300 seconds; the browser currently offers 0, 5, 10, 15, and 30-second presets.
- Pirelli has strict-model and display-only official historical evidence tiers.
- Display-only Pirelli evidence cannot produce model-comparable options or future windows.
- Pirelli history is fixed at ten seasons; the independently configurable replay catalog defaults to three.
- `actualStrategy` preserves every factual pit stop, including same-compound stops, and incomplete evidence stays `UNKNOWN`.
- Dry-tyre requirement is `UNSATISFIED`, `SATISFIED`, `NOT_APPLICABLE`, or `UNKNOWN`; only `UNSATISFIED` is actionable.
- Replay deletion preserves catalog/circuit/Pirelli/source manifests while removing replay timing, raw timing, and rebuildable Weekend Context.
- `IN_PIT` may be omitted from a physical map marker but is never an `OUT / STOPPED` label.

## Verification focus

Current coverage includes:

- F1 source unification and authentic Dutch Race/Qualifying/Practice fixtures;
- live normalization, lifecycle, and 0/30/120-second delay coherence;
- official static SessionTime-to-UTC reconstruction and whole-source fallback;
- final-classification cursor boundaries;
- Qualifying cursor truth and cross-session behavior;
- Pirelli runtime, backfill, evidence tiers, and published strategy;
- replay deletion and durable-context preservation;
- Race intelligence and frontend semantic/render contracts.

See the current `tests/` and `web/tests/` trees rather than older milestone-specific test lists.

## Explicitly deferred

- authentication and the persistent control plane;
- Sync Groups and device pairing;
- Net Pit Loss and stationary pit-box duration without a defensible source;
- deterministic archived-session backtesting;
- protected/authenticated telemetry by default;
- precise live X/Y and hardware clients;
- broad visual redesign after the M3.5 factual baseline.
- replay download/preparation readiness, control activation, slider readiness, initialization flashes, and bootstrap performance.
