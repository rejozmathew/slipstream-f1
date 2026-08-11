# Source and license notes

These references were inspected directly to establish protocol facts, current source boundaries, and license constraints. They informed the design; their implementations, tests, and fixtures were not copied.

## Sources used by the application

### OpenF1 historical API

Checked at repository commit `b3b5061` (CC BY-NC-SA 4.0). Slipstream uses the hosted historical API for session metadata and timing acquisition. Provider responses are preserved in `slipstream.openf1-recording.v1` files and translated independently by the OpenF1 adapter.

OpenF1’s hosted real-time tier required authentication/payment when checked, so its live ingestor was not reused. Users are responsible for complying with the terms that apply to downloaded data; the Slipstream source code remains MIT-licensed.

### Linked circuit geometry

OpenF1 meeting records can link to circuit information served by the MultiViewer circuit API. Singapore 2023 was checked directly on 2026-08-11 and returned an ordered X/Y outline plus year and rotation. Slipstream preserves the source URL for provenance and normalizes only the fields needed by `RaceState.circuit`.

Circuit geometry is static track shape. It must not be represented as driver GPS or proof of a precise racing line.

### Public Formula 1 SignalR endpoint

Slipstream independently implements the SignalR Core framing needed by its experimental raw public recorder. The endpoint returned HTTP 403 when probed outside a live session from the development environment, so availability and payload coverage still require real-weekend validation.

The recorder requests only the topics listed in `src/slipstream/live.py`. Protected GPS, car data, team radio, and similar enhanced topics are intentionally excluded.

## References used for verification only

- **FastF1**, checked at `c4156d6` (MIT): confirmed current SignalR Core usage and that unauthenticated access may be partial.
- **f1_sensor**, checked at `7873804` (MIT): independently confirmed a public/authenticated topic split in 2026.
- **br-g/fastf1-livetiming**, checked at `5c3676e`: no repository license file was present. It was inspected only for protocol comparison.
- **slowlydev/f1-dash**, checked at `d21607a` (AGPL-3.0): no source code, fixtures, styling, or implementation structure is used in Slipstream.

## Project boundary

Do not copy code or fixtures from a repository unless its license is compatible and the reuse is deliberate, attributed, and documented. AGPL material is out of scope for this MIT project. When a source is used only to validate a protocol fact, implement the behavior independently and test it against Slipstream’s own captures.
