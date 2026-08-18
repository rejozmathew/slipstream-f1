# Slipstream — Race Intelligence & Strategy v2.1 Implementation Map

**Branch:** `agent/milestone-3.5-improvements` (branched from `agent/milestone-3-race-intelligence` @ `e17fcfa`)
**Authoritative requirements:** `Slipstream_Race_Intelligence_Strategy_v2.1_New_Agent_Handoff_M3.5.md` (v2.1 doc)
**Status:** Phase 1 — decision source of truth. Update this file whenever a decision changes.
**Precedence (v2.1 doc §0.1):** v2.1 doc > `ARCHITECTURE.md`/`docs/protocol.md` invariants > `ROADMAP.md` milestone boundaries > `docs/analytics.md` > current V1 code.

---

## 0. Reading check (my own result, honestly reported)

### 0.1 The 12 invariants — quoted verbatim from v2.1 doc §2 "Invariants"

All 12 present, all 12 quoted verbatim:

1. `RaceState` remains factual.
2. Detailed accumulated evidence stays outside high-frequency `RaceState`.
3. `WeekendContext` remains strictly same-`meeting_key`, earlier-session, no-hindsight evidence.
4. Previous race weekends never silently enter the current weekend model.
5. Analytics remains deterministic at a given replay cursor/model version.
6. React/TV/mobile render backend analytical truth; they do not recreate Strategy math.
7. `UNKNOWN` remains a valid analytical outcome.
8. Every estimate retains evidence provenance and model version.
9. A viewer's **source cursor / as-of time is the single temporal authority** for both factual state and analytics.
10. State and analytics delivered to a viewer must be computed from the same source position; delayed viewers must never receive newer analytical knowledge than the state they are watching.
11. Strategy/analytics calculations remain server-side. Browser, TV, mobile, and future hardware clients render the returned analytical truth; they do not independently recalculate Strategy.
12. High-frequency analytical answers are rebuildable runtime outputs, not authoritative persistent race assets.

### 0.2 Regression scenarios — v2.1 doc §25

**RED FLAG / DISCREPANCY (stated, not hidden):** The handoff task description and prior context refer to "25 regression scenarios," but v2.1 doc §25 "Required regression scenarios" lists **26** numbered items. I report all 26 verbatim-by-number below. Scenario 26 (Admin deletion lifecycle) is explicitly scoped to Milestone 4 per doc §2.7/§5.5 — it is *verified in M4*, not implemented here.

1. Normal one-stop race.
2. Normal two-stop race.
3. Late-race fresh tyre with only 3–5 laps remaining.
4. Early Safety Car moving a planned stop.
5. Safety Car making an additional stop attractive.
6. Window passes without a stop -> `EXTENDING STINT`.
7. Wet/intermediate transition.
8. Same-compound stop `M→M`.
9. Early-race vs late-race same-compound stint comparability.
10. Lapped/non-comparable rejoin gaps.
11. Sprint-weekend evidence.
12. Previous-season circuit absent -> no Historical Context.
13. Historical replay only sees previous-season context.
14. Pirelli pre-race context published after cutoff -> rejected.
15. Strategy/Battle hidden for Qualifying/Practice.
16. Projection thrashing suppressed by stability gate.
17. SC/VSC/Red resets current published Outlook.
18. Hard validity gate rejects race-end-overrun window.
19. Two viewers at different delays receive analytics consistent with their own source cursors; no delayed-viewer hindsight leak.
20. Intentional future-evidence/cross-meeting integrity violation fails loudly in test rather than degrading to ordinary `UNKNOWN`.
21. Post-SC warm reset keeps facts/context/constraints visible while T4 is recalculating.
22. Sprint race-progress evidence is rejected from Grand Prix stint-life/pit-window comparability.
23. Active-runner distributions exclude a retired car from "yet to stop" and current tyre counts.
24. 2025-to-2026 Historical Context is labelled limited comparability / prior regulation era.
25. Free-stop and Projected Rejoin remain unavailable when `NetPitLoss` is unavailable.
26. Admin deletion lifecycle is verified in Milestone 4: recording + target-owned persistent derived artifacts are removed and runtime analytics cache is invalidated.

### 0.3 Five real functions confirmed from actual code (not invented)

All verified present in `src/slipstream/analytics.py` via `grep -nE "^(def|class) "`:

1. `build_analytics_snapshot(...)` — line 79 — top-level snapshot builder.
2. `pace_model(laps)` — line 196 — representative-lap pace/baseline/degradation.
3. `battle_recommendation(...)` — line 243 — Battle candidate scoring + hysteresis constants.
4. `_driver_transition_outlook(...)` — line 381 — next-compound + pit-window outlook.
5. `_driver_strategy(...)` — line 453 — per-driver Strategy assembly.

Other real functions noted for the map (same file): `_race_strategy` (603), `_likely_stop_count` (804), `_rejoin_metrics` (833), `_pit_loss_metric` (949), `_analytics_stage` (1142), `_signature` (1154), and `class AnalyticsService` (45, cache wrapper).

### 0.4 Real functions in `evidence.py` (from actual code)

- `SessionEvidence.from_events(...)` — classmethod, line 63.
- `SessionEvidence.laps_for_driver(...)` — line 86 (cursor/`at`/`event_limit`-limited).
- `SessionEvidence.pit_events_for_driver(...)` — line 106.
- Dataclasses: `LapObservation` (11), `LapEvidence` (35), `PitEvent` (43), `SessionEvidence` (57).

### 0.5 Reading-check verdict

**PASS on invariants and functions.** One red flag surfaced and is explicitly reported: the scenario count is **26 in the doc, not 25** as the task description states. I proceed against the authoritative doc (26) and flag the mismatch. No invented names. All 12 invariants and all 26 scenarios accounted for.

---

## 1. Baseline (established with real output)

| Check | Command | Result |
|---|---|---|
| Backend install | `pip install -e ".[dev]"` | OK (deps present) |
| Lint | `ruff check src tests` | **clean** |
| Backend tests | `pytest -q` | **53 passed** |
| Frontend install | `npm install` | OK |
| Typecheck | `npm run typecheck` | **clean** |
| Lint | `npm run lint` | **clean** |
| Frontend tests | `npm test` (node --test) | **6 passed** |

Runtime targets (unchanged by this work): backend `127.0.0.1:8000`, UI `127.0.0.1:3344` (NOT 5173).

---

## 2. Answers to the 10 implementation-expectation questions (v2.1 doc, top-level section `# 4. IMPLEMENTATION EXPECTATION FOR A NEW AGENT`) — against actual code

> **Attribution note (avoiding a §-collision):** the doc has TWO numbering schemes — top-level meta sections (`0.1`, `1.1`, `1.2`, `2`, `# 4. IMPLEMENTATION EXPECTATION`, `5.1–5.7`) and the product-spec sections (`## 1` … `## 28`). The **10 questions** live in top-level **`# 4. IMPLEMENTATION EXPECTATION FOR A NEW AGENT`** (NOT product-spec `## 4`, which is "Epistemic tiers"). In the requirement table below, `§N` always means product-spec `## N`.

### Q1. Which current V1 fields/contracts can be retained?

Retain (already conform to invariants; keep as-is):
- **Envelope & transport:** `serialization.state_envelope` (v1, seq, sessionTime/sourceTime, playback, data) — unchanged. Analytics is a separate sidecar (`envelope["analytics"]`).
- **Temporal authority plumbing:** `playback.ReplayController` (seek/seek_delay/seek_relative/advance/step/play), `replay.replay(...at|event_limit...)`, `evidence.SessionEvidence.laps_for_driver/at|event_limit`. This is the existing per-viewer cursor model that invariant 9/10/§2.1 rely on. **Keep.**
- **Metric envelope shape:** `metric()` / `unknown()` in `analytics.py` (value/status/unit/evidenceBasis/modelVersion/quality). Keep — it already carries provenance + model version (invariant 8) and `UNKNOWN` (invariant 7).
- **Pace primitives:** `pace_model`, `_robust_baseline`, `_degradation` — keep; re-version, don't rewrite.
- **Rules boundary:** `strategy_rules.strategy_rule_profile` + `StrategyRuleProfile` — keep as the deterministic T2 constraint source; extend its contract (see Q2).
- **Cache boundary:** `AnalyticsService._signature` + `_cache` (128-entry) — keep the "rebuildable cacheable" pattern (invariant 12); extend the signature to include the new context classes.
- **Frontend render contract:** `domain/protocol.ts` `AnalyticsSnapshot`, `StrategyAnalytics`, `AnalyticsMetric`, `PaceSample`, `DriverBattleContext` — keep the shape; add fields (additive).
- **Server-side Battle scoring:** `battle_recommendation` (scoring, `minimumHoldSeconds`, `switchMargin`) — keep server-side (invariant 11).

### Q2. Which fields must be renamed / deprecated / replaced?

Per v2.1 §17 (terminology corrections) + §15 (dry-tyre rule) + §12 (disposition):

| Current (V1) | Target (v2.1) | Disposition |
|---|---|---|
| `degradation` | **Pace Trend / Observed Pace Degradation** | Keep key `degradation`, change **UI label** to "PACE TREND / OBSERVED PACE DEGRADATION"; keep value semantics. |
| `tyreStress` (LOW/MED/HIGH) | **Degradation Severity** | Keep key, relabel; keep threshold semantics. |
| `pitLoss` | **Pit-Lane Duration** (until true Net Pit Loss exists) | Keep key `pitLoss` but **relabel** "PIT-LANE DURATION"; do NOT rename the field (avoids breaking); add explicit `netPitLoss: null` to signal absence of the derived metric. |
| `undercutStrength` (STRONG/MODERATE/LIMITED) | **Undercut Conditions** (descriptive only) | Keep key, **downgrade semantics** from quantified strength to descriptive conditions; must not imply quantified pit-economics (blocked by NetPitLoss). |
| `weatherRisk` | **Rain Status** | Keep key, relabel; stays OBSERVED when `state.weather.rainfall` true, else UNKNOWN (no forecast). |
| `quality` (metric) | **Evidence Quality** | Keep key; relabel. |
| `likelyStopCount` / `primaryStrategy` / `alternateStrategy` / `pitWindow` | Retain, but now **gated** by validity/stability/plausibility + race-horizon + dry-rule + disposition. | Replace internals, keep keys. |
| `projectedRejoinPosition`, `freeStopMargin` | **Suppressed** until NetPitLoss | Keep keys present for contract stability but force `UNKNOWN` with explicit `evidenceBasis` naming the missing `NetPitLoss` dependency. (see Q4) |
| `mandatoryPitStops` (int) | **`dryTyreRequirement`** state (UNSATISFIED/SATISFIED/NOT_APPLICABLE/UNKNOWN) | Additive new field; keep `mandatoryPitStops` for now but stop presenting "MUST STOP" language. (see Q2/Q3) |
| `nextCompound` fabricated on TO_FINISH | **Do not fabricate**; `TO_FINISH` → `WINDOW —` | Behavior change in `_driver_strategy`/`_driver_transition_outlook`. |

### Q3. Which new fields are additive within API v1 vs semantically breaking?

**Additive (safe within `schemaVersion: 1`):**
- `strategy.disposition`: `"PIT_EXPECTED" | "TO_FINISH" | "UNKNOWN"` (per driver + battle).
- `strategy.windowState`: `"ACTIVE" | "WINDOW_PASSED_EXTENDING" | "TO_FINISH" | "RESETTING"` (preserves prior window as context).
- `dryTyreRequirement`: `{state, evidence, profileVersion}` at race + driver scope.
- `strategyValidity`: `"VALID" | "RESETTING" | "RECALCULATING" | "UNAVAILABLE"` (race-level + per-driver).
- `raceStrategy`: expanded population objects — `activeRunnerCount`, `startingTyreDistribution`, `stopDistribution`, `observedSequences`, `stintContextByCompound`, `ruleLandscape`, `fieldTrend` (see §18).
- `context.historical`: `HistoricalContext` block (season, circuitId, comparability NORMAL/LIMITED/INCOMPATIBLE, stopDistribution, compoundSequences, stintLengths, sourceNote).
- `context.officialPreRace`: `OfficialPreRaceContext` block (source, publishedAt, retrievedAt, sourceUrl, expectedStopCount, primarySequence, alternateSequence, statedPitWindows, caveats, providerVersion).
- `netPitLoss`: explicit `null` marker + `dependency` note.
- `projectionGate`: `{hardValidity:{violations:0,...}, plausibility, stability}` provenance block.
- Bump `modelVersion` to a new value (e.g. `race-intelligence-v2.1`) — additive, not a schema break.

**Semantically breaking (must NOT be hidden behind `schemaVersion: 1` without caller migration):**
- Changing `pitWindow` value semantics from "likely stop" to "gated, horizon-bounded, may be `TO_FINISH`/`WINDOW_PASSED`". Consumers that assume a `[lo,hi]` number must handle null. **Mitigation:** keep `pitWindow.value: [lo,hi] | null` type (already `null`-able in protocol.ts) and add `windowState` so callers branch explicitly.
- Downgrading `undercutStrength` from quantified to descriptive changes `value` from STRONG/MODERATE/LIMITED to descriptive tokens — a **consumer-visible** semantic shift. **Mitigation:** keep the key, document the change, update UI labels; coordinate with §21.5 Battle page.
- Suppressing `freeStopMargin` / `projectedRejoinPosition` from published to forced-UNKNOWN is a behavior regression for any consumer that read a number. **Mitigation:** they are already `UNKNOWN`-able; force `UNKNOWN` with explicit reason; §17.1 says these must not be published until NetPitLoss — so this is the *correct* new truth, not a defect.

**Net:** no `schemaVersion` bump required (stays `1`); `modelVersion` bump + additive fields + documented semantic shifts. This is an **additive-with-documented-semantics** change, not a v2 schema break.

### Q4. Which Strategy outputs must be suppressed until `NetPitLoss` exists?

Per v2.1 §17.1 + §25 scenario 25 + acceptance principle 21:
- **Free-stop Margin** (`freeStopMargin`) — force `UNKNOWN`, evidenceBasis: "blocked: NetPitLoss not yet implemented".
- **Projected Rejoin Position** (`projectedRejoinPosition`) — force `UNKNOWN`, same reason.
- **Undercut** (`undercutStrength`) — demote to **descriptive conditions only**; must not imply quantified pit-economics advantage.
- Do **NOT** substitute raw `pitLoss` (pit-lane duration) into any of these.
- Add explicit `netPitLoss: {status: "NOT_IMPLEMENTED", requiredBy: ["freeStopMargin","projectedRejoinPosition","undercutQuantified"]}` to the snapshot so the dependency chain is visible in code + docs.

### Q5. How will race-only Strategy/Battle navigation be represented?

- **Backend:** analytics snapshot is only meaningful for `session_kind in {race, sprint}`. For `practice_*` / `qualifying` / `sprint_qualifying`, the backend still returns a valid (possibly minimal) snapshot but the **frontend hides** Strategy + Battle destinations (v2.1 §3.1/§3.2 — "Hide them because the concepts are not applicable"; do not show disabled tabs).
- **Frontend `AppShell.tsx`:** add a `ProductView = ... | "strategy"` union; render `STRATEGY` nav button **only** when `layout === "race"` (race-family). Battle button already present — also gate it to race-family. For qualifying/practice, nav becomes `SESSION | DRIVER | TV MODE | SETTINGS`.
- **TV:** gate `TVModeView` Strategy/Battle panels to race-family; qualifying/practice TV uses authored session states (v2.1 §3.4).
- **Driver page:** `DriverFocusView` shows Strategy lens only for race-family; qualifying/practice driver shows factual lap/tyre/sector/pace evidence only (v2.1 §3.3).
- Determination of "race-family": `session_kind in {"race","sprint"}` — a single helper `isRaceFamily(kind)` in `domain/sessionLayout.ts` (extend `classifySession`) used by AppShell, TV, Driver, Battle.

### Q6. How will source cursor consistency be tested for delay/replay?

- **Existing plumbing (keep + test):** `playback.ReplayController.seek_delay(seconds)` and `replay.replay(..., at=...)` already produce a cursor-limited state; `evidence.SessionEvidence.laps_for_driver(at=...)`/`pit_events_for_driver(at=...)` already enforce the cutoff. `build_analytics_snapshot` receives `sequence` + `as_of` and builds evidence via `event_limit=sequence`.
- **New regression test (v2.1 §2.3 + scenario 19):** two viewers, viewer A delay 0s, viewer B delay 30s, compared at the **same source cursor** → their semantic state + analytics must be equivalent for same model/context versions (transport-only metadata may differ).
  - Test approach: build a `ReplayResource` with a known event list; call `build_analytics_snapshot(resource, state_A, sequence=K, as_of=T, context)` and `(resource, state_B, sequence=K, as_of=T, context)` where state_A/state_B are reconstructed from the same `at=T` cutoff; assert `drivers`, `battle`, `raceStrategy`, `pitLoss` are deep-equal (ignore `asOf`/`sequence`/transport).
- **New regression test (scenario 20 — loud failure):** inject a cross-meeting / future-evidence context and assert the snapshot is **rejected/invalidated** (raises an integrity error or returns a `strategyValidity: "UNAVAILABLE"` with a hard-integrity provenance entry), **not** silently demoted to `UNKNOWN`.
- **New test (scenario 18):** a projection whose `pitWindow` bound exceeds total race laps is rejected by the hard validity gate (violations=0 published).
- **New test (scenario 16):** projection thrashing — a window that changes every lap is suppressed by the stability gate (hysteresis over recent laps), falling back to T0–T3.
- **New test (scenario 17):** SC/VSC/Red event at cursor N invalidates the prior published Outlook; the snapshot at N shows `strategyValidity: "RESETTING"` and no stale window.

### Q7. Which context artifacts are persisted vs ephemeral?

Per v2.1 §5.5:
- **Persistent (low-frequency, target-session-owned):**
  - `WeekendContext` (existing `weekend.WeekendContextStore`/`Coordinator`) — keep persisted.
  - `HistoricalContext` — **new** persisted artifact, target-session-owned, cached locally (replay must not need internet).
  - `OfficialPreRaceContext` (Pirelli) — **new** persisted artifact, target-session-owned, cached locally.
  - Downloaded/recorded session (existing) — authoritative persistent asset.
- **Ephemeral / rebuildable (NOT persisted per-second):**
  - `AnalyticsSnapshot` / Strategy answers — server-computed, in-memory cache (`AnalyticsService._cache`), deterministically rebuildable from evidence + context + model version.
  - Cursor-keyed analytics cache — disposable.
- **Contract for Milestone 4 (define here, enforce there):** each persistent derived artifact carries explicit `target_session_key` ownership; M4 Admin delete must cascade: remove recording + target-owned derived artifacts + invalidate in-memory analytics cache for that session + leave global catalog metadata intact. **Not implemented here** (v2.1 §2.7, §5.5, non-goal §26).

### Q8. Which requirements belong only to future Milestone 4 lifecycle enforcement?

- Admin delete operation + SQLite/control-plane lifecycle (v2.1 §5.5 "Milestone 4 deletion semantics").
- Viewer Profiles / remembered preferences / Administration (ROADMAP M4).
- Sync Groups / devices (ROADMAP M5).
- Normalized public live timing (ROADMAP M6).
- **We only define the data-ownership contract** (target-session ownership on persisted derived artifacts) so M4 can enforce it. We do **not** build a second Admin/delete subsystem (explicit non-goal, §26).

### Q9. Which historical/Pirelli acquisition pieces are implement-now vs bounded discovery spike?

Per v2.1 §6 + §22:
- **IMPLEMENT NOW (contract level):**
  - `OfficialPreRaceContext` normalized contract (dataclass + serialization + snapshot field) — **now**, so the model/UI contract is stable regardless of source.
  - `HistoricalContext` contract (dataclass + serialization + snapshot field + comparability state) — **now**.
  - Replay-cutoff enforcement for both (scenario 13, 14, 24) — **now** (tests + gate logic).
  - Manual structured metadata path for Pirelli (v2.1 §6.3 — "support a small manual structured metadata path before building a fragile scraper") — **now**, so the contract is exercisable in replay without internet.
- **BOUNDED DISCOVERY SPIKE (time-boxed, may return empty):**
  - Automated Pirelli acquisition from an official Pirelli/F1 press article (v2.1 §6.2 step 2–3): determine a stable official source path, parse **only explicit published statements**, no LLM inference, store with full provenance. **Spike, not full build.** If brittle → fall back to the manual path (already implemented).
  - Automated `HistoricalContext` generation from Slipstream-compatible historical race data (v2.1 §22): resolve `Y-1` same-circuit, compute stop/sequence/stint facts, cache. **Spike** — depends on having the prior-season race in the local archive; if absent → omit (scenario 12).
- **NOT now (deferred / non-goal):** full tyre-set inventory, multi-year priors, probabilistic ML race sim, LLM real-time Strategy (all §26 non-goals).

### Q10. Smallest coherent implementation sequence leaving the product working after each step

Follow the doc's A–H, refined to concrete units (each leaves backend:8000 + UI:3344 running, all tests green):

- **A. Contracts + invariants + tests.** Add new dataclasses (`OfficialPreRaceContext`, `HistoricalContext`), extend `strategy_rules` with `dryTyreRequirement`, add `disposition`/`windowState`/`strategyValidity`/`netPitLoss`/`projectionGate` fields to the snapshot schema + `protocol.ts`. Add the integrity + hard-validity + stability **test skeletons** (red). No behavior change yet — product still runs.
- **B. Evidence / semantic primitives.** Extend `evidence.py` with evidence-domain separation (§14): distinct sets for Pit-Event / Stint-Life / Compound-Choice / Stop-Count / Rules / Pace / Race-Control. Add `raceProgress` comparability primitive. Add `active-runner` population helper. (No UI change.)
- **C. Analytical model changes.** Rewrite `_driver_strategy`/`_race_strategy`/`_driver_transition_outlook` internals to: enforce race-horizon (`TO_FINISH`, `WINDOW_PASSED_EXTENDING`, no terminal-lap cutoff), apply dry-tyre requirement, apply stability gate (hysteresis), apply soft plausibility gate, force `freeStopMargin`/`projectedRejoinPosition` to UNKNOWN, demote undercut to descriptive, suppress Sprint→GP stint-life comparability, active-runner distributions. **CHECK-IN with user at end of C (model changes).**
- **D. Race Strategy page + session snapshot.** Add top-level `STRATEGY` destination (race-family only), compact Session Strategy Snapshot card, full Strategy page (6 sections per §21.3). **CHECK-IN with user at end of D (Strategy page).**
- **E. Driver/Battle/TV consumers.** Update `DriverFocusView` (race-only strategy lens), `BattleView` (interaction insight, descriptive undercut), `TVModeView` (race-family strategy/battle states, no interactive popovers in TV).
- **F. Historical/official context contracts + bounded acquisition.** Wire `HistoricalContext` + `OfficialPreRaceContext` into snapshot + replay cutoff enforcement; run the Pirelli/Historical acquisition spike (manual path guaranteed, automated optional).
- **G. Backtest harness / validation docs.** Replay archived races at multiple cursors, score raw + event-censored hit rate, false-stop, window error, stability, coverage, hard-validity=0; development/holdout split with pre-registration. **CHECK-IN with user before G (backtesting).**
- **H. Documentation + final regression.** Refactor `docs/analytics.md` into the living charter + `docs/analytics/` model registry + `CHANGELOG.md`; run the full 26-scenario regression suite; final report (branch, SHAs, files, checks, gaps, deferred).

---

## 3. Requirement → file map (v2.1 normative sections → concrete files touched)

| v2.1 § | Requirement | Backend file(s) | Frontend file(s) |
|---|---|---|---|
| 2 / 2.1 / 2.3 | Temporal authority, delay, cursor consistency | `playback.py`, `replay.py`, `evidence.py`, `analytics.py` | `useSlipstreamSession.ts` |
| 3.1 / 3.2 / 3.3 / 3.4 | Race-family gating (Strategy/Battle) | `analytics.py` (kind guard) | `AppShell.tsx`, `sessionLayout.ts`, `TVModeView.tsx`, `DriverFocusView.tsx`, `BattleView.tsx` |
| 4 | Epistemic tiers T0–T4 + presentation rule | `analytics.py` (tier tagging) | `StrategyOutlook.tsx`, `InfoPopover.tsx` |
| 5.1 | `WeekendContext` rules | `weekend.py`, `analytics.py` | — |
| 5.2 | `HistoricalContext` (new) | **new** `context.py` or `weekend.py`; `analytics.py`; `serialization.py` | `protocol.ts`, Strategy page |
| 5.3 | `OfficialPreRaceContext` (new) | **new** `context.py` or `external.py`; `analytics.py`; `serialization.py` | `protocol.ts`, Strategy page |
| 5.5 | Persistence/ownership + M4 contract | `weekend.py` (ownership key), **new** context stores | — (contract only) |
| 6 | Pirelli acquisition (contract + spike) | **new** `pirelli.py` (contract) + spike script | Strategy page (display) |
| 7 / 7.1 | Replay semantics for all context | `replay.py`, `analytics.py` | — |
| 8.1 | Data/temporal/evidence integrity invariants | **new** `integrity.py`; `analytics.py`; `evidence.py` | — |
| 8.2 | Hard projection publication gate | **new** `publication_gate.py`; `analytics.py` | — |
| 9 | Soft plausibility/evidence gate | `analytics.py` (plausibility) | — |
| 10 | Projection stability gate (hysteresis) | `analytics.py`; **new** `stability.py` | — |
| 11 | Strategy validity state | `analytics.py` | `StrategyOutlook.tsx`, Strategy page |
| 12 | Race-horizon behavior (TO_FINISH / WINDOW_PASSED) | `analytics.py` (`_driver_transition_outlook`, `_driver_strategy`) | `StrategyOutlook.tsx` |
| 13 | Race-phase / fuel-load comparability | `analytics.py` (raceProgress primitive) | — |
| 14 | Evidence domain separation + lap-quality vocab | `evidence.py`, `analytics.py` | `PaceDeltaChart.tsx` (labels) |
| 15 | Tyre-rule constraint model (dryTyreRequirement) | `strategy_rules.py`, `analytics.py` | `StrategyOutlook.tsx`, Strategy page |
| 16 | Descriptive race intelligence (compact) | `analytics.py` | Strategy page, `StrategyOutlook.tsx` |
| 17 / 17.1 | Terminology corrections + NetPitLoss suppression | `analytics.py` (labels, suppress) | `StrategyOutlook.tsx`, `BattleView.tsx`, `CompoundBadge.tsx`, `InfoPopover.tsx` |
| 18 | Race-level Strategy model (distributions) | `analytics.py` (`_race_strategy`) | **new** `views/StrategyView.tsx` |
| 19 | Driver Strategy model | `analytics.py` (`_driver_strategy`) | `DriverFocusView.tsx` |
| 20 | Battle Strategy model | `analytics.py` (`battle_recommendation`) | `BattleView.tsx`, `useBattleRecommendation.ts` |
| 21.1–21.6 | Strategy product surfaces | `analytics.py` | `AppShell.tsx`, **new** `StrategyView.tsx`, `RaceView.tsx`, `StrategyOutlook.tsx`, `TVModeView.tsx` |
| 22 | Historical Context acquisition (spike) | **new** `historical.py` (spike) | Strategy page |
| 23 | Projection backtesting (harness) | **new** `backtest.py` + tests | — (harness) |
| 24 | Model documentation | `docs/analytics.md`, **new** `docs/analytics/*.md` | — |
| 25 | 26 regression scenarios | **new** `tests/test_strategy_v2.py` (+ extend `test_intelligence.py`, `test_api.py`) | `web/tests/domain.test.mjs`, `rendered-html.test.mjs` |

---

## 4. Ambiguities and conflicts found against the real codebase (flag, do not assume)

1. **FRONTEND DOES STRATEGY MATH (conflicts with invariant 6/11 + §5.1).**
   - `web/hooks/useBattleRecommendation.ts` imports `advanceBattleRecommendation` from `web/domain/battleHysteresis.mjs` and **re-runs hysteresis in React** (holdSeconds/switchMargin) over the backend candidate. This is exactly the "recreate Strategy math" the invariants forbid.
   - `web/components/analysis/PaceDeltaChart.tsx` computes a **MAD-based scale in the browser** (`Math.abs`, median/MAD, magnitude) from `sample.delta` — a model-specific comparability filter (v2.1 §14.1 says these must be deterministic, documented per model, and server-side).
   - `web/views/BattleView.tsx` computes a gap-history `min/max/range` and a local scale.
   - **Conflict:** the doc's own current-file list (`battleHysteresis.mjs`, `PaceDeltaChart.tsx`) includes these, so the doc *knows* they exist. **I flag, I do not silently rewrite.** Recommendation: move hysteresis + scale logic server-side (Phase E), leave frontend as pure render. **Need user confirmation before removing the client-side hysteresis path** (it changes the Battle recommendation UX).

2. **Battle is not currently race-family-gated.**
   - `AppShell.tsx` always renders the `BATTLE` nav button regardless of `layout`; only `RaceView`/`StrategyOutlook` are race-gated. v2.1 §3.1/§3.2 require Battle to be **race/Sprint only** and hidden for Qualifying/Practice. **Change needed; low-risk** (hide the button for non-race families). Flagging because it is a visible nav change.

3. **`pitLoss` currently mixes Sprint pit-lane durations into the Race metric.**
   - `_pit_loss_metric` in `analytics.py` (line 949) explicitly appends **same-meeting Sprint** pit-lane durations to the Race candidates list. v2.1 §13/§5.1/§25-22 forbid Sprint stint-life/race-progress evidence from directly driving Grand Prix pit-window comparability in V2.1. **This is a direct conflict — must remove Sprint values from the Race pit-loss/pit-window path** (Sprint may remain for explicitly documented contextual metrics only). Flagging as a required behavior change.

4. **`_rejoin_metrics` already computes `freeStopMargin` and `projectedRejoin` from raw gaps + pit-loss.**
   - `analytics.py` line 833. v2.1 §17.1 says both must be **suppressed until NetPitLoss exists** and must not use raw pit-lane duration. **Required change: force both to `UNKNOWN`.** This regresses the current V1 published numbers — that is the *intended* correction, not a defect. Flagging because it is the single most user-visible removal.

5. **`strategy_rules.py` returns `mandatory_pit_stops: None` for 2026 Race + `dry_compound_obligation: "conditional_two_specifications"`.**
   - v2.1 §15 wants an explicit `dryTyreRequirement` state (UNSATISFIED/SATISFIED/NOT_APPLICABLE/UNKNOWN) per driver, accounting for wet/intermediate + red-flag tyre-change. The current profile is a **single static string**, not a per-driver computed state. **Change needed:** compute `dryTyreRequirement` per driver from compound history + rule profile in `analytics.py`. Flagging as a model change (Phase C).

6. **No `disposition` (PIT_EXPECTED/TO_FINISH/UNKNOWN) or `windowState` (WINDOW_PASSED_EXTENDING) exists today.**
   - Current `_driver_transition_outlook` (analytics.py:381) computes `nextCompound` + `pitWindow` from same-compound stint-life consensus (returns `unknown` when unsupported — it does *not* fabricate, good) but: (a) it has no `disposition`/`windowState` distinction, (b) it has no race-horizon bound — a `projected[1]` beyond total race laps is only caught if it falls *before* the current lap, and (c) it cannot express `WINDOW_PASSED_EXTENDING` or `TO_FINISH`. v2.1 §12 requires explicit disposition + window-passed state + no arbitrary terminal-lap cutoff. **New fields + behavior + horizon gate.** Flagging (Phase C).

7. **No `strategyValidity` (VALID/RESETTING/RECALCULATING/UNAVAILABLE) state today.**
   - v2.1 §11 requires it + the "do not keep displaying stale pit windows" rule after SC/VSC/Red. Current code has no reset invalidation. **New field + reset detection from `state` race-control events.** Flagging (Phase C).

8. **No active-runner population logic today.**
   - `build_analytics_snapshot` builds `evidence_by_driver` for **every** `state.drivers` entry and `_race_strategy` counts all of them; `grep` confirms **no** `retired`/`withdrawn`/`dnf`/`active-runner` filter anywhere in `analytics.py`. v2.1 §18 requires field distributions over **active race participants at the cursor** (retired/DNS excluded, field size never hard-coded). `DriverState` (state.py:12) already carries a `status: str = "UNKNOWN"` field plus an `availability: dict[str,str]` — so the "active" predicate is derivable from existing state, but it must be **defined and applied** (a documented active-runner filter in `analytics.py`), not assumed. Flagging as a model change (Phase C) + a decision needed on exactly which `status`/`availability` values count as active.

9. **§25 count mismatch (26 vs "25").** Already flagged in §0.2. Proceeding with the doc's 26.

10. **`external.py` currently models a generic `ExternalIntelligence` boundary.**
    - v2.1 §5.3/§5.4 says Pirelli must be a **separate `OfficialPreRaceContext`** class, not lumped into generic `ExternalIntelligence`. The existing `external.py` `ExternalStrategyItem` is the generic bucket. **Change needed:** introduce `OfficialPreRaceContext` as its own artifact; keep `external.py` for future non-core sources. Flagging (Phase F).

**No assumption made on any of the above — each is flagged for user decision before implementation.**

---

## 5. Implement-now vs bounded-discovery-spike (explicit)

| Item | Mode |
|---|---|
| `dryTyreRequirement` state (§15) | **Implement now** (Phase C) |
| `disposition` / `windowState` / race-horizon (§12) | **Implement now** (Phase C) |
| `strategyValidity` + SC/VSC/Red reset (§11) | **Implement now** (Phase C) |
| Hard validity gate (0 violations) (§8.2) | **Implement now** (Phase A skeleton, C logic) |
| Soft plausibility gate (§9) | **Implement now** (Phase C) |
| Projection stability gate / hysteresis (§10) | **Implement now** (Phase C) |
| Active-runner distributions (§18) | **Implement now** (Phase C) |
| Sprint→GP comparability removal (§13/§22) | **Implement now** (Phase C) |
| `freeStopMargin`/`projectedRejoin` suppression (§17.1) | **Implement now** (Phase C) |
| Race-family nav gating (§3) | **Implement now** (Phase D) |
| Strategy page + session snapshot (§21) | **Implement now** (Phase D) |
| Driver/Battle/TV consumers (§21) | **Implement now** (Phase E) |
| `HistoricalContext` + `OfficialPreRaceContext` **contracts** + replay cutoff + manual Pirelli path (§5/§6/§22) | **Implement now** (Phase F) |
| **Automated Pirelli acquisition** (official press article) | **Bounded discovery spike** (Phase F, time-boxed, may return empty → manual path) |
| **Automated Historical Context generation** from prior-season archive | **Bounded discovery spike** (Phase F; if no prior-season race locally → omit, scenario 12) |
| Backtesting harness + dev/holdout (§23) | **Implement now** (Phase G, after check-in) — harness is required, not a spike |
| Admin delete / M4 lifecycle (§5.5) | **Define contract only** — M4 enforces (non-goal here) |
| Frontend Strategy-math removal (battleHysteresis, PaceDeltaChart MAD) | **Flagged; needs user sign-off** (Phase E) before removing client-side logic |

---

## 6. Check-in gates (per task instructions — do not blast through A–H)

- **END of Phase C** → check in: **model changes** (dry-rule, disposition, validity, gates, suppression).
- **END of Phase D** → check in: **Strategy page** (nav, session snapshot, full page).
- **BEFORE Phase G** → check in: **backtesting** (harness design, dev/holdout, metrics).

---

## 7. Hard product rules carried into implementation (non-negotiable)

- No hindsight (§5.3, §7): never use later laps / final result / later stops / later race-control / context published after cutoff.
- `UNKNOWN` remains valid (invariant 7).
- Evidence-boundary violations **fail loudly** as integrity errors, never disguised as low-confidence (invariant 8, §8.1).
- Hard validity target: **0 violations published** (§8.2).
- Viewer source cursor is the sole temporal authority (invariant 9/10, §2.1, §7.1).
- No persistent high-frequency Strategy snapshots; analytics rebuildable/cacheable (invariant 12, §5.6).
- Server-side analytics only; **no Strategy math in React** (invariant 6/11, §5.1, §5.5).
- No AGPL-derived code/fixtures/structure from `slowlydev/f1-dash` (§5.7).
- Sprint stint-life/race-progress does **not** directly drive GP pit-window comparability in V2.1 (§13, §25-22).
- Field distributions over active runners, never hard-coded (§18, §25-23).
- Free-stop/Projected Rejoin not published until defensible NetPitLoss (§17.1, §25-25).
- Pirelli = separate attributed `OfficialPreRaceContext`, replay-safe, no LLM in deterministic path (§5.3, §6, §5.7).

---

## 8. Decisions — status

### 8.1 DECIDED (user, 2026-08-17)
1. **Proceed against all 26 regression scenarios** (doc §25), **including mandatory Scenario 26 (Admin deletion lifecycle)**.
   - Scenario 26 is the v2.1 **data-ownership contract** for Milestone 4. The truncated handoff phrase "…correct data-ownership contract fo…" resolves to doc §5.5 (line 779): *"It must, however, **define the data-ownership contract that Milestone 4 will enforce**."* — i.e. "…for Milestone 4 to enforce."
   - This revision **defines the contract** (target-session ownership on persistent derived artifacts + M4 cascade semantics, §5.5, §26-item-26); M4 **enforces** the actual Admin delete. We do NOT build a second Admin/delete subsystem here (§26 non-goal).

### 8.2 DECIDED (user, 2026-08-17)
2. **Move client-side Battle hysteresis + PaceDeltaChart MAD scale to the server** (invariant 6/11). Frontend becomes pure render.
3. **Hide the BATTLE nav button** for Qualifying/Practice (race-family gating).
4. **Suppress `freeStopMargin` + `projectedRejoinPosition`** to `UNKNOWN` until NetPitLoss exists.
5. **Remove Sprint pit-lane durations** from the Race `pitLoss`/pit-window path.
6. **Approve the A–H sequence** and the three check-in gates (end-C, end-D, before-G).
7. **Approve treating automated Pirelli + Historical Context acquisition as bounded spikes** (manual path guaranteed).

**Phase A started 2026-08-17.**
