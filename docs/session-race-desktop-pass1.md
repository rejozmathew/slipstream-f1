# Regular Race desktop — first visual pass

## PCR-RACE-DESKTOP-INTERVAL-20260915

APPROVED by the owner in this task: “Approve desktop INT revision”.

This narrowly extends PCR-POSTRACE-INTERVAL-20260906 to Regular Race desktop
Standard and Strategy tower modes. GAP and source-supported INT are separate,
adjacent fields in all three desktop modes. Existing source capability, missing
value, leader, lifecycle and lap-deficit rules are unchanged. No interval is
calculated in React. Phone and TV retain their current inventories. Existing
protected tests and golden fixtures remain unchanged; additive rendered tests
cover the explicit desktop opt-in.

Visual review and measurements are recorded below after browser verification.

## Implementation and measurements

Review state: downloaded 2026 Dutch GP Race (11353), paused at **3600 seconds / 2026-08-23 14:00:00Z**, sequence **35238**, lap 20/72. Latest factual update is 13:59:59.970Z. The source has 22 drivers. Before/after use Papaya, Midnight Gradient, the existing Analysis Wide preset (56% timing), Standard tower, zero delay and 10x selected speed. Strategy/Map/Control sizes are Standard; Conditions is Compact. Preset values, saved settings and resize behavior are retained.

| Measurement | Final desktop value |
| --- | --- |
| CSS viewports | 1440×900 and 1366×768; DPR ≈1, zoom 100%; fonts loaded |
| Upright font stacks | Inter / Segoe UI / Arial; SFMono-Regular / Consolas / Liberation Mono; unchanged families, normal style |
| Heading / column label / timing | 14px 700 sans / 10px 500 mono / 13px 400 mono |
| Driver code / surname / team | 14px / 11.5px / 10px; upright |
| Main header / session strip / replay | 52px / 44px / 58px |
| Tower heading / column header / row | 42px / 28px / 34px |
| 1440 split | 791.3px tower, 9px divider, 621.7px context; 8px context gutters |
| Standard GAP / INT / LAST at 1440 | 111.8px / 98.7px / 131.6px |
| Context panel heights at 1440 | Strategy 173.5px, Map 275.5px, Conditions 115px, Control 144px |
| Short laptop | Map 177.5px, Control 110px; all four context panels fit in 600px |
| Responsive bounds | Desktop >900px; short-height fitting ≤840px; toolbar wraps at ≤1180px |

The split menu retains all presets and Edit. Timing/Strategy keep their full inventories and use local horizontal scrolling at narrower splits (816px / 874px minimum rows). Standard retains full strings; every driver is reachable through local vertical scrolling. No field slicing or page zoom is used. Lap progress moves to the desktop map heading. Weather values, track-local time and the sensor qualification remain visible. Replay Race Now says IN PROGRESS instead of the ambiguous LIVE label.

## Verification and review limits

- `npm run lint`, `npm run typecheck`, `npm test`: **68/68 passed**, no skips. Final `npm run build` also passed after the last CSS adjustment. Logs are in `.codex-tmp/session-layout-pass1/`. `git diff --check` passed.
- Additive rendered tests cover the approved desktop columns, unsupported/missing intervals, zero, leader, pit/stopped/retired/DNF/finished states, lap-deficit strings, 22 rows and map-label isolation. Existing protected expectations and fixtures were not changed.
- Actual browser: all Race modes; split presets; horizontal scrolling through LAST STOP; final row P22; Driver selection; Battle, standalone Strategy, Settings and TV at 1920×1080. Qualifying at Q1 +900s retained Standard results and Timing scope/sectors. Practice at +1800s retained LAST/BEST, GAP/INT, statuses and REMAINING.
- Phone at 390×844, 360×800 and 844×390 matched the baseline table text, all 22 rows, column geometry and 50px row heights exactly. No page-level horizontal overflow. The existing dense two-line phone layout is preserved; the proposed portrait policy remains deferred.
- Live runtime, new motion and Python checks were not run: this pass changes frontend presentation only. Existing automated Live delay/connection checks passed. Gemini supplied bounded regression suggestions; implementation and verification were performed locally.

The generated target contains 20 illustrative rows, an aerial map, shorter control messages and different values. This implementation retains the real 22-car state, observed circuit outline, labelled timing-derived positions, factual rain sensor and longer control messages. At short laptop heights the circuit is compact; timing and control messages scroll locally. Visual acceptance remains the owner's decision.

Changed files: `RaceView.tsx`, new `race-session.css`, `TimingTower.tsx`, `TrackMap.tsx`, `SessionStrategySnapshot.tsx`, the AppShell scope attribute, additive `session-components.test.mjs` tests, and this note. No backend, protocol, fixture or golden changes. Work remains uncommitted on the original main branch.
