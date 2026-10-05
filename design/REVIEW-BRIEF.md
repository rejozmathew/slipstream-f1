# Slipstream session redesign — review brief

> **Round 2 (4 Oct 2026):** both reviews have been worked through. See `handoff/review-response.md` for every finding's status, `handoff/implementation-notes.md` for the React spec, and `index.html` for the hub. Parts of §2 and §6 below describe round 1.

**For:** an independent reviewer (Astra).
**Status:** mid-point prototype for direction review. This is not production code and nothing is committed.
**Where:**
- Worktree: `C:\GitClone\slipstream-f1-redesign`
- Branch: `design/session-redesign`, created from `f6952e8`
- All design work is under `design/`.

**Please do not modify any files.** Report findings only (format at the end).

---

## 1. What this is

This is an evolutionary redesign of the session experience for TV, desktop and phone, built on the approved Claude Design language: Saira + JetBrains Mono and the existing palette. Three new cause colours were added: pit blue, gain green and loss red.

The goal is to make the experience more engaging and readable without inventing data:

- Order changes are animated by cause.
- A story layer explains what changed and why.
- TV mode gets a status rail that reacts to flags, plus moment cards.
- Every piece of information the current app shows is kept. This is an explicit owner requirement: any omission needs a stated reason.

The prototypes run on real recordings. Plain JavaScript (classic scripts, no build step) was chosen so it opens from `file://`. Production stays React with server-authored semantics.

| Session | Source |
|---|---|
| Hungarian GP 2026 race (key 11342) | Official timing archive, `output/recordings/f1-static-11342.json` |
| Bahrain GP 2026 qualifying (Kuala Lumpur, key 11730) | Recorded live, `output/recordings/live-11730.json`. Recording starts at the end of Q1. |
| Bahrain GP 2026 practice 2 (Kuala Lumpur, key 11728) | Recorded live, `slipstream-f1/recordings/live-11728.json`. Joins mid-session. |

## 2. How to open

Open these directly in Chrome or Edge from `design/prototypes/`:

| File | What |
|---|---|
| `tv.html` | TV mode at 1920×1080, scaled to the window. A review panel sits bottom right (H hides it). |
| `web.html` | Desktop: session page, plus Driver, Battle and Strategy pages from the nav. |
| `phone.html` | Phone. Use a 390×844 window or the device toolbar. |
| `states.html` | Library and downloads, opening, the live lifecycle, live vs replay, missing data, results, settings, errors. |

**Data files:** `design/prototypes/data/*.js` are generated from the recordings by `design/tools/extract_recordings.py`. They are git-ignored (see AGENTS.md: never commit recordings). `data/server-context.js` holds the Pirelli context exactly as the current server showed it for Hungary.

**Captures:** short TV videos and screenshots are in `design/_review/captures/` (git-ignored). `design/tools/capture.py` regenerates them.

### Useful URLs (append to the file path)

| Scenario | Query |
|---|---|
| TV · race start | `tv.html?s=hungaroring-2026-race&t=-25&speed=5` |
| TV · first pit cycle | `tv.html?s=hungaroring-2026-race&t=1101&speed=10` |
| TV · on-track lead change, then the battle feature | `tv.html?s=hungaroring-2026-race&t=3880&speed=2` |
| TV · yellow, then VSC, then the leader stops | `tv.html?s=hungaroring-2026-race&t=4766&speed=3` |
| TV · chequered flag, penalties applied, result | `tv.html?s=hungaroring-2026-race&t=5960&speed=3` |
| TV · qualifying, laps completed after the flag change the cut | `tv.html?s=kl-2026-qualifying&t=1262&speed=3` |
| TV · pole | `tv.html?s=kl-2026-qualifying&t=2440&speed=2` |
| TV · practice (no circuit outline) | `tv.html?s=kl-2026-practice-2` |
| TV · simulated live: feed drop (review panel) and delay panel (D key or click LIVE) | `tv.html?s=hungaroring-2026-race&t=2400&live=1` |
| TV · variants | add `&reduced=1`, `&map=line` (no outline) or `&map=none` (no positions), `&module=track\|battle\|pits\|driver\|result`, `&follow=1` |
| Desktop · race session | `web.html?s=hungaroring-2026-race&t=2400` (add `&tower=timing` or `&tower=strategy`) |
| Desktop · deep pages | add `&view=driver&driver=1`, `&view=battle` or `&view=strategy` |
| Desktop · live chrome | add `&live=1` |
| Desktop · qualifying and practice | `web.html?s=kl-2026-qualifying&t=1330&speed=2` · `web.html?s=kl-2026-practice-2` |
| Phone | `phone.html?s=hungaroring-2026-race&t=1101` (add `&tab=track\|story\|more`, `&more=battle\|pits\|driver\|result`, `&live=1`) |

## 3. Ground rules the design claims to follow (please check against these)

1. **Only data Slipstream has.**
   - Positions are `track_position`, which is quantized to timing points: 22 per lap at Hungaroring, 20 at Kuala Lumpur. Markers interpolate between crossings in replay. In live they use capped dead-reckoning that never passes the next timing point. They are always labelled approximate.
   - There is no sector purple/green grading in the feed, so sector times are shown plain.
   - There is no telemetry, DRS, speed traps or radio.
   - For pit stops the feed gives pit-lane time only; there is no stationary time.
   - Weather is air, track, humidity, pressure, rainfall and wind.
   - Overtake ON/OFF comes from race control messages.
2. **Live vs replay is unmistakable.**
   - Live is a solid red badge with no progress line and no seek.
   - Replay is grey and outlined, with a progress line and the full transport.
3. **A jump is not news.** Seeking, skipping, changing delay, reconnect catch-up and reload all snap without motion. They produce no moment cards and no "new" items in the story.
4. **A classification change is not an overtake.** Pit-induced moves, stopped cars, post-flag classification and penalties each have their own motion and copy.
5. **Information retention:** see the map in section 4.
6. **Delay controls exist everywhere.**
   - Live: 5s–5m presets, a custom M:SS field, Apply and Go Live.
   - Replay: speed 0.5–120× plus sync delay with Apply.
   - TV: D key or click the LIVE badge.
   - Phone: a delay selector in the bottom bar.
7. **Reduced motion is respected.** The system setting is honoured and there is a toggle. Rows snap, rail changes are outlined, and moment cards appear without travel.
8. **Missing capability is said plainly.**
   - Kuala Lumpur has no outline, so it shows a straightened track line with its timing points.
   - No positions at all falls back to the race-order-in-time ribbon.
   - A missing value in a row shows "—".
9. **The story layer is causal.** Events only use facts known at that moment. In the prototype it is derived client-side in `shared/engine.js` (`SS.classify`); in production it should live in the server `AnalyticsSnapshot`.

## 4. Information retention map (current app → redesign)

Please verify this against the current app: the baseline worktree `C:\GitClone\slipstream-f1-session-design-baselines`, views under `web/views` and captures under `output/playwright`.

| Current | Redesign | Notes |
|---|---|---|
| Header: brand, nav (Session / Driver / Battle / Strategy / TV / Settings), connection state, library | Same | Library list also in `states.html#library` |
| Session strip: mode, meeting, session, date, local time, lap, status | Status rail | Flag word plus sector, lap and to-go, chips (overtake, fastest, rain, track/air temperature), date and track-local clock, mode badge with speed, sync and delay |
| Tower views Standard / Timing / Strategy, split presets, Edit | Same | Columns: P, driver/team, gap, int, tyre+age, last, pit · sectors, last, best · stint, pit, tyre strategy, last stop |
| Strategy context panel (Pirelli, race now, now facts, View strategy) | Same | Pace context labelled as server analytics |
| Track map panel (lap, shape and position provenance, coverage) | Same, plus race-order ribbon | Cars sharing a spot become one marker with a count |
| Conditions | Same, plus wind direction | |
| Race control (latest, count) | Same | Shows lap and track-local time |
| Replay controls | Same, plus event markers and a moments menu | |
| Live controls | Same | |
| Driver page | Same sections | The stint trend chart (server pace delta) becomes a lap-times-this-stint chart from timing. Outlook is server-only and labelled. |
| Battle page | Same sections, plus lap-by-lap times | Battle score is server-only and labelled |
| Strategy page | Same sections, plus a stints-by-lap chart | Pace context is server-only and labelled |
| TV states: tower, track, strategy, battle, driver; rotation; alerts; preferences | Tower always visible; features: track, battle, strategy, following, result; auto director with pin; moment cards; ticker | Battle mode recommended or leader in the panel; pinned is in settings |
| Qualifying and practice views | Same columns | Q1/Q2/Q3 or best, gap, int, tyre+age, status · last, best, gap, int, stint, stops, status. Plus a session panel and cut-line / spread panels. |
| Phone tabs | **Incomplete:** order, track, story, more | Strategy, conditions and race control still to add |
| Settings: appearance, layouts, TV preferences | `states.html#settings` | Display (incl. accent), motion, TV, layouts, live |

## 5. What to review

- **A. Retention.** Anything from the current app that is missing, degraded or harder to reach, with screen and steps.
- **B. Data honesty.** Any displayed value not backed by the recording or the server. Please check these derivations against the raw recording:
  - stints and tyre sequences (`SS.stints`)
  - the dry-tyre rule
  - race-now facts and stint context
  - places gained since the start
  - battle definition (≤ 1.0 s, lap ≥ 3, green flag)
  - pair gap history
  - quali cut and settle logic
- **C. Story layer.** False, missing or mis-timed events, and wording. Focus on:
  - passes vs pit, stopped and classification changes
  - lead-change causes
  - drop zone after the flag
  - eliminations and pole settling
- **D. Motion.** Durations and easing by cause (`shared/tower.js` `DUR`/`EASE`), jumps, reduced motion, rail escalation (wipe plus 3 blinks) and de-escalation.
- **E. TV.** Legibility at about 3 m, director rotation, holds and pins, moment cards (never over the tower), ticker, stale and reconnect, and the delay panel.
- **F. Desktop.** Hierarchy and density, the three tower views, the analysis stack, deep pages, and transport usability.
- **G. Phone.** Only the parts that exist; phone retention is a known gap.
- **H. Feasibility for the React app.**
  - What must move server-side (story events, pass confirmation, settle logic).
  - New fields needed: last-lap PB/fastest flags, interval trend, coverage.
  - Performance at 22 rows with transform-based motion.
- **I. Prototype code that would mislead a port.** Wrong assumptions, hidden coupling, client-side analytics.

## 6. Known gaps (please don't report these)

- The phone has not had the keep-everything pass yet (strategy, conditions, race control).
- On TV, the weather chip in the top bar is clipped at 1920 when many chips are present.
- Battle score, pace fade and driver outlook are server analytics. They appear as labelled placeholders, not numbers.
- Not written yet: the review hub (`design/index.html`), `design/README.md` and implementation notes for the build.
- Library and download states on `states.html` are illustrative. Names and dates come from the catalog.
- Desktop screenshots in older capture runs predate the information-retention rebuild.

## 7. How to report

Group findings by area A–I. For each one give:

- **Severity:** blocker, major or minor.
- **Where:** file or screen, plus the URL query to reproduce.
- **What you saw** and what you expected.
- **Why it matters.**
- **Suggested fix.**

Keep **bugs** separate from **design questions**. End with the top five changes you'd make before this goes to implementation.
