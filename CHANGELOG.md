# Changelog

## Unreleased — Milestone 3.5 source unification and replay readiness

### Added

- Direct official Formula 1 static historical reconstruction with whole-session OpenF1 fallback.
- Shared F1 timing semantics between public Live SignalR and official static replay.
- Provider SessionTime-to-UTC anchoring from a consensus of factual source UTC evidence.
- Explicit current F1 source condition (`RUNNING`, `IN_PIT`, `STOPPED`, `RETIRED_INDICATED`, `UNKNOWN`) separated from final classification.
- Cursor-safe final classification and settled replay boundaries.
- `PitLaneTimeCollection` normalization for factual complete-lane duration.
- Source-neutral lap, stint, and pit evidence parity across direct F1 Live/Replay paths.
- Cross-session Race, Qualifying, and Practice validation.
- Per-viewer live-delay validation across state, lifecycle, evidence, map population, envelope playhead, and analytics.
- Pirelli V1 acquisition and history closure: bundled normalized production seed, quiet deterministic self-backfill, current-weekend official acquisition, semantic article-boundary filtering, immutable archival storage, and strict/display-only evidence tiers.
- Stop-preserving actual tyre strategies, published stop-window comparison, dry-tyre requirement states, and the shared Session/Timing Tower/Driver/Battle/Strategy/TV presentation contract.
- Lifecycle-aware Track Map behavior and active-coverage semantics.
- Replay deletion that preserves catalog, circuit, Pirelli, and source manifests.
- Replay readiness and lifecycle delivery: atomic first-frame canonical start with `playbackReady: true` before preparation; metadata-only catalog discovery; bounded 3-resource LRU cache (512 MiB budget / 300 MiB per-resource ceiling) tracking preparation leases; cancellation-safe async per-viewer advance; live collector release immediately after factual drain with independent bounded publication retries and delayed tails; restart journal validation and offline publication; HTTP 409 on deleting active/pending targets; optional `recording_version` identity handshake with legacy seq compatibility; browser 0–300s delay presets and exact M:SS entry; in-process download jobs (`QUEUED` → `DOWNLOADING` → `FINALIZING` → `AVAILABLE` / `FAILED`); and decoupled catalog initialization status.
- A capability-dependent interval column alongside the leader gap in Race Timing mode.
- Driver Read follows source-backed stopped/retired conditions and distinguishes pending classification from a confirmed finishing position.

### Corrected

- Fixed the historical F1 stream timebase; scheduled session start is no longer treated as stream zero.
- Prevented known catalog session identity from collapsing into an unsupported layout when provider identity fields are sparse.
- Preserved transient Retired/Stopped retractions instead of poisoning the rest of replay.
- Restored Driver stint trend and Pit History under the direct F1 historical path.
- Added factual lap-deficit display fallback without using lap deficit as retirement evidence.
- Prevented stopped, retired, and final-out cars from remaining frozen as active Track Map markers.
- Removed transient IN PIT cars from the `OUT / STOPPED` status list.
- Restored full TV timing fields and AUTO-leader Driver behavior.
- Restricted active observed strategy sequences to active running/in-pit drivers.
- Restored semantic Pirelli compound colors and horizontal pit compound transitions.
- Fixed Practice Track Map collapse.
- Ensured Qualifying replay progresses Q1 → Q2 → Q3 without future-segment leakage and settles at final status.
- Extended Race replay to the settled classification boundary rather than the first chequered packet.
- Rejected implausible suspension-spanning pit-lane durations instead of exposing them as one transit.
- Kept `RaceState` and `AnalyticsSnapshot` on the same inclusive 0/30/120-second delayed-live cursor.

### Known intentional limits

- `PitLaneTimeCollection` is not stationary pit-box time and is not Net Pit Loss.
- Pit-lane duration values outside `0 < duration <= 300s` remain unavailable.
- Historical Pirelli strict-model coverage remains conservative when exact version provenance is unavailable; the separately labelled display tier is not model-admissible.
- Protected GPS, high-frequency car data, team radio, and precise live X/Y are outside the default public-source slice.
- Deterministic archived-session backtesting, authentication/control plane, Sync Groups, and hardware clients remain deferred.
- Broad visual redesign remains a separate post-M3.5 phase.
- The first cold seek still misses the 300 ms target (1.085 s in the last recorded workload); it remains an accepted documented limitation, not a completed optimization.
- The owner 11353 OpenF1 protected archive is missing from the test environment; its existing test remains skipped.
- Genuine public live-race operation was validated locally after disabling the NordVPN route causing HTTP 403. Actual Unraid hardware and the production reverse proxy were not separately validated or modified during branch closure.
