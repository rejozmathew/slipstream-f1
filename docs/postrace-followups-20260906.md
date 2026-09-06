# Italian GP post-race follow-ups

## PCR-POSTRACE-INTERVAL-20260906

- State: APPROVED by the owner's explicit request on 2026-09-06.
- Milestone: M3.5 follow-up.
- Affected requirement: RACE-001, Race desktop Timing mode only.
- Previous behavior: a leader gap/lifecycle column without a separate interval.
- New behavior: retain that column and add a capability-dependent interval.
- Reason: show the gap to the immediately preceding driver as well as the leader.
- Source-truth impact: none; render existing canonical interval facts.
- Acceptance impact: narrowly supersede the old source-text prohibition on
  `interval_to_ahead` in the shared tower. Keep all existing mandatory columns,
  lifecycle protections, fixtures and cursors; add rendered mode/fallback coverage.
- Golden impact: no approved golden metadata changes.
- Owner decision: requested "a column like that, in addition to the gap to leader"
  in Timing mode. Standard/Strategy/TV are outside this revision.

The owner requested an additional interval to the preceding classified driver in
Race Timing mode on 6 September 2026. This adds `INT` while preserving the existing
leader gap/lifecycle, tyre and timing columns, Standard/Strategy modes, and TV.
The source's session-level `intervals` capability controls column presence. Values
come directly from canonical `interval_to_ahead`; no subtraction of leader gaps or
lap deficits is performed. Unsupported sessions omit the column; missing values,
the leader and stopped/retired drivers show a dash. Finished drivers retain any
source-supplied interval. Existing pinned acceptance fixtures and cursors remain unchanged.

Finished Driver Read and published-strategy facts now say, for example,
`RUS finished P2.` A missing position produces `RUS finished.` The classification
must already exist at the viewer's cursor, and future strategy commentary remains
absent after finishing.

At the owner's later screenshot (14:58:31 UTC, sequence 72029), the session is
already final but Russell's individual classification is not yet available.
Driver Read now says `RUS is P2; final classification pending.` in that interval,
without future-outlook commentary. It changes to `RUS finished P2.` only when the
individual result arrives. Explicit STOPPED/DNF/DNS/DSQ states remain distinct,
and a backward seek restores the earlier wording.

The same cursor reproduces `ALO is running P21`, `LEC is running P22`, and
`STR is running P20` despite canonical retirement/stopped conditions. Driver Read
now uses the shared lifecycle predicates used elsewhere: a source retirement
indication says `reported RETIRED`, STOPPED remains resumable, and explicit final
DNF/DNS/DSQ classifications take precedence. These states do not publish future
outlook commentary. This changes commentary only, not source or classification
state; replay and a later source-supported recovery remain reversible.

This follow-up passed 37 focused tests and lint. The running preview was checked
against the real recording at 14:00:00 UTC, the screenshot cursor at 14:58:31 UTC,
and the final cursor at 14:58:42 UTC. At the screenshot cursor it now reports
Russell's pending classification, Alonso/Leclerc reported retired and Stroll
stopped; at the final cursor it reports Russell finished P2 and the three DNFs.

## Suspension tyre-change investigation

The local race recording begins receiving driver timing during the suspension,
following the earlier VPN connection failure. Russell's first timing snapshot at
13:27:36 UTC already has one reported stop and medium tyres. Hard tyres are observed
at 13:39:13 UTC after the explicit restart. No normalized pit observation was
captured for that earlier stop. A baseline count alone supplies neither a defensible
pit lap nor its timestamp.

A synthetic adapter regression covers both acquisition histories. When a zero-to-one
stop increment is observed before resumption, the existing code records one
medium-to-hard stop and a complete strategy sequence. Starting with a baseline
count of one reproduces the missing history. Duplicate stint packets do not create
another stop, and a suspension-length lane duration remains unavailable. This
supports missing early acquisition as the explanation; it does not prove the exact
contents or ordering of packets missed during the outage.

No tyre-change, pit-count, sporting-rule, source-adapter, or recording behavior was
changed. No synthetic stop was added to the user's recording.

## Verification

80 focused Python tests and 58 web tests passed, together with Python/web lint,
TypeScript checks and the production web build. At 1440×900 the browser renders
ten aligned Timing columns with no horizontal overflow, and the restarted local
preview renders `RUS finished P2.` from the saved race. Gemini provided a bounded
read-only review; its grid concern was checked against actual computed header/row
tracks, which match. No deployment or recording replacement was performed.
