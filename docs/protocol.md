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
  "data": { "schema_version": 1 }
}
```

`seq` is the number of normalized events applied to the snapshot. `sessionTime` is the viewerâ€™s replay playhead. `sourceTime` currently follows the same clock and is reserved for distinguishing source receipt time later.

## HTTP API

| Route | Purpose |
| --- | --- |
| `GET /api/v1/catalog` | List known seasons, weekends, and sessions; identify the default session and whether downloads are writable |
| `GET /api/v1/state` | Return the final normalized state for a selected session resource |
| `GET /api/v1/capabilities` | Describe the selected source/session data capabilities |
| `GET /api/v1/replay` | Return event count, time bounds, availability, live schedule status, and position mode |
| `GET /api/v1/driver-history` | Return one driver's normalized lap evidence on demand, outside high-frequency state snapshots |
| `POST /api/v1/download` | Download one finished catalog session into the recording directory |
| `WS /api/v1/stream` | Create an independent interactive replay controller for one client |

Pass `session_key` as a query parameter where a session can be selected. Omitting it uses the library default.

`POST /api/v1/download?session_key=...` accepts only a known catalog session whose scheduled end is in the past. Downloads are serialized per application instance. After a successful write, the library is refreshed and the session becomes available without restarting the process.

`GET /api/v1/driver-history?session_key=...&driver_number=...` returns source-neutral completed-lap observations for Driver Focus and future analytics. It is an on-demand viewer endpoint rather than part of `RaceState`; consumers filter the returned evidence against the current replay time or cursor. An unavailable recording returns an empty evidence list with `available: false`.

## Catalog semantics

Catalog session fields have specific meanings:

- `available`: a local timing recording exists.
- `downloadable`: the scheduled session end is in the past.
- `isLive`: the current clock is inside the scheduled start/end window.
- `circuitShapeAvailable`: cached circuit geometry exists; this says nothing about car position.
- `positionMode`: `precise_xy`, `timing_estimate`, or `unavailable`.
- `downloadsEnabled`: the server is using a writable recording directory.

`isLive` is schedule status, not proof that a live timing adapter is connected. An active scheduled session is selected by default even when only its catalog placeholder is available.

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

An observation records lap number and start time, duration and sectors when supplied, compound, stint number, tyre age, pit-in/pit-out evidence, and provenance-friendly quality fields. `quality` is `representative`, `contaminated`, or `unknown`. `contamination_reasons` names only observed conditions such as `pit_in`, `pit_out`, `neutralized_track`, `neutralization_end_unknown`, or `missing_duration`; it is not a strategy verdict.

Whole-track contamination is derived from timestamped intervals opened only by genuine track-scoped yellow/red or explicit SC/VSC deployment evidence and closed by a whole-track clear/green transition. Sector- and driver-scoped flags do not neutralize the whole lap. An unclosed interval remains unknown where overlap cannot be proven. Future analytics may consume this evidence, but calculated pace or strategy does not become part of canonical `RaceState`.

## Circuit, position, and conditions

`RaceState.circuit.path` is an ordered array of `[x, y]` points. `rotation` is the source display rotation and `source` preserves geometry provenance.

`circuit_shape` means the outline is available. `location_xy` means driver source coordinates are present in `x`, `y`, and optional `z`. Otherwise `track_position` may contain a timing-derived lap fraction mapped onto the outline.

Weather carries observation time, air and track temperature in degrees Celsius, humidity percentage, pressure in hPa, rain detection, wind speed in m/s, and wind direction in degrees. Rain detection is a sensor observation; it must not be presented as a guaranteed wet/dry surface classification.

Race-control messages preserve `scope`, `driver_number`, `sector`, and `lap` when supplied. Only whole-track green, yellow, double-yellow, red, chequered, safety-car, and virtual-safety-car messages may update `session.track_status`. Driver- and sector-scoped flags remain messages only.

## Recording formats

| Format | Purpose |
| --- | --- |
| `slipstream.openf1-recording.v1` | Historical OpenF1 session capture with unmodified endpoint arrays and declared source capabilities |
| `slipstream.openf1-catalog.v1` | Lightweight session/meeting metadata and normalized circuit geometry; no timing events |
| `slipstream.f1-signalr-recording.v1` | Raw public live SignalR JSONL evidence; not normalized state |

Historical recording envelopes include capture time, session key, source capabilities, and endpoint arrays. Raw live files begin with a header, followed by rows containing `received_at`, `stream`, optional `source_timestamp`, raw `payload`, and whether the row came from the initial subscription result.

Recordings are private operational inputs. Their formats may need migrations independently of API v1, and they must never contain committed credentials or authenticated captures.
