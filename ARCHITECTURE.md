# Architecture

Slipstream is a historical replay application with an experimental raw live recorder. Historical replay is integrated end to end; public live messages are recorded for research but do not yet feed the application state.

## System shape

```text
Historical timing path

OpenF1 HTTP responses
        |
        v
versioned raw recording ---> OpenF1 adapter ---> normalized events
                                                    |
                                                    v
                                               RaceState reducer
                                                    |
                                  +-----------------+-----------------+
                                  |                 |                 |
                           replay controller    terminal          API v1
                                                                      |
                                                               browser pit wall

Metadata path

OpenF1 sessions/meetings ---> lightweight catalog ---> session library
                                      |                      |
                               dates + circuits       local recordings overlay

Experimental live path

public F1 SignalR ---> versioned raw JSONL recording ---> future live normalizer
```

The live recorder is deliberately disconnected from `RaceState` until its payloads have been captured and validated during a real session. A session can be schedule-active and marked `LIVE` without a live timing adapter being connected.

## Core invariants

1. `RaceState` is the only canonical presentation state.
2. Provider payloads are translated by adapters before reaching state or transports.
3. State reduction is deterministic and independent of HTTP, WebSocket, and UI concerns.
4. Each replay viewer owns an independent cursor and clock.
5. One instance owns no more than one upstream live connection.
6. Capabilities describe available data; consumers do not branch on provider names.
7. Public and authenticated capabilities remain separate.
8. Recordings are inputs and operational evidence, not the public API contract.

## Components

| Component | Responsibility |
| --- | --- |
| `adapters/openf1.py` | Acquire historical endpoint data and translate supported recordings into normalized events |
| `catalog.py` | Cache recent session metadata and circuit geometry without timing data |
| `library.py` | Merge catalog entries with local recordings and lazily load the selected session |
| `events.py` | Define normalized event envelopes and timestamp parsing |
| `state.py` | Apply current factual events to immutable, lightweight `RaceState` snapshots |
| `evidence.py` | Reconstruct queryable source-neutral session/lap evidence by replay time or cursor |
| `replay.py` | Load supported recordings and reconstruct state deterministically |
| `playback.py` | Own replay cursor, source clock, seek, delay, pause, and play behavior |
| `api.py` | Expose API v1, per-client WebSocket playback, downloads, and compiled browser files |
| `live.py` | Record unauthenticated public SignalR messages without normalizing them |
| `terminal.py` | Render canonical state for command-line inspection |
| `web/` | Typed API/WebSocket clients, session context, shared factual panels, and Race/Qualifying/Practice views; never read a provider directly |

## Canonical state

`RaceState` is an immutable snapshot with schema version 1. Its main children are:

- `session`: identity, official time window, lap, total race laps, local time, status, and whole-track state
- `circuit`: exact ordered outline, display rotation, provenance, and availability
- `weather`: observation time, temperatures, humidity, pressure, rain detection, and wind
- `drivers`: identity, classification, timing, tyre/stint state, sectors, estimated progress, optional source X/Y, field availability, and current factual values
- `race_control`: ordered messages with track, sector, driver, and lap scope where provided

Every event produces a new snapshot. Seeking resets the reducer and reapplies all events through the inclusive target time or cursor. This is intentionally simple and deterministic; checkpointing can be added later without changing the state contract.

Full lap history is not part of `RaceState`. `SessionEvidence` reconstructs append-only normalized lap observations from the same deterministic event stream and supports queries by replay timestamp or event cursor. Observations retain duration, sectors, compound/stint context, tyre age, pit-in/out evidence, and quality reasons without being retransmitted in every state snapshot. Strategy and representative-pace calculations will consume this sidecar in tested backend logic; they do not belong in `RaceState` or a parallel frontend truth model.

## Browser architecture

The Vite application has a thin entry page. `web/api` owns versioned HTTP and WebSocket transport, `web/domain` owns canonical TypeScript contracts and session classification, and `web/hooks` coordinates one selected replay resource. Shared timing/analysis components are composed by separate Race, Qualifying, and Practice views.

The Race view alone owns the draggable Timing-to-Analysis split and its Balanced, Timing Focus, and Strategy Focus presets. Qualifying and Practice have authored layouts rather than inheriting that divider. Missing capabilities render `UNKNOWN`, `UNSUPPORTED`, or unavailable states; production code never substitutes plausible sample race data.

## Catalog and replay library

The catalog and recordings solve different problems:

- `catalog.json` supplies season/weekend/session discovery, dates, local offsets, and circuit outlines.
- Recording JSON supplies timing and replay events for one session.

`ReplayLibrary` overlays local recordings on catalog descriptors. It normalizes only the selected recording and caches only that selected resource. A catalog-only session produces a small placeholder state so the UI can show its date, circuit, download status, and live schedule window without inventing timing.

The default session is the currently active scheduled session when one exists. Otherwise it is the newest locally available recording, falling back to the newest catalog entry.

## Track and car position

Circuit shape and car position are separate capabilities:

- `circuit_shape` means an exact ordered historical outline is available.
- `positions` means timing supports an approximate lap-progress value.
- `location_xy` means source X/Y samples are present for drivers.

A normal historical recording maps timing-derived progress onto the circuit outline. A recording fetched with `--include-location` can instead display source X/Y samples. These coordinates are still source observations and should not be described as precise lateral racing-line telemetry.

If neither timing progress nor X/Y is available, the circuit remains visible and the UI explains why cars cannot be placed.

## Replay transports

REST endpoints expose catalog metadata, final normalized state, capabilities, replay bounds, and historical download operations. The WebSocket owns interactive replay:

```text
browser connection
    |
    +-- private ReplayController
    +-- private cursor/playhead
    +-- private speed and delay
    `-- shared immutable recording/event history
```

One viewer seeking or applying a broadcast delay does not move another viewer. Playback advances in source-clock batches rather than sending a snapshot for every upstream event.

Routes and message compatibility are defined in [docs/protocol.md](docs/protocol.md).

## Live-source boundary

`PublicLiveRecorder` currently negotiates one unauthenticated SignalR connection and stores selected public topics in a versioned JSONL file. It does not:

- update `RaceState`
- feed the browser or API
- provide a resilient reconnecting service
- request protected GPS, car-data, or team-radio topics
- prove that every advertised public topic is available throughout a race weekend

The next live milestone starts with a real-session capture. Only after the raw messages are validated will the project add live normalization and extract a shared source abstraction from the historical and live implementations.

## Deployment

The production image has a Node build stage and a Python runtime stage. Vite produces static browser assets; the runtime contains Python, the Slipstream package, and those assets. FastAPI serves:

```text
/                 static browser application
/api/v1/*         REST API
/api/v1/stream    WebSocket
```

There is one runtime process, one container, and one internal port (`3444`). A reverse proxy is an external deployment choice. `api-only` mode omits browser routes but keeps REST and WebSocket behavior.

## Adding another source

A new source should:

1. preserve its raw input in a versioned recording format when practical;
2. translate provider fields into normalized events inside its adapter;
3. declare capabilities explicitly;
4. keep authentication and secrets outside recordings and source control;
5. reuse `RaceState`, replay, API, and presentation layers unchanged;
6. include focused reducer/adapter tests and capability fallback tests.

Do not introduce a generic source interface merely for symmetry. Extract it when a second validated implementation demonstrates the common operations.
