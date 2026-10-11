# Review response — round 2

This document answers the review of the Slipstream session-redesign prototype. The inputs are:

- `_review/astra-review.md` ("Ultra", finding IDs A1–I-Q1)
- `_review/astra-pro-review.md` ("Pro", finding IDs M1–W3 and S1–S4)
- the owner's notes: the icon, a denser desktop and a loading animation

## Status key

| Status | Meaning |
|---|---|
| **Done** | Built in the prototype. Where to look is given. |
| **WP-1** | Logic or data work handed to Astra in `handoff/astra-wp1-logic.md`. The UI side is already wired to it. |
| **Partly** | Part of it is built; the reason for the rest is given. |
| **Declined** | Not done, with the reason. |
| **Owner** | Needs your device or a decision from you. |

Paths are relative to `design/prototypes/`.

## Owner's notes

| Note | Status | What changed |
|---|---|---|
| Use the icon (SS, slipstream and heat, Eau Rouge kerbs) | Done | One swappable brand piece: `shared/brand/` and `brand.css`, with `SS.brand` in `shared/contract.js`. It appears in the desktop header, the phone app bar, the TV ticker, favicons and `states.html#brand`. The approved accent (#ff3d24) already matches the mark, so no new UI colours were added. |
| Pages feel zoomed in; about 75% is better | Done | A display-size setting with 75 / 80 / 90 / 100%; the default is 80%. Analysis presets put map, strategy, story, conditions and race control on one 1440×900 screen. The smallest labels went up a step and secondary-text contrast was raised, so 75–80% stays readable. |
| Animated version for loading | Done | Cold open: a hot highlight runs through the SS, with the real loading step written underneath and no percentages. The red/white kerb is the indeterminate "working" bar for downloads and connecting. The mark is still under reduced motion and never returns on reconnect. See `web.html?…&opening=1` and `states.html#opening`. |

## Retention (Ultra A)

| ID | Finding | Status | Where / note |
|---|---|---|---|
| A1 | Qualifying Driver Focus lost Q status, teammate comparison and attempt history | WP-1 + Done | The phone driver page shows Q1/Q2/Q3, cut status and on-track state. Full attempt history and teammate comparison come from `SS.Focus.qualifying` (WP-1); desktop and phone call it when present. |
| A2 | TV tower dropped columns | Done | TIMING (T or toolbar) widens the tower into the full table for every session kind (`tv.js` COLS.wide). The compact tower keeps code, team, interval, gap, tyre and pit. |
| A3 | Published strategy context became generic | WP-1 | `SS.strategyContextHTML` plus illustrative option fixtures in `analysis.js`. |
| A4 | Strategy tower lost INT; practice focus lost conditions and pit history | Done + WP-1 | INT is back in the strategy tower. Practice conditions and pit history: `SS.Focus.practice` (WP-1). |
| A5 | Entering TV dropped viewer context | Done | `SS.viewer` carries session, cursor, mode, delay, speed, play state, followed driver, pinned pair and motion between desktop, TV and phone, in both directions. |
| A-Q1 | Team names on TV and phone | Done | TV rows show code + team. Phone rows show code + team, and chips take the team line. |
| A-Q2 | Brand slot in all postures | Done | See the owner's notes. |
| A-Q3 | Raw lap times are not the server pace delta | WP-1 | `SS.Focus.paceChart(mode)` keeps both: lap times from timing, and pace labelled as server analytics. |

## Data honesty (Ultra B)

| ID | Finding | Status | Where / note |
|---|---|---|---|
| B1 | Future tyre observations leak into strategy and dry rule | WP-1 | — |
| B2 | Pinned non-adjacent pair showed the wrong gap | Done + WP-1 | `BattleView` shows the interval only for adjacent cars; otherwise the gap between them, a lap difference or unknown. PIA vs VER now reads 4.932. Server semantics come from `SS.pairGap` (WP-1). |
| B3 | Gap history read beyond the cursor | WP-1 | — |
| B4 | A stopped car's final stint vanished | WP-1 | — |
| B5 | Race-now groups lose lifecycle meaning | WP-1 | — |
| B-Q1 | Meaning of a completed stop | WP-1 | Counted at pit exit; an ongoing stop is shown separately. |

## Story layer (Ultra C, Pro S1–S4)

| ID | Finding | Status | Where / note |
|---|---|---|---|
| C1 / S1 | Confirmed passes published early | WP-1 + Done | Every consumer now filters on availability (`SS.avail`: `at`, else `t`): feed, ticker, takeovers, markers, driver moments, logs and result. The engine adds `at` (WP-1). Tower motion is neutral outside green running. |
| S2 | Result narration borrows later classification | Done + WP-1 | The WINNER card uses only the state at the viewer's moment, is labelled PROVISIONAL, and shows "ON FINAL LAP" for cars not yet finished. The engine-side `at` is WP-1. |
| S3 / S4 | Deleted-lap effect and pit enrichment look ahead | WP-1 | — |
| C2 | Battles under yellow or VSC | WP-1 + Done | The eligibility predicate is WP-1. The tower no longer styles non-green moves as passes. |
| C3 | Hidden feed replays news after a seek | Done | Navigation generation (`player.gen`). Feeds and the ticker render silently after any jump or when revealed again (`shared/story.js`). |
| C-Q1 | Ambiguous labels (OUT, SAFE) | WP-1 + Done | Tower chip changed to ABOVE CUT. The `describe()` copy (PIT EXIT, RETIRED/STOPPED, ABOVE CUT) is WP-1. |
| Story contract | Occurrence vs availability, state, supersession | Done (spec) + WP-1 | `implementation-notes.md` §4; engine fields in WP-1. |
| Inspect vs replay, spoilers | — | Done | Tapping a story item shows details (happened at, known at, drivers); REPLAY is a separate button. ↩ returns you to where you were. Timeline markers and moments only show what you have already watched unless you turn spoilers on. Live shows no rewind and says why. |

## Motion (Ultra D)

| ID | Finding | Status | Where / note |
|---|---|---|---|
| D1 | A stale rail animation overwrote status | Done | A generation token cancels in-flight wipes, blinks and callbacks (`shared/rail.js`). |
| D2 | Reduced motion was partial | Done | One policy, `SS.motion`: system setting or explicit choice, reacts to system changes, finishes running effects. A blanket CSS rule stops travel, pulses, blinks and marching stripes. Phone has a motion setting in its menu. |
| D-Q1 | Fast replay | Done | From 5×, moves are shorter and only the newest pending card survives. From 20–30×, rows snap and only results and red flags get cards, and the director stops chasing events. |

## TV (Ultra E, Pro T)

| ID | Finding | Status | Where / note |
|---|---|---|---|
| E1 / T3 | Live accepted replay keys | Done · live pause policy confirmed by owner | `player.can()` guards every path. In live, Space pauses (the delay grows) and ←/→ change the delay; no seek or speed. Escape closes, focus is restored, and stage chips are real buttons. |
| E2 / T2 | Delay and transport contract | Done | The toolbar appears on any key or pointer move. The sync panel has presets, nudges, an exact M:SS with Apply, Pause and GO LIVE; in replay, speed 0.5–120×, sync offset and ±30 s. The rail badge keeps "LIVE −0:30". |
| E3 | Pinned Result crowned a mid-race winner | Done | "No result yet" before the flag; PROVISIONAL after it; the chip is disabled with a reason. Uses `SS.resultState` (WP-1) when present. |
| E-Q1 | Interaction and settings inventory | Done / Owner | Settings now list rotation interval, following, pinned pair, feature size, TV text size and tower names. Checking legibility at 3 m on your TV is yours. |
| T1 | Team identity | Done | See A-Q1. |
| T4 | Viewer context | Done | See A5. EXIT TV returns to the page you came from. |
| T5 | Fixed-stage scaling | Partly · owner confirmed the approach | The canvas now scales to the screen and fills any aspect ratio (16:10, 21:9, 4:3) instead of letterboxing. There is a minimum scale and a TV text-size option, and phone-sized windows are offered the phone view. **Not done:** separate re-laid-out breakpoints. On a TV, readability depends on screen size and distance, not pixel count, so one authored composition scaled to the screen is the 10-foot convention. Production should still build this with tokens, not CSS zoom. The owner plans a standalone Android TV app built from TV mode. Remote navigation, a safe-area setting and a session list for standalone use are now in the prototype (`tv.html?app=1`). |
| T6 | New qualifying and practice stages | Owner + spec | They are kept as proposed additions. Each needs server inputs and a missing-data behaviour (implementation notes §7). No race-only stage appears in other session types. |

## Desktop (Ultra F, Pro W)

| ID | Finding | Status | Where / note |
|---|---|---|---|
| F1 / W1 | Splits collapsed driver identity | Done | Identity has a 140 px minimum. Columns drop by priority ("+N HIDDEN" with a tooltip); past that, the tower scrolls sideways inside its own panel. Re-fits on any resize. Verified at 1440, 1280 and 1024. |
| F-Q1 / W2 | Map-heavy hierarchy | Done | Analysis presets: BRIEF (map + strategy, then story + conditions + race control), MAP (large map) and STORY. Map size S/M/L. Split presets and EDIT LAYOUT remain. Rows fill the tower height. |
| W3 | Strategy content recomputed and hard-coded | WP-1 | — |

## Phone (Ultra G, Pro M)

| ID | Finding | Status | Where / note |
|---|---|---|---|
| G1 | No session identity | Done | App bar with mark, session and switcher sheet. |
| G2 | Live story invited a no-op | Done | Hints and actions depend on the mode. |
| G-Q1 / M1 | Rows over-constrained | Done | Code + team, one primary value with a GAP/INT (or TIME/GAP) switch, and tyre. No clipping at 320. 36 px rows; 15–16 rows visible at 390×844. |
| M2 | Navigation excluded capabilities | Done | Session-aware tabs: Timing, Track, Strategy (race) or Cut line / Runs, Activity (story + full official race control). Menu holds desktop, TV, settings and motion. |
| M3 | Follow and focus conflated | Done | Row tap opens Driver Focus. Follow is an explicit button there; the follow strip has ×. Compare picks any two drivers (race). |
| M4 | No landscape | Done | Timing on the left, chosen panel on the right, one-row top bar. |
| M5 | Transport too compressed | Done | Slim bar plus a Playback sheet (position, ±30 s, speed, sync offset, moments) or a Live delay sheet (presets, ±5 s, M:SS, Pause, GO LIVE). Replay never says LIVE. |
| M6 | Takeover covered leaders | Done | A compact banner at the bottom of the content. |
| M7 | Track and story used space unevenly | Done | The map labels the followed driver and its neighbours. Story has filters, detail-on-tap, older battles marked EARLIER, and keeps your scroll position with an "N new ↑" pill. |
| Targets | 44 px primary controls | Done | Tabs 58, transport 40–44, sheet buttons 44. |

## Feasibility and port hazards (Ultra H, I)

| ID | Finding | Status | Where / note |
|---|---|---|---|
| H1 | One causal story contract | Spec + WP-1 | Implementation notes §4; truncation test in WP-1 (`tools/truth-test.mjs`). |
| H2 | Render facts on revisions, not frames | Partly | Slow panels already refresh on a ~450 ms tick and the tower diffs cells. The full revision-based pipeline is specified for React (implementation notes §9) rather than rebuilt in the prototype. |
| I1 | Live interpolation used a future crossing | WP-1 | — |
| I2 | Capability applied inconsistently | Done | `SS.capabilities()` is passed to every feature. TV Following without positions says so. Server-sourced coverage is a WP-1 note. |
| I-Q1 | Qualifying settlement and cut sizes | WP-1 | — |

## Accessibility (Pro)

- **Contrast:** `--text-3` raised from #5b6674 to #7a8594. That is 4.5:1 or better on every surface; the approved value measured 2.9–3.4:1.
- **Semantics:** feed items are focusable buttons (Enter or Space opens them). TV stage and toolbar controls are buttons with visible focus. Phone sheets and the TV sync panel take focus, close on Escape and return focus.
- **Not done:** a full screen-reader audit. The absolutely positioned tower rows need reading-order testing in the React build.

## Declined, with reasons

- **Running real server analytics inside the prototype.** That needs the backend running locally next to the recordings, and the live-capture worktree must stay untouched. It remains a hard requirement for the React build (implementation notes §2).
- **Separate TV breakpoint layouts.** See T5.
- **Cross-device sync, auth and admin.** Outside this presentation pass, per both reviews and the roadmap.
