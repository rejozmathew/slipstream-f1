# Combined replay and live reliability repair — 5 September 2026

> [!NOTE]
> **HISTORICAL CHECKPOINT (2026-09-05)**
> This document is a historical repair checkpoint. See the [consolidated closure report](consolidated-closure-20260906.md) for the latest candidate and release evidence.
>
> **Release gate remains: NOT READY.**
> - The 300 ms all-seeks budget is still missed on the first cold seek (~1.088s prior measure; 956 ms in Docker benchmark).
> - The owner-supplied OpenF1 recording for session 11353 remains missing from the test tree (`tests/test_openf1.py::test_pcr0003_dutch_race_exact_neutralization_cursors`).
> - Observation against actual Unraid hardware, production reverse proxy, and default live upstream remains unvalidated.
> No push, merge, deployment, production restart, or production-data mutation was performed.

## Authority and revisions

- Repository: `C:\GitClone\slipstream-f1`, branch `replay-readiness-performance`; continued directly from its verified current tip `d72ddd6652f1e2f6d13c8949c253d2944b2eac1a` without reset.
- Governing direction: the actual `replay-readiness-review.md` and later approved loading/viewer-opening decisions (`d8558e53`, `060a1212` in Repository Decision Analysis), plus the combined handoff and active preservation authority. The old persistent-package proposal is retained unchanged as historical evidence, not implemented.
- `4e088c4374460bbfc027544e53255705a0166392`: shared loading, browser recovery, UTC/completion/restart repair, download jobs and regression coverage.
- `08f7b5782d2d2eef8e95aff36137cc2d117f93c1`: resolves Gemini's publication deadlock/flicker findings; strengthens actual control and sustained-monitor checks. This is the final production source revision. The final report/test-harness commit does not change the tested runtime.
- User-approved isolated Gemini worktree: `C:\GitClone\slipstream-p0-gemini-tests-20260905`. No production edits were delegated. The obsolete OneDrive checkout was not modified. Pre-existing local server logs/PID were preserved.

## Observations, reproduced causes and uncertainty

The original FP3 recording contains 29,310 events (26,876 timing); Qualifying contains 190 events (101 timing, 44 driver events) with two short timing bursts. Their SHA-256 values remain:

| Original | SHA-256 |
|---|---|
| `live-11356.json` | `d392bbd6eee56b98856ed5652d9ef3db8af26fc5ff042faedfd45fb4f3add538` |
| `live-11357.json` | `5bc62d73f6c0542b30bbc416c6d3f95ba26faed27915d5b2ebe70c476077d61c` |

The actual reducer, API and Chromium render zero drivers at 14:05:08 UTC and all 22 identities with best laps at 14:13:20 UTC (inclusive sequence 94). The stored later timing was already reconstructible by the baseline reducer. This is not evidence that its acquisition was continuous or that the original browser displayed it correctly. No missing Q3 timing was fabricated.

Reproduced defects and repairs:

1. Populated discovery/opening repeatedly reconstructed timing and evidence; opening requested final state before resetting to start, and monitor activity displaced cached work. Discovery now reads identity/capabilities, loads coalesce, a bounded pinned cache retains reusable immutable preparation, and private viewer controllers start with a single ready snapshot. Complete state/evidence/checkpoints remain lazy after that snapshot.
2. Naive F1 provider-local boundaries overwrote UTC seed bounds; string ordering mishandled mixed precision/offsets; Q1 completion could cap partial Qualifying bounds. F1 source boundaries now apply the supplied offset once, event ordering uses UTC instants before cursor filtering, and completion is reconciled chronologically with session kind/phase.
3. Older Q1 finish history could latch overall completion despite newer Q2 activity. Existing partial canonical files suppressed live acquisition after restart. Q1/Q2 do not complete Qualifying, genuine completion is not reopened by older history, and partial files resume collection without modifying the originals before atomic publication.
4. A failed initial timing transport could leave the viewer unusable while successful catalog polling concealed the error. The browser now retries WebSocket opening with bounded REST fallback, retains proven timing on disconnect, resumes its cursor and persists deliberate replay separately from follow-live intent. Optional analytics cannot gate controls or leak a different cursor.
5. Gemini reproduced a permanent publication error holding the transition lock. The final correction separates factual drain completion from independently retried publication. The old upstream closes before new acquisition; the old delayed viewer retains its own tail and error until publication succeeds. Callback identity is derived from the completed artifact, preventing contamination by the new collector. Errors stay `FINALIZING` throughout retries.

The precise cause of the sparse original acquisition and the user's absent sheet from the start remains **unverified**: these are normalized recordings, not raw SignalR traces. Saved receipt timestamps, counts and filesystem times cannot establish real network arrival, reconnects or the triggering task failure. The continuous-feed tests below use explicitly **synthetic** raw SignalR framing through production decoder, adapter, collector, reducer and persistence. Real upstream smoke: **NOT RUN**.

## Measured results

All Docker comparisons use 23 recordings, 271,224,708 bytes across the top-level JSON inventory, and 1,000 additional operational JSON files under `.slipstream`. Original copies are isolated. The large replay is **2026 Dutch GP, session 11353, 109,067 events** (not the older benchmark's British/2024 label), SHA-256 `c88f02c2c0985f6fd8fa80c180af37ef10547ed04ec77fbb5b1d274b978219c1`; second race 11326 is also opened/searched independently. Its source has no driver rows at official start, so the test verifies its identity in metadata and populated timing at the later cursor rather than inventing start rows.

Environment: Intel Core Ultra 9 285K, 24 cores/logical processors; Windows 11 with Docker Desktop 4.66.1 / Engine 29.3.1, Linux WSL2 kernel 6.6.87.2, Python 3.13.15 in Docker; native Python 3.11.15 and Node 24.19.0. Containers run UID 10001 with isolated Windows bind mounts. Public live, Pirelli seed/refresh/backfill and catalog background paths are enabled; the upstream feed alone is replaced by the marked fixture. Fresh catalog metadata takes its normal cache path. A separate test blocks seed import and fails external catalog refresh while proving HTTP/viewer/live progress.

Final image: `slipstream-p0-candidate:08f7b57`, manifest-list digest `sha256:20ed01cba6f823e99408c7ba2a91511b8f5e98927275bd6db663c1b8e5182ed2`, OCI revision label `08f7b5782d2d2eef8e95aff36137cc2d117f93c1`. Baseline image was built independently from unchanged `d72ddd6`; neither branch nor original benchmark artifacts were reset/rewritten.

| Measurement | Baseline `d72ddd6` | Final runtime `08f7b57` | Budget / result |
|---|---:|---:|---|
| Populated harness launch → HTTP ready | 77.184 s | 1.352 s | About 2 s; PASS |
| Normal production entrypoint → shell / catalog | Not separately measured | 1.523 / 1.577 s | Shell <5 s; PASS, 380 catalog sessions |
| Cold ready large-replay snapshot | 7.695 s | 1.334 s | ≤2 s; PASS, 22 race drivers present |
| Warm ready snapshot | 199–208 ms | 38–62 ms | ≤300 ms; PASS |
| Immediate unprepared 95% seek | 3,395 ms | **956 ms** | ≤300 ms; **FAIL** |
| Subsequent prepared seeks | 779–3,629 ms across 20%/95% | 9–38 ms across 5%/20%/70%/95% | ≤300 ms; PASS |
| Independent refresh / return to cached A after B | 359–429 ms refresh | 40–211 ms | ≤500 ms cached return; PASS |
| HTTP during busy replay work | 7,412 ms p95/max, 10 samples | 204 ms p95, 463 ms max, 83 samples | p95 <250 ms, p99 <1 s; PASS (max also <1 s) |
| HTTP over combined run including 70-second soak | No equivalent long baseline | 31 ms p95 / 55 ms p99 / 463 ms max, 1,577 samples | PASS; busy interval reported separately to avoid dilution |
| Process RSS: initial → two race resources → after soak → completion | 116 MiB at startup; about 245 MiB after baseline probe, collector absent | 77.8 → 381.7 → 375.0 → 387.0 MiB | Bounded observed run; aggregate RSS, not per-entry admission size |
| Synthetic TimingData accounting through Q2 reconnect/Q3 completion | No collector connections | 528 received rows → **11,616 normalized = 11,616 persisted** events | Exactly 22 per received TimingData row; PASS |

The sustained probe completed in about 75 seconds plus its synthetic 140-second completion-clock advance. Two source connections include the deliberate Q2 disconnect/reconnect; 527 timing bursts plus one final timing row account for all 528. The generator is pull-driven with a nominal 100 ms interval, so processing/backpressure affects its observed rate. This proves accounting for every generated fixture row, not fixed-rate independent network delivery or real upstream packet-loss behavior.

Final raw metric artifacts: `docker-startup-08f7b57.json`, `docker-entrypoint-08f7b57.json`, `docker-probe-diagnostic.json`, `docker-image-08f7b57.txt`. A first long probe failed an overly broad assertion that the **global** load count must stay constant. Bounded load tracing then showed ordinary Pirelli loads of upcoming sessions (11361/11369) while historical A (11353) was loaded once and remained cached. The traced 70-second run passed even the original global assertion (5 loads before and after); the harness now asserts unchanged load identity for A specifically, preserving the actual cache-retention requirement. The failed log is retained, not presented as a passing measurement.

The original baseline Docker opening contract requires final REST state, metadata/capabilities and WebSocket startup; the candidate measures the complete ready WebSocket frame. Both require actual timing content/controls, not a status code. Baseline collector connections remain zero because the partial file suppresses acquisition; candidate ingestion therefore imposes additional real processing work. Baseline HTTP statistics contain only ten samples due the stalls and should not be interpreted as a robust percentile distribution.

Native corrected-semantics profiling (before commit, exact diff hash/runtime recorded in `candidate-profile-pass1.json`) found race reduction about 1.028 s versus 3.164 s and FP3 reduction 0.191 s versus 5.611 s; combined race preparation 0.747 s. Immutable state equivalence was checked at 153 cursors across race, FP3 and Qualifying. One large resource added 173.3 MiB RSS in that native run. These are separate diagnostics, not replacements for concurrent Docker measurements. Memory reservations estimate retained Python objects plus preparation space; they are not an RSS guarantee. Cache defaults are three resources / 512 MiB, with 300 MiB per-entry admission and pinning of active viewers.

## Acceptance matrix

`PASS` below means the stated local fixture/assertions passed, not a claim about the unseen real incident transport or target deployment.

| Case | Result | Evidence and scope |
|---|---|---|
| C01 Original exact cursors | PASS | Hash-checked original through reducer/API/Chromium; zero then 22 drivers/best laps; no future flash; real slider and +30s control. |
| C02 Q2 catch-up order variants | PASS | Six topic delivery permutations through synthetic SignalR decoder/adapter; older Q1 finish/chequered, newer Q2 activity; subsequent timing accepted. |
| C03 Segments, suspension/resume, genuine completion | PASS | Q1 → break → Q2 → explicit red flag/restart → Q3 finish; shortened explicit completion also covered. |
| C04 Older history after completion | PASS | Older RUNNING cannot reverse genuine Q3 completion. |
| C05 Partial restart | PASS | Existing partial canonical artifacts at Q1, break and Q2; journal recovery/dedup; same collector task retained; original final-path bytes untouched until publication. |
| C06 FP3 → Qualifying with old delayed tail | PASS | 137-second old viewer survives new target; REST reconnect and WS tail/analytics coherent. Repeated FP3 publication errors do not stop Qualifying; old handoff waits for successful publication. |
| C07 Initial failure and recovery | PASS | Chromium blocks both WS and REST; two successful catalog polls cannot hide timing failure; automatic recovery without manual refresh. Established timing survives disconnect with controls disabled until recovery. |
| C08 Refresh and monitor cache retention | PASS | Repeated large-replay refreshes, independent live target; traced 70-second soak retains the same A resource across multiple 15-second monitor intervals. |
| C09 Independent viewers/delays | PASS | Separate large-replay controllers/cursors and live zero/137-second viewers; state/analytics/clock share each cursor. Existing protocol delay tests preserved. |
| C10 Populated cold startup and unavailable enrichment | PASS | Real populated Docker entrypoint plus blocked optional seed/failed catalog test; HTTP, ready replay and live target progress independently. |
| C11 Offset and ordering | PASS | UTC seed + naive +02:00, -05:30, +05:45, already-aware values and mixed precision; stable UTC order before cursor. |
| C12 Continuous ingestion with replay work | PASS | Synthetic 22-driver deltas, large opens/seeks/refreshes, forced Q2 reconnect, Q3 completion; 11,616 normalized/persisted timing events, no missing generated rows. Pull-driven load limitation stated above. |
| C13 Early finish/overrun | PASS | Explicit early completion and active scheduled-end overrun; schedule/file presence does not author sporting completion. |
| C14 Viewing intent/origin | PASS | Chromium deliberate replay and follow-live persist across refresh; `127.0.0.1` and `localhost` storage isolated. Actual production domain/proxy NOT RUN. |
| C15 Download during live | PASS | Visible job survives refresh; duplicate requests coalesce; failure/retry; catalog availability updates while live sequence progresses. Synthetic download failure/success, real server job path. |
| C16 Sustained candidate Docker | LOCAL PASS / RELEASE FAIL | 70-second soak with normal background features, bounded observed counters/memory and HTTP budgets met. First unprepared seek fails; actual Unraid/proxy remains unvalidated. |

Final production revision: **377 backend tests passed, 1 skipped** in 286.19 seconds, including the explicit original-recording check. Frontend: **34 passed**, typecheck/lint/build passed. Chromium 151.0.7922.34 on the final Docker image passed six grouped browser gates with zero page errors. Gemini's subsequently accepted publication-retention test was extended to assert journal recovery and task cleanup; the two-test publication file independently passed in 0.50 seconds after integration. No production code changed after the full run.

The existing skip is `tests/test_openf1.py::test_pcr0003_dutch_race_exact_neutralization_cursors`: owner archive `recordings/openf1-11353.json` is not installed. It was also absent from the diagnostic tree. This protected original-source check was not rewritten, substituted with the F1-static recording, or disabled by this repair. Restore the actual owner archive and run that exact test before claiming complete preservation validation; do not download a newly changed response and call it the pinned original.

Repository-wide Ruff lint passes. The optional full-tree formatter check reported differences in 53 files, including untouched existing source; unrelated files were not reformatted. Changed/new code was formatted as appropriate. No protected fixture expectation or golden was weakened to pass. The exact original-recording check lives in `tools/incident_recording_check.py` and requires the preserved external evidence path; the original recording itself is deliberately not committed. Browser control testing initially observed optimistic slider state before server acknowledgement; the harness was fixed to await the same exact server timestamp, without weakening the expected cursor.

## Gemini review and disposition

The installed Gemini CLI's old subscription client rejected authentication with `UNSUPPORTED_CLIENT`. The already-approved local Antigravity proxy was verified to expose `gemini-3.8-flash-high` and native file/test tools using the existing authenticated runner; no keys, billing changes, installations or approval bypass were used. Only one Gemini helper ran at a time. Earlier assumptions that the proxy was text-only were corrected after verifying native execution.

Early Gemini tests executed against `d72ddd6`: one meaningful failure (premature Q2 finalization), four passes. Accepted tests were reviewed and integrated; primary corrected its Q3 identity setup and made the chronological replay assertion exercise unordered input. The exact original check was retained separately without committing its recording.

Fresh independent review on `4e088c4` verified its imported module path and executed 32 focused checks, then 33 including its positive bug reproduction. Response ID `chatcmpl-bef86847db9c4dd4a5d649204c8ef1c6`, actual model `gemini-3.8-flash-high`. Findings:

| Finding | Primary disposition |
|---|---|
| F01 Permanent publication failure blocks next live target | Accepted and reproduced. Fixed in `08f7b57` with separate publication ownership after drain; stronger regression fails on pre-fix revision and passes after. A timeout-only workaround would have discarded retry/tail ownership, so was not used. |
| F02 COMPLETE/FINALIZING and error flicker during retries | Accepted; phase/error retained throughout failures and cleared only on successful publication. Tested through retries and new target acquisition. |
| F03 Raw `Ends` / no genuine upstream smoke | No invented canonical raw status added. F1 adapter translates provider status into normalized completion; retained as an upstream-validation limitation, not proof of the incident's cause. |
| F04 First unprepared seek exceeds 300 ms | Accepted as a failing release gate. No target relaxation or hidden full preparation before readiness. |

Gemini then inspected the actual `4e088c4..08f7b57` correction and independently executed **35 passing checks** in 9.78 seconds, including its new three-publication-context bounds test. It verified the helper's exact HEAD and imported source and reported F01/F02 **RESOLVED**, with no new actionable finding. Response ID `chatcmpl-4612c0c15bea47fbaef4e93ee4edf3a6`, actual model `gemini-3.8-flash-high`. Primary reviewed and integrated the useful bounds test, adding explicit journal-recovery and shutdown-cleanup assertions; the original reviewer files remain in the helper unchanged. Gemini did not independently rerun Docker/browser performance; it reviewed those supplied artifacts and explicitly limited its claims.

Gemini's original “approved with conditions” deployment opinion was not adopted: the primary gate is NOT READY while required budgets/target checks remain outstanding. Full Gemini reports, requests/responses and exact commands stay under the isolated helper's `.codex-tmp/gemini-final-review` and `.codex-tmp/gemini-final-revalidation`; no credentials or unrelated private context were sent.

## Reproduction and artifacts

Primary diagnostics: `C:\GitClone\slipstream-f1\.codex-tmp\combined-p0-20260905-01`. Original ZIP extraction and hashes, old baseline files, new startup/probe JSON, native profiles, test logs and checkpoint remain there. Browser screenshots/DOM/results are under `output/playwright-08f7b57`. Diagnostic originals are external inputs, never production `/data`.

From the main repository, with its existing environment:

```powershell
$env:SLIPSTREAM_INCIDENT_DIR = "$PWD\.codex-tmp\combined-p0-20260905-01\recordings"
.\.venv\Scripts\python.exe -m pytest tests tools/incident_recording_check.py -q
.\.venv\Scripts\python.exe -m ruff check src tests tools/combined_p0_acceptance.py tools/incident_recording_check.py
# In web/, with Node >=22.13:
npm run typecheck
npm run lint
npm test
```

For a new isolated populated harness run, choose a destination that does not exist; never supply production storage:

```powershell
.\.venv\Scripts\python.exe tools/combined_p0_acceptance.py setup --repo . --data .codex-tmp/p0-new-isolated-data
.\.venv\Scripts\python.exe tools/combined_p0_acceptance.py measure --repo . --data .codex-tmp/p0-new-isolated-data --web web/dist --port 18344 --output .codex-tmp/p0-new-probe.json
# Docker: mount only the new isolated data at /data and this harness read-only,
# run the candidate as UID 10001, with a private published port.
# Run the external probe against that port; use --soak-seconds 70.
# Browser, with installed Playwright reachable through NODE_PATH:
node web/tests/browser-p0.mjs http://127.0.0.1:18346 output/playwright-new --downloads
```

The browser `--downloads` option requires harness `serve --synthetic-downloads`. Harness-only routes and synthetic transport are not installed in the production image. Runtime/source/image/dataset identities and exact actual commands are captured in the diagnostic logs; do not relabel native or WSL2 results as target-hardware validation.

## Remaining gate and deployment/rollback procedure

The smallest proposed exception is to allow the measured roughly 0.96-second first random seek to wait for the already-running in-memory preparation, while keeping the approved 300 ms target for prepared seeks and preserving immediate first-snapshot readiness. This is a proposal only; it has not been accepted. If that exception is rejected, meeting 300 ms for arbitrary immediate cold seeks requires further work/architecture review. No persistent package, database, extra service or process worker has been introduced. Target-host/proxy validation and the missing protected owner-archive test also remain outstanding.

After explicit user acceptance of the remaining gate and authorization to deploy:

1. On the actual Unraid host, record the currently running container's exact image ID/digest and configuration. Preserve a restorable `/data` backup, including `.slipstream`, catalog, circuit/Pirelli/context artifacts and in-progress journals. Do not delete or “repair” the incident files.
2. Transfer/build the reviewed candidate image from the exact runtime commit using the existing Dockerfile. Pin the image in the existing deployment configuration; do not use moving `latest` with `pull_policy: always` for this review. Keep one container, existing port mapping and the same `/data` mount.
3. Recreate only the Slipstream service after approval. Verify launch-to-shell and ready timing through the actual reverse proxy, correct session/cursor/mode, delayed viewers, downloads, and continuous live acquisition while opening/seeking large replay. Compare target p95/p99/RSS with these local results; test slow/unavailable optional sources. Run a genuine public-upstream smoke when the session is available and record it separately.
4. To roll back, recreate only Slipstream using the previously recorded immutable image/configuration and the preserved data mount. Never run a volume removal, `down -v`, recursive data deletion or source-history reset. The repair introduces no new persistent prepared format or database migration; existing normalized recordings/journals remain canonical inputs. Preserve newly captured journals even when investigating a rollback.

No release command above has been executed on production. Local diagnostic containers are stopped after verification; local review commits, images and evidence remain available.

## Local smoke follow-up: sparse Qualifying replay

The user's browser clip showed elapsed 9:47–10:12, with no driver rows. The unchanged 190-event Qualifying artifact has no driver timing at that cursor; its first timing burst is 12:50–12:54 elapsed and its next burst is 28:52–28:53. Correcting the old timezone/session-start handling and removing the final-state bootstrap makes that empty opening visible. These changes cannot reconstruct updates absent from the saved file. The clip does not establish a seek failure or the original acquisition-loss cause.

The frontend now renders `PARTIAL RECORDING` when the backend explicitly reports `complete: false`, explaining that session completion is not recorded and only saved updates can be replayed. The notice does not imply packet-loss proof, move the cursor, or appear for null/absent completion metadata. It occupies its own space above the session content.

`web/tests/browser-replay-smoke.mjs` exercises actual mouse clicks/drags and Play/Pause against that external original artifact through the normal local CLI backend and Vite proxy. Chromium 151.0.7922.34 passed empty-to-22-row seeking, backward removal of later facts, 10x playback across the first timing burst, and the final timing burst followed by pause at sequence 190. It also checks the notice does not cover the header or timing rows. Frontend typecheck, lint, build, and all 35 tests passed. The original Qualifying SHA-256 remains `5bc62d73f6c0542b30bbc416c6d3f95ba26faed27915d5b2ebe70c476077d61c`.

Gemini through the local Antigravity proxy (`gemini-3.8-flash-low`) provided a bounded diagnostic review; its caution to distinguish missing completion evidence from proven packet loss was retained. Its speculation about quiet sporting intervals was not adopted. Backend code and the prior Docker measurements were unchanged by this frontend follow-up; the release gate above remains NOT READY. The prior Docker image does not include this notice. The requested local preview remains running at `http://localhost:3344`.

## Download/open cursor repair — 2026-09-06

The first Barcelona Race download (11307) exposed a separate frontend defect. The pre-download catalog placeholder emitted sequence 2. On download completion, the browser reopened the new file using that placeholder sequence, which meant 12:06:40 UTC in the downloaded recording, 53m20s before its 13:00 UTC official start. Play advanced that pre-start clock while the browser clamped elapsed time to zero. A manual seek entered the proper race window, matching the user's workaround. This is a reproduced cursor ownership error, not evidence of missing Barcelona timing or a slow download.

Reconnect positions now require an available replay and a matching local download revision. A selected replay publication invalidates the previous recording's event-count position, including late packets from its old socket. Same-recording transport reconnects preserve their cursor. Background download completion does not reconnect an active Live viewer, and explicit `REPLAY_READY` handoff preserves its drained cursor.

Validation: `npm run typecheck`, `npm run lint`, and `npm test` pass (40 tests). Five new hook regressions cover placeholder reconnect/download, same-recording reconnect, trailing old-recording packets, another selected replay, and Live publication/handoff. `ruff check` and `ruff format --check` pass for the test-only server. A real Chromium test failed before the fix with `seq=2`, 12:06:40 opening time, and zero displayed elapsed after Play. With the fix, it opens at 13:00:00, sequence 114, and all 22 named drivers; Play reaches 13:00:07.5 with elapsed 0:08 without a seek. Placeholder and same-recording reconnects also pass in that browser run. Local screenshots/results are under `output/download-open-before` and `output/download-open-final`.

The test substitutes acquisition with the user's downloaded OpenF1 file, while running the actual job, publication, WebSocket and browser paths in a fresh isolated data directory. It does not re-download from an upstream service. The unchanged external input SHA-256 is `3a5bab467527a74860669aa45bade2c90f2883bf350a3d97379c5c32d8d0ef1c`; no recording is committed. To repeat from the repository root (with Playwright available to Node):

```powershell
.venv/Scripts/python.exe tools/download_open_acceptance.py --data .codex-tmp/download-open-new-run --catalog <catalog.json> --recording <openf1-11307.json> --web web/dist --port 18350
node web/tests/browser-download-open.mjs http://127.0.0.1:18350 output/download-open-new-run
```

Build the frontend first; the data directory must not already exist. Stop the isolated test server after the browser run. Gemini through the verified local Antigravity proxy supplied a bounded review of cursor scoping, late packets, and viewer isolation; these cases were checked locally. Production backend code and prior release gates are unchanged.
