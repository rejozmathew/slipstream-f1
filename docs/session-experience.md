# Session experience contract

This document defines Slipstream's session-facing behavior. It complements the wire contracts in `docs/protocol.md`; it does not create a second truth model.

## Session families

Provider session names normalize into Practice, Qualifying, Sprint Qualifying, Sprint, and Race kinds. Shared presentation families may reuse components, but Race Qualifying and Sprint Qualifying remain distinct factual sessions. Session-specific policy, including the number of advancing cars, is selected explicitly from season and field-size context.

## Product live lifecycle

The viewer consumes a product lifecycle rather than equating a socket state with the sporting event:

`PRE_EVENT → CONNECTING → LIVE → STALE → RECONNECTING → LIVE`

At the end of a session:

`LIVE → FINALIZING → COMPLETE → REPLAY_READY`

`UNAVAILABLE` means the public source cannot currently provide the session. A scheduled session may be pre-event while the source is disconnected; a connected source may also be between meaningful timing updates. Sporting suspension is not transport unavailability: a red-flagged race remains Live-capable while its source continues or retained canonical state is reconnecting.

Pre-event UI shows the official start when known and a countdown derived from server time. A countdown reaching zero does not fabricate a green session: the experience remains connecting/waiting until factual upstream evidence arrives.

## Viewer delay

The server owns one upstream connection per application instance. Each viewer independently chooses 0, 5, 10, 15, or 30 seconds of presentation delay. Both `RaceState` and `AnalyticsSnapshot` are built from the same delayed cursor. Returning to LIVE resets the viewer delay to zero.

Live viewing has no pause, seek, relative-seek, or speed command. Those controls belong only to replay.

## Recording and immediate replay

Public live packets normalize into the same source-neutral events used by historical replay. The in-progress recording is operational data and is not exposed as a complete replay. After factual completion, a short drain accepts late packets; only newly emitted canonical factual events extend the drain; Heartbeat and other no-op source rows do not. The finalized file is promoted atomically, the catalog is refreshed, the completed upstream is released, and the lifecycle becomes `REPLAY_READY`.

An existing viewer then receives the final state from that same session's refreshed replay resource and changes to Replay controls. A later session may become global `liveSessionKey` and is offered through GO LIVE, but the viewer is not moved away from the completed session.

Reconstruction remains deterministic: the inclusive event cursor determines both canonical state and analytics. The normalized recording—not a provider-specific raw capture—is the product replay artifact.

## Qualifying

The backend owns Qualifying truth. It publishes the current phase and clock, driver activity/usage observations, factual attempts, benchmark, cutline, and advancing/eliminated classification when evidence supports them. The browser formats these values but does not calculate a competing cutline or attempt model.

An attempt requires observed qualifying timing evidence; elapsed wall time or a changing position alone does not invent a lap. Eliminations are session- and policy-aware. Unknown phase, clock, validity, or advancing evidence stays unknown.

## Driver activity and terminal state

`ON_TRACK`, `IN_PIT`, `NO_RECENT_PROGRESS`, and `UNKNOWN` describe source-observed activity. They are not synonyms for `STOPPED`, `RETIRED`, `DNS`, `DNF`, or `DSQ`. Terminal lifecycle is published only when explicit source evidence establishes it. A missing timing update, a stationary map marker, or a low final classification never proves retirement.

## Track presentation

Global status is server-authored from independent sporting/control and marshal facts. A suspended race or latched red flag governs the presentation even if marshal status later becomes all-clear or yellow. `TRACK CLEAR` does not resume the session; only explicit session-level resumption changes `SUSPENDED` back to `RUNNING` and clears the red-flag latch. Sector flags remain scoped race-control evidence and do not replace global status.

Static circuit geometry is preloaded catalog data. Precise per-car X/Y is used only when the selected source declares and supplies that capability. Otherwise, observed timing progress is mapped approximately onto the circuit and retained across sparse packets. If neither source is available, car position is unavailable rather than fabricated.

## Availability language

- `UNKNOWN`: the capability exists but current evidence is insufficient.
- `UNSUPPORTED`: the active source cannot provide the capability.
- `UNAVAILABLE`: the source or session cannot currently be reached or rendered.
- `STALE`: previously observed state is retained but has exceeded its freshness threshold.

Presentation may use an em dash in dense numeric cells, but diagnostics and panel-level states retain the explicit reason. Capability-authored desktop and TV views must not substitute plausible sample values.
