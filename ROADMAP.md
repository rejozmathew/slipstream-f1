# Roadmap

Slipstream has a mature M3.5 factual/source baseline: public Live, deterministic Replay, official F1 historical reconstruction with whole-session fallback, cursor-safe evidence and analytics, Qualifying, Pirelli context, and authored Race/Qualifying/Practice/TV experiences.

## Milestones 1–3 - completed foundations

### Milestone 1 - frontend and contract foundation

- typed HTTP, state, and WebSocket clients;
- canonical `RaceState`, normalized events, and source-neutral lap evidence;
- shared Race, Qualifying, and Practice session classification and replay layouts;
- hierarchical catalog, download, play, pause, seek, speed, terminal, and API v1 behavior;
- explicit capability and missing-data states with no production sample fallback.

### Milestone 2 - responsive layouts and focused views

- final Session, Driver, Battle, TV Mode, and Settings navigation;
- responsive portrait and landscape states without separate applications;
- authored TV Mode and reversible device-local presentation preferences;
- contextual Driver Focus with on-demand normalized history;
- factual Battle and truthful Strategy shells without frontend calculations.

### Milestone 3 - Race Intelligence and Weekend Context

- source-neutral session kind separated from reusable layout family;
- same-meeting, cutoff-safe Weekend Context with no prior-weekend leakage;
- cached analytics sidecar synchronized to deterministic replay time/cursor;
- clean-lap pace, stint, pit, Driver, Strategy, and provenance-aware RaceRead;
- completed-lap Battle histories and server-owned recommendation stabilization;
- optional External Strategy Intelligence boundary, disabled by default.

Historical replay remains the development and regression harness. Unsupported or insufficient evidence remains `UNKNOWN`; React does not create a parallel factual or analytics model.

## Milestone 3.5 - source, live, and replay closure

The current merge candidate includes:

- direct F1 public Live normalization through one server-owned upstream;
- official F1 static historical reconstruction using the same F1 timing semantics;
- finalized Live > official static > OpenF1 whole-session timing precedence;
- provider SessionTime-to-UTC reconstruction with fail-closed anchor consensus;
- independent per-viewer Live delay while `RaceState` and `AnalyticsSnapshot` share one cursor;
- normalized in-progress Live recording with completion drain and atomic replay promotion;
- server-authored Qualifying phase, clock, benchmark scope, advancement boundary, final segment facts, lap history, teammate comparison, and Driver Focus;
- resumable `STOPPED` and `RETIRED_INDICATED` separated from terminal classification, with no `NO_RECENT_PROGRESS` derivation;
- factual pit events plus bounded official `PitLaneTimeCollection` lane transit;
- sparse official Pirelli acquisition, immutable archives, strict/display-only evidence tiers, and the `publishedStrategy` sidecar;
- lifecycle-aware Track Map semantics, cross-session Race/Qualifying/Practice parity, restricted session-specific TV rotations, and capability-stable missing-data presentation;
- replay deletion that preserves catalog, circuit, Pirelli, and source manifests.

M3.5 is the factual/source merge candidate. OCR/VLM/manual transcription and image-only tyre-bank extraction remain deliberately absent. General historical context, Net Pit Loss, deterministic archived-session backtesting, authenticated live data, precise live X/Y, and hardware remain future work; their contracts publish absence or `NOT_IMPLEMENTED`, never sample results.

## Next phase - visual and interaction design

The immediate product phase after the M3.5 baseline is merged is a bounded visual and interaction pass over stable contracts.

Primary targets:

- Strategy/Pirelli hierarchy and density;
- Driver and Pit History composition;
- Race desktop layout and information hierarchy;
- Qualifying density and status treatment;
- Practice composition;
- TV Track/Tower/Driver/Battle composition;
- mobile/landscape polish;
- spacing, typography, and interaction clarity.

The design pass must not silently change provider/source truth, lifecycle meaning, evidence cutoffs, source precedence, or analytics formulas.

## Milestone 4 - persistent control plane and access

- SQLite migrations under `/data`;
- first-run Admin creation, including existing installs with recordings but no database;
- Viewer Profiles with reusable password/passphrase credentials;
- remembered sessions, access policy, persistent preferences, and Administration;
- anonymous access restricted to normalized viewer catalog/capability/state/replay metadata and viewer streams;
- management, diagnostics, downloads, sources, groups/devices, and hardware control behind authorization.

Existing recordings, catalog data, and Pirelli evidence must be preserved. There is no anonymous migration grace period.

## Milestone 5 - Sync Groups and devices

- server-owned shared replay/live controller per group;
- server-serialized last-write-wins updates;
- authoritative monotonically increasing group revision/sequence;
- temporary Independent View without mutating group state;
- expiring short codes only for device and hardware pairing.

V1 does not use controller leases or locks.

## Milestone 6 - expanded source coverage

- additional validated public-live topics;
- source-neutral live evidence required by analytics without provider-payload leakage;
- optional authenticated source adapters configured only at runtime;
- explicit stale/unavailable capability states and one upstream connection per instance.

Credentials and protected captures never belong in the repository.

## Hardware

Hardware clients should consume versioned normalized Slipstream state rather than upstream provider payloads. Candidate clients include race-status lights, LED matrices, WLED integrations, and synchronized secondary displays. The existing delayed-live cursor is intended to provide one temporally coherent world.

## Deferred and research

- Net Pit Loss and separately sourced stationary pit-box duration;
- deterministic archived-session strategy backtesting;
- richer historical official context and complete remaining-tyre inventory;
- authenticated precise live GPS;
- optional external strategy intelligence;
- advanced hardware control.
