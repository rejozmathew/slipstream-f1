# Implementation notes for the React build

**Audience:** Astra, or whoever ports the session redesign into `slipstream-f1`.
**Status:** the prototype in `design/prototypes/` is the reference for behaviour and visual design. It is not code to copy. It runs from `file://` with classic scripts and derives some semantics client-side; production keeps React and server-authored semantics.

Read with:
- `handoff/review-response.md` — what changed and why
- `handoff/astra-wp1-logic.md` — the logic package
- `REVIEW-BRIEF.md` — how to open everything

---

## 1. Ground rules (unchanged)

- Show only data Slipstream has.
  - Positions are timing-point estimates (22 points per lap at Hungaroring, 20 at Kuala Lumpur) and are always labelled approximate.
  - No telemetry, radio or sector grading.
  - Pit-lane time is lane transit only.
- Live and replay are unmistakable. A jump is not news. A classification change is not an overtake.
- Missing capability is said once and plainly. Unknown stays unknown.
- Every piece of information the current app shows stays reachable. See the retention map in `REVIEW-BRIEF.md` §4 and its updates in `review-response.md`.

## 2. What must be server-authored

Render these from server contracts, never recompute them per surface:

| Concept | Source (existing or extended) | Prototype stand-in |
|---|---|---|
| Story events, with occurrence and availability | extend AnalyticsSnapshot / SessionEvidence (§4) | `SS.classify` in `engine.js` |
| Pass confirmation, lead-change cause | same | `engine.js` |
| Battle eligibility (green only, lap ≥ 3, same lap, ≤ 1.0 s) | same | `vm.js` `battleOn`, `SS.battleEligible` (WP-1) |
| Qualifying settlement, cut sizes by field | qualifying model and phase policy | `engine.js`, `SS.qualiPolicy` (WP-1) |
| Result state: none / provisional / final | RaceState lifecycle | `SS.resultState` (WP-1) |
| Race-now populations and dry rule (incl. unknown) | `raceRead` | `SS.raceNow` (WP-1) |
| Actual strategy (stints, tyre sequence, completed stops) | actual-strategy contract | `SS.stints` (WP-1) |
| Published strategy, options, windows, tyre bank | `pirelliReferences`, PublishedStrategy | `SS.pirelliHTML`, `SS.strategyContextHTML` (WP-1) |
| Pair gap and completed-gap history | analytics `pair` gap (`analytics.py` 590–639) | `SS.pairGap`, `SS.pairHistory` (WP-1) |
| Position coverage with reasons | supported-position definition | TrackMap footer |
| Lap PB / session-best flags, interval trend | new fields | `vm.js` row flags |
| Battle score, pace fade, driver outlook | existing analytics | labelled placeholders |

**Key acceptance test:** truncate a recording at time T. Factual state, story and live position estimates at T must equal the full recording viewed at T. The only exception is labelled replay interpolation between known crossings. WP-1 adds this test for the prototype (`tools/truth-test.mjs`); keep an equivalent in the backend test suite.

## 3. One viewer, three postures

**Viewer context:**

```
{ session, cursor t, mode: live|replay, delay, requestedDelay, speed, playing, follow, pinnedPair, motion }
```

- Desktop ↔ TV ↔ phone is a presentation change. Keep one controller. Across documents, serialize and restore the whole context (`SS.viewer` in `shared/contract.js`).

**Live model** (owner-confirmed):

- The live edge advances in real time. `cursor = edge − delay`.
- **Pause** holds the cursor, so the delay grows (like pausing a TV). Resume keeps the new delay. GO LIVE sets the delay to 0.
- **Limits:** the delay buffer is 5:00 (`MAX_LIVE_DELAY`). If the requested delay is larger than what the buffer holds, show both values ("asked 5:00 · buffer holds 3:12").
- **No seek or speed in live.** ←/→ change the delay: 5 s steps, or 1 s while the delay panel is open.
- **Stale feed:** the cursor freezes. On reconnect it catches up silently to the same delay; that is a jump.

**Replay model:**

- Seek, speed 0.5–120×, and a sync offset to line up with a recorded broadcast.
- Replaying a moment stores a return point (↩).

**Capability checks** (`player.can(cmd)`): every input path calls the same check before acting — buttons, keyboard, remote and sheets.

**Navigation generation** (`player.gen`): bumps on every jump. Any feed or ticker that sees a new generation, or is revealed after being hidden, renders silently.

## 4. Story contract

Event fields:

| Field | Meaning |
|---|---|
| `id` | stable |
| `session` | — |
| `kind` | — |
| `t` | occurrence time |
| `at` | when the evidence exists; `at ≥ t` |
| `drivers[]` | — |
| `cause` | if established |
| `state` | provisional, confirmed or corrected |
| `supersedes` | id it replaces |
| `evidence` | refs |
| `priority` | — |
| `lap` | — |
| `copy` | template inputs |

Rules:

- **Presentation:** show an event only when `at ≤ viewer cursor`, on every surface: feed, ticker, cards, timeline markers, driver moments, logs, result.
- **Reconnect and seek:** dedupe on reconnect. Rebuild deterministically after a backward seek. Never replay old notifications on a seek.
- **Spoilers:** finished-session replays show markers and moments only up to the furthest point watched, unless the viewer turns spoilers on. Delayed live never shows anything past the delay.
- **Interaction:** tapping an item shows details first (happened at, known at with the lag, state, drivers). Replay is a separate action and stores the return point.
- **Conservative language:**

| Situation | Copy |
|---|---|
| Order change, cause not established | "moves to P8" / "moves ahead of …" |
| Confirmed on-track pass in green running | "passes" |
| Order change under yellow, VSC or SC | neutral copy; never "passes" |
| Leaving the pit lane | PIT EXIT (not OUT) |
| Out of the race | STOPPED vs RETIRED, as the feed says; never inferred from silence |
| Qualifying, before settlement | ABOVE CUT / BELOW CUT |
| Qualifying, settled | ADVANCES / ELIMINATED |
| Chequered flag | "wins on the road" · PROVISIONAL until a final classification exists |

## 5. Motion

| Cause | Duration (ms, desktop) | Easing |
|---|---|---|
| pass / passed | 520 + 70·(d−1), ≤ 1150 | (.45,.05,.2,1) |
| start | 360 + 40·d, ≤ 700 | (.3,.6,.3,1) |
| pit | 820 + 80·d, ≤ 1700 | (.6,0,.3,1) |
| promoted | 680 | (.4,0,.2,1) |
| out | 1050 + 50·d, ≤ 1800 | (.55,0,.45,1) |
| class (after flag / penalties) | 950 | (.65,0,.35,1) |
| improve (timed) | 560 + 60·d, ≤ 1200 | (.3,.9,.25,1) |
| pushed / deleted / neutral | 600 / 900 + 40·d / 700 | — |

- **Posture scale:** TV ×1.35, phone ×0.85.
- **Replay speed:**
  - Below 5×: full motion.
  - 5× and up: ×0.6, and only the newest pending card survives.
  - 20× and up: cards only for results and red flags; the director stops chasing events.
  - 30× and up: rows snap without cause effects.
- **Neutral moves:** no pass styling outside green running. The cause is not established.
- **Rail:**
  - Escalation: a wipe (520 ms desktop, 700 ms TV), then 3 blinks.
  - De-escalation: a 600 ms fade.
  - Every transition cancels the previous one (generation token).
- **Jumps:** snap with a 350 ms fade-in of the tower body and nothing else.
- **Reduced motion:** one policy for every surface — the system setting or an explicit choice, reacting to system changes.
  - Travel, pulses, blinks, marching stripes and the brand sweep stop.
  - Causes stay visible as static outlines, colour and labels.
  - Running effects finish immediately.

## 6. Display size and tokens (desktop)

- **Setting:** display size 75 / 80 / 90 / 100%; default 80%.
  - Production: scale the type and spacing tokens (rem-based) from one `--ui-scale`.
  - The prototype uses CSS `zoom` only for speed. Do not port `zoom`.
- **Minimum type at the default:** labels 10 px, eyebrows 10 px, body 12–13 px. Apply the scale on top.
- **Contrast:** `--text-3` is #7a8594, which passes 4.5:1 on every surface.

## 7. Posture specifications

### Desktop

- **Session page:** tower | analysis panel. The split presets (balanced 50%, tower wide 62%, analysis wide 40%) and EDIT LAYOUT remain.
- **Tower:**
  - Identity is at least 140 px.
  - Columns carry a drop priority per view (`web.js` COLS) and hide before names ever squeeze ("+N HIDDEN").
  - Past that, the tower scrolls sideways inside its own panel.
  - Rows fill the panel height (28–38 px).
- **Analysis presets** are rows of either one wide module or a pair of columns:
  - Race:
    - BRIEF: [track | strategy] then [story | conditions + race control]
    - MAP: large map, then [strategy | conditions + race control], then story
    - STORY: story first
  - Qualifying and practice have their own versions.
  - Map size is S, M or L.
  - Module order and hide stay in settings.

### Phone

- **App bar:** brand, session (opens the session switcher), menu.
- **Rail:** flag, lap or clock, mode.
- **Tabs by session:**
  - Race: Timing · Track · Strategy · Activity
  - Qualifying: Timing · Cut line · Track · Activity
  - Practice: Timing · Runs · Track · Activity
- **Rows:** P · code + team · one primary value with a switch (INT/GAP, or TIME/GAP, BEST/GAP/LAST) · tyre. Transient chips take the team line.
- **Row tap** opens Driver Focus. Follow is explicit there, and in a race so is Compare with any driver. The follow strip is hidden while that driver's page is open.
- **Transport:** play, scrubber, ↩ and position, with a Playback sheet. Live has pause, a delay sheet and GO LIVE.
- **Moments:** a compact banner at the bottom of the content.
- **Landscape:** timing on the left and the chosen panel on the right.

### TV

- **Scaling** (owner-confirmed): one authored composition, scaled by `k = clamp(min(vw/1920, vh/1080), 0.5) × textSize`. The grid fills any aspect ratio. Below a 900 px wide window, offer the phone or desktop view.
  - Production: tokens, not zoom.
  - Validate at about 3 m on the target TV.
- **Persistent:** rail, tower (code + team), ticker with the brand bug.
- **Feature stage:** director rotation, or the viewer's pin. Chips are buttons; unavailable ones are disabled with a reason.
- **TIMING** is manual only. It widens the tower into the full table, and moment cards are suppressed while it is open (the ticker continues).
- **Toolbar:** appears on input and hides after 6 s. Contents: exit, features, follow, sync/delay, play, settings.
- **Sync panel:**
  - Live: presets, nudges, exact M:SS, pause, GO LIVE.
  - Replay: speed, sync offset, ±30 s.
- **Result** exists only after the flag, and is PROVISIONAL until final.
- **Qualifying and practice stages** (cut line, spread, following) are proposed additions. Each needs server inputs (phase policy, settlement state, on-track activity) and a missing-data behaviour before approval. No race strategy or battle concept appears in other session types.

### Standalone TV app (Android TV, planned)

The owner plans a standalone TV app that is just TV mode. Build the TV route so it can ship on its own:

- **Self-contained route:** no desktop chrome or desktop-only state. Launching it opens a TV session list; EXIT becomes SESSIONS (prototype: `tv.html?app=1`).
- **Any resolution or aspect ratio:** the single composition scales by `k`. At 4K, `k` is 2, or the WebView reports 1920×1080 at DPR 2; both give the same physical layout. Android TV's 960×540 dp base is the same 16:9 grid at 2×.
- **Remote first:**
  - D-pad spatial focus navigation across toolbar, panels and lists.
  - OK selects. Back closes in order: panel, then toolbar, then session list.
  - Media keys: play/pause, ⏪/⏩. With controls hidden, ←/→ move in time; in live, they move the delay.
  - No hover-only affordances. Every control has a visible focus state.
  - Prototype reference: `tv.js`, keys section.
- **Safe area:** a setting (off / 2.5% / 5%) moves content in while backgrounds stay full-bleed (`--safe-x`/`--safe-y`). Android TV's guideline margin is about 5% (48 × 27 dp).
- **Route options:**
  - A thin wrapper (WebView or TWA) around the React TV route reuses everything above. Map Android `KEYCODE_BACK` and the media keycodes to the same commands.
  - A native Compose-for-TV client would consume the same server contracts and viewer model (§2–§4).
- **Long sessions on OLED:** the calm green rail already keeps long green periods dark. Consider a slow 1–2 px pixel shift of the static chrome every few minutes.
- **Hardware:** TV SoCs are slow; the §9 rules (render on revisions, animate transforms only) are mandatory, not nice-to-have.

## 8. Brand

- **Components:**
  - `BrandMark` (size, static fallback)
  - `BrandOpening` (truthful phase text, sweep while loading)
  - `Kerb` (indeterminate progress)
- **Swap:** replace the files in `shared/brand/` and the mask in `brand.css`.
- **Where it moves:** only on a cold open.
- **Where it never moves:** reconnects, stale feeds, tab, driver or feature changes. It is never a connection indicator.

## 9. Performance

- Render facts on snapshot revisions and animate only transforms and map interpolation between them. The prototype rebuilds view models every frame; production should not.
- Memoize derived rows per revision and virtualize long histories.
- Profile frame time, long tasks and memory on TV hardware.

## 10. Acceptance checklist

1. No lost driver names at 320, 360, 390 and 430 (phone) or at 1024, 1280 and 1440 in every tower view (desktop).
2. The short-landscape phone layout is usable.
3. VSC, SC and flag cards never cover the leaders.
4. TV entry and exit keep the same source moment, mode, delay and followed driver.
5. Delay works from the product controls on every posture, with no debug UI.
6. No keyboard or remote path bypasses `can()`.
7. At cursor 1179, no event that needs evidence from 1184 is shown.
8. Flags and results never leak across a 30 s viewer delay.
9. Unknown data stays unknown.
10. Same-compound stops (PIA M → H → H) survive, including after the car stops.
11. Non-race sessions gain no race-only navigation or stages.
12. Reduced motion keeps every essential fact.
13. Pinning RESULT mid-race shows no winner.
14. A pinned non-adjacent pair shows the gap between those two cars.
15. Seeking during a VSC wipe never ends on a stale flag colour.
16. TV is fully operable with a D-pad remote: focus never gets lost, Back always closes the topmost layer, and media keys follow `can()`.
17. A story panel hidden during a seek reopens silently.
18. The phone's 44 px primary targets hold. Secondary text is 4.5:1 or better.
