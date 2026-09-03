# Source and license notes

These references were inspected directly to establish protocol facts, current source boundaries, and license constraints. They informed the design; their implementations, tests, and fixtures were not copied.

## Sources used by the application

### OpenF1 historical API

Checked at repository commit `b3b5061` (CC BY-NC-SA 4.0). Slipstream uses the hosted historical API for catalog/session metadata, direct `slipstream fetch*` captures, and whole-session timing fallback when official F1 static reconstruction is unusable. Provider responses are preserved in `slipstream.openf1-recording.v1` files and translated independently by the OpenF1 adapter.

OpenF1’s hosted real-time tier required authentication/payment when checked, so its live ingestor was not reused. Users are responsible for complying with the terms that apply to downloaded data; the Slipstream source code remains MIT-licensed.

Historical source capability is intentionally conservative. The Dutch 2026 OpenF1 recording contains `RED FLAG - RACE SUSPENDED` plus later resumption-order/planned-time messages, but no explicit event proving the actual sporting transition back to running. Slipstream therefore preserves the race-control history without inventing a persistent suspended/red interval or using `TRACK CLEAR`, lap/sector activity, or marshal changes as a restart. The same recording establishes Lance Stroll #18 as DNF only in the official session-end result, so historical replay does not fabricate his retirement earlier.

OpenF1 is the whole-session historical fallback. It is used only when a complete official F1 static reconstruction is unavailable; its timing facts are never filled into or blended with an official reconstruction.

### Official Formula 1 static timing archive

Historical download first resolves the session through the official `static/<year>/Index.json` archive and requests only the same low-volume public topics used by Live: session/driver/timing, lap count, control messages, clock, and weather. Timestamp-prefixed `.jsonStream` patches are deep-merged with explicit `false` preserved, then passed through the same F1 `TimingData` normalizer used by SignalR. CarData, Position, TeamRadio, and other large/protected topics remain excluded.

The outer `.jsonStream` prefix is provider SessionTime, not elapsed time from the scheduled session start. `F1HistoricalClient` derives stream zero from provider UTC anchors in `ExtrapolatedClock` and `SessionData`. It requires a 10 ms consensus cluster containing at least 75% of the available candidates and fails reconstruction closed when the timebase is absent or inconsistent.

The product artifact is a canonical normalized event recording with source `f1-static-public`; a small source/capability manifest is retained separately. Whole-session precedence is finalized Slipstream live recording, official F1 static reconstruction, then OpenF1 fallback.

### Linked circuit geometry

OpenF1 meeting records can link to circuit information served by the MultiViewer circuit API. Singapore 2023 was checked directly on 2026-08-11 and returned an ordered X/Y outline plus year and rotation. Slipstream preserves the source URL for provenance and normalizes only the fields needed by `RaceState.circuit`.

Circuit geometry is static track shape. It must not be represented as driver GPS or proof of a precise racing line.

### Pirelli official newsroom

Slipstream uses the public Pirelli Formula 1 RSS/newsroom as an official pre-race strategy source. A bundled normalized seed supplies release-time history, a single-concurrency coordinator quietly self-backfills missing meetings, and a sparse server-owned coordinator handles current/near-weekend acquisition. Both network paths archive source bytes and metadata, then run the same deterministic HTML/prose/structured extraction. Normal startup validates/imports the seed and never scrapes the fixed ten-season horizon. Native machine-readable PDF tyre-bank text is optional through `pypdf`; image-only assets are not processed. OCR, PaddleOCR, VLM/LLM extraction, and a normal-product manual transcription workflow are deliberately excluded.

Meeting, Race/Sprint target, and exact evidence cutoff are enforced before publication. Browser code never requests Pirelli or its asset hosts directly. Published strategy is presented as Pirelli's baseline, not team intent or a guaranteed result.

Strict model evidence requires each artifact version to be proven at or before the cutoff. When strict evidence is absent, a display-only official historical tier may be admitted from approved Pirelli hosts if meeting/session scope is correct and the known publication time is pre-cutoff. It is labelled `PUBLISHED PRE-RACE · ARCHIVED LATER`, sets `modelAdmissible: false`, and cannot silently influence model relations or windows.

### Public Formula 1 SignalR endpoint

Slipstream independently implements the SignalR Core framing used by its public recorder and live adapter. On 2026-08-22 the public endpoint accepted POST negotiation and a real initial subscription without credentials; an OPTIONS request returned 405, so the server-owned client does not require a browser-style preflight. The observed session exposed the public topic subset documented in `src/slipstream/live.py`.

The recorder/live adapter requests only the topics listed in `src/slipstream/live.py`. Timestamped `SessionData.StatusSeries` entries preserve observed session-running/suspension and marshal-status history at each provider `Utc`; `SessionData` and `ExtrapolatedClock` also provide factual Qualifying phase and clock evidence. Current `SessionStatus` outranks its stale auxiliary `Started` marker. `TrackStatus` supplies marshal facts or SC/VSC control facts, while scoped race-control messages remain separately structured. For the Dutch 2026 capture, `SessionStatus=Started` at `2026-08-23T13:33:00.088Z` is the explicit sporting restart and clears the public-Live red latch. `TimingData.Retired` and `TimingData.Stopped` are current provider facts, not final classification. They may be explicitly retracted, and `Stopped` is resumable. Final FINISHED/DNF/DNS/DSQ or authoritative RETIRED is authored only at the factual result cursor. `TimingAppData` may indicate driver activity and tyre usage, but silence is not retirement evidence.

The subscription allow-list contains `DriverList`, `ExtrapolatedClock`, `Heartbeat`, `LapCount`, `RaceControlMessages`, `SessionData`, `SessionInfo`, `SessionStatus`, `TimingAppData`, `TimingData`, `PitLaneTimeCollection`, `TopThree`, `TrackStatus`, and `WeatherData`. Subscription alone does not make a stream canonical truth; the adapter must map it to normalized events.

`PitLaneTimeCollection.Duration` is admitted only as complete `pit_lane_duration` when `0 < duration <= 300 seconds`. It never populates stationary `stop_duration` or Net Pit Loss. Suspicious long suspension-spanning values remain unavailable rather than being clamped.

Protected GPS, high-frequency car data, team radio, and similar enhanced topics are intentionally excluded. The observed public slice did not provide per-car X/Y (including a usable `Position.z` progression channel), and the Live product currently declares `positionMode: unavailable`. The adapter may normalize timing progress where present for evidence/replay parity, but the Live UI does not promote that into a supported car-position capability. Static circuit geometry remains separately catalogued and is never presented as car-location evidence.

The optional raw SignalR capture is a provider diagnostic artifact. Product replay uses the normalized live recording written in the same source-neutral event vocabulary used by historical replay. That recording remains in progress while live, is finalized atomically after the completion drain, and is then exposed through the replay library.

## References used for verification only

- **FastF1**, checked at `c4156d6` (MIT): confirmed current SignalR Core usage and that unauthenticated access may be partial.
- **f1_sensor**, checked at `7873804` (MIT): independently confirmed a public/authenticated topic split in 2026.
- **br-g/fastf1-livetiming**, checked at `5c3676e`: no repository license file was present. It was inspected only for protocol comparison.
- **slowlydev/f1-dash**, checked at `d21607a` (AGPL-3.0): no source code, fixtures, styling, or implementation structure is used in Slipstream.

## Project boundary

Do not copy code or fixtures from a repository unless its license is compatible and the reuse is deliberate, attributed, and documented. AGPL material is out of scope for this MIT project. When a source is used only to validate a protocol fact, implement the behavior independently and test it against Slipstream’s own captures.
