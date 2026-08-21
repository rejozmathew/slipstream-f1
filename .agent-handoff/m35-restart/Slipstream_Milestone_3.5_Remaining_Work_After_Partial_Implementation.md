# Slipstream F1 — Milestone 3.5 Remaining Work
## Updated Coding-Agent Handoff After Partial Implementation

**Repository:** https://github.com/rejozmathew/slipstream-f1  
**Branch:** `agent/milestone-3.5-improvements`  
**Base:** `agent/milestone-3-race-intelligence`  
**Goal:** finish Milestone 3.5, validate it, and return it for owner review/merge before Milestone 4.  
**Do not merge to `main`.**

---

## 0. Mission

A partial implementation pass has already been completed on this branch. Do **not** restart the milestone.

Preserve the good work already present, finish the remaining correctness/model/UI work, remove fake/stub outputs that look production-ready, and leave the branch genuinely merge-ready.

Product principle:

> Slipstream should always tell the viewer what is happening, usually tell them what it means, and only sometimes tell them what it thinks will happen next.

Use:

```text
FACTS → CONTEXT → CONSTRAINTS → TRENDS → OUTLOOK
```

`UNKNOWN` is preferable to an unsupported but plausible answer.

No LLM is needed for live Strategy commentary. Broad commentary should be deterministic formatting of computed facts.

---

## 1. First steps

Confirm:

```bash
git status
git branch --show-current
git rev-parse HEAD
git log --oneline --decorate -n 15
```

You must be on:

```text
agent/milestone-3.5-improvements
```

Record the starting HEAD.

Read:

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `docs/protocol.md`
4. `ROADMAP.md`
5. `IMPLEMENTATION_MAP.md`
6. `docs/analytics.md`
7. `CHANGELOG.md`

Then inspect at minimum:

```text
src/slipstream/analytics.py
src/slipstream/lifecycle.py
src/slipstream/evidence.py
src/slipstream/strategy_rules.py
src/slipstream/adapters/openf1.py
src/slipstream/state.py
src/slipstream/historical.py
src/slipstream/pirelli.py
src/slipstream/backtest.py

web/domain/protocol.ts
web/domain/battle.ts
web/hooks/useBattleRecommendation.ts
web/components/shell/AppShell.tsx
web/components/analysis/SessionStrategySnapshot.tsx
web/components/analysis/StrategyOutlook.tsx
web/components/analysis/PaceDeltaChart.tsx
web/components/analysis/TrackMap.tsx
web/views/StrategyView.tsx
web/views/BattleView.tsx
web/views/DriverFocusView.tsx
web/views/TVModeView.tsx
web/app/globals.css
```

Do not trust `IMPLEMENTATION_MAP.md` or `CHANGELOG.md` claims over actual code.

---

# 2. Already implemented — preserve this work

The current branch already has useful fixes. Do not redo or regress them.

### 2.1 Canonical lifecycle helper

`src/slipstream/lifecycle.py` now centralizes:
- terminal status vocabulary;
- active participant predicate;
- display status label;
- Battle eligibility;
- terminal-state mapping.

Keep one canonical lifecycle vocabulary.

### 2.2 Cursor-safe analytics cache key

`AnalyticsService._signature()` now includes `sequence`.

Keep:

```text
analytics(cursor X) cannot reuse evidence from cursor Y
```

### 2.3 Same-compound stops retained

`_transition_samples()` now keeps factual M→M/H→H/S→S events and marks whether a compound change occurred.

Keep separate:
- pit-event evidence;
- stint-life evidence;
- compound-choice evidence.

### 2.4 Race lap preferred for driver projection timing

`_driver_transition_outlook()` now uses the race/session lap before frozen `driver.lap`.

Keep race time and driver progress conceptually separate.

### 2.5 Arbitrary final-three-lap rule removed

Do not reintroduce another magic final-4/final-5 cutoff.

### 2.6 Terminal projection suppression exists

Terminal drivers have future pit/compound/primary/alternate fields suppressed.

Keep this, but fix upstream mid-race lifecycle detection.

### 2.7 NetPitLoss boundary is correct

Keep:
- `NetPitLoss = NOT_IMPLEMENTED`;
- no Free-stop Margin;
- no Projected Rejoin;
- no quantified undercut economics based on raw pit-lane duration.

### 2.8 Candidate Battle gap is server-provided

Keep `gapSeconds/gapBasis/comparisonState` for backend Battle candidates.

### 2.9 PaceDelta null-direction fix is done

Missing delta is no longer treated as a slow lap.

### 2.10 Sprint pit-lane duration is not directly used as GP equivalent

Keep this boundary.

---

# 3. P0 — mid-race retirement/stopped lifecycle is still missing

This is the biggest factual defect.

Current OpenF1 normalization still initializes drivers as `RUNNING`, preserves driver-scoped race-control messages only as race-control facts, and applies final DNF/DNS/DSQ status at session end.

Therefore `lifecycle.py` cannot exclude a driver mid-race unless `DriverState.status` actually changes.

## Required

Create cursor-safe source-neutral lifecycle updates from timestamped source evidence.

Candidate states:

```text
RUNNING
STOPPED
RETIRED
FINISHED
DNF
DNS
DSQ
UNKNOWN
```

Rules:

- never leak final DNF backward in replay;
- `STOPPED` is not automatically `RETIRED`;
- a stopped car may resume if later factual evidence supports it;
- only mark `RETIRED` when source evidence explicitly establishes retirement;
- final session result may finalize DNF/DNS/DSQ/FINISHED at session end.

Use the lifecycle truth everywhere:
- active counts;
- current tyre distribution;
- dry-rule landscape;
- Strategy eligibility;
- Battle;
- Driver;
- Timing;
- Track map.

Add regression tests for a car stopping mid-race and the race continuing.

---

# 4. P0 — terminal race semantics are still wrong

Current `_driver_disposition()` can map a finished/CHEQUERED race to `TO_FINISH`.

That is semantically wrong.

`TO_FINISH` means a live-race expectation that the current car can reach the flag without another ordinary stop.

At:

```text
70 / 70
CHEQUERED
```

Strategy is retrospective.

## Required

Add an additive terminal/race lifecycle semantic, e.g.:

```text
strategyLifecycle:
  LIVE
  RESETTING
  RECALCULATING
  FINAL
  UNAVAILABLE
```

and/or:

```text
terminalState:
  FINISHED
  DNF
  DNS
  DSQ
  RETIRED
  null
```

At terminal race:
- no `TO FLAG`;
- no future pit window;
- no likely next compound;
- no future primary/alternate plan;
- Driver Strategy rows show factual terminal state;
- race Strategy becomes a factual summary.

---

# 5. P0 — `TO_FINISH` still needs real reasoning

Do not infer `TO_FINISH` merely because:
- the car has already pitted;
- a window passed;
- no pit window could be derived;
- the race is late.

Use:

```text
race lap / total laps
remaining laps
current tyre age/stint
same-race comparable stint life
race phase
current clean pace trend
completed stops
estimated strategy archetype / remaining stops when supported
dry-rule state
track regime
```

Output:

```text
PIT_EXPECTED
TO_FINISH
UNKNOWN
```

When `TO_FINISH`:
- clear future pit window;
- clear next compound;
- clear future primary/alternate strategy.

If evidence is insufficient, use `UNKNOWN`.

---

# 6. P0 — race-phase comparability is still missing

Current transition selection is still dominated by same compound + tyre-life similarity.

Implement race-phase comparability.

Use:

```text
raceProgress = raceLap / totalLaps
```

only as a transparent race-phase proxy, not measured fuel.

Evidence priority:

```text
current driver's clean current stint
↓
current-race same compound + similar race phase
↓
current-race broader same-compound evidence
↓
current-race field evidence
↓
same-meeting contextual evidence
```

Requirements:
- explicit named bands/weights/constants;
- down-weight materially different race phases;
- current driver evidence increasingly matters when sufficiently clean/long;
- wet/dry regime change breaks comparability;
- Sprint normalized progress is not GP-equivalent;
- Practice remains contextual;
- insufficient evidence → UNKNOWN.

Document the exact algorithm.

---

# 7. P0 — projection gates remain placeholders

Current snapshot still publishes:

```text
hardValidity = PASS
plausibility = NOT_MODELLED
stability = NOT_MODELLED
```

while future Strategy remains visible.

Finish the gate system.

## Hard validity

Validate the actual candidate:
- no window after race end;
- no future forecast for terminal race/driver;
- no `TO_FINISH` with a future window;
- no `TO_FINISH` with a next compound;
- no impossible stop counts;
- no future/cross-meeting evidence.

Reject invalid candidates; do not merely clamp them.

## Plausibility

Require:
- enough comparable evidence;
- appropriate race phase;
- Strategy/remaining-stop consistency;
- understandable rule state;
- next compound supported by compound-choice evidence;
- eligible driver/current race regime.

Failure → T4 projection suppressed.

## Stability

Make publication stable using deterministic source history.

Properties:
- small shifts do not republish every update;
- major new evidence can replace after persistence;
- SC/VSC/Red/weather regime may invalidate immediately;
- same replay cursor always reproduces same result;
- request order never changes result.

---

# 8. P0 — Battle hysteresis is still request-history dependent

The current `_battle_memo/_battle_cursors` design depends on which earlier cursors happened to be requested.

Example:

```text
A: request 500 directly
B: request 400, then 500
```

Cursor 500 can inherit different held state.

That violates deterministic replay.

## Required

Derive Battle stabilization from source history, not API request history.

Preferred approach:
- evaluate candidate persistence at semantic source points, preferably completed laps;
- require the challenger to remain superior across the hold interval;
- apply switch margin;
- immediately invalidate if held pair becomes ineligible.

A cache of deterministic results is fine.

Do not use cross-viewer mutable model state.

Replace/retire the 20-source-second hold; at 10× replay it is only 2 seconds of viewing.

Prefer lap-semantic persistence.

---

# 9. P0/P1 — Battle eligibility still needs a real gate

Do not recommend every adjacent classified pair with a numeric interval.

Before scoring require:
- both cars eligible/active;
- Race/Sprint family;
- comparable timing;
- valid/lapped state;
- meaningful gap or defined convergence criterion.

A 40–60 second adjacent pair is not a Battle.

Use explicit model constants and test them.

Possible internal states:

```text
CLOSE
DEVELOPING
NOT_A_BATTLE
NOT_COMPARABLE
```

---

# 10. P1 — starting tyre distribution is still wrong

Current `startingTyreDistribution` is built from each active driver's **current** compound.

Fix it.

Publish:

```text
startingTyreDistribution
currentTyreDistribution
```

Starting tyre:
- derive from first stint / race-start evidence;
- describes starting field, not current active field.

Current tyre:
- derive from current documented race population.

Use tyre badges in UI.

---

# 11. P1 — RaceRead is still missing

Add a first-class structured race summary.

Suggested:

```text
raceRead:
  raceLifecycle
  activeRunnerCount
  completedStopDistribution

  startingTyreDistribution
  currentTyreDistribution

  paceTrendDistribution:
    comparableDrivers
    highFade
    moderateFade
    lowOrStable
    unknown

  stintContextByCompound

  dryRequirementLandscape:
    satisfied
    unsatisfied
    notApplicable
    unknown
    denominator

  strategyArchetype
  recentPitActivity
  summaryFacts[]
```

This is the centerpiece of the Strategy page.

---

# 12. P1 — deterministic broad Strategy commentary

No LLM.

Examples:

```text
13 of 19 active runners have completed two stops; four have completed three.
Pace fade is elevated across 9 of 14 comparable active runners.
One active runner still has an unsatisfied dry-tyre requirement.
```

Do not call a factual completed-stop count a final Strategy archetype.

Prefer:

```text
completed two stops
```

unless final/estimated total Strategy is actually supported.

Race-wide pace commentary must use current-race comparable evidence only, not Weekend degradation fallback.

Expose the denominator.

---

# 13. P1 — Session Strategy Snapshot still reuses old StrategyOutlook

Replace `SessionStrategySnapshot` with a purpose-built race snapshot.

Suggested:

```text
STRATEGY

FIELD
13 / 19 completed 2 stops
4 completed 3

CURRENT TYRES
○H 11   ○S 8

PACE
Elevated fade · 9 / 14 comparable

DRY RULE
1 active runner still owes another spec

OPEN STRATEGY →
```

The Session card is not a driver forecast panel.

---

# 14. P1 — Strategy page still needs redesign

Current page still has:
- oversized header/whitespace;
- no RaceRead;
- no Pace/Stints panel;
- large “Absent” context cards;
- wrong population recomputation;
- unknown pace displayed as `stable`.

## Required layout

Compact title:

```text
STRATEGY · HUNGARIAN GRAND PRIX      LAP 38 / 70 · GREEN
```

Then RaceRead.

Then one desktop row:

```text
FIELD SHAPE | PACE & STINTS | CONSTRAINTS
```

Then compact Context.

Then Driver Strategy Landscape.

Fix the CSS class collision between Strategy page layout and old `.strategy-grid` metric layout.

Unknown pace must display `—`, not `stable`.

Allowed plan states include:

```text
L24–28
TO FLAG
EXTENDING
RESETTING
UNKNOWN
FINISHED
DNF
```

---

# 15. P1 — dry-rule population and rule logic

Race-wide dry-rule counts must come from one backend population object, not React looping through all drivers.

Use the same denominator as active/current Strategy population.

Also finish the rule logic:
- two dry specifications where applicable;
- Sprint distinction;
- Wet/Intermediate exception;
- red-flag implication only when factual evidence supports it;
- unknown legal/allocation details remain UNKNOWN.

Do not present a generic `MUST STOP`.

---

# 16. P1 — Historical/Pirelli remains fake/not wired

Snapshot currently returns truthful `ABSENT`, which is acceptable.

But `historical.py` and `pirelli.py` still contain realistic-looking mocked values.

Remove fake behavior.

Allowed:

```text
REAL DERIVED/OFFICIAL CONTEXT
or
ABSENT / NOT_CONFIGURED / NOT_AVAILABLE
```

Historical:
- real local prior-season same-circuit data only;
- real aggregates;
- 2025→2026 `LIMITED` comparability.

Official Pre-Race/Pirelli:
- official source;
- publication/retrieval time;
- source URL;
- replay cutoff enforcement;
- explicit statements only;
- no LLM inference.

Manual structured ingestion is acceptable.

---

# 17. P1 — backtest harness is still fake

`backtest.py` still returns canned metrics independent of input.

Replace it with a real replay evaluator or explicitly mark it unimplemented.

Minimum real harness:
1. load real local replay;
2. sample by completed laps or another semantic cadence;
3. compute analytics at each cursor;
4. record published projections;
5. compare to future factual pit events only in evaluator;
6. compute real metrics.

Suggested:

```text
coverage
pitWindowHitRate
eventCensoredHitRate
falseStopPredictionRate
windowErrorLaps
strategyChurn
lateRaceFalseStopRate
hardValidityViolations
```

Do not commit recordings.

---

# 18. P1/P2 — Battle UI remains mostly old

Current Gap History still uses the last 90 transport snapshots.

Replace it with backend factual history over a defined lap range, e.g.:

```text
LAST 5 COMPLETED LAPS
```

Publish lap + gap and deterministic trend.

Use center space for a focused two-driver track map.

Highlight only the selected pair; mute others.

Replace mostly empty Interaction with structured comparative facts:

```text
TYRE OFFSET
PACE DIFFERENCE
RULE STATE
DISPOSITION
WINDOW DIFFERENCE
```

If none:

```text
NO MATERIAL STRATEGIC DIFFERENCE
```

---

# 19. P2 — Driver Focus remains mostly old

Add deterministic Driver Read:

```text
P1 · 10 laps remaining
4 laps into this stint
7 total laps on this Soft set
PACE: elevated fade
FIELD: comparable Soft stints 12–16 laps
RULE: satisfied
PLAN: TO FLAG
```

Add TrackMap focus modes:
- Driver: selected + ahead + behind emphasized;
- Battle: pair emphasized;
- normal: full field.

Redesign Pit History:

```text
STOP 1 · L17    ○M → ○H    PIT LANE 22.1s
STOP 2 · L56    ○H → ○S    PIT LANE 21.8s
```

Verify the real H→S boundary from source; do not patch by guess.

---

# 20. P2 — TV Mode remains mostly old

Current Track TV still uses:

```text
drivers.slice(0, 10)
```

and may visually show fewer.

Replace with full-field compact TV tower fitting 1080p.

Status rail:
- permanent 24–30px labelled semantic rail;
- GREEN visible;
- CHEQUERED explicitly handled;
- critical states stronger.

TV Driver:
- author a real TV layout;
- do not drop generic desktop StrategyOutlook into a TV grid;
- suggested 28% / 42% / 30% Driver / Pace / Strategy.

TV Battle:
- use corrected stable pair;
- server gap;
- lap-defined trend;
- focused pair map;
- meaningful interaction.

No scrolling at 1080p.

---

# 21. P2 — navigation gating incomplete

Strategy is race-gated; Battle is still unconditional.

For Race/Sprint:

```text
SESSION | DRIVER | BATTLE | STRATEGY | TV MODE | SETTINGS
```

For Practice/Qualifying/Sprint Qualifying:

```text
SESSION | DRIVER | TV MODE | SETTINGS
```

Hide Strategy/Battle.

If session changes while one of those views is active and it becomes invalid, safely return to Session.

---

# 22. P1 — Strategy terminology

Preferred UI wording:

```text
PACE TREND
PACE FADE SEVERITY
PIT-LANE DURATION
UNDERCUT CONDITIONS
RAIN STATUS
```

Do not call the slope pure physical tyre degradation.

No Rejoin/Free-stop until NetPitLoss exists.

Different surfaces may use different layouts while consuming the same backend truth.

---

# 23. P1 — strategy archetype / remaining stops

Current `likelyStopCount` late-race median heuristic is not enough.

Add:

```text
strategyArchetype:
  ONE_STOP
  TWO_STOP
  THREE_STOP
  UNKNOWN

expectedTotalStops
completedStops
expectedRemainingStops
```

Observed completed stops are factual.

Expected values are estimates with provenance.

This logic sits upstream of:

```text
PIT_EXPECTED / TO_FINISH / UNKNOWN
```

---

# 24. P1 — Strategy reset semantics

Current reset includes generic `YELLOW`.

Refine to events that materially reset pit economics/model regime, at minimum:
- SC;
- VSC;
- Red;
- dry↔wet regime transition.

Facts/context/constraints remain visible while T4 is `RESETTING/RECALCULATING`.

Do not blank the Strategy page.

---

# 25. P1 — backend/TypeScript contract mismatch

Audit all analytics wire fields.

Known mismatch:

Backend:

```text
sportingRules.dryTyreRequirement.perDriverState
= Record<driverNumber, DryTyreRequirementState>
```

Frontend currently types it as one `DryTyreRequirementState`.

Fix.

`heldRecommendation` shape also differs between backend and TypeScript.

After Battle redesign, define one exact shape and mirror it.

Add contract coverage.

---

# 26. P1 — model version/docs are stale

Runtime still reports:

```text
race-intelligence-v2.1
```

This finishing pass materially changes model semantics.

Bump model version, recommended:

```text
race-intelligence-v2.2
```

Update:

```text
docs/analytics.md
docs/analytics/race-intelligence-v2.2.md
CHANGELOG.md
IMPLEMENTATION_MAP.md
```

`docs/analytics.md` should be the charter/model registry.

The detailed doc must describe actual implemented algorithms and maturity.

Do not claim “stability gates” or “automated backtesting” until real.

---

# 27. P2 — repository hygiene

Remove the accidentally committed:

```text
node_modules/.vite/vitest/.../results.json
```

Add an ignore rule for generated Vite/Vitest caches.

Do not commit recordings, credentials, `.env`, node_modules, or generated caches.

---

# 28. Milestone 4 boundary

Do not implement:
- SQLite;
- Admin/auth;
- Viewer Profiles;
- Administration;
- persistent user preferences;
- Admin deletion UI/API.

M3.5 only needs clean ownership semantics for:
- recording;
- target-session persistent context;
- runtime analytics/cache.

An internal `invalidate_session(session_key)` is fine if useful.

Actual deletion lifecycle is Milestone 4.

---

# 29. Required regressions

At minimum:

1. timestamped STOPPED is cursor-safe;
2. final DNF does not leak backward;
3. resumed STOPPED car can return RUNNING when evidence says so;
4. terminal driver gets no future Strategy;
5. terminal driver not Battle eligible;
6. race lap drives horizon, not frozen driver lap;
7. lap 67/70 never produces >70 window;
8. legitimate final-3-lap stop not rejected solely by lap count;
9. 70/70 CHEQUERED has no future Strategy;
10. same-compound stop is stint-life evidence;
11. same-compound stop is not compound-choice evidence;
12. early-race stint down-weighted late race;
13. current driver late stint can outweigh old field evidence;
14. TO_FINISH clears window/next;
15. UNKNOWN remains UNKNOWN;
16. RaceRead pace excludes Weekend fallback;
17. hard-invalid projection suppressed;
18. low-plausibility projection suppressed;
19. unstable projection suppressed;
20. reset invalidates T4 but keeps lower tiers;
21. request 500 directly vs 400→500 gives same Battle result;
22. request 500→400→500 gives same Battle result;
23. two delayed viewers remain independent;
24. backward seek does not retain later Strategy/Battle state;
25. 60s adjacent pair is not Recommended Battle;
26. close meaningful pair can be recommended;
27. held pair invalidates when ineligible;
28. gap history is lap-defined;
29. starting tyre distribution remains start fact after stops;
30. current tyre distribution changes with current state;
31. dry-rule denominator matches active population;
32. Sprint rule differs from GP;
33. Wet/Inter exception works when evidence exists;
34. fake Historical/Pirelli values can never reach snapshot;
35. different replay inputs do not return identical canned backtest metrics;
36. Qualifying/Practice hide Strategy/Battle;
37. unknown pace is not displayed as stable;
38. full TV field renders;
39. CHEQUERED status rail renders;
40. source-supported H→S pit transition displays correctly.

---

# 30. Implementation order

Use:

```text
A. factual lifecycle + terminal semantics
B. deterministic cursor/Battle stabilization
C. Strategy core: race phase, archetype, TO_FINISH, gates
D. RaceRead + current-race pace distribution
E. Session/Strategy UI
F. Battle + Driver
G. TV
H. real context/backtest or truthful unavailable
I. contracts/docs/hygiene
J. final validation
```

Do not start with CSS polish.

---

# 31. Final validation

Backend:

```bash
ruff check src tests
pytest -q
```

Frontend:

```bash
cd web
npm run typecheck
npm run lint
npm test
npm run build
```

Local preview:
- backend `127.0.0.1:8000`
- Vite `127.0.0.1:3344`

Do not use 5173.

Manual replay checks:
- retirement/stopped cursor;
- late race around 67/70;
- 70/70 CHEQUERED;
- later pit H→S;
- two different replay delays;
- Battle at 10× replay.

---

# 32. Final report

Return:

```text
STARTING HEAD
FINAL HEAD

COMMITS CREATED

PRESERVED PARTIAL WORK

NEW WORK COMPLETED
- lifecycle
- cursor determinism
- Strategy
- RaceRead
- Battle
- Driver
- TV
- context/backtest
- docs

MODEL VERSION

TEST RESULTS

MANUAL REPLAY CHECKS

KNOWN LIMITATIONS

DEFERRED TO MILESTONE 4

MERGE READINESS
READY / NOT READY
```

Do not merge to `main`.

---

# 33. Final product test

For every analytical output ask:

> Is this a fact, context, constraint, trend, or forecast?

Then:

> Does the evidence actually support that category at this replay cursor?

If not, render:

```text
UNKNOWN
```

Finish Milestone 3.5 on that principle.
