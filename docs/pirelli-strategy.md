# Published Pirelli strategy

This document is the normative description of Slipstream's published-strategy sidecar. Pirelli is an official pre-race baseline, not team intent or a guaranteed outcome. Slipstream adds only deterministic facts observed at the selected replay cursor. It does not invent a replacement plan.

## Evidence pipeline

1. The current-weekend server-owned coordinator uses the official Pirelli Formula 1 RSS feed as an optional fast path, the exact event archive page as the first per-meeting fallback, and the exact event/tag RSS when the archive is insufficient. A malformed shared RSS response cannot poison a sweep; one event failure belongs only to that meeting. It follows sparse pre-weekend, post-session, race-morning, final-pre-race, and post-race triggers, plus startup recovery for missing/stale evidence. A failed attempt is observable and retries after 30 minutes; it is not recorded as success.
2. Responses are archived immutably under `/data/.slipstream/pirelli/<meeting_key>/` with retrieval and source metadata.
3. Deterministic HTML/prose and structured extractors normalize compound nominations, ranked or unranked strategy options, published pit windows, explicit delta seconds/ranges, source-local conditions/caveats, concise compound/strategy outlook, other context facts, and optional native-text PDF tyre-bank rows. Exact-event nominations may inherit their proven event scope; releases with separate nomination triplets still require local meeting binding. Multi-event context retains section boundaries and fails closed when the target meeting cannot be proven. Obvious Practice/Qualifying-only and historical sentences are excluded from Race context unless the sentence states a Race implication.
4. Validation requires source-backed evidence. Strategy purpose and target scope are explicit: Practice/Qualifying prose cannot populate Race, Sprint cannot populate Race, and Race cannot populate Sprint. WEEKEND compound nominations are reusable only inside their meeting; UNKNOWN applicability fails closed.
5. Admission requires the selected `meeting_key`, target session, session scope, and `evidence_cutoff`. Strict model admission rejects a release retrieved after the cutoff unless source metadata proves that exact version existed by the cutoff. Every contributing child artifact must independently pass the same cutoff test; it cannot inherit the parent HTML page's timestamp.
6. The admitted baseline is supplied to the cursor-synchronized analytics builder. No browser code fetches Pirelli data.

OCR, image parsing, VLM/LLM extraction, and manual product transcription are deliberately absent. A missing machine-readable tyre bank is ordinary absence and never blocks Strategy.

## Bundled seed and historical catch-up

`slipstream.pirelli.seed.v1` is a deterministic gzip-compressed distribution artifact containing validated normalized releases plus the minimal artifact provenance required by existing admission. It contains no raw HTML, PDF, image, article body, evidence excerpt, or text offsets. The current normalizer is `slipstream-pirelli-v5-adapted.4`. Older immutable derivations remain on disk; consumers deterministically select the newer normalizer. The maintenance commands are:

```sh
slipstream renormalize-pirelli --data-root recordings --from-year 2017 --through-year 2026
slipstream refresh-pirelli-seed --data-root recordings --from-year 2017 --through-year 2026 --output src/slipstream/data/pirelli-seed-v1.json.gz
slipstream build-pirelli-seed --data-root recordings --from-year 2017 --through-year 2026 --output pirelli-seed-v1.json.gz
```

The years are configurable; they are examples rather than a hard-coded first Pirelli season. `renormalize-pirelli` is offline. Exact-event discovery proof is retained as immutable derived provenance for later offline normalizer upgrades; a legacy archive without that proof is reprocessed only when its article text/title names the target event. `refresh-pirelli-seed` updates private metadata, re-normalizes local immutable sources, uses the normal backfill path for genuine gaps, and refuses an empty release seed. Build output records exact season bounds and current normalizer, is canonical, integrity-hashed, and deterministic. Writable application startup only validates/imports the seed; it never runs the release workflow or scrapes ten years. Import writes individual immutable normalized records atomically, is idempotent after interruption/retry, and preserves an equal-source local release when its normalizer/fact/retrieval quality is newer or better. Seed failure is logged and startup continues.

After import, `PirelliHistoricalCoordinator` uses the same discovery → acquisition → normalization → validation → evidence-store path as runtime ingestion. It has one lock, attempts at most one historical Race meeting per low-frequency pass, re-normalizes obsolete covered meetings before using the network, persists attempt/failure/next-retry state, and prioritizes a selected missing meeting when available. `DEFAULT_PIRELLI_HISTORY_YEARS` is 10 and is shared by the API, coordinator, CLI, and maintenance defaults. Configure it with `SLIPSTREAM_PIRELLI_HISTORY_YEARS=10` or `slipstream serve --pirelli-history-years 10`. Meeting/session discovery uses a separate small `.slipstream/pirelli-metadata.json` cache, so ten-season Pirelli discovery neither expands a three-season browser catalog nor requires historical timing downloads. Meetings ending within the current two-day window are left to the faster current-weekend coordinator. Late acquisition retains the existing cutoff rules and cannot manufacture strict provenance.

The optional overtaking-difficulty, track-position-cost, and generic undercut context requested for evaluation remains deferred. The modern examples did not justify a compact high-precision pattern without broader language interpretation or source-specific rules. Explicit VSC conditions attached directly to an option are supported; no wider strategic implication is inferred.

## Evidence tiers

`PirelliEvidenceStore` tries the tiers in order:

1. `STRICT_MODEL`: each contributing artifact version is independently proven to have existed by the replay cutoff. The resulting baseline is model-admissible.
2. `DISPLAY_ONLY_OFFICIAL_HISTORICAL`: used only after strict admission is absent and only for approved official Pirelli hosts, correct meeting/session scope, and a known `published_at` no later than the cutoff. It is labelled `PUBLISHED PRE-RACE · ARCHIVED LATER` and sets `modelAdmissible: false`.

Display-only evidence may preserve official options and context for retrospective presentation, but `published_strategy.py` supplies no model-comparable options from it. It therefore cannot silently become a matching/diverged model relation or produce future windows.

## Published contract

`AnalyticsSnapshot.publishedStrategy` is authored in `src/slipstream/published_strategy.py` and uses model version `pirelli-published-strategy-v1`.

- `status`, `lifecycle`, and `modelVersion` describe the sidecar.
- `baseline` contains source/retrieval/cutoff metadata, `evidenceTier`, `modelAdmissible`, `provenanceLabel`, all published `options` in source order, physical `compoundSelection`, optional `tyreBank`, context facts, and an absence reason.
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

A display-only baseline follows the same presentation/provenance contract but is deliberately excluded from the comparable option set. Current race facts remain authoritative regardless of Pirelli tier.

Backward and forward seeks rebuild `RaceState`, session evidence, and this sidecar from the inclusive replay cursor. Request order and wall-clock time do not affect results.

## Presentation semantics

The shared compound-badge vocabulary is semantic across Pirelli, Driver, Race Now, and pit transitions: Soft is red, Medium yellow, Hard white, Intermediate green, and Wet blue. Directional arrows represent source-published or factually observed order; they are not an inferred preferred strategy.

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
| P28 | Offline adapted.3 → adapted.4 repair preserves the old derivation and builds/imports a current non-empty seed |
| P29 | Bundled-seed-only clean-install API acceptance for Dutch 2026 and Canada 2026 |
| P30 | Prioritized Canada-missing self-backfill becomes PRESENT without restart |
| P31 | Event-specific RSS, exact-event nomination inheritance, Race context filtering, and multi-event isolation |

M3.5 product Strategy surfaces pair this admitted baseline with factual `raceRead` fields (current tyre and completed-stop distributions, observed compound sequences, stint context, dry-requirement landscape, recent pits, and factual pace/population context). They remain useful when no Pirelli baseline is present. Legacy projection-heavy `raceStrategy` fields remain wire-compatible but are not read by Strategy/Session/Driver/TV product components. Automated tests cover those ownership boundaries; final visual/product acceptance still requires human replay inspection.
