# Published Pirelli strategy

This document is the normative description of Slipstream's published-strategy sidecar. Pirelli is an official pre-race baseline, not team intent or a guaranteed outcome. Slipstream adds only deterministic facts observed at the selected replay cursor. It does not invent a replacement plan.

## Evidence pipeline

1. The single server-owned coordinator checks the official Pirelli Formula 1 RSS/newsroom at startup for the relevant selected meeting and then no more often than every 30 minutes.
2. Responses are archived immutably under `/data/.slipstream/pirelli/<meeting_key>/` with retrieval and source metadata.
3. Deterministic HTML/prose and structured extractors normalize compound nominations, ranked or unranked strategy options, published pit windows, context facts, and optional native-text PDF tyre-bank rows.
4. Validation requires source-backed evidence. Race and Sprint facts remain separate. Multi-event nomination facts retain their own meeting applicability.
5. Admission requires the selected `meeting_key`, target session, session scope, and `evidence_cutoff`. A release retrieved after the cutoff is rejected unless source metadata proves that exact version existed by the cutoff.
6. The admitted baseline is supplied to the cursor-synchronized analytics builder. No browser code fetches Pirelli data.

OCR, image parsing, VLM/LLM extraction, and manual product transcription are deliberately absent. A missing machine-readable tyre bank is ordinary absence and never blocks Strategy.

## Published contract

`AnalyticsSnapshot.publishedStrategy` is authored in `src/slipstream/published_strategy.py` and uses model version `pirelli-published-strategy-v1`.

- `status`, `lifecycle`, and `modelVersion` describe the sidecar.
- `baseline` contains source/retrieval/cutoff metadata, all published `options` in source order, physical `compoundSelection`, optional `tyreBank`, context facts, and an absence reason.
- each option preserves `rank`, `order`, stop count, compounds, published windows/deltas, conditions, and caveats;
- `drivers[number]` contains the factual observed distinct-compound path, its relationship to published options, all compatible option IDs, pending published windows, and at most three explanatory facts;
- `fieldFacts` contains only cursor-valid contextual statements such as rainfall or an active SC/VSC overlapping a published window.

Ranks are `FASTEST_PUBLISHED`, `EQUIVALENT_FASTEST`, `ALTERNATIVE`, `CONDITIONAL`, and `UNRANKED`. Orders are `ORDERED`, `ANY_ORDER`, `PARTIALLY_ORDERED`, and `UNKNOWN`. The UI must not rename these to Primary/Alternate or choose the first equivalent option.

## Deterministic derivation

For each driver, consecutive repeats are removed from the observed compound history. Only `ORDERED` published options are prefix-comparable.

- one matching prefix: `MATCHING_ONE`;
- multiple matching prefixes: `MATCHING_MULTIPLE`;
- evidence conflicts with every comparable option: `DIVERGED`;
- options exist but do not define a comparable order: `NOT_COMPARABLE`;
- factual terminal lifecycle: `TERMINAL`;
- absent baseline or compound evidence: `UNKNOWN`.

A pending published window is the window at index `len(observedCompounds) - 1` for every compatible option. Relative to the factual current lap it is `BEFORE`, `ACTIVE`, `PASSED`, or `UNKNOWN`. Final/chequered state retains the baseline for retrospective comparison but publishes no future windows or action language. Terminal drivers likewise receive no future action. Rain leaves the dry baseline visible while explicitly stating that it is not directly applicable. SC/VSC overlap states only that neutralization and a published window coincide; it never claims a cheap, optimal, or free stop.

Backward and forward seeks rebuild `RaceState`, session evidence, and this sidecar from the inclusive replay cursor. Request order and wall-clock time do not affect results.

## Parser corpus result

The supplied 17-source corpus was evaluated once before and once after the bounded generic correction on 2026-08-22. Windowless shorthand for an exact compound sequence was previously retained beside a later, more specific windowed extraction. The parser now drops the weaker duplicate when sequence and order match.

After the correction, 12 artifacts were measurable with no evaluation errors: 17 facts extracted, 51 expected, 15 exact, 2 false positives, 88.24% exact precision, and 29.41% exact recall. The 2023 Australia case has no remaining false positives. The two remaining false positives are legacy 2020 Sakhir/Bahrain prose and are returned with `NEEDS_REVIEW`; conservative abstention and incomplete legacy recall remain known limitations.

## Acceptance coverage

| ID | Coverage |
| --- | --- |
| P1-P4 | Published option/rank/order contract and non-comparable ANY_ORDER behavior in `tests/test_published_strategy.py` |
| P5-P7 | Absent baseline and optional tyre-bank contract/component omission |
| P8-P10 | One/multiple/diverged observed-path relations and compatible option IDs |
| P11 | Terminal relation suppresses windows |
| P12-P14 | Pure cursor inputs, deterministic rebuild, and final-window suppression |
| P15-P16 | Rain and SC/VSC field facts without optimal-stop claims |
| P17-P19 | Meeting/session/cutoff admission tests in `tests/test_pirelli.py` |
| P20 | Frontend static contract test confirms no direct Pirelli fetch |
| P21 | Australia three-leg and weaker-shorthand regression tests |
| P22-P23 | Render test excludes legacy Strategy Outlook, Primary/Alternate/Next, undercut, and Net Pit Loss surfaces |
| P24 | Physical C3/C4/C5 nomination remains separate from H/M/S display semantics |

The implementation tests semantics rather than claiming visual acceptance. Product surfaces still require human replay inspection with real admitted Pirelli evidence.
