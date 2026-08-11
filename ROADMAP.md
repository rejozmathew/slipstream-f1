# Roadmap

## Phase 0 — data proof

- [x] Historical OpenF1 acquisition and raw recording envelope
- [x] Provider normalization into canonical immutable `RaceState`
- [x] Race, qualifying, and practice terminal output
- [x] Golden regression tests and explicit protocol versions

## Phase 1 — replay product simulator

- [x] Pause/resume, step, seek, and 0.5x/1x/2x/10x clock playback
- [x] Timing, tyre age, stint length, pit count, sectors, and approximate track position
- [x] Expand golden checkpoints across a complete pit cycle and flag changes
- [x] Add missing-data availability semantics with a reserved live `stale` state
- [x] Weather, rain detection, track conditions, and circuit-local clock

## Phase 2 — browser pit wall

- [x] Versioned REST/WebSocket transport over `RaceState`
- [x] Timing tower and race-control display
- [x] Exact historical circuit outline with timing-derived car placement

## Phase 3 — live source

- [x] Public live collector with one upstream connection per instance
- [ ] Validate alongside replay during a live weekend
- [ ] Extract the common source adapter interface from both implementations
- [x] Detect an active scheduled session, select it by default, and cap its timeline at now

## Later

- [x] Per-client replay scrubbing and broadcast-delay cursor
- [x] Season/weekend/session replay library and clocked browser playback
- [x] Three-season lightweight catalog with dates and preloaded circuit geometry
- [ ] Buffered live delay, event snapshots, and external clients
- [ ] Authenticated enhanced sources and precise per-car X/Y capability
- [ ] Battle groups (including two-on-two) with gap and position progression over time
- [ ] Golden capability/fallback scenarios for precise X/Y, timing estimates, and unavailable positions
- [ ] Hardware consumers
