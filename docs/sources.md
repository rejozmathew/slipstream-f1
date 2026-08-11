# Source notes

Checked directly on 2026-08-10; these repositories informed boundaries and protocol facts, not copied implementation.

- **FastF1** at `c4156d6` (MIT): current live client uses SignalR Core. Its default path supports F1TV authentication and its no-auth mode may return partial data.
- **OpenF1** at `b3b5061` (CC BY-NC-SA 4.0): historical API remains the replay source. Its hosted real-time tier now requires authentication/payment, so its live ingestor code was not reused.
- **OpenF1 meeting circuit link / MultiViewer circuit API**: checked directly on 2026-08-11 for Singapore 2023. The meeting record links a circuit object containing 544 ordered X/Y pairs plus year and rotation. Slipstream preserves that payload as source data and normalizes only the path fields needed by `RaceState`.
- **f1_sensor** at `7873804` (MIT): independently confirms a 2026 split between public timing/session streams and auth-gated GPS, telemetry, and team radio. Slipstream implements the documented SignalR Core framing independently.
- **br-g/fastf1-livetiming** at `5c3676e` has no repository license file. It was inspected only to confirm current message shapes; no code or fixtures were copied.
- **slowlydev/f1-dash** at `d21607a` is AGPL-3.0. Its source is not used or copied.

The public F1 endpoint returned HTTP 403 when probed outside a live session from the development environment. Phase 3 therefore keeps live-weekend validation separate from transport implementation and tests the transport end to end against a local SignalR simulation.
