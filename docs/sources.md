# Source and license notes

These references were inspected directly to establish protocol facts, current source boundaries, and license constraints. They informed the design; their implementations, tests, and fixtures were not copied.

## Sources used by the application

### OpenF1 historical API

Checked at repository commit `b3b5061` (CC BY-NC-SA 4.0). Slipstream uses the hosted historical API for session metadata and timing acquisition. Provider responses are preserved in `slipstream.openf1-recording.v1` files and translated independently by the OpenF1 adapter.

OpenF1’s hosted real-time tier required authentication/payment when checked, so its live ingestor was not reused. Users are responsible for complying with the terms that apply to downloaded data; the Slipstream source code remains MIT-licensed.

### Linked circuit geometry

OpenF1 meeting records can link to circuit information served by the MultiViewer circuit API. Singapore 2023 was checked directly on 2026-08-11 and returned an ordered X/Y outline plus year and rotation. Slipstream preserves the source URL for provenance and normalizes only the fields needed by `RaceState.circuit`.

Circuit geometry is static track shape. It must not be represented as driver GPS or proof of a precise racing line.

### Pirelli official newsroom

Slipstream uses the public Pirelli Formula 1 RSS/newsroom as an official pre-race strategy source. One sparse server-owned coordinator archives source bytes and metadata, then runs deterministic HTML/prose/structured extraction. Native machine-readable PDF tyre-bank text is optional through `pypdf`; image-only assets are not processed. OCR, PaddleOCR, VLM/LLM extraction, and a normal-product manual transcription workflow are deliberately excluded.

Meeting, Race/Sprint target, and exact evidence cutoff are enforced before publication. Browser code never requests Pirelli or its asset hosts directly. Published strategy is presented as Pirelli's baseline, not team intent or a guaranteed result.

### Public Formula 1 SignalR endpoint

Slipstream independently implements the SignalR Core framing used by its public recorder and live adapter. On 2026-08-22 the public endpoint accepted POST negotiation and a real initial subscription without credentials; an OPTIONS request returned 405, so the server-owned client does not require a browser-style preflight. The observed session exposed the public topic subset documented in `src/slipstream/live.py`.

The recorder/live adapter requests only the topics listed in `src/slipstream/live.py`. Timestamped `SessionData.StatusSeries` entries preserve observed session-running/suspension and marshal-status history at each provider `Utc`; `SessionData` and `ExtrapolatedClock` also provide factual Qualifying phase and clock evidence. Current `SessionStatus` outranks its stale auxiliary `Started` marker. `TrackStatus` supplies marshal facts or SC/VSC control facts, while scoped race-control messages remain separately structured. `TimingAppData` may indicate recent driver activity and tyre usage, but silence is not retirement evidence.

Protected GPS, high-frequency car data, team radio, and similar enhanced topics are intentionally excluded. The observed public slice did not provide per-car X/Y (including a usable `Position.z` progression channel), so live map placement falls back to retained timing-derived lap progress when available and otherwise reports position as unavailable. Static circuit geometry remains separately catalogued and is never presented as car-location evidence.

The optional raw SignalR capture is a provider diagnostic artifact. Product replay uses the normalized live recording written in the same source-neutral event vocabulary used by historical replay. That recording remains in progress while live, is finalized atomically after the completion drain, and is then exposed through the replay library.

## References used for verification only

- **FastF1**, checked at `c4156d6` (MIT): confirmed current SignalR Core usage and that unauthenticated access may be partial.
- **f1_sensor**, checked at `7873804` (MIT): independently confirmed a public/authenticated topic split in 2026.
- **br-g/fastf1-livetiming**, checked at `5c3676e`: no repository license file was present. It was inspected only for protocol comparison.
- **slowlydev/f1-dash**, checked at `d21607a` (AGPL-3.0): no source code, fixtures, styling, or implementation structure is used in Slipstream.

## Project boundary

Do not copy code or fixtures from a repository unless its license is compatible and the reuse is deliberate, attributed, and documented. AGPL material is out of scope for this MIT project. When a source is used only to validate a protocol fact, implement the behavior independently and test it against Slipstream’s own captures.
