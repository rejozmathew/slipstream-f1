# Roadmap

Slipstream has a working historical-replay foundation. Product work proceeds against that foundation without replacing canonical `RaceState`, replay controls, API v1, or the single-container deployment.

## Milestone 1 - frontend and contract foundation

- typed HTTP, state, and WebSocket clients
- modular desktop application shell
- canonical Race, Qualifying, Practice session classifier
- replay-driven Race, Qualifying, and Practice layouts
- Race-only draggable Timing-to-Analysis divider and presets
- explicit disconnected, unavailable, `UNKNOWN`, and `UNSUPPORTED` source-capability states
- no production sample-data fallback
- source-neutral lap evidence with quality, pit, compound, stint, and whole-track neutralization context outside high-frequency `RaceState` snapshots
- preserved hierarchical replay catalog, download, play, pause, seek, speed, TV-sync delay, terminal, and API v1 behavior

Strategy calculations, Recommended Battle, authentication, Sync Groups, devices, mobile/landscape, TV Mode, normalized live timing, and hardware are deliberately outside this milestone.

## Milestone 2 - responsive layouts and focused views

- final Session, Battle, TV Mode, and Settings product navigation
- mobile portrait and mobile landscape states; no `/mobile` or `/landscape` routes
- authored TV Mode
- layout schema/editor using Instance default -> User preference -> Device override ownership
- contextual Driver Focus using on-demand normalized lap evidence
- factual Battle with Recommended, Leader, and Pinned pair selection
- independent background and accent settings with locked semantic state colors
- truthful production Strategy shells without calculations

## Milestone 3 - Race Intelligence and Weekend Context

- source-neutral `SessionKind` distinct from shared Race/Qualifying/Practice layout families
- versioned, non-blocking Weekend Context packs restricted to the same `meeting_key`, with explicit evidence cutoffs and no prior-weekend/circuit-edition inputs
- cached analytics sidecar synchronized to deterministic replay time/cursor
- clean-lap pace delta, degradation, pit events, and provenance-aware Strategy
- shared Recommended Battle score with hysteresis
- first-class Driver navigation, factual ahead/behind, and pace visualization
- separate Race split-width presets and Timing Tower Standard/Timing/Strategy modes
- Driver TV state, persistent race-status treatment, short critical alerts, and device-local rotation preferences
- optional External Strategy Intelligence boundary, disabled by default

Historical replay remains the development and regression harness for analytics. Unsupported or insufficient evidence remains `UNKNOWN`; no frontend strategy calculations or parallel factual model are introduced.

## Milestone 3.5 - live, Qualifying, replay, and Pirelli closure

- explicit public-live lifecycle from pre-event through replay-ready, without treating source connectivity as event status
- normalized in-progress live recording with a completion drain and atomic promotion into the replay library
- independent per-viewer live delay while `RaceState` and `AnalyticsSnapshot` share one delayed cursor
- server-authored Qualifying phase, clock, scoped benchmark, stable-roster advancement rules, final segment facts, completed-lap history, teammate comparison, and session-aware Driver Focus
- explicit resumable `STOPPED` versus persistent terminal lifecycle, with `NO_RECENT_PROGRESS` disabled rather than used as a classification heuristic
- timing-derived live track progress retained across sparse packets; precise X/Y remains capability-gated
- sparse official Pirelli newsroom acquisition, immutable evidence archives, cutoff-safe target-session admission, and the server-authored `publishedStrategy` sidecar
- factual Race UI plus Pirelli-present/absent Strategy behavior, restricted Qualifying/Practice TV rotations, and capability-stable missing-data presentation
- source-dependent red-flag truth: explicit public-Live suspension/restart, conservative OpenF1 historical degradation when restart evidence is absent
- zero-delay incremental Live state/evidence plus same-session `FINALIZING → REPLAY_READY` retention and hard-refresh selection

Milestone 3.5 is implementation-complete and awaiting final owner acceptance. OCR/VLM/manual transcription and image-only tyre-bank extraction remain deliberately absent. General historical context, Net Pit Loss, deterministic archived-session backtesting, authenticated live data, and precise live car X/Y remain future work; their contracts publish absence or `NOT_IMPLEMENTED`, never sample results.

## Milestone 4 - persistent control plane and access

- SQLite migrations under `/data`
- first-run Admin creation, including existing installs with recordings but no database
- Viewer Profiles with reusable password/passphrase credentials
- remembered sessions, access policy, preferences, and Administration
- anonymous access restricted to normalized viewer catalog/capability/state/replay metadata and viewer stream endpoints
- no anonymous downloads, management, diagnostics, sources, groups/devices, or hardware control

Existing recordings and catalog data must be preserved. There is no anonymous migration grace period.

## Milestone 5 - Sync Groups and devices

- server-owned shared replay/live controller per group
- server-serialized last-write-wins updates
- authoritative monotonically increasing group revision/sequence
- temporary Independent View without changing group state
- expiring short codes only for device and hardware pairing

V1 does not use controller leases or locks.

## Milestone 6 - expanded live-source coverage

- extend the M3.5 conservative public live slice from additional complete real-session captures
- add source-neutral live evidence needed by analytics without leaking provider payloads
- retain one upstream connection per instance and explicit stale/unavailable capability states
- add optional authenticated source adapters when configured at runtime

Authenticated sources remain optional adapters configured only at runtime. Credentials and protected captures never belong in the repository.

## Later hardware

Hardware clients consume versioned normalized contracts and remain independent of provider payloads.
