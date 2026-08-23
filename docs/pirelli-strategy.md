# Published Pirelli strategy

This document is the normative description of Slipstream's published-strategy sidecar. Pirelli is an official pre-race baseline, not team intent or a guaranteed outcome. Slipstream adds only deterministic facts observed at the selected replay cursor. It does not invent a replacement plan.

## Evidence pipeline

1. The single server-owned coordinator checks the official Pirelli Formula 1 RSS/newsroom using the event's exact Pirelli category tag. It follows sparse pre-weekend, post-session, race-morning, final-pre-race, and post-race triggers, plus startup recovery for missing/stale evidence. A failed attempt is observable and retries after 30 minutes; it is not recorded as success.
2. Responses are archived immutably under `/data/.slipstream/pirelli/<meeting_key>/` with retrieval and source metadata.
3. Deterministic HTML/prose and structured extractors normalize compound nominations, ranked or unranked strategy options, published pit windows, context facts, and optional native-text PDF tyre-bank rows.
4. Validation requires source-backed evidence. Strategy purpose and target scope are explicit: Practice/Qualifying prose cannot populate Race, Sprint cannot populate Race, and Race cannot populate Sprint. WEEKEND compound nominations are reusable only inside their meeting; UNKNOWN applicability fails closed.
5. Admission requires the selected `meeting_key`, target session, session scope, and `evidence_cutoff`. A release retrieved after the cutoff is rejected unless source metadata proves that exact version existed by the cutoff. Every contributing child artifact must independently pass the same cutoff test; it cannot inherit the parent HTML page's timestamp.
6. The admitted baseline is supplied to the cursor-synchronized analytics builder. No browser code fetches Pirelli data.

OCR, image parsing, VLM/LLM extraction, and manual product transcription are deliberately absent. A missing machine-readable tyre bank is ordinary absence and never blocks Strategy.

## Published contract

`AnalyticsSnapshot.publishedStrategy` is authored in `src/slipstream/published_strategy.py` and uses model version `pirelli-published-strategy-v1`.

- `status`, `lifecycle`, and `modelVersion` describe the sidecar.
- `baseline` contains source/retrieval/cutoff metadata, all published `options` in source order, physical `compoundSelection`, optional `tyreBank`, context facts, and an absence reason.
- each option preserves `rank`, `order`, stop count, compounds, published windows/deltas, conditions, and caveats;
- `drivers[number]` contains the factual observed distinct-compound path, its relationship to published options, all compatible option IDs, every relevant published window across compatible options, and at most three explanatory facts;
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

Every declared transition window for every compatible option remains in the contract. A window whose corresponding compound transition is already observed is `COMPLETED`; otherwise its state relative to the factual current lap is `BEFORE`, `ACTIVE`, `PASSED`, or `UNKNOWN`. Final/chequered state retains the baseline for retrospective comparison but publishes no live/future windows or action language. Terminal drivers likewise receive no future action. Rain leaves the dry baseline visible while explicitly stating that it is not directly applicable. SC/VSC overlap states only that neutralization and a published window coincide; it never claims a cheap, optimal, or free stop.

`ANY_ORDER`, `PARTIALLY_ORDERED`, and `UNKNOWN` options remain visible as published context but are not prefix-compared. The UI uses a non-directional separator for `ANY_ORDER` and never silently selects the first option or first window when several remain compatible.

Backward and forward seeks rebuild `RaceState`, session evidence, and this sidecar from the inclusive replay cursor. Request order and wall-clock time do not affect results.

## Parser corpus result

The supplied 17-source corpus was evaluated once before and once after the bounded generic correction on 2026-08-22. Windowless shorthand for an exact compound sequence was previously retained beside a later, more specific windowed extraction. The parser now drops the weaker duplicate when sequence and order match.

After the correction, 12 artifacts were measurable with no evaluation errors: 17 facts extracted, 51 expected, 15 exact, 2 false positives, 88.24% exact precision, and 29.41% exact recall. The 2023 Australia case has no remaining false positives. The two remaining false positives are legacy 2020 Sakhir/Bahrain prose and are returned with `NEEDS_REVIEW`; conservative abstention and incomplete legacy recall remain known limitations.

A separate bounded live check on 2026-08-22 used four official modern pages: 2025 Abu Dhabi and 2026 China headline one-stop options/windows were captured; 2026 Austria captured the explicit Medium-Hard-Hard route but omitted its prose-only Soft-Medium-Hard alternative window; 2026 Hungary captured the two explicitly hyphenated slower alternatives but omitted the cross-sentence main one/two-stop constructions. These omissions remain explicit `NEEDS_REVIEW`, not fabricated facts. This was a sanity sample, not a corpus-wide recall claim.

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
| P25 | Exact-tag runtime feed -> discovery -> ingestion -> archive/store -> published baseline in `tests/test_pirelli_runtime.py` |
| P26 | Race/Sprint purpose isolation and meeting-scoped WEEKEND nomination reuse through discovery+ingestion |
| P27 | Child-artifact cutoff proof, failed-refresh retry/observability, and a persisted PRESENT state matrix |

M3.5 product Strategy surfaces pair this admitted baseline with factual `raceRead` fields (current tyre and completed-stop distributions, observed compound sequences, stint context, dry-requirement landscape, recent pits, and factual pace/population context). They remain useful when no Pirelli baseline is present. Legacy projection-heavy `raceStrategy` fields remain wire-compatible but are not read by Strategy/Session/Driver/TV product components. Automated tests cover those ownership boundaries; final visual/product acceptance still requires human replay inspection.
