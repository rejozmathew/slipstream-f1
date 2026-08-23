# Protocol and data conventions

This document defines the compatibility boundary between source adapters, canonical state, and downstream clients. It describes the current version 1 behavior; it is not a promise that every possible field is already populated by every source.

## Versioning

- Canonical state contains `schema_version: 1`.
- HTTP and WebSocket routes use `/api/v1/`.
- Transport envelopes contain `v: 1`.
- Raw recording formats include their major version in the `format` value.

Adding optional fields is compatible within version 1. Removing a field, changing its meaning, or changing a required type requires a new major version. Clients must ignore unknown object fields and unknown event types.

## Canonical state

`RaceState` is the normalized contract used by the terminal, REST API, WebSocket, and browser. Provider response shapes must not appear in it.

`session.session_kind` distinguishes `practice_1`, `practice_2`, `practice_3`, `qualifying`, `sprint_qualifying`, `sprint`, `race`, and `unknown`. `session.layout_family` maps those discovered kinds to the shared `practice`, `qualifying`, `race`, or `unsupported` presentation family. Catalog entries expose the same values as `sessionKind` and `layoutFamily`.

Qualifying session facts use `session.qualifying_phase` (`Q1`, `Q2`, `Q3`, `SQ1`, `SQ2`, `SQ3`, or `UNKNOWN`), `session.session_clock`, and `session.session_clock_running`. Driver facts add `activity` (`ON_TRACK`, `IN_PIT`, `NO_RECENT_PROGRESS`, or `UNKNOWN`), `progress_observed_at_lap`, `qualifying_eliminated`, and `tyre_usage` (`NEW`, `USED`, or `UNKNOWN`). Activity is not lifecycle: `NO_RECENT_PROGRESS` and `STOPPED` are non-terminal, while retirement/DNF requires explicit terminal evidence.

```text
RaceState
â”œâ”€â”€ schema_version
â”œâ”€â”€ updated_at
â”œâ”€â”€ session
â”œâ”€â”€ circuit
â”œâ”€â”€ weather
â”œâ”€â”€ drivers[number]
â””â”€â”€ race_control[]
```

Normalized events preserve `source`, `occurred_at`, and optional `received_at`. Event ordering is determined by parsed timestamps, not JSON array order or textual timestamp formatting. Replay seeks and CLI `--at` snapshots include events occurring exactly at the target timestamp.

Source/event timestamps use ISO 8601. Canonical event times are UTC; `session.local_time` intentionally carries the circuit offset derived from `gmt_offset`.

## State envelopes

REST state responses and WebSocket snapshots use:

```json
{
  "v": 1,
  "seq": 123,
  "type": "state.snapshot",
  "sessionTime": "2023-09-17T13:30:00+00:00",
  "sourceTime": "2023-09-17T13:30:00+00:00",
  "playback": { "playing": false },
  "data": { "schema_version": 1 },
  "analytics": { "type": "analytics.snapshot", "schemaVersion": 1 }
}
```

`seq` is the number of normalized events applied to the snapshot. `sessionTime` is the viewerâ€™s replay playhead. `sourceTime` currently follows the same clock and is reserved for distinguishing source receipt time later.

`analytics` is optional and additive. Replay and live WebSocket snapshots include it when the analytics service is available. It is always reconstructed at the same inclusive `seq` and `sessionTime` as `data`; it is not part of canonical `RaceState`.

Live envelopes additionally carry `mode: "live"` and a `live` object containing transport `status`, authoritative product `phase`, `connected`, `stale`, `sequence`, `lastReceivedAt`, `error`, `replayReady`, `finalRecording`, and the connection-owned `delaySeconds`. Product phases are `PRE_EVENT`, `CONNECTING`, `LIVE`, `STALE`, `RECONNECTING`, `FINALIZING`, `COMPLETE`, `REPLAY_READY`, and `UNAVAILABLE`.

## HTTP API

| Route | Purpose |
| --- | --- |
| `GET /api/v1/catalog` | List known seasons, weekends, and sessions; identify the default session and whether downloads are writable |
| `GET /api/v1/state` | Return the final normalized state for a selected session resource |
| `GET /api/v1/capabilities` | Describe the selected source/session data capabilities |
| `GET /api/v1/replay` | Return replay and live availability separately, event/time bounds, live source state, and position mode |
| `GET /api/v1/driver-history` | Return one driver's normalized lap evidence on demand, outside high-frequency state snapshots |
| `GET /api/v1/analytics` | Return the versioned analytics sidecar at an optional inclusive `at` or `seq` cutoff and start non-blocking Weekend Context preparation |
| `POST /api/v1/download` | Download one finished catalog session into the recording directory |
| `WS /api/v1/stream` | Create an independent replay controller or delayed-live cursor for one client |

Pass `session_key` as a query parameter where a session can be selected. Omitting it uses the library default.

`POST /api/v1/download?session_key=...` accepts only a known catalog session whose scheduled end is in the past. Downloads are serialized per application instance. After a successful write, the library is refreshed and the session becomes available without restarting the process.

`GET /api/v1/driver-history?session_key=...&driver_number=...` returns source-neutral completed-lap observations for Driver Focus and future analytics. It is an on-demand viewer endpoint rather than part of `RaceState`; consumers filter the returned evidence against the current replay time or cursor. An unavailable recording returns an empty evidence list with `available: false`.

The driver-history response also contains viewer-oriented `pitEvents`. A pit event keeps the observed pit lap, previous/new compound, stationary `stopDuration`, and complete `pitLaneDuration` independently. Missing values remain `null`; lane duration is never relabelled as stationary stop time.

## Weekend context and analytics

`GET /api/v1/analytics` returns `analytics.snapshot` schema version 1. Its top-level fields include `modelVersion`, `sessionKind`, `layoutFamily`, `sequence`, `asOf`, stage, context status/provenance, explicit race-wide `raceStrategy`, per-driver models, `raceRead`, projection gates, separate starting/current tyre populations, one dry-rule landscape, pit-loss capability state, completed-lap Battle histories, and the shared stabilized Battle recommendation. `raceStrategy.scope` is `RACE`; `drivers[number].strategy.scope` is `DRIVER` and includes `driverNumber`. Race/TV Strategy must not substitute the first driver model. `context.meetingKey` declares the only meeting whose evidence may contribute to the Weekend model. Metric values use:

- `OBSERVED`: a normalized source fact;
- `DERIVED`: a deterministic calculation from observed facts;
- `ESTIMATE`: a modelled outlook whose assumptions are stated;
- `UNKNOWN`: insufficient evidence; no fallback value is invented.

The wire contract is defined here; the calculation meanings, thresholds, formulae, confidence rules, and limitations are specified in [analytics.md](analytics.md).

Weekend stages are `BASELINE_AVAILABLE`, `WEEKEND_MODEL_READY`, and `LIVE_OUTLOOK`. Context status is `missing`, `preparing`, `ready`, or `unavailable`; playback never waits for it.

Context packs use `slipstream.weekend-context.v1` and live under `/data/.slipstream/weekend-context/<meeting>/<target-session>.json`. They contain `generated_at`, the selected session's start as `evidence_cutoff`, `model_version`, `meeting_key`, discovered same-meeting session inventory, compact earlier-session evidence, capability-gated tyre inventory, and a separate optional external-intelligence envelope. Pack loading and analytics consumption reject session evidence whose `meeting_key` differs from the selected meeting. Sessions after the cutoff, previous race weekends, prior editions at the circuit, and the selected session's later evidence are excluded. External Intelligence is disabled by default and is never silently folded into the Slipstream model.

The allowed sequence is discovered from the catalog: a normal meeting can contribute FP1 → FP2 → FP3 → Qualifying → Grand Prix evidence, while an Alternative Format meeting can contribute FP1 → Sprint Qualifying → Sprint → Qualifying → Grand Prix evidence. The arrows describe possible evidence progression, not a hardcoded session inventory.

### Qualifying intelligence

Every `AnalyticsSnapshot` contains `qualifying`. Outside the Qualifying layout it is `NOT_APPLICABLE`; otherwise it is server-authored and contains `phase`, `phaseEvidence`, `sessionClock`, `sessionClockRunning`, current `benchmark`, `cutLine`, per-driver intelligence, and `modelVersion`.

Per-driver fields are `activity`, `benchmarkDelta`, `cutState`, `attempts`, and `tyreUsage`. Cut state is `ADVANCING`, `BELOW_CUT`, `ELIMINATED`, or `UNKNOWN`. A current advancement boundary exists only for an explicit season/field-size/segment rule profile; `ELIMINATED` additionally requires explicit source evidence. An attempt is a completed-lap observation available by the inclusive cursor and contains only phase, lap/time/sectors, compound, age/usage, factual validity, and occurrence time. Missing phase, clock, rule profile, validity, or usage remains `UNKNOWN`/`null`.

## Catalog semantics

Catalog session fields have specific meanings:

- `available`: a local timing recording exists.
- `downloadable`: the scheduled session end is in the past.
- `isLive`: the current clock is inside the scheduled start/end window.
- `circuitShapeAvailable`: cached circuit geometry exists; this says nothing about car position.
- `positionMode`: `precise_xy`, `timing_estimate`, or `unavailable`.
- `gmtOffset`: official circuit offset used for pre-event local-start presentation.
- `livePhase`: authoritative product lifecycle for the selected public-live target.
- `replayReady`: the finalized canonical recording is visible in ReplayLibrary.
- `downloadsEnabled`: the server is using a writable recording directory.

`isLive` is schedule status, not proof that a live source is connected. `replayAvailable`, `liveAvailable`, `liveConnected`, `liveStale`, `liveStatus`, `livePhase`, and `replayReady` are separate. The catalog also exposes `liveSessionKey`; an active scheduled session is selected in live mode by default, while a viewer already watching replay is not forcibly switched.

For an active scheduled session, replay `endTime` is capped at the earlier of the scheduled end and the current time. Clients must not create future seek targets.

For historical races, `session.total_laps` is derived from recorded race-result metadata and is available from the session-start snapshot. Practice and qualifying sessions leave it `null` because they have no meaningful scheduled lap denominator.

## WebSocket commands

Each WebSocket connection receives an initial snapshot and owns its own `ReplayController`.

| Command | Fields | Behavior |
| --- | --- | --- |
| `snapshot` | none | Return the current snapshot without moving the cursor |
| `play` | `speed` | Play at a speed greater than 0 and at most 120 |
| `pause` | none | Stop automatic clock advancement |
| `seek` | `at` or `seq` | Reconstruct through an inclusive timestamp or event-count cursor |
| `seek_relative` | `seconds` | Move by signed source-clock seconds, clamped to replay bounds |
| `step` | none | Apply one normalized event |
| `delay` | `seconds` | Seek to a non-negative number of seconds behind the newest event |
| `reset` | none | Reconstruct state at the official session-start boundary |

Commands that move the cursor pause current playback first. The browser exposes delay as TV synchronization, and the protocol operation is defined for any replay. A delay of zero means the newest event.

Invalid input produces a versioned error frame:

```json
{ "v": 1, "type": "error", "error": "description" }
```

Playback advances in clock batches and emits snapshots at the transport cadence rather than once per source event.

With `mode=live`, only `snapshot`, `delay`, and `reset`/`live` are accepted. Delay is clamped to 0–300 seconds and selects an inclusive cursor from the shared live event history. `reset`/`live` returns that viewer to delay zero. Live has no pause, backward seek, step, or speed command, and one viewer's delay never mutates another viewer.

## Capability vocabulary

Session/source descriptors use these boolean capabilities:

- `historical_replay`
- `live_timing`
- `positions`
- `intervals`
- `location_xy`
- `circuit_shape`
- `race_control`
- `weather`
- `local_time`
- `authenticated`

Consumers select behavior from capabilities and `positionMode`, never from provider names.

Driver and weather fields carry an `availability` map separate from their values. Allowed status values are:

- `available`: the source supplied a usable value;
- `unavailable`: the capability exists but no current value is present;
- `unsupported`: the selected source cannot provide the field;
- `stale`: reserved for live data whose last observation is too old.

`null` alone must not mean all four cases.

### Normalized lap evidence

Full accumulated lap history is deliberately excluded from `RaceState` and therefore from high-frequency REST/WebSocket state snapshots. Completed-lap observations remain source-neutral facts in the normalized event stream. The internal `SessionEvidence` sidecar reconstructs them deterministically and can query the evidence available at an inclusive replay timestamp or event-count cursor.

An observation records lap number and start time, duration and sectors when supplied, compound, stint number, tyre age, `qualifying_phase`, `tyre_usage`, factual `lap_validity`, pit-in/pit-out evidence, and provenance-friendly quality fields. `quality` is `representative`, `contaminated`, or `unknown`. `contamination_reasons` names only observed conditions such as `pit_in`, `pit_out`, `neutralized_track`, `neutralization_end_unknown`, or `missing_duration`; it is not a strategy verdict.

Pit observations may additionally carry `pit_occurred_at`, `previous_compound`, `new_compound`, `stop_duration`, and `pit_lane_duration`. These remain optional and source-capability dependent.

Whole-track contamination is derived from timestamped intervals opened only by genuine track-scoped yellow/red or explicit SC/VSC deployment evidence and closed by a whole-track clear/green transition. Sector- and driver-scoped flags do not neutralize the whole lap. An unclosed interval remains unknown where overlap cannot be proven. Future analytics may consume this evidence, but calculated pace or strategy does not become part of canonical `RaceState`.

## Circuit, position, and conditions

`RaceState.circuit.path` is an ordered array of `[x, y]` points. `rotation` is the source display rotation and `source` preserves geometry provenance.

`circuit_shape` means the outline is available. `location_xy` means driver source coordinates may be present in `x`, `y`, and optional `z`. Placement prefers a driver's X/Y when present and otherwise retains that driver's timing-derived `track_position`; a sparse provider packet does not erase either value. Static catalog geometry is seeded independently and survives later live session updates. When neither per-car mode exists, the circuit remains visible with `CAR POSITION UNSUPPORTED`.

Weather carries observation time, air and track temperature in degrees Celsius, humidity percentage, pressure in hPa, rain detection, wind speed in m/s, and wind direction in degrees. Rain detection is a sensor observation; it must not be presented as a guaranteed wet/dry surface classification.

Race-control messages preserve `scope`, `driver_number`, `sector`, and `lap` when supplied. Only whole-track green, yellow, double-yellow, red, chequered, safety-car, and virtual-safety-car messages may update `session.track_status`. Driver- and sector-scoped flags remain messages only.

## Recording formats

| Format | Purpose |
| --- | --- |
| `slipstream.openf1-recording.v1` | Historical OpenF1 session capture with unmodified endpoint arrays and declared source capabilities |
| `slipstream.openf1-catalog.v1` | Lightweight session/meeting metadata and normalized circuit geometry; no timing events |
| `slipstream.f1-signalr-recording.v1` | Optional raw public live SignalR JSONL evidence; live viewers still consume canonical state |
| normalized event-list JSON | Canonical live product recording; ordinary ReplayLibrary-supported `NormalizedEvent` mappings finalized atomically |
| `slipstream.weekend-context.v1` | Compact operational meeting context for one target-session cutoff; not a replay asset |

Historical recording envelopes include capture time, session key, source capabilities, and endpoint arrays. Raw live files begin with a header, followed by rows containing `received_at`, `stream`, optional `source_timestamp`, raw `payload`, and whether the row came from the initial subscription result.

Canonical live recording first appends JSONL mappings to `live-<session>.in-progress.jsonl`, which is never catalog-visible. Explicit completion starts a deterministic drain that is extended only by newly emitted canonical factual events; Heartbeat and other no-op rows do not extend it. Finalization writes the ordinary normalized event-list JSON to a temporary sibling and atomically replaces `live-<session>.json`. Valid same-session in-progress JSONL is recovered and deduplicated after restart; malformed or incompatible recovery fails explicitly. ReplayLibrary refresh then publishes `REPLAY_READY` and releases the completed upstream. A disconnect alone never finalizes either artifact.

Recordings are private operational inputs. Their formats may need migrations independently of API v1, and they must never contain committed credentials or authenticated captures.

### Race-intelligence publication rules

`raceRead` is a deterministic server-side interpretation of factual current-session evidence; clients must not recalculate it. `startingTyreDistribution` uses first-stint evidence and `currentTyreDistribution` uses active runners at the cursor. Each includes an explicit denominator.

`drivers[number].strategy.projectionGate` and top-level `projectionGate` contain hard-validity, plausibility, stability, and `publishAllowed`. Future strategy values are absent/`UNKNOWN` unless all gates pass. `finishAssessment` is the positive evidence record behind `TO_FINISH`; the absence of a pit window never implies a run to the flag. `paceTrend` is raw clean-stint pace slope, not isolated tyre degradation; `degradation` remains a compatibility alias.

`battle.histories` contains only completed-lap interval samples. `battle.stabilizedRecommended` and `heldRecommendation` are functions of source history at the cursor and are request-order independent. A pair must remain eligible within the meaningful-gap threshold and have source history spanning the configured hold time.

`sportingRules.dryTyreRequirement.perDriverState` is a map keyed by driver number, not a scalar. `historical` and `officialPreRace` are separately attributed, target-session-owned optional artifacts; absence is explicit and neither is silently blended into `WeekendContext`. `backtest.status` is `NOT_IMPLEMENTED` and `backtest.metrics` is `null` until a deterministic archived-session evaluator exists.

`netPitLoss.status = NOT_IMPLEMENTED` blocks free-stop, projected-rejoin, and quantified-undercut claims. Raw pit-lane duration does not satisfy that dependency.


## Published strategy sidecar

Every analytics snapshot contains `publishedStrategy`, even when no admissible Pirelli evidence exists. The server authors it; clients must not infer a preferred option.

- `status`: `PRESENT` or `ABSENT`.
- `lifecycle`: current strategy lifecycle.
- `baseline`: source metadata, `evidenceCutoff`, ordered published options, physical compound nomination, optional native tyre bank, context facts, and absence reason.
- `fieldFacts`: at most three cursor-valid race-context statements.
- `drivers`: observed compound path, relation, every compatible option ID, published window states, and concise facts.
- `modelVersion`: `pirelli-published-strategy-v1`.

Driver relations are `MATCHING_ONE`, `MATCHING_MULTIPLE`, `DIVERGED`, `NOT_COMPARABLE`, `TERMINAL`, or `UNKNOWN`. Every compatible option/window is represented. Window states are `BEFORE`, `ACTIVE`, `PASSED`, `COMPLETED`, or `UNKNOWN`; an observed compound transition deterministically marks the corresponding window `COMPLETED`. Final state keeps the baseline but emits no live/future windows. `ANY_ORDER` remains published context but is not prefix-compared or rendered as a directional transition.

Pirelli raw/normalized archives live below `/data/.slipstream/pirelli/<meeting_key>/` and are operational evidence, not API payloads. See [Published Pirelli strategy](pirelli-strategy.md) for admission and derivation semantics.
