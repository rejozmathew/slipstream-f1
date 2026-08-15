# Race Intelligence and Strategy Analytics

This document specifies the production derivations currently emitted by `analytics.snapshot` model `race-intelligence-v1`. It describes what Slipstream calculates, which evidence is allowed, when a value becomes `UNKNOWN`, and important limitations.

The implementation is in `src/slipstream/analytics.py`. Strategy, Driver, Battle, Timing Tower, and TV are renderers of this one backend model; they must not independently recreate these calculations in React.

## Evidence boundary

Analytics combines four deliberately separate inputs:

```text
static rules/circuit identity
        + same-meeting WeekendContext
        + selected-session SessionEvidence as of the replay cursor
        + optional, separately labelled External Intelligence
        -> AnalyticsSnapshot
```

- `RaceState` is the current factual state of the selected session.
- `SessionEvidence` contains normalized detailed evidence from the selected session only. A replay calculation uses only observations at or before its `seq`/`asOf` position.
- `WeekendContext` contains only earlier sessions with the same `meeting_key` that ended before the selected session's `evidence_cutoff`.
- Previous Grand Prix weekends, prior editions at the same circuit, and generic recent-race form are not V1 inputs.
- External Intelligence is disabled by default and is never silently mixed into the deterministic Slipstream model.
- Full replay recordings remain session-scoped. Weekend Context contains compact evidence, not replay assets.

Persisted context packs and analytics consumption both reject cross-meeting session evidence. This is a hard no-hindsight and no-cross-weekend boundary.

## Metric envelope

Every calculated metric has the same shape:

```json
{
  "value": null,
  "status": "UNKNOWN",
  "unit": null,
  "evidenceBasis": ["why this value is or is not available"],
  "modelVersion": "race-intelligence-v1",
  "quality": "insufficient"
}
```

| Status | Meaning |
| --- | --- |
| `OBSERVED` | Direct normalized source fact. |
| `DERIVED` | Deterministic calculation from observed facts. |
| `ESTIMATE` | A deterministic projection or contextual inference with declared limitations. |
| `UNKNOWN` | Required evidence is missing, incomparable, unsupported, or insufficient. |

`UNKNOWN` is a valid result. Slipstream does not substitute generic values to fill a card.

## Evidence stages

| Stage | Current trigger | Meaning |
| --- | --- | --- |
| `BASELINE_AVAILABLE` | No current-session lap evidence and Weekend Context is not ready. | Only versioned rules and static factual context are available. V1 does not invent a generic circuit strategy. |
| `WEEKEND_MODEL_READY` | Same-meeting Weekend Context is ready and the selected session has not produced lap evidence. | Eligible earlier sessions can inform pit loss and a contextual degradation reference. |
| `LIVE_OUTLOOK` | At least one selected-session lap observation exists, or the session is beyond lap 1. | Current-session evidence progressively replaces contextual estimates when its quality threshold is met. |

For historical replay, “live” means live at that replay cursor—not knowledge from the completed race.

## Lap quality and pace delta

Only laps normalized as `representative` can move the clean-lap baseline or degradation model. Pit-in, pit-out, whole-track SC/VSC/red neutralization, and other contaminated laps remain visible in the pace chart but are excluded from the model. Unknown quality is not silently treated as clean.

For each stint:

1. Require at least three representative laps with numeric duration.
2. Calculate the median lap duration and median absolute deviation (MAD).
3. When MAD is greater than zero, retain laps no farther than `3 × MAD` from the median. When MAD is zero, retain the original sample.
4. Require at least three retained laps and use their median as the stint baseline.

```text
lap pace delta = raw lap duration - robust clean-stint median
```

Positive values are slower than the baseline; negative values are faster. Contaminated laps can have a displayed delta but never influence the baseline. Model identifier: `clean-stint-median-mad-v1`.

## Degradation

Current-session degradation uses the driver's current stint:

1. Require at least four representative laps with numeric duration.
2. Establish the robust baseline described above.
3. Exclude laps more than 3.0 seconds from that baseline.
4. Require at least four remaining laps spanning tyre age or lap index.
5. Fit an ordinary least-squares line of lap duration against tyre age. Lap number is used only when tyre age is unavailable.

The returned slope is seconds per lap (`s/lap`) and is `DERIVED` for current-session evidence.

| Quality | Rule |
| --- | --- |
| High | At least 8 retained laps and regression residual RMS no greater than 0.35 seconds. |
| Medium | At least 6 retained laps. |
| Low | 4–5 retained laps. |

When current-session degradation is unavailable, the Weekend model may use one same-driver, same-meeting prior-session long run. Stints are never mixed. V1 selects the eligible stint with the largest sample, using the later session only as a tie-breaker. This becomes an `ESTIMATE`, and quality is capped at Medium because prior-session degradation is context rather than current-race fact.

If both weekend and current-session degradation exist, the UI reports `DEGRADATION ABOVE WEEKEND REFERENCE` or `DEGRADATION BELOW WEEKEND REFERENCE` when the difference is at least `0.05 s/lap`.

## Pit events and pit loss

A viewer pit event preserves pit lap/time, previous/new compound, source-supported stationary stop duration, and source-supported complete pit-lane duration as independent facts. Stationary duration is never fabricated from pit-lane duration.

Pit loss is the median of observed pit-lane durations available from the selected session up to the replay cursor plus eligible same-meeting context. At least two values are required.

| Sample count | Quality |
| --- | --- |
| 2–3 | Low |
| 4–7 | Medium |
| 8 or more | High |

V1 does not separately calculate SC/VSC pit loss; that remains `UNKNOWN` until defensible evidence exists.

## Strategy metrics

### Likely next compound

Slipstream examines current-session field pit transitions whose previous compound matches the selected driver's current compound. The most common observed next compound requires at least two comparable transitions. It is an `ESTIMATE`; fewer observations remain `UNKNOWN`.

This is not a claim about complete remaining tyre inventory. Set identity, new/used condition, and availability remain capability-gated.

### Pit window

At least three comparable current-session transition laps are required. V1 reports the central observed range using the indexed first and third quartile transition laps. It is an `ESTIMATE`, not an optimization result. Practice lap numbers are not converted into a Grand Prix pit window.

### Primary and alternate strategy

- Primary is `current compound → likely next compound` only when both are established.
- Alternate uses the second-most-common comparable transition and also requires at least two observations.
- Otherwise each value remains `UNKNOWN`.

V1 does not claim an observed compound transition is legally available to a particular car without inventory evidence.

### Likely stop count

- At a completed session, the driver's normalized pit count is `OBSERVED`.
- During a Sprint, V1 does not apply a Grand Prix stop pattern and returns `UNKNOWN`.
- During a Race, an estimate is allowed only after at least 65% distance and with pit counts from at least five classified drivers. The value is the larger of the driver's current pit count and the rounded field median.
- Earlier or thinner evidence remains `UNKNOWN`.

This is a likely behavior estimate, not a tyre-legality assertion.

### Tyre stress

| Degradation | Label |
| --- | --- |
| At least `0.15 s/lap` | High |
| At least `0.06 s/lap` | Medium |
| Below `0.06 s/lap` | Low |

It inherits the degradation evidence and quality. Missing degradation means `UNKNOWN`.

### Undercut strength

V1 requires both degradation and observed pit loss.

| Degradation | Label |
| --- | --- |
| At least `0.15 s/lap` | Strong |
| At least `0.08 s/lap` | Moderate |
| Below `0.08 s/lap` | Limited |

Pit loss is currently an evidence gate, not a weighted term in the threshold. Traffic, tyre warm-up, driver pace changes, and precise rejoin traffic are not modelled, so this is an `ESTIMATE`.

### Free-stop margin

When the driver's gap to the leader, the next car's gap, and pit loss are numeric:

```text
free-stop margin = gap of car behind - driver gap - pit loss
```

A positive value indicates the observed gap exceeds the modelled normal pit loss. Missing or non-comparable gaps produce `UNKNOWN`.

### Projected rejoin position

V1 adds normal pit loss to the driver's current gap to the leader and compares that projected gap with every other classified car. Complete numeric field gaps are required. Lapped-car labels or any other non-comparable gap make the projection `UNKNOWN`; they are never treated as zero.

The estimate excludes pace evolution, simultaneous pit stops, traffic delay, safety-car compression, and tyre warm-up.

### Weather risk

`RAIN DETECTED` is `OBSERVED` only when the current normalized rainfall sensor is true. A false/no-rain observation is not a forecast, so V1 otherwise returns `UNKNOWN` rather than claiming no weather risk.

## Driver battle context

Ahead and behind identities come from current factual classification. The adjacent interval is parsed only when it is a comparable numeric time gap. Lapped or missing gaps retain the identity but use status `UNKNOWN` for the gap. No closing-rate value is invented in the backend when a reliable time series is unavailable.

## Recommended Battle score

V1 scores adjacent classified pairs only when their interval is numeric. Scores are deterministic and clamped to 0–100.

| Factor | Contribution |
| --- | --- |
| Current gap | `max(0, 70 - min(gap, 14) × 5)` |
| Relative degradation | `(ahead degradation - behind degradation) × 80`, clamped from -10 to +15 |
| Representative pace | `(ahead baseline - behind baseline) × 12`, clamped from -10 to +18 |
| Tyre-age offset | `(ahead age - behind age) × 0.8`, clamped from -5 to +10 |
| Position significance | `max(0, 8 - (ahead position - 1))` |
| Pit-window overlap | Two points per overlapping lap, capped at +8 |

Only factors with sufficient evidence contribute. Closing/opening trend is displayed from factual viewer history but is not currently part of the backend Battle Score.

Recommended Battle hysteresis uses replay/source time:

- minimum hold: 20 seconds;
- challenger margin: 8 score points;
- a missing held pair may switch immediately;
- seeking backwards resets the held recommendation to the candidate valid at the earlier source time.

`LEADER` always means P1 versus P2. `PINNED` never auto-switches.

## Sporting-rule profiles

- The 2026 Sprint profile does not inherit the Grand Prix two-dry-specification obligation and does not assume a mandatory pit stop.
- The 2026 Race profile records the conditional dry-compound obligation but does not convert it into a universal mandatory pit-stop count. Wet/intermediate use and red-flag tyre changes matter.
- Unverified historical seasons/events return an unknown rule profile rather than receiving current rules.
- Event-specific historical exceptions require explicit future profiles.

The current profile cites the [FIA 2026 Formula 1 Regulations, Section B Sporting, Issue 08](https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_b_sporting_-_iss_08_-_2026-08-05_7.pdf).

## Caching and replay determinism

Analytics is cached by meaningful factual and context revisions, not recalculated from scratch every 250 ms. Each response copies the cached model and applies the requested `sequence` and `asOf` metadata.

The result is deterministic for the same recording/cursor, normalized SessionEvidence, validated Weekend Context/model version, sporting-rule profile, and analytics model version. Changing a formula or evidence interpretation requires a model-version change and focused regression coverage.

## Known V1 limitations

- No ML or probabilistic race simulation.
- No complete remaining tyre-set inventory.
- No authenticated live per-car telemetry.
- No driver-specific tyre warm-up or fuel-correction model.
- No separate SC/VSC pit-loss model.
- No prior-weekend or prior-edition circuit baseline.
- No enabled External Intelligence provider.
- No guaranteed optimal strategy; values are evidence-qualified outlooks.

These limitations must remain visible through status, evidence, and quality rather than hidden behind plausible numbers.
