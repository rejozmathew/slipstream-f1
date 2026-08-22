# Race Intelligence and Strategy Analytics v2.1

This is the normative derivation reference for `AnalyticsSnapshot` model `race-intelligence-v2.1`. The implementation lives in `src/slipstream/analytics.py` and `src/slipstream/race_intelligence.py`. React, TV, and future hardware clients render this server result; they do not recreate analytics truth.

## Evidence boundary

```text
versioned sporting/circuit facts
        + same-meeting WeekendContext before evidence_cutoff
        + selected-session SessionEvidence at or before the cursor
        + optional separately labelled External Intelligence
        -> AnalyticsSnapshot
```

`RaceState` is factual current state. `SessionEvidence` is the session-scoped history sidecar. No prior weekend, prior edition, future lap, or result-table inference enters the model. Missing or incomparable evidence produces `UNKNOWN`.

## Pace Trend and lap quality

Only `representative` laps affect pace calculations. Pit-in/out, whole-track SC/VSC/red overlaps, and other contaminated laps remain visible but are excluded. Sector- or driver-scoped yellow evidence does not contaminate a whole lap.

The clean stint baseline requires at least three representative durations, uses the median, and filters at three median absolute deviations when MAD is non-zero. Pace delta is:

```text
raw lap duration - clean-stint median
```

Pace Trend is an ordinary least-squares slope of duration against tyre age over at least four representative current-stint laps, after rejecting samples more than 3.0 seconds from the robust baseline. It is expressed in seconds/lap. It is a raw pace/fade signal, not pure tyre degradation: fuel burn, traffic, driver variation, and changing conditions are not isolated. The legacy `degradation` field is a compatibility alias; product labels use Pace Trend or Pace Fade.

Quality is High for at least 8 laps with residual RMS <= 0.35s, Medium for at least 6 laps, and Low for 4–5 laps. Same-meeting prior-session pace can be shown as separately attributed context, but RaceRead distributions use current-race Pace Trend only.

## Race phase and comparability

Normalized progress `lap / total_laps` defines four explicit bands:

| Phase | Progress |
| --- | --- |
| OPENING | 0–25% |
| EARLY | 25–50% |
| MIDDLE | 50–75% |
| LATE | 75–100% |

Same-phase evidence has weight 1.0; evidence one, two, or three bands away has weight 0.5, 0.2, or 0.1. Current driver/current Race evidence has priority. Sprint is not treated as Grand Prix strategy evidence. Practice/Qualifying can provide labelled context but not Race compound-choice or pit-loss evidence. Wet/dry regime changes are not silently mixed.

## Driver strategy

### Next compound and pit window

A next compound uses current-Race field transitions from the driver’s current compound at comparable or later tyre life. It requires at least three genuine compound-change transitions, at least two for the leading choice, and at least 60% agreement. Same-compound stops remain stint-life evidence but are not compound-choice evidence.

A pit window requires three comparable stint-life observations. The central quartile range is projected from the current stint start. A window behind the cursor, reversed, or beyond the flag is rejected rather than clamped into a plausible-looking value.

### TO_FINISH

`TO_FINISH` is a positive evidence claim, never the absence of a future window. It requires all of:

- a live Race or Sprint and nonterminal driver;
- race lap, total laps, current compound, and current tyre age;
- dry-rule state `SATISFIED` or `NOT_APPLICABLE`;
- no SC/VSC/red/full-track reset state;
- a current clean Pace Trend no greater than 0.25 s/lap;
- at least three completed same-race stint-life samples on the current compound;
- phase-weighted effective sample support of at least 2.0;
- required tyre age at the flag no greater than the phase-weighted 75th percentile of observed life.

If any input is missing or the observed capacity is inadequate, the result is `UNKNOWN`; the model does not infer an extra stop. When `TO_FINISH` is supported, pit window, next compound, primary, and alternate are cleared.

### Dry-tyre rule

Sporting rules are selected by season and session kind. Sprint does not inherit Grand Prix dry-compound obligations. For a Race, incomplete wet/intermediate history, missing event-specific mandatory-specification facts, or unseen red-flag tyre changes can make legality `UNKNOWN`. Tyre changes and pit stops are distinct facts.

## Projection gates

A future strategy is publishable only when all three deterministic gates pass:

1. Hard validity: no future plan for terminal/final states; no past, reversed, or beyond-flag window; no future fields alongside `TO_FINISH`; likely total stops cannot be below completed stops.
2. Plausibility: the driver is active, dry-rule state supports the plan, current-race transition evidence exists, and the track is not in a whole-track reset. `TO_FINISH` uses its stronger evidence test above.
3. Stability: the window is recomputed at each of the last three representative completed laps. Both bounds must stay within two laps. `TO_FINISH` stability comes from its multi-stint phase-weighted support.

SC, VSC, VSC ending, red, and red flag reset the future outlook. Generic yellow does not automatically mean a whole-track reset. A failed/insufficient gate suppresses future plan fields while preserving factual and retrospective data.

Race-wide projections require hard validity plus at least three driver projections passing plausibility and stability. Otherwise they remain `UNKNOWN`.

## RaceRead

`raceRead` is one deterministic server-side field read containing:

- lifecycle and participant/active/circulating/stopped/terminal populations;
- completed-stop distribution;
- separate starting-tyre and current-tyre distributions with denominators;
- current-race Pace Trend distribution;
- observed completed-stint context by compound and phase;
- one authoritative dry-rule population;
- recent factual pit activity;
- an observed compound-sequence archetype only when at least two drivers and 40% of observed sequences agree;
- deterministic `summaryFacts` generated only from the above facts.

Starting tyres come from first-stint evidence and include drivers who later become terminal. Current tyres and stop counts use active runners at the cursor. Archetype is based on observed compound/stint sequences, not pit count alone.

## Battle

Only adjacent, battle-eligible drivers with a numeric interval-to-ahead no greater than 12.0 seconds enter scoring. A 40–60 second pair is not a meaningful recommended battle. Lapped gaps are non-comparable.

The score retains declared contributions for current gap, relative Pace Trend, representative pace, tyre-age offset, position significance, and supported pit-window overlap. Gap history is sampled only when the behind driver completes a lap; transport snapshots do not become chart history.

The server publishes a stabilized recommendation only after the same ordered pair has completed-lap source history spanning at least 20 source seconds and remains within the meaningful-gap limit. Histories are capped at 40 samples. The held pair and `since` time are pure functions of source evidence at or before the cursor, so direct access, backward seeks, and different request orders produce the same result.

## Pit economics boundary

`NetPitLoss` is `NOT_IMPLEMENTED`. Raw pit-lane duration is not a net race-time loss. Therefore free-stop margin, projected rejoin position, and quantified undercut remain suppressed. The model may expose raw factual pit durations and descriptive Pace Trend context without crossing that boundary.

## Determinism and limitations

Analytics caches by source/session/cursor/context/model signature and returns copies. No request history, viewer state, future event, or frontend calculation changes the answer at a cursor.

Not modelled: tyre-set inventory/condition, fuel correction, traffic simulation, warm-up, separate SC/VSC pit loss, probabilistic race simulation, prior-edition circuit baselines, and enabled external intelligence. These remain explicit `UNKNOWN`/`NOT_IMPLEMENTED` boundaries.
