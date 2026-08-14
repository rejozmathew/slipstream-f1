# Roadmap

Slipstream has a working historical-replay foundation. Product work proceeds against that foundation without replacing canonical `RaceState`, replay controls, API v1, or the single-container deployment.

## Milestone 1 - frontend and contract foundation

- typed HTTP, state, and WebSocket clients
- modular desktop application shell
- canonical Race, Qualifying, Practice session classifier
- replay-driven Race, Qualifying, and Practice layouts
- Race-only draggable Timing-to-Analysis divider and presets
- explicit disconnected, unavailable, `UNKNOWN`, and `UNSUPPORTED` states
- no production sample-data fallback
- factual lap-observation history with quality, pit, compound, and stint extension points
- preserved replay catalog, download, play, pause, seek, speed, terminal, and API v1 behavior

Strategy analytics, Recommended Battle, authentication, Sync Groups, devices, mobile/landscape, TV Mode, normalized live timing, and hardware are deliberately outside this milestone.

## Milestone 2 - responsive layouts and focused views

- mobile portrait and mobile landscape states; no `/mobile` or `/landscape` routes
- authored TV Mode
- layout preferences and ownership mechanics
- Driver Focus and factual Battle
- desktop layout editing beyond the Race divider

## Milestone 3 - persistent control plane and access

- SQLite migrations under `/data`
- first-run Admin creation, including existing installs with recordings but no database
- Viewer Profiles with reusable password/passphrase credentials
- remembered sessions, access policy, preferences, and Administration
- anonymous access restricted to normalized viewer catalog/capability/state/replay metadata and viewer stream endpoints
- no anonymous downloads, management, diagnostics, sources, groups/devices, or hardware control

Existing recordings and catalog data must be preserved. There is no anonymous migration grace period.

## Milestone 4 - Sync Groups and devices

- server-owned shared replay/live controller per group
- server-serialized last-write-wins updates
- authoritative monotonically increasing group revision/sequence
- temporary Independent View without changing group state
- expiring short codes only for device and hardware pairing

V1 does not use controller leases or locks.

## Milestone 5 - normalized public live timing

- validate a complete public real-session capture
- normalize the proven public topics through the existing adapter/event/`RaceState` path
- one upstream connection per instance with reconnect and bounded delay behavior
- same normalized viewer presentation for replay and live
- explicit stale/unavailable capability states

Authenticated sources remain optional adapters configured only at runtime. Credentials and protected captures never belong in the repository.

## Later analytics and hardware

Strategy and pace analytics must be provider-independent, tested production logic with provenance and robust clean-lap selection. Insufficient evidence produces `UNKNOWN`; the UI never invents a fallback. Hardware clients consume versioned normalized contracts and remain independent of provider payloads.