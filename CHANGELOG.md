# Changelog

## Unreleased — session redesign and evidence-timed story

### Added

- Production React desktop/phone/TV presentation based on the approved round-two design, shared branding and bundled fonts, token-based density, reduced motion, adaptive timing columns, and phone-specific navigation.
- Source-neutral `causal-story-v1` ledger with separate occurrence/publication times, neutral order observations, corroborated passes, pit/lifecycle/flag/lap/weather history, provisional results and later corrections.
- Cursor- and recording-identity-scoped story pagination, Everything/Highlights/Following filters, separate inspection/replay actions, and exact return to the saved replay moment.
- TV Activity and major-moment presentation with silent navigation rebuilds, playback-speed suppression, and remote controls; standalone browser TV entry remains separate from a future native Android TV package.
- Private Live pause/resume bounded by a five-minute delay, requested/effective delay separation, reconnect continuity, and a visible automatic-resume notice.

### Corrected

- Pirelli race guidance in mixed Sprint/Qualifying reports is retained when the article explicitly identifies the next day's Grand Prix, opening compound, and one-stop finishing alternatives. Unpublished stop laps and rankings stay unspecified; refresh attempts and results are exposed in diagnostics.
- Track maps separate overlapping display symbols, including neighbouring clusters, without changing source progress. Active-car coverage and stopped/pit trays retain their factual meanings.
- Qualifying stays live when the next segment is explicitly `SCHEDULED` after the cached timetable ends, including recovery after a server restart. The Q2-to-Q3 waiting interval no longer disconnects the collector or changes the default session to an older replay.
- Place pre-event and unavailable live-feed notices inside the timing tower on desktop and phone, keeping analysis panels unobstructed.
- Qualifying replay timelines include late final laps and classification changes after the flag, while delayed live viewers retain the full saved tail before replay handoff.
- Track movement preserves velocity across new position packets and eases into sparse endpoints without predicting future positions or restarting the animation loop on every snapshot.
- Track maps keep every active car marker visible while packing labels separately. Official mini-sector recolouring and repeated lap counters no longer produce false position updates; shared desktop/TV motion follows observed cadence across packet bursts and start/finish wraps without extrapolating.
- Official completed-lap recording now reconciles split time/counter updates and suppresses reconnect repeats without inventing lap numbers. Existing qualifying history collapses repeated observations and explicitly labels ambiguous lap numbers.
- Driver qualifying history shows the newest segments and laps first and labels source lap numbers as session laps, with an explanation for gaps in recorded history.
- Qualifying Timing retains each driver's best completed lap sectors per segment; Driver history groups and colours completed laps within their own segment. Refresh prefers the current Live session and preserves saved Live intent through temporary catalog gaps instead of opening the historical default.
- Confirmed qualifying elimination fades desktop, TV and phone timing cells to the reference 42% opacity; below-cut positions remain provisional. Map animation follows each driver's position-update cadence and retains motion through marker clustering, with timing-derived travel kept on the circuit path. Live animation uses real-time speed independently of the saved replay multiplier.
- Delayed qualifying remains available in Live between Q1/Q2 or SQ1/SQ2 and the next segment after the scheduled session end.
- Qualifying Timing sectors now use the reference purple/green/yellow palette for cursor-safe observed field-best, personal-best and slower sectors; qualifying chequered labels name the ended segment in desktop/TV rails and Story.
- Matched the authored TV footer, sync panel, feature compositions, Story cards/ticker, track markers/ribbon, and timing-row motion; added the persistent desktop timing rail and the qualifying/practice reference panels.
- Applied the complete flag presentation: yellow, striped VSC/ending, solid-yellow Safety Car, red suspension, green return and chequered finish, with escalation wipes, three blinks, silent seek rebuilds and reduced-motion treatment.
- Added source-confirmed elimination and completed-session pole/practice stories; replay moments now include a five-second lead-in and desktop/TV share the sync offset.
- Racing battle recommendations require known green running from lap 3, eligible on-track drivers, and matching known laps. Pinned non-adjacent comparisons now use server-authored pair truth instead of browser arithmetic.
- Completed pit stops come from cursor-scoped completed evidence; pit entry counts and later compound observations cannot fill missing earlier facts.
- Partial race history and unverified sporting profiles remain UNKNOWN for dry-tyre requirements; observed wet/intermediate use is handled explicitly.
- Qualifying flag/settlement state is distinct from a final result. Above the current cut is not declared guaranteed advancement.
- Story identities are independent of Live/static transport labels. Real-recording prefix checks cover the earlier confirmation, tyre, caution, stop, and result regressions.

### Documentation and scope

- Added a detailed story derivation contract and reconciled architecture, protocol, analytics, strategy, experience, contributor maps, and product flows.
- This is a branch implementation, not a production deployment or renewed certification of the historical cold-seek, protected-fixture, or Unraid hardware limits below.

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
- The visual redesign was a separate post-M3.5 phase; its implementation is recorded in the newer entry above.
- The first cold seek still misses the 300 ms target (1.085 s in the last recorded workload); it remains an accepted documented limitation, not a completed optimization.
- The owner 11353 OpenF1 protected archive is missing from the test environment; its existing test remains skipped.
- Genuine public live-race operation was validated locally after disabling the NordVPN route causing HTTP 403. Actual Unraid hardware and the production reverse proxy were not separately validated or modified during branch closure.
