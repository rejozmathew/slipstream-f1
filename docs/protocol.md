# Protocol conventions

`RaceState` is the normalized contract for every output. Its serialized form begins at `schema_version: 1`. Timestamps are ISO 8601 UTC strings. Normalized events preserve `source`, `occurred_at`, and optional `received_at`; upstream payload shapes never leak into state.

HTTP routes use `/api/v1/`. State envelopes use `{ "v": 1, "seq": 123, "type": "state.snapshot", "sessionTime": "...", "sourceTime": "...", "playback": { "playing": false }, "data": ... }`. Additive fields are compatible within a major version; changed meanings/removals require a new major version. Clients ignore unknown fields and event types.

Routes are `GET /api/v1/catalog`, `GET /api/v1/state`, `GET /api/v1/capabilities`, `GET /api/v1/replay`, `POST /api/v1/download`, and WebSocket `/api/v1/stream`. State, capability, replay, stream, and download routes accept a `session_key` as applicable. Catalog returns season/weekend/session metadata and a default key; `available` means a timing recording exists locally, `downloadable` means the session has ended, and `circuitShapeAvailable` only describes preloaded geometry. `downloadsEnabled` indicates that the server owns a writable recording directory. `isLive` is evaluated against the current clock. An active session is the default even when its live timing adapter is not connected.

`POST /api/v1/download?session_key=...` accepts only sessions already present in the catalog and whose scheduled end is in the past. Acquisition requests are serialized per instance. A successful response includes the refreshed catalog, and the new recording is immediately available without a process restart.

Replay metadata exposes `available`, `isLive`, and `positionMode`. Position modes are `precise_xy`, `timing_estimate`, and `unavailable`. For an active live session, `endTime` is the earlier of the scheduled end and the current time; clients must not construct a seek target later than that bound.

WebSocket clients may send `snapshot`, `play`, `pause`, `seek`, `seek_relative`, `step`, `delay`, or `reset`; each connection owns its own replay cursor and clock. `play` accepts a speed greater than zero and at most 120. `seek` accepts either an inclusive ISO 8601 `at` timestamp or an event-count `seq` cursor. `seek_relative` moves by signed source-clock seconds. `delay` accepts any non-negative numeric `seconds` value (for example `21`) and seeks relative to the newest event visible to that connection. The browser exposes this as a live-only per-viewer TV-sync control; zero means the newest live point, not “leave the cursor unchanged.” Playback snapshots are batched rather than emitted once per upstream event.

For historical races, `session.total_laps` is static replay metadata derived from the recorded race result and is available from the session-start snapshot. Practice and qualifying sessions leave it `null` because they do not have a meaningful scheduled lap denominator.

With multiple adapters, descriptors expose boolean capabilities: `historical_replay`, `live_timing`, `positions`, `intervals`, `location_xy`, `circuit_shape`, `race_control`, `weather`, `local_time`, and `authenticated`.

Raw OpenF1 captures use `format: slipstream.openf1-recording.v1`. The envelope records capture time, session key, source capabilities, and unmodified endpoint arrays. Recordings are input artifacts, not the public API contract.

The lightweight season cache uses `format: slipstream.openf1-catalog.v1`. It contains session and meeting metadata plus normalized linked circuit geometry, but no timing events. It may be refreshed independently from recordings and is not a substitute for replay or live-timing capability.

Raw public-live captures use newline-delimited JSON beginning with a `slipstream.f1-signalr-recording.v1` header. Each following row records `received_at`, `stream`, optional provider `source_timestamp`, raw `payload`, and whether it came from the initial subscription result. These rows are evidence for the future live normalizer; they are not normalized events or public API messages.

Replay order is determined by parsed UTC event time, not JSON array order or textual timestamp formatting. CLI snapshots are inclusive of the `--at` timestamp.

Driver metrics carry an `availability` map separate from their values. Status values are `available`, `unavailable`, `unsupported`, and (for future live ingestion) `stale`. `null` alone must not be used to mean both “the source cannot provide this” and “the source can provide this but has no current value.”

`RaceState.weather` carries the observation timestamp, air and track temperature in °C, humidity in percent, pressure in hPa, rainfall detection, wind speed in m/s, wind direction in degrees, and per-field availability. Rainfall means precipitation detected at the sensor; it must not be presented as a guaranteed wet/dry surface classification. `session.local_time` is derived from each event timestamp and the source-provided `gmt_offset`.

`RaceState.circuit.path` is an ordered array of canonical `[x, y]` coordinate pairs for the historical circuit outline. `circuit.rotation` is the source-provided display rotation in degrees, while `circuit.source` preserves the linked geometry URL for provenance. `circuit_shape` means an exact recorded outline is available; it does not imply precise driver location. When `location_xy` is available, drivers carry source coordinates in `x`, `y`, and optional `z`; otherwise `track_position` remains a timing-derived lap fraction mapped onto the outline.

Race-control messages preserve `scope`, `driver_number`, `sector`, and `lap` when supplied. Driver- and sector-scoped flags never update the session-wide `track_status` field.
