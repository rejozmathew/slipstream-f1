# Pirelli V1 Closure

This document is the implementation contract for the bounded post-M3.5 Pirelli closure milestone.

Baseline: `main` at `ed79112e26f3627863c11274e3d758d49f489d6d`.

The M3.5 source-unification, lifecycle, replay, live-delay, timing ownership, and existing Pirelli evidence-tier architecture are not reopened by this milestone.

## Product intent

Pirelli is official pre-race tyre/strategy context. It is not team intent, not a gold-standard strategy teams are expected to follow, and not a replacement race-prediction model.

V1 should make the official Pirelli material that Slipstream can deterministically and defensibly extract more useful, while keeping current race truth primary.

### High-value Pirelli information

Prefer to preserve and surface, when explicitly supported by the source:

- weekend physical compound nomination (for example C2/C3/C4 mapped to Hard/Medium/Soft);
- all published race strategy options;
- strategy rank/equivalence and stop count;
- compound order when Pirelli defines one;
- published pit windows;
- explicitly published exact or ranged time deltas between options;
- explicit conditions/caveats attached to a strategy;
- concise compound outlook such as all three compounds being viable or particular compounds being expected to dominate;
- concise, directly strategy-relevant context such as degradation, grip/track evolution, weather, tyre stress, overtaking difficulty/pit-stop track-position cost, or an explicitly stated VSC/undercut condition when extraction is straightforward and high precision.

Absence is normal. Do not manufacture a field merely to make the UI look complete.

### Existing published-vs-observed relationship fields

Keep the deterministic `MATCHING_ONE`, `MATCHING_MULTIPLE`, `DIVERGED`, `NOT_COMPARABLE`, `TERMINAL`, compatible-option IDs, and window-state calculations unless a correctness problem is found.

They are not the product center of gravity for this milestone. Do not add new UI emphasis that treats Pirelli as a strategy teams are expected to follow. Pirelli's published strategies themselves remain important official context.

## Explicitly deferred

The following are out of scope for Pirelli V1 Closure:

- OCR;
- Tesseract work;
- image/infographic table extraction;
- VLM/LLM extraction;
- new PDF/image scraping infrastructure;
- race-start tyre-bank expansion beyond already defensible machine-readable evidence;
- live remaining physical tyre sets;
- physical set identity or ages of unused/remaining sets;
- a separate `slipstream-f1-data` repository;
- remote curated-dataset distribution;
- Claude Design / broad visual redesign.

Keep existing tyre-bank contracts compatible. Missing tyre-bank evidence remains ordinary absence.

## Current end-to-end capability picture

### Already represented and already renderable

The existing contracts/API/frontend support:

- Pirelli source and publication timestamp;
- provenance/evidence tier;
- published H/M/S strategy sequence;
- stop count;
- rank (`FASTEST_PUBLISHED`, `EQUIVALENT_FASTEST`, `ALTERNATIVE`, `CONDITIONAL`, `UNRANKED`);
- order semantics;
- pit windows;
- weekend compound nomination;
- published exact/range delta fields;
- option conditions and caveats;
- context facts.

`PirelliBaseline` already renders all options and can render deltas, conditions and caveats if populated. Do not build redundant frontend representations merely because the current historical corpus under-populates those fields.

### Extracted/retained but under-presented

- Context facts are accumulated in the backend, but the current baseline UI takes only the first three rather than selecting useful categories.
- `publishedStrategy.fieldFacts` are computed for contextual conditions such as rainfall, active published windows and SC/VSC overlap, but Strategy does not currently render them.
- Existing published-vs-observed relationship data is available in Strategy/Driver/Battle/TV; do not increase its prominence in this milestone.

UI changes in this branch should be minimal and semantic. The later design phase will decide the final presentation.

## Extraction corrections

Implement the following bounded, deterministic corrections before generating the bundled seed.

### 1. Multi-meeting compound nominations

Support an explicit triplet that is clearly assigned to multiple named meetings in one clause/sentence, for example one C2/C3/C4 selection assigned to both the Dutch and Spanish Grands Prix.

Create one meeting-scoped `CompoundSelection` per explicitly named applicable meeting. Do not treat arbitrary multi-event text as a wildcard.

### 2. Context keyword correctness

Fix substring collisions such as `wind` matching `window`. Use word-aware matching or otherwise prove the intended token.

### 3. Multi-event article scoping

A multi-event Pirelli release must not allow one event's context paragraph to populate another meeting. Restrict context extraction to a meeting-local clause/section/paragraph when the release covers multiple events.

Fail closed when local meeting scope cannot be proven.

### 4. Non-article/index contamination

Newsroom home/archive/index text must not become meeting strategy context merely because it contains matching keywords. Preserve provenance and source-purpose validation.

### 5. Article-body acquisition

Improve bounded recovery of real article text where Pirelli returns a title/shell/incomplete response but an already supported official archive/event-page path can supply the article. Do not introduce browser automation or a general-purpose scraper.

### 6. Published delta extraction

Populate `published_delta_seconds` or `published_delta_seconds_range` only from explicit local language such as a strategy being stated as approximately N seconds slower or between N and M seconds slower.

Never derive time deltas from Slipstream race timing and label them as published Pirelli deltas.

### 7. Explicit option conditions/caveats

Add only bounded, source-local patterns that repeatedly occur in modern Pirelli strategy prose, such as explicitly stated clean-air, traffic, VSC, or similar conditions.

Do not infer strategic meaning that is not stated.

### 8. Compound outlook

Add a concise context category for explicit source statements such as all three compounds being viable/in play, or a stated expectation that particular compounds will be the common race choices.

This may remain a `ContextFact`; a new heavyweight model is not required.

### 9. Optional strategy-relevant constraints

Overtaking difficulty / pit-stop track-position cost and explicit VSC/undercut remarks are useful when Pirelli states them clearly. Add bounded deterministic extraction only if it is simple and high precision on the audited corpus.

If this requires broad NLP or brittle special cases, leave it deferred and document the gap rather than expanding the milestone.

## Bundled seed + self-backfill architecture

V1 will not require a remote curated dataset or second repository.

The preferred flow is:

```text
bundled normalized Pirelli seed
        +
gradual local historical catch-up
        +
existing current/near-weekend direct acquisition
        -> PirelliEvidenceStore
        -> existing evidence-tier admission
        -> AnalyticsSnapshot / UI
```

### Bundled seed

Ship a generated, normalized, validated Pirelli seed with the application/Docker image.

Requirements:

- normalized facts and the provenance required by existing evidence-tier semantics;
- no copies of raw Pirelli HTML/PDF/JPG/article bodies;
- deterministic format/version;
- integrity validation before import;
- generated from the same public builder/extractor code in this repository;
- cover up to the configured historical horizon and the seed generation cutoff;
- import idempotently into writable `/data` storage without overwriting newer local evidence.

Default historical scope: the current season plus the preceding nine seasons (10-season horizon). Make the builder horizon configurable rather than hard-coding a specific first year.

A future maintainer may extend the horizon farther back without changing the dataset format.

### Self-backfill

After seed import, quietly fill missing historical meetings between local/seed coverage and the current date.

Requirements:

- reuse the existing Pirelli discovery/ingestion/store path; do not create a second parser;
- one meeting at a time / bounded concurrency of one;
- low-frequency rate; do not hammer Pirelli;
- idempotently skip meetings that already contain suitable normalized evidence;
- prioritize a user-selected missing meeting when practical, then fill the remaining queue gradually;
- persist progress/failures so restart does not create a tight retry loop;
- late historical acquisition may be display-only according to existing provenance rules; never forge strict replay-cutoff provenance;
- failure to backfill Pirelli must never block replay, live timing, or application startup.

### Backfill metadata must be independent of the UI catalog horizon

The browser/Docker catalog currently defaults to three recent seasons. A self-backfiller must not silently inherit that limit, otherwise an old image installed years later could miss years between its seed cutoff and the current three-season catalog.

Reuse the existing lightweight season metadata acquisition primitives, but keep Pirelli backfill metadata/cache logically separate from the user-facing replay catalog so extending the Pirelli catch-up horizon does not automatically expose ten seasons in the browser.

No historical timing replay needs to be downloaded merely to fetch Pirelli context.

### Current weekend

Retain `PirelliRuntimeCoordinator` as the fastest/current-weekend path. Historical catch-up must not interfere with the sparse current-weekend refresh schedule.

## Builder / maintenance interface

The public maintenance interfaces are:

```text
slipstream renormalize-pirelli \
  --data-root recordings \
  --from-year 2017 \
  --through-year 2026

slipstream refresh-pirelli-seed \
  --data-root recordings \
  --from-year 2017 \
  --through-year 2026 \
  --output src/slipstream/data/pirelli-seed-v1.json.gz

slipstream build-pirelli-seed \
  --data-root recordings \
  --from-year 2017 \
  --through-year 2026 \
  --output pirelli-seed-v1.json.gz
```

`renormalize-pirelli` is offline and uses the normal extraction/validation path. `refresh-pirelli-seed` is maintainer-only orchestration and never runs at application startup. A production build fails when it has zero useful current-normalizer releases; `build-pirelli-seed --allow-empty` exists only for diagnostics.

Do not couple seed depth to `sync-catalog --years` or the browser catalog-years default.

## Dataset/seed format

Prefer one small compressed atomic file, approximately:

```json
{
  "format": "slipstream.pirelli.seed.v1",
  "generatedAt": "...",
  "normalizerVersion": "...",
  "coverage": {
    "fromSeason": 2017,
    "throughSeason": 2026,
    "throughPublishedAt": "..."
  },
  "horizon": {
    "fromSeason": 2017,
    "throughSeason": 2026,
    "throughPublishedAt": "..."
  },
  "materialized": {
    "meetingCount": 2,
    "releaseCount": 5,
    "meetingKeys": ["1285", "1292"]
  },
  "meetings": {
    "1292": {
      "season": 2026,
      "meetingName": "Dutch Grand Prix",
      "raceSessionKey": "11353",
      "releases": []
    }
  }
}
```

The implementation may use a normalized-release representation instead of the illustrative fields above if that more directly preserves existing `PirelliRelease` semantics. Prefer reuse over a parallel schema.

The seed must retain enough normalized provenance to preserve existing `STRICT_MODEL` versus `DISPLAY_ONLY_OFFICIAL_HISTORICAL` behavior. Do not include long raw evidence text unless it is actually required for admission after import.

## UI/product changes in this milestone

Keep UI work intentionally limited.

Required semantic behavior:

- when a valid `CompoundSelection` exists, expose the physical C-number nomination clearly;
- existing strategy-option presentation must continue to show published strategies as Pirelli-suggested official context;
- populate existing delta/condition/caveat UI where extraction begins providing those fields;
- replace arbitrary first-three context selection only if a small deterministic category-priority presentation can be implemented without entering broad visual redesign;
- do not make `Pirelli Fit`/divergence a larger concept than it is today;
- do not redesign Strategy/Driver/Battle/TV layouts. Claude Design follows this closure milestone.

## Tests / acceptance

Add focused tests for at least:

1. one triplet explicitly applying to two named meetings produces two correctly scoped compound selections;
2. unrelated meeting paragraphs in a multi-event release cannot cross-contaminate context;
3. `window` cannot satisfy the `wind` weather token;
4. index/home/archive pages cannot become target-session context without valid purpose/scope;
5. explicit published delta and range extraction;
6. explicit condition/caveat extraction only inside the correct local strategy scope;
7. compound-outlook extraction with false-positive cases;
8. seed build is deterministic for identical normalized inputs;
9. seed import is idempotent and preserves newer local evidence;
10. historical catch-up skips already-covered meetings;
11. historical catch-up proceeds at bounded concurrency and failures do not block startup;
12. late backfill cannot become strict model evidence without exact cutoff/version proof;
13. Pirelli backfill can cover years outside the browser catalog horizon without expanding the user-facing catalog;
14. current-weekend runtime refresh remains functional and independent;
15. no OCR/image/VLM path is introduced;
16. the checked-in seed is non-empty and distinguishes its historical horizon from exact materialized meeting/release contents;
17. seed-only API acceptance proves Dutch 2026 and Canada 2026 facts on an empty runtime;
18. missing Canada is prioritized and becomes PRESENT through one bounded self-backfill without restart;
19. adapted.4 source archives re-normalize offline to adapted.5 while preserving old output.

Use the known modern corpus cases already documented in `docs/pirelli-strategy.md` (including Austria/Hungary recall limitations) plus bounded new regression fixtures for the nomination/context bugs. Do not commit the user's raw `.slipstream` archive.

## Verification

Before merge:

- Python lint passes;
- full Python tests pass;
- web lint/tests pass for any frontend changes;
- deterministic seed round-trip/import tests pass;
- manual dry-run/backfill report demonstrates missing-meeting selection and idempotent skip behavior;
- documentation reflects final behavior and deferred tyre-bank/OCR scope;
- independent review checks that no M3.5 timing/lifecycle/source ownership boundary was changed.

## Stop conditions

Do not broaden the milestone merely to raise extraction recall.

Stop and report a deferred gap when a desired Pirelli fact requires:

- OCR/image interpretation;
- LLM/VLM/NLP inference;
- brittle event-specific transcription;
- unproven meeting/session scope;
- invented provenance;
- a new external distribution service.

The goal is a small, mergeable closure milestone, not a second M3.5.
