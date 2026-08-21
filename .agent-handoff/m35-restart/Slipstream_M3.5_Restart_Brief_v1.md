# Slipstream F1 — Milestone 3.5 Clean Restart Brief v1

**Repository:** `https://github.com/rejozmathew/slipstream-f1`  
**Authoritative restart base:** `agent/milestone-3.5-improvements` at commit  
`16fa0b5a65a9611a8a408516fa786611bff09bca`

**Failed/reference branch only:** `agent/milestone-3.7-improvements`  
Current 3.7 head at review time: `72df2f48aa99cfb0ebc5417cc8d1b3a716a9e7f7`

**Recommended new working branch:** `agent/milestone-3.5-restart`

**Do not merge to `main`. Do not build on 3.7. Do not cherry-pick 3.7 wholesale.**

---

# 0. Why this restart exists

Two implementation passes claimed substantial or complete Milestone 3.5 progress while leaving major factual, analytical, and visible product requirements incomplete.

This restart is designed to prevent a third pass from confusing:

> "I changed code in this area"

with:

> "The required behavior works, is visible in the product, is deterministic in replay, and is proven by tests."

The goal is not to make the requirements longer. The goal is to make completion **observable and falsifiable**.

The `agent/milestone-3.7-improvements` branch is preserved only as a failed/reference implementation. It is not the implementation base for this restart.

---

# 1. Source hierarchy

Use these sources in this order:

1. **This restart brief** — normative execution and acceptance contract.
2. **The attached annotated screenshots** — visual/product defect evidence and owner intent.
3. **`Slipstream_Milestone_3.5_Remaining_Work_After_Partial_Implementation.md`** — detailed technical source material from the earlier review.
4. Repository architecture and protocol documents:
   - `AGENTS.md`
   - `ARCHITECTURE.md`
   - `docs/protocol.md`
   - `ROADMAP.md`
   - `IMPLEMENTATION_MAP.md`
   - `docs/analytics.md`
   - `CHANGELOG.md`
5. **Actual code and tests on the restart base** — when docs disagree with code, report the mismatch before changing behavior.

The annotated screenshots are **not final mockups to reproduce pixel-for-pixel**. They show the current/failed UI with red owner comments. The red callouts are the requirement signal. Preserve the established Slipstream visual system unless a callout or this brief explicitly requires a change.

If this brief conflicts with the older handoff, this brief wins.

Do not treat claims in `CHANGELOG.md`, `IMPLEMENTATION_MAP.md`, or comments as proof that behavior exists.

---

# 2. Mandatory restart procedure

Before modifying any file:

```bash
git fetch origin
git status
git branch --show-current
git rev-parse HEAD
git log --oneline --decorate -n 15
```

The new branch must be created from exactly:

```text
16fa0b5a65a9611a8a408516fa786611bff09bca
```

Recommended:

```bash
git checkout -b agent/milestone-3.5-restart \
  16fa0b5a65a9611a8a408516fa786611bff09bca
```

Then report:

```text
START_BRANCH=
START_HEAD=
WORK_BRANCH=
WORKTREE_CLEAN=yes/no
```

If the environment cannot create or switch branches, stop and report the constraint. Do not silently continue from 3.7 or another HEAD.

Do **not** commit this prompt, the screenshots, or other handoff artifacts into the repository unless the owner explicitly asks.

---

# 3. Execution model — packets, not one giant pass

Milestone 3.5 will be completed in gated packets.

**Do not implement all packets in one run.**

The first run implements **Packet A only**, validates it, reports evidence, and stops for owner review.

Packets:

- **Packet A — Factual lifecycle and terminal semantics**
- **Packet B — Viewer Live/Replay session mode**
- **Packet C — Strategy core, RaceRead, projection correctness**
- **Packet D — Strategy, Driver, and Battle product surfaces**
- **Packet E — TV, context/backtest truthfulness, contracts, docs, final validation**

The owner must explicitly authorize moving to the next packet.

A later packet may depend on an earlier packet, but an earlier packet must not be declared complete because a later packet would eventually hide its defect.

---

# 4. Permanent architecture invariants

These are non-negotiable.

## 4.1 Factual state vs analytics

`RaceState` is the canonical factual state.

`AnalyticsSnapshot` is a separate deterministic analytical sidecar.

Do not move analytical conclusions into `RaceState`.

Do not make React or TV rebuild Strategy math.

## 4.2 Replay determinism

At a given replay cursor, the result must be reproducible.

No future evidence may leak backward.

Analytics for viewer A at cursor X must not depend on which cursor viewer B requested first.

Request history is not source history.

## 4.3 Source neutrality

Provider-specific parsing belongs at the adapter/normalization boundary.

Analytics must not parse OpenF1/F1 raw prose directly to infer factual lifecycle.

The factual layer should expose source-neutral state before analytics consumes it.

## 4.4 Truthful uncertainty

`UNKNOWN` is correct when evidence is insufficient.

Do not display plausible-looking invented numbers, fake context, canned metrics, or "stable" merely because the real metric is absent.

## 4.5 Strategy hierarchy

Use:

```text
FACTS
→ CONTEXT
→ CONSTRAINTS
→ TRENDS
→ OUTLOOK only when evidence earns it
```

The product should always tell the viewer what is happening, usually what it means, and only sometimes what it predicts.

## 4.6 No LLM in the live Strategy path

Broad race/driver commentary should be deterministic formatting of computed facts.

## 4.7 Milestone 4 boundary

Do not implement M4 features here:

- SQLite ownership/persistence redesign
- Admin
- authentication
- Viewer Profiles
- anonymous policy
- persistent user preference backend
- recording deletion lifecycle

M3.5 may clean ownership semantics so M4 can build on them, but must not absorb M4.

---

# 5. Global completion rules

These apply to every packet.

## 5.1 Requirement status is binary and evidenced

For each requirement ID report exactly one of:

```text
PASS
FAIL
BLOCKED
NOT STARTED
```

"Mostly done", "substantially complete", "implemented conceptually", or similar language is not accepted.

## 5.2 No proof = no PASS

A requirement cannot be marked PASS unless the required proof exists.

Proof may include:

- named automated test(s)
- typecheck/build result
- replay checkpoint state
- running-app screenshot
- API payload sample
- deterministic replay comparison

## 5.3 UI requirements require rendered proof

For any requirement that changes what a user sees, provide a screenshot from the **running app**, not only code diffs.

If the agent environment cannot run/render the browser, mark the visual acceptance portion **BLOCKED** and do not claim the UI requirement is complete.

## 5.4 No placeholder completion

Any of the following in a production-facing path is an automatic failure unless explicitly required as the truthful unavailable state:

- fake "MAP" boxes
- "not yet implemented" inside a supposedly completed feature
- hard-coded race-specific analytical statements
- canned Pirelli/history/backtest numbers
- hard-coded stint ranges such as `12–16 laps`
- `"stable"` when the value is unknown
- visually empty panels pretending to contain analytics
- placeholder Strategy outlook presented as real
- fake axis-less charts with undefined sampling

Truthful `UNAVAILABLE`, `UNKNOWN`, or hidden optional content is preferable.

## 5.5 Changelog comes last

Do not update `CHANGELOG.md` to claim a feature until its acceptance tests and visual evidence pass.

## 5.6 Tests must accompany fixes

For correctness defects, add a regression that would fail on the restart base.

A code change without a regression test is not complete unless there is a documented reason the behavior cannot be automated.

## 5.7 Final report is forensic

At the end of a packet provide:

| Requirement | Status | Files changed | Tests | Runtime/replay proof | Screenshot proof | Known limitation |
|---|---|---|---|---|---|---|

Do not create a commit named "complete milestone 3.5" unless every packet has been owner-reviewed and all merge gates pass.

---

# 6. Annotated screenshot manifest

The package contains eight unique screenshots. One duplicate uploaded screenshot was intentionally omitted.

## S01 — `S01_session_timing_strategy_retirement.png`

Current Race Session page.

Owner callouts:
- skepticism about the Strategy Outlook shown in the right rail;
- concern that the same race-wide information is not represented coherently on the Strategy page;
- driver 22 appears retired but is still rendered as an ordinary live timing participant;
- a retired driver must not continue receiving future Strategy.

Acceptance signal:
- retirement must be obvious and consistent end-to-end;
- Session Strategy is a compact race summary, not a random driver's plan;
- race-wide Strategy page and Session summary must share the same backend truth.

## S02 — `S02_strategy_overview_density_context.png`

Current Strategy overview.

Owner callouts:
- large amount of wasted space;
- tyre information should use compact tyre visual language where useful;
- high-level race interpretation is missing;
- field boxes can be denser;
- Official Pre-Race / Historical context saying "Absent" is unexplained and may not be wired.

Acceptance signal:
- add a first-class Race Read;
- improve information density without abandoning the current design system;
- context must be real or truthfully unavailable with reason.

## S03 — `S03_strategy_terminal_semantics.png`

Driver Strategy table at lap 70/70 and CHEQUERED.

Owner callout:
- a retired driver still appears to have a future pit plan;
- many rows say `TO FLAG` despite the race already being over.

Acceptance signal:
- terminal race is retrospective;
- no future pit window, next compound, Primary/Alternate future plan, or `TO FLAG` at CHEQUERED;
- driver terminal state must be factual.

## S04 — `S04_battle_recommendation_layout.png`

Battle overview near lap 69.

Owner callouts:
- Recommended pair jumps too frequently;
- a pair should persist long enough to be useful;
- center space could host a focused two-driver track map;
- driver cards feel overly stretched.

Acceptance signal:
- deterministic stabilization from source history;
- focused battle map;
- better use of center space.

## S05 — `S05_battle_history_interaction.png`

Lower Battle page.

Owner callouts:
- gap-history graph has no clear axis/time/lap meaning;
- interaction section is always empty.

Acceptance signal:
- gap history should be by completed laps with clear semantics;
- shared Strategy interaction must contain actual information or truthfully say unavailable;
- no permanently empty production panels.

## S06 — `S06_driver_focus_read_map_pits.png`

Driver Focus.

Owner callouts:
- use available space for broad deterministic driver commentary / Driver Read;
- selected driver should be visually highlighted on the map; ordinary dots are not useful enough;
- Strategy cards sometimes disappear without explanation;
- pit history should be compact;
- compound transitions should show correctly, including later transitions;
- stop numbering/count should be obvious.

Acceptance signal:
- add deterministic Driver Read;
- focused map;
- compact accurate pit history;
- stable truthful Strategy availability.

## S07 — `S07_tv_track_tower_colors.png`

TV Track page.

Owner callouts:
- TV timing tower only shows four drivers and feels too sparse;
- track dots should follow a consistent team-color identity across TV and non-TV views.

Acceptance signal:
- TV field representation must be intentionally designed, not arbitrarily top-4;
- use one global driver/team color language.

## S08 — `S08_tv_driver_layout_status.png`

TV Driver page.

Owner callouts:
- race-status band is too thin/weak;
- race-status color should be more visibly integrated into the page/header;
- alignment, font sizing, whitespace and pace-chart layout are visibly broken.

Acceptance signal:
- stronger semantic GREEN/YELLOW/SC/VSC/RED/CHEQUERED presentation;
- repair layout and information hierarchy;
- TV remains across-room readable.

---

# 7. Packet A — Factual lifecycle and terminal semantics

**This is the only packet to implement in the first run.**

Goal:

> A driver's factual lifecycle at a replay cursor must be correct before Strategy, Battle, Driver, Timing, Track, or TV is allowed to reason about that driver.

## LIFE-01 — One canonical lifecycle vocabulary

Maintain one backend lifecycle vocabulary.

At minimum distinguish:

```text
RUNNING / circulating
STOPPED but potentially resumable
RETIRED
FINISHED
DNF
DNS
DSQ
UNKNOWN
```

Exact internal naming may vary if existing contracts require compatibility, but meanings must not collapse.

### Required

- `STOPPED` must not be in the terminal set.
- `display_status_label(STOPPED)` may return `STOPPED`.
- `terminal_state(STOPPED)` must return `None`.
- RETIRED/DNF/DNS/DSQ are terminal.
- Unknown status must not silently remove a participant merely because data is missing.

### Test proof

Add explicit tests for:

```text
STOPPED is non-terminal
STOPPED has visible label
RETIRED is terminal
DNF is terminal
DNS is terminal
DSQ is terminal
UNKNOWN does not silently become terminal
```

## LIFE-02 — Resolve participant/circulating/terminal concepts

Do not use one ambiguous "active" predicate for every question.

Model and document the distinctions needed by consumers:

- participant in the session/race population;
- currently circulating;
- temporarily stopped but potentially resumable;
- terminal/non-running;
- Battle eligible.

Do not reflexively add `position is not None` to the canonical participant predicate without proving startup behavior remains correct. Initial driver metadata can exist before position events.

If a position requirement is needed for a narrower concept, create that narrower concept explicitly.

## LIFE-03 — Cursor-safe mid-race STOPPED/RETIRED updates

The adapter/normalization path must convert timestamped factual source evidence into source-neutral driver lifecycle updates.

### Required

- before the source event, the driver is not retrospectively retired;
- at the source event, state changes at that cursor;
- final session result must never leak DNF/retirement backward;
- `STOPPED` is not automatically retirement;
- only explicit/reliable evidence may establish RETIRED;
- if later evidence proves a stopped driver resumed, state may return to circulating/RUNNING;
- document what factual evidence is accepted as proof of resumption.

Do not have analytics parse provider text directly.

## LIFE-04 — Session-end finalization

At the end of the session, final classification/result evidence may finalize:

```text
FINISHED
DNF
DNS
DSQ
RETIRED where the source supplies it
```

But final results remain timestamped at the end and cannot rewrite earlier replay cursors.

## LIFE-05 — Terminal Strategy suppression

For a terminal driver at the cursor:

- no future pit window;
- no likely next compound;
- no future Primary Strategy;
- no future Alternate Strategy;
- no Free Stop / rejoin future projection;
- no Battle eligibility;
- factual terminal label is published for frontend rendering.

`STOPPED` is not automatically subjected to terminal suppression merely because it has a display label.

## LIFE-06 — Race terminal semantics

At:

```text
CHEQUERED
or session lifecycle FINAL
```

Strategy is retrospective.

### Must not show

- `TO FLAG`
- `TO_FINISH` as a post-race action
- future pit window
- future next compound
- future Primary/Alternate plan

Publish/add a first-class race/Strategy lifecycle such as:

```text
LIVE
RESETTING
RECALCULATING
FINAL
UNAVAILABLE
```

Use the existing contract surface where possible; additive change is preferred over silently changing the meaning of an existing field.

## LIFE-07 — End-to-end visible terminal state

A factual terminal state must be visible consistently.

### Race Timing Tower

For RETIRED/DNF/DNS/DSQ:
- show an obvious terminal label;
- do not present the row as an ordinary circulating car;
- preserve classification position where factual;
- misleading live interval/strategy fields should be suppressed or replaced appropriately.

For STOPPED:
- show `STOPPED` distinctly without claiming retirement.

### Strategy driver table

Terminal row shows factual terminal state in Plan/Status and no future Strategy.

### Driver Focus

Prominently show terminal state and suppress future Strategy.

### Battle

Terminal and stopped non-circulating drivers are not Battle candidates.

### Track map

Terminal/non-circulating state must be visually distinguishable from ordinary circulating cars. Do not invent precise telemetry if the position source is approximate.

## LIFE-08 — Contract alignment

Python and TypeScript lifecycle/Strategy contracts must agree.

Specifically inspect and fix:

- `terminalState` publication vs TypeScript typing;
- Strategy lifecycle typing;
- any `WindowState` value emitted by Python but missing in TypeScript;
- STOPPED semantics;
- terminal values used by the Timing/Driver/Strategy/Battle components.

`npm` typecheck/build must pass.

---

# 8. Packet A required replay scenarios

Do not mark Packet A complete without deterministic regression scenarios covering:

### A1 — Before retirement
At cursor immediately before retirement evidence:
- driver is not terminal;
- still eligible according to factual state;
- no future result leakage.

### A2 — Retirement occurs
At first cursor with explicit retirement evidence:
- `RaceState` changes to RETIRED or the correct terminal state;
- analytics suppress future Strategy;
- Battle excludes driver;
- Timing/Strategy/Driver UI visibly show retirement.

### A3 — STOPPED then resume
Synthetic or real fixture:
- STOPPED is visible;
- not terminal;
- Battle-ineligible while stopped;
- later factual resumption returns the driver to circulating state;
- no permanent retirement contamination.

### A4 — CHEQUERED
At 70/70 CHEQUERED:
- Strategy lifecycle is FINAL;
- no driver says `TO FLAG`;
- no driver has a future pit window/next compound/future plan;
- retired drivers show factual terminal state.

### A5 — Request/cursor order
For the lifecycle facts above:
- requesting a later cursor before an earlier cursor must not change either result.

---

# 9. Packet A visual acceptance against screenshots

Produce running-app screenshots demonstrating fixes for:

- **S01 concern:** terminal driver is visibly terminal in Race timing and receives no future Strategy.
- **S03 concern:** at CHEQUERED no rows show `TO FLAG`; retired driver does not show a future pit window.
- **S06 concern where applicable:** Driver Focus shows terminal state instead of a disappearing/misleading Strategy outlook.

The screenshot may use a different replay cursor/session if the local fixture differs, but it must demonstrate the exact state transition.

---

# 10. Packet B — Viewer Live/Replay session mode

**Do not implement until Packet A is owner-approved.**

This packet is about **session discovery and viewer navigation**, not the future live normalizer.

The architecture currently has a public live recorder, but live provider messages are not yet normalized into canonical RaceState. Do not claim full live timing merely because the catalog detects a scheduled live session.

## NAV-01 — Global viewer mode

Live vs Replay is a viewer-level choice.

A live session can continue while a particular browser watches a replay.

Do not model Live/Replay as a single global server mode.

## NAV-02 — Default on app launch

Selection precedence:

1. If a session is currently live according to trustworthy session schedule/current-source evidence, default to that session.
2. Otherwise prefer the most recently completed usable session from the latest/current weekend.
3. Otherwise prefer the most recently completed usable replay.
4. Fall back to the best truthful catalog preview if nothing is locally available.

Do not hardcode current event names or dates.

## NAV-03 — Persistent Live/Replay header

The app header must clearly show current viewer mode.

Illustrative behavior:

```text
● LIVE · DUTCH GP · SPRINT QUALIFYING      [ REPLAY ▾ ]
```

When watching replay while a live session exists:

```text
REPLAY · HUNGARIAN GP · RACE
● DUTCH GP · SPRINT QUALIFYING LIVE NOW    [ GO LIVE ]
```

Exact visual styling should use the existing Slipstream design system.

## NAV-04 — GO LIVE

A visible `GO LIVE` control switches the viewer to the current live session.

It must not require navigating through Season → Weekend → Session.

If the actual live timing normalizer is not available in this milestone, the destination must truthfully show that the session is live while timing data is unavailable; it must not fabricate RaceState.

## NAV-05 — Replay picker remains global

Replay selection is global and may select Practice, Sprint Qualifying, Sprint, Qualifying, or Race.

The selected session automatically drives the correct layout.

Do not require the user to visit Race first.

## NAV-06 — Detect session boundary while tab remains open

The current catalog must not be fetched only once forever.

If a tab is open before a scheduled session begins, the UI must discover the new live session within a bounded period without requiring page reload.

Target acceptance: within 60 seconds of a mocked session boundary.

Do not auto-force a user who intentionally chose replay into Live. Show `LIVE NOW` + `GO LIVE` instead.

## NAV-07 — Truthful capability labels

Distinguish:

```text
live session detected
live timing data available
historical replay available
```

Do not label a metadata-only live preview as if live timing is connected.

## NAV-08 — Tests

Tests must cover:
- app launch during live session;
- app launch with no live session;
- replay while live exists;
- GO LIVE;
- live session begins while app is already open;
- multiple session kinds;
- unavailable live timing capability.

---

# 11. Packet C — Strategy core, RaceRead, projection correctness

**Do not implement until prior packets are approved.**

## STRAT-01 — Real TO_FINISH

`TO_FINISH` is a live-race expectation that the car can reach the flag without another ordinary stop.

Do not infer it simply because:
- car already pitted;
- a previous window passed;
- no window could be derived;
- race is late.

Use:
- race lap / total laps;
- remaining laps;
- current tyre age/stint;
- same-race comparable stint life;
- race phase;
- current clean pace trend;
- completed stops;
- supported Strategy archetype/remaining stops;
- dry-rule state;
- track regime.

Insufficient evidence → `UNKNOWN`.

When `TO_FINISH`:
- future pit window cleared;
- next compound cleared;
- future Primary/Alternate cleared.

## STRAT-02 — Race-phase comparability

Use normalized race progress as a transparent **race-phase proxy**, not measured fuel.

Evidence priority:

```text
current driver's clean current stint
↓
current-race same compound + similar race phase
↓
broader same-race same-compound evidence
↓
current-race field evidence
↓
same-meeting contextual evidence
```

Requirements:
- explicit documented phase bands/weights/constants;
- materially different phase down-weighted;
- wet/dry regime breaks comparability;
- Sprint progress is not silently GP-equivalent;
- Practice remains contextual;
- insufficient evidence → UNKNOWN.

## STRAT-03 — Strategy archetype

Completed stop count is factual history, not by itself the final Strategy archetype.

Estimate/publish remaining strategic shape only when supported.

Do not let pit-window generation define archetype backwards.

## STRAT-04 — Projection gates

Implement real:

```text
hard validity
plausibility
stability
```

No future Strategy projection may be shown while plausibility/stability are `NOT_MODELLED`.

Hard validity includes:
- window not after race end;
- no future forecast for terminal driver/race;
- no TO_FINISH with future window;
- no TO_FINISH with next compound;
- no impossible remaining stops;
- no future/cross-meeting evidence.

Plausibility includes:
- enough comparable evidence;
- appropriate race phase;
- archetype/remaining-stop consistency;
- understandable rule state;
- compound-choice evidence where needed;
- eligible live driver/regime.

Stability must be deterministic from source history.

## STRAT-05 — Starting vs current tyre distributions

Publish separately:

```text
startingTyreDistribution
currentTyreDistribution
```

Starting:
- first stint / race-start evidence;
- starting field meaning.

Current:
- current documented race population at cursor.

Do not label current tyres as starting tyres.

## STRAT-06 — Dry-rule landscape

Use one backend-produced race-wide population semantic.

Do not recompute the population independently in React.

Make denominator explicit and based on the correct active/eligible population.

## STRAT-07 — RaceRead

Create a first-class structured RaceRead.

It should support at minimum:

- race lifecycle;
- active/circulating/terminal population summary;
- completed stop distribution;
- starting tyre distribution;
- current tyre distribution;
- Strategy archetype / field shape where supported;
- pace trend distribution using correctly nested driver analytics;
- dry-rule landscape;
- recent pit activity;
- stint context by compound / phase where supported;
- deterministic `summaryFacts`.

Do not implement RaceRead as a shallow object whose code reads fields from the wrong level of `driver_models`.

## STRAT-08 — Deterministic broad commentary

Race Read and Driver Read prose should be deterministic templates over structured facts.

Example type of output:

```text
Most active runners are on two completed stops.
Three-stop runners show elevated late-stint fade.
Four runners still owe another dry specification.
```

Only emit sentences whose predicates are supported.

## STRAT-09 — NetPitLoss boundary remains honest

Keep:

```text
NetPitLoss = NOT_IMPLEMENTED
```

until a defensible model exists.

Therefore:
- no Free-stop Margin;
- no Projected Rejoin;
- no quantified undercut economics based on raw pit-lane duration.

## STRAT-10 — Same-compound stops

M→M/H→H/S→S are valid:
- pit-event evidence;
- stint-life evidence.

They are not compound-choice evidence.

## STRAT-11 — Track-regime resets

SC/VSC/Red can invalidate future Outlook immediately.

Do not blindly treat generic local Yellow as equivalent to SC/VSC/Red unless the factual scope warrants it.

Lower factual/context tiers remain visible while Outlook resets.

## STRAT-12 — UNKNOWN is visible, not rewritten

Missing/zero degradation must not become `"stable"` by frontend fallback.

Unknown pace = unknown.

---

# 12. Packet D — Strategy, Driver, Battle product surfaces

## UI-STRAT-01 — Session Strategy Snapshot

Race Session page keeps a compact race-wide Strategy snapshot.

It is not the first driver's Primary/Alternate plan.

It should communicate compactly:
- field stop shape;
- current compounds;
- dry-rule landscape;
- overall Outlook/reset state;
- `OPEN STRATEGY`.

It must use the same backend RaceRead/Strategy truth as the full Strategy page.

## UI-STRAT-02 — Dedicated Strategy page hierarchy

Use this hierarchy:

1. **RACE READ**
2. **FIELD SHAPE**
3. **PACE & STINTS**
4. **CONSTRAINTS**
5. **CONTEXT**
6. **DRIVER STRATEGY LANDSCAPE**
7. **OUTLOOK**

Improve density compared with S02; do not leave giant empty boxes.

## UI-STRAT-03 — Tyre presentation

Use compact compound badges/icons/colors where useful.

Do not make critical meaning depend on color alone.

Use text labels where ambiguity would remain.

## UI-STRAT-04 — Context

Official Pre-Race and Historical Context:
- display real attributed data when present;
- display truthful unavailable state with reason when absent;
- never fabricate production-looking defaults.

## UI-STRAT-05 — Driver Strategy table

Terminal semantics from Packet A apply.

At CHEQUERED:
- retrospective factual rows;
- no `TO FLAG`;
- no future windows.

Unknown pace does not display `stable`.

## BATTLE-01 — Battle eligibility

Before scoring require:
- Race/Sprint family;
- both cars eligible/circulating;
- comparable timing/lap state;
- meaningful gap or defined convergence criterion.

A 40–60 second adjacent pair is not automatically a Battle.

Use explicit constants and tests.

Potential internal states:

```text
CLOSE
DEVELOPING
NOT_A_BATTLE
NOT_COMPARABLE
```

## BATTLE-02 — Deterministic stabilization

Remove request-history-dependent hysteresis.

Derive persistence from source history, preferably semantic completed-lap points.

Requirements:
- same cursor => same result regardless of request order;
- held pair invalidates immediately if driver becomes ineligible;
- challenger must persist and exceed switch margin before replacing a live held pair;
- use lap-semantic persistence rather than a 20 source-second timer.

## BATTLE-03 — Gap history

Plot factual gap by **completed laps**, not transport snapshots.

Clearly label:
- x-axis or lap markers;
- sampling window;
- observed nature of data.

"Last 5 completed laps" must actually mean last 5 completed laps.

## BATTLE-04 — Focused two-driver map

Use the center space indicated in S04 for a focused two-driver track map.

Highlight the selected pair.

Other drivers may be hidden or heavily de-emphasized.

Do not fabricate exact GPS if only approximate position is available.

## BATTLE-05 — Interaction

Show meaningful shared Strategy interaction from backend-supported facts:
- current gap/trend;
- tyre/age offset;
- stop count;
- dry-rule differences;
- pace trend;
- dispositions;
- stable windows where available.

If evidence is insufficient, show a compact truthful unavailable explanation.

Do not leave a permanently empty panel.

## DRIVER-01 — Driver Read

Add a deterministic Driver Read using structured facts.

Examples of supported themes:
- current position/battle context;
- current stint/tyre age;
- clean pace/fade state;
- dry-rule constraint;
- Strategy disposition;
- pit activity.

No LLM.

## DRIVER-02 — Focused track map

Selected driver must be visually obvious.

Ahead/behind may receive secondary emphasis.

Other drivers de-emphasized.

Use consistent team identity/color language with Session/Battle/TV.

## DRIVER-03 — Pit history

Make pit history compact and factual.

For every stop:
- stop number;
- lap;
- previous compound;
- new compound, including same-compound where factual;
- pit-lane duration only under the correct name;
- no fake net pit loss.

## DRIVER-04 — Strategy availability

The Strategy area should not silently disappear.

If unavailable, render the reason/state.

## NAV-RACE-01 — Race-family gating

Strategy and Battle navigation only for Race/Sprint family.

Practice/Qualifying must not expose them as applicable views.

If session changes while currently on an invalid view, return safely to Session.

---

# 13. Packet E — TV, context/backtest, contracts, docs, hygiene

## TV-01 — TV is passive

TV renders server truth.

No independent Strategy math or interactive evidence popovers.

## TV-02 — TV field coverage

The TV tower must not arbitrarily show only four drivers without a deliberate documented product rule.

Design for across-room readability while preserving enough of the field to make the state useful.

If paging/scrolling/compact full-field is used, define the behavior explicitly.

## TV-03 — Global team/driver color language

Track dots and driver identity use one consistent color mapping across:
- Session;
- Driver;
- Battle;
- TV.

Retirement/terminal styling may override or mute identity where required.

## TV-04 — Strong semantic status rail

Make current race status visible across TV pages:

```text
GREEN
YELLOW
SC
VSC
RED
CHEQUERED
```

The status treatment should be materially more visible than the thin band shown in S08.

Preserve readability and do not let status color destroy team/compound semantics.

## TV-05 — Driver/Battle layout cleanup

Fix S08 issues:
- alignment;
- whitespace;
- font hierarchy;
- pace chart sizing;
- consistent columns.

No placeholder map boxes.

## CTX-01 — Historical context

Historical context comes from Slipstream-compatible historical race data.

Previous-season context is separately attributed.

No prior race => unavailable.

2025→2026 comparability should be limited where regulation discontinuity makes direct blending inappropriate.

Do not silently blend historical data into current-race Strategy.

## CTX-02 — Official pre-race/Pirelli

Official pre-race context is separately attributed.

Manual structured ingestion is acceptable.

Do not ship fake Pirelli dates, stop counts, sequences, or windows as production data.

## CTX-03 — Backtest

Either implement a real backtest over actual predictions/outcomes or report it truthfully as unavailable/not implemented.

Delete canned metrics that return fixed "good" scores independent of input.

## CONTRACT-01 — Python/TypeScript alignment

Type definitions must match actual backend payloads.

No missing `terminalState`, mismatched `heldRecommendation`, missing enum values, or dry-rule shape mismatch.

## DOC-01 — Model version/docs

Increment model version only for real model/contract changes.

Docs describe what the code actually does.

Do not document aspirational behavior as implemented.

## HYGIENE-01 — Repository hygiene

Remove accidental generated/cache artifacts.

Do not commit:
- Vite/Vitest cache results;
- local environment junk;
- screenshots/handoff files unless intentionally requested.

## FINAL-01 — Final validation

Run all repository-prescribed tests plus:
- Python tests;
- frontend tests;
- TypeScript typecheck;
- production frontend build;
- replay regressions;
- runtime smoke;
- screenshot acceptance for all affected product surfaces.

---

# 14. Screenshot-proof rules for later UI packets

For S02/S04/S05/S06/S07/S08 fixes, provide both:

1. screenshot before or reference screenshot ID;
2. screenshot from the running fixed application at comparable viewport.

Use 1920×1080 where practical for desktop/TV comparisons.

For each screenshot report:
- session;
- replay cursor/lap;
- viewport;
- requirement IDs demonstrated.

Do not use a static mockup as proof that the production React app works.

---

# 15. Required final report template for every packet

```markdown
# Packet X Report

START_HEAD:
END_HEAD:
BRANCH:

## Requirement matrix

| ID | Status | Files changed | Tests | Replay/runtime proof | Screenshot | Limitation |
|---|---|---|---|---|---|---|

## Commands executed

```text
...
```

## Test results

```text
...
```

## Replay checkpoints

### checkpoint name
session:
cursor/seq:
expected:
observed:

## Visual proof

- screenshot file:
- requirement IDs:
- session/cursor:
- what changed:

## Known incomplete work

List every item honestly.

## Out-of-scope work not started

List later packets and confirm they were not pulled forward.

## Recommendation

READY FOR OWNER REVIEW / NOT READY
```

The report must not say "Milestone 3.5 complete" after Packet A.

---

# 16. First-run stop condition

For the first agent run:

**Implement Packet A only.**

Do not implement:
- Live/Replay shell changes;
- RaceRead redesign;
- Strategy page redesign;
- Battle redesign;
- Driver Read;
- TV changes;
- context/backtest.

You may inspect those areas only to ensure Packet A's lifecycle truth is consumed correctly where required by LIFE-07/LIFE-08.

When Packet A tests and visual proof are complete, stop and return the report for owner review.

Do not continue autonomously into Packet B.
