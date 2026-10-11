# WP-1 for Astra — logic truth, the proof test, and retention sections

**From:** Claude (design lead on the session redesign)
**Inputs:** `design/_review/astra-review.md` (your review) and `design/_review/astra-pro-review.md` (second review). Finding IDs below refer to those files.
**Why you:** these items are logic-level and provable with Node. You can't open the prototypes in a browser, so Claude keeps everything visual and works on other files at the same time.

## Ground rules

- **Edit only these files:**
  - `design/prototypes/shared/engine.js`
  - `design/prototypes/shared/vm.js`
  - `design/prototypes/shared/analysis.js`
  - new `design/prototypes/shared/focus.js`
  - new `design/prototypes/data/server-context-fixtures.js`
  - new `design/tools/truth-test.mjs`, plus helpers under `design/tools/`
  - new `design/handoff/wp1-notes.md`
  - `design/tools/extract_recordings.py`, and regenerated `design/prototypes/data/*.js`, only if a fix needs per-field timestamps that the generated data does not have. Data stays git-ignored.
- **Do not edit anything else.** Claude is changing `tower.js`, `story.js`, `rail.js`, `player.js`, `track.js`, `modules.js`, all CSS, and the web/tv/phone/states HTML and JS. Do not commit. Do not touch `C:\GitClone\slipstream-f1-session-design-baselines` (read it only); it is needed for a live capture.
- **Stay backwards compatible.**
  - Keep every existing function name, signature and field. Add new fields and functions.
  - If a return shape must change, add a key and keep the old one working. For example, `SS.dryRule` keeps `{key, text}` and gains `key: 'unknown'`.
- **Same tech:** classic scripts on `window.SS`, no modules and no build step. Pages must still open from `file://`.

## Tasks

If time runs short, do them in this order: 1 → 12 → 2 → 3 → 4 → 6 → 9 → 5 → 7 → 8 → 10 → 11.

1. **Event availability contract** (C1/S1, S2, S3, S4, H1).
   - Every event gets `at`: the source time when it becomes knowable. `at` is never earlier than `t` (occurrence) and defaults to `t`.
   - `PASS` and `CONTESTED` use `at` = confirmation time. `LEAD_CHANGE` with cause ON_TRACK uses `at` = its confirm time.
   - `WINNER` and practice `SESSION_END` may use only facts at or before their `at`. The leader taking the flag is `state:'provisional'`. Remove `snapshot(event + N)` look-ahead (the WINNER card's `+20` is in describe/render paths).
   - `LAP_DELETED`: publish the message at the message time with no positional claim. Publish the position effect separately, when the order actually changes.
   - `PIT_IN` carries only entry-time facts. `PIT_OUT` carries lane time, and the new compound only if it has been observed by its `at`; otherwise `null`, rendered as unknown.
   - Add `state` (`'provisional' | 'confirmed' | 'corrected'`) and `supersedes` (an event id) where they apply. Keep ids stable.
   - `session.eventsBetween(t1, t2)` filters on `at`. Add `session.eventsUpTo(t)`: events with `at <= t`, sorted by `at`.
   - Wording in `SS.describe` follows C-Q1 and the second review's "conservative language".
     - An order change without an established cause says "moves ahead of" or "moves to P8", never "passes".
     - No pass language for order changes under non-GREEN track status (LEC/ANT at t≈4768).
     - Use `PIT EXIT`, not `OUT`. Keep `STOPPED` and `RETIRED` distinct.
     - Qualifying uses `ABOVE CUT` before settlement. Advancement language is only for the settled state.
2. **Tyres and stints** (B1, B4, B-Q1).
   - Fold observations only through the cursor, with per-field availability. The next compound stays unknown until it is observed.
   - A stopped or retired car's last stint ends at its last observed lap and carries `ended: 'stopped' | 'retired'`.
   - Completed stops come from exit evidence. Keep the ongoing stop separate: the vm row keeps `pits` and adds `stopsCompleted` and `inPitNow`.
3. **Pair gap** (B2). Add `SS.pairGap(s, vm, aheadNum, behindNum)` returning `{ v, laps, basis: 'interval' | 'gap-difference' | 'none', ahead, behind }`.
   - Use the interval only when the two cars are adjacent.
   - Use the gap difference when they are on the same lap.
   - Report the lap difference otherwise, and `null` when the gap is unknown.
4. **Pair history** (B3). Never read beyond `uptoT`.
   - Sample at the trailing car's completed-lap crossings, using data at that time.
   - Return `null` where the gap isn't comparable, so the chart can show the break.
5. **Race-now populations** (B5).
   - Groups: running, in pit, stopped, retired, finished. After the chequered flag, report finished/classified, not running.
   - Dry rule is met, needs another compound, or unknown (compound unknown, or the recording joined mid-race).
   - Update the facts copy to match.
6. **Battle eligibility** (C2).
   - One predicate, `SS.battleEligible(s, vm, row?)`: race, lap ≥ 3, track status GREEN only (not YELLOW, VSC, SC or RED), both cars running on the same lap, neither in the pit.
   - `vm.battleOn`, `row.battle` and the story battle runs all use it. Runs reset on caution.
7. **Live position estimate** (I1).
   - `progressAt(num, t, 'live')` uses past crossings only: the rate comes from earlier crossings.
   - Apply a freshness limit (stop advancing after about 1.5× the expected segment time) and never pass the next timing point.
   - Replay may keep interpolating between known crossings.
8. **Qualifying settlement** (I-Q1).
   - Settle when the flag has been shown and every car that was on track at the flag has completed that lap, entered the pit or stopped. Otherwise stay provisional; a timeout yields provisional, never settled.
   - Cut sizes come from a field-size policy (20 cars → 5/5, 22 cars → 6/6), exposed as `SS.qualiPolicy(s)`.
   - `ELIMINATED` and `POLE` carry `state`.
9. **Result eligibility** (E3). Add `SS.resultState(s, t)` returning `{ state: 'none' | 'provisional' | 'final', since }`.
   - `provisional` starts when the leader takes the chequered flag.
   - `final` only if the data carries a final-classification signal; otherwise never.
   - Claude does the rendering; you only provide this.
10. **Strategy context** (A3, W3) in `analysis.js`.
    - Remove the hard-coded "No specific Pirelli strategy published" and render from the context.
    - Add the driver- and pair-relevant published-strategy relationships the baseline shows (`web/components/analysis/PublishedStrategy.tsx`): option relationships, window states, tyre bank. Expose them as `SS.strategyContextHTML(s, vm, { driver })` and `SS.strategyContextHTML(s, vm, { pair: [a, b] })`.
    - Fill the landscape's published-window column from the options.
    - Add fixtures in `data/server-context-fixtures.js`, each marked illustrative:
      - no context
      - Hungary as supplied (no options)
      - two options with windows
      - an archival display-only reference
      - an unknown estimate
11. **Driver Focus sections** (A1, A4, A-Q3) in new `shared/focus.js`.
    - `SS.Focus.qualifying(s, num, now)`: Q status, teammate comparison, and the classified attempt history (phase, lap time, sectors, compound, new/used, tyre age, deleted/out/in-lap).
    - `SS.Focus.practice(s, num, now)`: conditions, factual pit history, runs.
    - `SS.Focus.paceChart(s, num, now, mode)`: mode `'laps'` (the existing lap chart) or `'pace'` (a placeholder labelled server analytics).
    - Return plain markup using the existing class vocabulary (`pnl`, `dp-*`). Claude will style it.
12. **The proof test** (H1 acceptance). Write `design/tools/truth-test.mjs` (Node, no dependencies).
    - Load `data/*.js` through a `window` shim.
    - For each T, build a Session from the data truncated at T (drop every frame, race-control message, pit record and session frame after T). Compare it with the full data viewed at T.
    - Compare:
      - events available at T (id, type, drivers, describe text)
      - vm rows (order, gaps, compound, stops)
      - stints and dry rule
      - race-now groups
      - pairHistory
      - battle flags
      - live progress estimates
    - T values:
      - pit fields: 721–750, 3440–3470
      - pass confirmation: 100–110, 1175–1190
      - VSC: 4760–4870
      - final laps and flag: 5960–6200
      - every penalty and deleted lap
      - qualifying: 150–160, 1290–1350, 1410–1425, 2600–2650
      - practice end
    - Print a table and exit non-zero on any mismatch. The only allowed exception is labelled replay interpolation.
13. **Notes.** Write `design/handoff/wp1-notes.md` covering:
    - API added and semantics changed
    - test output
    - anything not done, and why
    - anything Claude must wire up

## Done means

- `node design/tools/truth-test.mjs` passes.
- At cursor 1179, no event that needs 1184 is available.
- Flags and results don't leak across a 30 s viewer delay.
- Unknown values stay unknown.
- PIA's M → H → H survives, including after he stops.
- A Node smoke load of every prototype script raises no errors.
