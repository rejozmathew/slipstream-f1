# Documentation audit — M3.5 source-unification baseline

Reconciled against the implementation and tests on `agent/milestone-3.5-source-unification-repair`, starting from `b3c971eb3586d3fa769b1e1e055eb735c2dba87e`.

## Executive finding

The proposed ZIP correctly identified the major documentation drift, but it was not applied mechanically. Existing architecture, protocol, source, and Pirelli documents contained stronger normative detail than the shorter drafts. The final set keeps that detail, replaces genuinely stale contributor maps, and adds focused source/product-flow guides.

## Final disposition

| Document | Disposition | Reason |
| --- | --- | --- |
| `README.md` | REPLACED | Rebuilt as the public entry point with verified source precedence, distinct browser/CLI paths, Live delay, session matrix, Pirelli tiers, storage behavior, and current commands. |
| `ARCHITECTURE.md` | UPDATED | Preserved detailed canonical, analytics, lifecycle, browser, and deployment sections; corrected the OpenF1-centric opening and added static timebase, Pirelli tier, topic allow-list, and classification details. |
| `IMPLEMENTATION_MAP.md` | REPLACED | Removed the stale clean-restart SHA and false “Pirelli parsing not implemented” claim; mapped current modules and verification focus. |
| `ROADMAP.md` | REPLACED | Consolidated shipped M1–M3 foundations, documented the actual M3.5 source baseline, and made the bounded visual/design pass the immediate next phase. |
| `CHANGELOG.md` | REPLACED | Updated the Unreleased entry to the real source-unification merge candidate and its intentional limits. |
| `docs/protocol.md` | UPDATED | Kept the normative wire contract; added browser-vs-protocol delay distinction and Pirelli evidence-tier fields, and repaired encoding artifacts. |
| `docs/session-experience.md` | UPDATED | Preserved red-flag/live handoff semantics while adding exact layout mapping, source-condition/final-classification separation, settled replay end, pit columns, and lifecycle-aware map behavior. |
| `docs/pirelli-strategy.md` | UPDATED | Preserved the normative extraction/admission/derivation and acceptance coverage; added the implemented display-only tier and semantic presentation rules. |
| `docs/sources.md` | UPDATED | Preserved source/license research detail; clarified OpenF1's fallback/CLI role, static UTC anchoring, full Live allow-list, pit-lane semantics, display-only Pirelli evidence, and current Live position capability. |
| `docs/data-flow.md` | NEW | Added a focused guide for Live, official static history, OpenF1 fallback, replay/delay cursors, evidence, pit timing, Track Map capability, Pirelli, and deletion. |
| `docs/product-flows.md` | NEW | Added session-aware Race, Qualifying, Practice, Driver, Strategy, Battle, TV, Live/Replay, map, and missing-data flows. |
| `DOCUMENTATION_AUDIT.md` | NEW | Records the actual final reconciliation rather than the package's pre-change recommendations. |
| `docs/analytics.md` and `docs/analytics/*` | LEFT AS-IS | Existing formula/evidence-gate authority remains current; no implementation mismatch was found in this documentation pass. |
| `AGENTS.md` | LEFT AS-IS | Contributor operating rules remain authoritative and are not product architecture. |

## Stale claims found and resolved

- `ARCHITECTURE.md` opened with an OpenF1-only historical diagram even though later sections described official static precedence.
- `IMPLEMENTATION_MAP.md` named an old clean-restart commit and said automated Pirelli parsing was not implemented.
- The public entry point did not clearly separate browser/API historical download from OpenF1-specific `slipstream fetch*` commands.
- Official F1 SessionTime-to-UTC anchoring was implemented but scattered rather than prominent.
- The implemented Pirelli display-only official historical tier was missing from normative documentation.
- Session documentation emphasized activity labels without one consolidated current-source-condition/final-classification explanation.
- Pit-lane transit, stationary duration, Net Pit Loss, validation bounds, and dynamic Pit History columns were not explained together.
- Live protocol capacity and current UI presets were easy to read as the same limit.
- Contributor-facing docs lacked focused Live/Replay source flow and Race/Qualifying/Practice product-flow references.
- `docs/protocol.md` contained mojibake in its canonical-state tree and a possessive.

## Supplied statements changed after code verification

- The ZIP's final-classification lists stopped at FINISHED/DNF/DNS/DSQ. The protocol and TypeScript contract also retain an authoritative `RETIRED` compatibility classification, so the final docs include it while keeping `RETIRED_INDICATED` non-terminal.
- The ZIP could be read as exposing timing-derived Track Map placement in current public Live. `/api/v1/capabilities` and `/api/v1/replay` deliberately return `positionMode: unavailable` for Live; the docs now distinguish normalized progress evidence from an exposed product capability.
- The ZIP's public-topic lists omitted subscribed `Heartbeat` and `TopThree`. The final docs distinguish the complete subscription allow-list from streams that actually map to canonical facts.
- The proposed replacement Pirelli document omitted the existing parser-corpus, acceptance, cutoff, and child-artifact detail. Those stronger normative sections were retained.
- The proposed Architecture replacement would have removed detailed Weekend Context, RaceRead, Qualifying, red-flag, live-finalization, and deployment boundaries. The current document was updated in place instead.
- The supplied audit recommended future replacements and a merge sequence. This audit records completed changes only and does not direct Codex to merge.

## Claims verified directly

- Whole-session timing priority is finalized `f1-signalr-public` > `f1-static-public` > `openf1`.
- Browser/API historical download attempts official static reconstruction before OpenF1 fallback; direct `fetch*` commands remain OpenF1-specific.
- Static stream zero requires at least two UTC-anchor candidates, a 10 ms cluster, and at least 75% consensus.
- Live delay is independently owned per WebSocket, accepts 0–300 seconds, and uses one inclusive sequence for state and analytics; browser presets are 0/5/10/15/30.
- `PitLaneTimeCollection.Duration` populates only `pit_lane_duration` inside `0 < duration <= 300s`; it never populates stationary `stop_duration`.
- `PirelliEvidenceStore` implements `STRICT_MODEL` and `DISPLAY_ONLY_OFFICIAL_HISTORICAL`; the latter sets `modelAdmissible: false` and is excluded from model-comparable options.
- Replay deletion removes session timing/raw timing and rebuildable Weekend Context while retaining catalog/circuit, Pirelli, and source manifests.
- Race TV supports Tower/Track/Strategy/Battle/Driver preferences; Qualifying TV is Tower plus renderable Track; Practice TV is Tower-only.

## Normative documents intentionally preserved

- `docs/protocol.md` remains the API, WebSocket, state, capability, and recording contract.
- `docs/analytics.md` and its model references remain the formula and evidence-gate authority.
- `docs/pirelli-strategy.md` remains the Pirelli admission and derivation authority.
- Preservation, acceptance, and approved PCR documents were not rewritten as contributor-facing prose.

## Validation

- All relative Markdown links resolve to repository files or valid in-document anchors.
- Mermaid fences are balanced and use supported diagram declarations.
- No accidental local absolute filesystem paths were added.
- CLI help was checked for `fetch`, `serve`, and `sync-pirelli`; README examples match the parser.
- Seven targeted implementation tests passed for official timebase failure, source precedence, pit-lane cursor semantics, 0/30/120 Live delay, Pirelli display-tier admission/model isolation, and durable replay deletion; no product code changed.
- `git diff --check` passes.

## Unresolved documentation/code inconsistency

None identified in this reconciliation pass.
