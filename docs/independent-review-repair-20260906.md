# Independent review repair — 2026-09-06

This records the `4958280` checkpoint. See the [consolidated closure report](consolidated-closure-20260906.md) for the subsequent seven boundary fixes and current validation.

All six findings from the independent review of `5f6f5fc` were reproduced and repaired on `replay-readiness-performance`. Work stayed in the original repository. No recording, credential, new persistent format, worker process, database, or service was added.

## Resulting behavior

| Finding | Repair and regression coverage |
|---|---|
| F1: cancelled playback still mutates a later seek | Cancellation retains its compute slot and waits for the running thread before the controller can be reused. A controlled in-flight advance/stop/backward-seek test verifies both ownership and the final cursor. |
| F2: missing completion loses old live viewers at rollover | The old writer stops before its proven state and events are retained as stale/incomplete. A real API/WebSocket test keeps an immediate and a 137-second delayed viewer on the old session while the new collector advances independently. Follow Live receives a next-session hint only after its retained tail; explicit selections stay selected. No completion or replay-ready state is fabricated. |
| F3: restart misses an overrunning session | A bounded recent-journal lookup recovers an unfinished session after its scheduled end, validates embedded identity and chronology, and retains the adapter's upstream identity check. Terminal, stale, future, missing-key, mismatched-key, and outdated-schedule candidates are rejected. |
| F4: first-seen or immediate AVAILABLE never replaces a placeholder | Publication compares the opened resource with availability and an opaque local file version. A selected changed replay opens without its previous recording's cursor; unchanged publication polls do not reopen it. Real React and Chromium tests cover first-seen AVAILABLE, immediate POST AVAILABLE, missing old versions, and unchanged publications. |
| F5: unknown completeness suppresses a requested download | Only verified complete files skip acquisition. Inspection is confined to the requested session. Partial recordings invoke acquisition; normalized and OpenF1 complete recordings avoid repeated downloads. |
| F6: optional seed blocks essential catalog initialization | Required catalog refresh runs independently of Pirelli seed import and reports refresh/retry status until it succeeds. Tests block the seed and verify independently available catalog data. |

The publication identity is frozen with the bytes actually read. A file replaced during opening cannot give old events the replacement's identity; a subsequent open loads the replacement. OpenF1 completeness is derived from its normalized session events on selected-file inspection, without reconstructing final RaceState before the first snapshot.

## Verification

- Python lint and changed-file formatting pass. The focused final API/library/reliability run passes all 40 checks.
- Web lint has no warnings; TypeScript checking, the production build, and all 48 frontend tests pass.
- Chromium 151.0.7922.34 passes both publication timing cases against the actual local API, download job, WebSocket, and built UI. Acquisition alone uses the saved external Barcelona 11307 file. Both open at 13:00:00 UTC, Play advances without seeking, 22 drivers render, catalog status settles correctly, and repeated AVAILABLE polling creates no extra connection.
- The container Chromium suite passes all six groups: original Qualifying cutoffs, real replay controls, initial HTTP/WebSocket failure and automatic recovery, retained cursor after disconnect, saved viewing intent, and download progress/coalescing/failure/retry while live timing continues. No browser runtime errors were recorded.
- The final full backend suite plus preserved incident-recording check passes: **395 passed, 1 skipped** in 524.92 seconds on native Windows. The skipped protected case requires the missing owner archive `recordings/openf1-11353.json`; its expectation was not weakened. All five container-entrypoint checks pass using Git's POSIX shell.

The local candidate image ID is `sha256:f541bb79ef4c4d92b7dcddf7317f85ae63fb9a8e5a02ae02d73d852a6f793352`. It runs Python 3.13.15 on Docker Desktop/WSL2 as UID 10001. The application source and built assets are checked against the committed candidate before delivery. This is local container evidence, not Unraid/proxy or genuine upstream validation.

The populated container probe used 23 recordings (271,224,708 bytes), 1,000 operational JSON files, the unchanged incident recordings, normal optional initialization, two replay sessions, and synthetic public-topic traffic through the production adapter/collector/persistence path. After 70 seconds:

| Measurement | Result |
|---|---:|
| Large replay cold useful opening | 1.426 s |
| Warm openings | 34–60 ms |
| First unprepared seek | **1.088 s — misses 300 ms target** |
| Prepared seeks | 10–52 ms |
| Viewer refresh | 42–70 ms |
| HTTP p95 / p99 / maximum, 1,456 samples | 46 / 140 / 460 ms |
| Busy-phase HTTP p95 | 222 ms |
| RSS with two replays / final sample | 393 / 400 MiB |
| Timing events normalized / persisted | 11,506 / 11,506 |

The probe also passed per-viewer isolation, reconnect without premature Q2 finalization, unchanged replay reuse across the monitor soak, delayed-tail finalization, and coherent replay handoff. Timing counts measure this synthetic input, not the completeness of a real race feed.

Gemini through the verified local Antigravity proxy generated bounded backend and React regression cases and supplied a final read-only review. The primary reviewed the suggestions, extended boundary tests, implemented the product changes, and verified the results locally. Its browser-generation request timed out; the browser harness and execution were completed locally. Speculative review findings were checked against actual lifecycle behavior rather than accepted as facts.

## Remaining release evidence

The arbitrary first cold seek still waits for canonical in-memory preparation and misses the approved target. A reducer experiment did not reliably improve it and was removed. No target was weakened, readiness delayed to hide preparation, or new persistent preparation architecture introduced. Real Unraid/proxy validation, the missing protected owner-archive case, and genuine upstream race observation remain outstanding as described in the prior repair report. The six correctness fixes do not establish those release gates.

Local evidence is under `.codex-tmp/review-reliability-20260906`, `output/playwright/review-reliability-20260906-final`, and `output/playwright/review-container-20260906`. The new backend cases are in `tests/test_review_reliability.py`; React cases are in `web/tests/session-connection.test.mjs`; the additional browser harness is `web/tests/browser-review-reliability.mjs`. Diagnostic recordings and screenshots are excluded from the commit.
