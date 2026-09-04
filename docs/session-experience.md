# Session experience contract

This document defines Slipstream's session-facing behavior. It complements the wire contracts in `docs/protocol.md`; it does not create a second truth model.

## Session families

Provider session names normalize into Practice 1/2/3, Qualifying, Sprint Qualifying, Sprint, Race, or Unknown. Practice sessions use the Practice layout; Qualifying and Sprint Qualifying use the Qualifying layout; Sprint and Race use the Race layout. Shared presentation does not collapse factual session kind, and session-specific policy such as the number of advancing cars is selected explicitly from season and field-size context.

## Product live lifecycle

The viewer consumes a product lifecycle rather than equating a socket state with the sporting event:

`PRE_EVENT → CONNECTING → LIVE → STALE → RECONNECTING → LIVE`

At the end of a session:

`LIVE → FINALIZING → COMPLETE → REPLAY_READY`

`UNAVAILABLE` means the public source cannot currently provide the session. A scheduled session may be pre-event while the source is disconnected; a connected source may also be between meaningful timing updates. Sporting suspension is not transport unavailability: a red-flagged race remains Live-capable while its source continues or retained canonical state is reconnecting.

Pre-event UI shows the official start when known and a countdown derived from server time. A countdown reaching zero does not fabricate a green session: the experience remains connecting/waiting until factual upstream evidence arrives.

## Viewer delay

The server owns one upstream connection per application instance. The Live protocol accepts an independent 0–300-second delay per viewer; the current browser exposes 0, 5, 10, 15, and 30-second presets. Both `RaceState` and `AnalyticsSnapshot` are built from the same delayed cursor. Returning to LIVE resets only that viewer to zero.

Live viewing has no pause, seek, relative-seek, or speed command. Those controls belong only to replay.

## Recording and immediate replay

Public live packets normalize into the same source-neutral events used by historical replay. The in-progress recording is operational data and is not exposed as a complete replay. After factual completion, a short drain accepts late packets; only newly emitted canonical factual events extend the drain; Heartbeat and other no-op source rows do not. The finalized file is promoted atomically, the catalog is refreshed, the completed upstream is released, and the lifecycle becomes `REPLAY_READY`.

During `FINALIZING`, the viewer continues to see the same session's retained authoritative Live state, extended only by accepted late canonical events. An existing viewer then receives the final state from that same session's refreshed replay resource and changes to Replay controls. An explicit viewer selection is persisted locally so hard refresh resolves that same session across the handoff. A later session may become global `liveSessionKey` and is offered through GO LIVE, but the viewer is not moved away from the completed session.

Reconstruction remains deterministic: the inclusive event cursor determines both canonical state and analytics. The normalized recording—not a provider-specific raw capture—is the product replay artifact.

Historical replay ends at the settled factual product boundary rather than necessarily at the first chequered packet. Late classification facts included in the normalized recording remain reachable, and backward seeks reconstruct the earlier cursor without projecting those final results into the past.

Replay download/preparation UX is still deferred. The product does not yet claim complete progress feedback, an explicit `DOWNLOADING` / `PREPARING` / `READY` lifecycle, elimination of the blank or partial post-download shell or possible refresh, immediate control/slider readiness, removal of the end-to-start initialization flash, or optimized bootstrap latency.

## Qualifying

The backend owns Qualifying truth. It publishes the current phase and clock, tyre/usage observations, completed-lap history, benchmark/scope, verified advancement boundary, final-segment results, teammate comparison, and advancing/eliminated classification when evidence supports them. The browser formats these values but does not calculate a competing benchmark or elimination model.

A lap-history entry requires observed completed-lap evidence; elapsed wall time or a changing position alone does not invent a lap. Eliminations are session- and policy-aware and use stable roster metadata rather than the current row count. Unknown phase or clock is omitted in the product instead of rendered as a large UNKNOWN label.

## Driver activity and terminal state

Activity and source condition are related but separate. `ON_TRACK`, `IN_PIT`, and internal `UNKNOWN` describe observed activity. Current F1 `source_condition` is `RUNNING`, `IN_PIT`, `STOPPED`, `RETIRED_INDICATED`, or `UNKNOWN`; `STOPPED` and `RETIRED_INDICATED` may recover when the provider explicitly retracts them. Final `FINISHED`, `DNF`, `DNS`, `DSQ`, or authoritative `RETIRED` classification is terminal and appears only at its factual cursor.

M3.5 does not derive or render `NO_RECENT_PROGRESS`. A missing timing update, lap deficit, stationary map marker, or low classification never proves retirement.

## Track presentation

Global status is server-authored from independent sporting/control and marshal facts. Public Live can keep a suspended/red state through later marshal changes and clears it only on explicit session-level resumption. Historical OpenF1 may legitimately degrade differently: when a red-flag message is known but the actual sporting restart is not represented, it does not create a persistent suspension/red latch; after later marshal evidence the global badge is omitted until another explicit sporting-control/session transition is available. `TRACK CLEAR` never resumes the session. Sector flags remain scoped race-control evidence and do not replace global status.

Static circuit geometry is preloaded catalog data. Precise per-car X/Y is used only when the selected source declares and supplies that capability. Timing progress is mapped approximately onto the circuit only when the selected descriptor declares `timing_estimate`; sparse packets retain the last factual estimate. If neither car-position mode is declared—as in the current public Live product—car position is unavailable rather than fabricated.

Marker eligibility is lifecycle-aware. A current running car can be placed only when the selected source declares usable position evidence. Stopped, retired-indicated, and final-out cars are removed from stale circulating markers and may receive a separate factual label. A transient `IN_PIT` car may be omitted when its physical position is not meaningful, but it is never added to `OUT / STOPPED`. A recovered `STOPPED` car can return when positive source evidence and position capability support it.

## Pit presentation

A factual pit event remains visible even when duration detail is absent. Pit History can show ordinal, lap, previous/new compound, complete `pitLaneDuration`, and stationary `stopDuration` independently.

`PitLaneTimeCollection.Duration` is complete pit-lane transit, not stationary pit-box time or Net Pit Loss. It is admitted only when `0 < duration <= 300 seconds`; out-of-domain suspension-spanning values remain unavailable. If a duration type is absent for the whole current history, its column is omitted. If the type exists for some events, individual missing rows render `—`.

## Missing-data presentation

Internal availability enums remain part of diagnostics and protocol state, but they are not default product copy. Stable source/session capability decides whether a whole column or element exists. Within a supported field, a missing row value renders `—`; a capability-wide absence omits the element, with at most one quiet explanatory note where useful. Capability-authored desktop and TV views never substitute plausible sample values.
