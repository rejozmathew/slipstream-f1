# Consolidated closure repair — 6 September 2026

The repair reports below retain their original measurements and validation status.
The [final branch acceptance](#final-branch-acceptance--6-september-2026) records the
subsequent live-race observation and the owner's wrap-up decision.

The seven additional correctness cases in the review of `4958280` are repaired on `replay-readiness-performance`. The original six corrected cases remain covered. These controlled reproductions establish the tested boundary failures; they do not establish their production frequency or the cause of the original Qualifying incident.

Work stayed in the original repository. No recording format, database, process worker, service, or source-truth exception was introduced. The first playback-ready opening still precedes full evidence/checkpoint preparation; an explicit resumed cursor reconstructs only the state it requests. Production deployment and main-branch merge remain separate from this branch update.

## C1–C7 results

| Case | Repair and verified behavior |
| --- | --- |
| C1 — reconnect adopts an old cursor in a replacement recording | Automatic WS and REST recovery send `seq` with its known `recording_version`. The server checks its frozen resource identity before seeking; a mismatch resets to official start in that same opening and returns matching metadata. Unchanged recordings retain their cursor. Unknown identities do not auto-resume. REST generations and accepted-snapshot epochs reject late responses; analytics requests, responses, and caches also respect recording identity. Actual Chromium exercises unchanged resume, replacement before catalog polling, and REST recovery. |
| C2 — snapshot reads a partly advanced controller | Each viewer's asynchronous lock covers controller mutation and capture of state, sequence, playhead, playback flags, and analytics. Socket I/O occurs after capture. A held worker test verifies coherent snapshots and continued playback; other viewers remain independent. |
| C3 — cancellation between acquisition and assignment leaks a pin | Acquisition records ownership inside the worker, and an asynchronous resource lease releases it even when cancellation arrives before the await returns. Cleanup survives further cancellation. Tests cover cancellation before, during, and after opening, errors, and surviving concurrent viewers. |
| C4 — release blocks the event loop behind another load | Resource release runs through the bounded worker path and retains cancellation ownership. The controlled 350 ms library-lock obstruction leaves the independent event-loop heartbeat below its unchanged 150 ms bound. |
| C5 — queued preparation retains objects outside the cache budget | Queued and running preparation hold their own existing-library reservations. Jobs coalesce per resource and release on success, failure, or cancellation, including cancellation before the job's first instruction. Six attempted opens with preparation held admit at most three distinct resources, retain zero unreserved objects, and allow rejected opens after capacity returns. |
| C6 — completed journal is stranded after restart | A separate offline scanner inspects up to three known numeric catalog sessions per batch. It validates embedded identity, timestamps, unchanged journal bytes, and overall completion before registering publication. Completed Q3 recovery and restart are idempotent and open no upstream connection. Missing/wrong identities, future data, and Q1-only completion are rejected after actual inspection. |
| C7 — deletion succeeds while an old publication can recreate the file | Publication registration and deletion share ownership. Active collection, a disk write, or pending publication returns HTTP 409, including an older session after collector transition. Cancellation waits through rename and catalog visibility. Completed publication can then be deleted successfully. A held offline inspection cannot register stale events after deletion acknowledges success. |

Explicit legacy API `seq` requests without a version remain supported. Deliberate selection, Follow Live, delayed tails, incomplete-recording semantics, source precedence, and original sporting expectations are preserved.

## Verification

- CI Python lint (`src tests`) and the modified acceptance tool pass. An exploratory lint of every directory also found pre-existing warnings in historical benchmark scripts; those scripts were not changed.
- Full native Python suite: **415 passed, 1 existing protected-archive skip** in 195.89 seconds. The final opening-path follow-up plus preserved incident check passed **62 checks**. The final lifetime/publication file run passed **22 checks**, including the subsequently added scanner/delete race.
- Web lint, TypeScript checking, production build, and **57 frontend tests** pass. The added standalone browser script also passes lint.
- Chromium **151.0.7922.34** passes the three identity/reconnect scenarios, four original-recording control checks, and six combined groups covering exact Qualifying cutoffs, controls, connection failure/recovery, cursor preservation, viewing intent, and downloads during live timing. No page errors were recorded.
- The two earlier publication browser cases also pass against this image: first-seen AVAILABLE and immediate POST AVAILABLE each open the preserved Barcelona recording at official start, Play advances without seeking, 22 drivers render, and repeated publication polls create no extra connection.
- The local image's **62 installed Python files and three built web assets** match the candidate. Its normal entrypoint runs `python -m slipstream` as UID **10001**, serves HTML and the exact built asset, and delivers a coherent playback-ready race opening with 22 drivers. Live upstream was disabled for this entrypoint smoke; it is not genuine upstream evidence.
- Gemini through the verified local Antigravity proxy authored bounded backend/React checks, implemented the initial frontend identity changes, updated documentation, and supplied an independent read-only review. The primary reviewed and corrected those changes, strengthened the regression coverage, and performed final validation. The read-only review reported no additional concrete material finding.

The maintained harness adaptations preserve behavioral assertions: private helper lookup follows the new resource-lease wrapper; source-string checks include the actual identity argument; handoff fixtures carry the recording metadata emitted by the server while retaining the exact drained-cursor assertion. Separate checks reject unknown-version handoff cursors. No owner sporting fixture, pinned cursor, golden expectation, or release target was weakened.

## Container workload and unchanged release gates

The populated harness began with 23 local recordings (271,224,708 bytes) and 1,000 operational JSON files. A separate tiny synthetic recording supported the browser replacement check. The same container then ran live/download browser traffic and the combined probe with normal optional initialization, two historical replays, synthetic public topics through production normalization/persistence, and a 70-second monitor interval.

| Measurement or gate | Result |
| --- | ---: |
| Large replay cold useful opening, target 2 s | **1.340 s — pass** |
| Warm openings | 38–46 ms |
| First unprepared seek, target 300 ms | **1.085 s — still fails** |
| Prepared seeks in this workload | 102–262 ms |
| Independent viewer refresh | 109–153 ms |
| Busy HTTP p95, target below 250 ms | **212 ms — pass** |
| Overall HTTP p95 / p99 / maximum, 1,390 samples | 60 / 155 / 366 ms |
| RSS with two replays / final sample | 394 / 440 MiB |
| Synthetic TimingData events normalized / persisted | **19,624 / 19,624** |
| Replay resource unchanged across monitor interval | Pass |
| Reconnect without premature Q2 completion; 137-second delayed final handoff | Pass |
| Protected owner OpenF1 archive for 11353 | Still missing; existing test skipped |
| Actual Unraid hardware and production reverse proxy | Not validated |
| Genuine live upstream observation | Not performed |

The first-seek target remains unmet; readiness was not delayed to hide preparation. The probe follows browser traffic in the same process and includes its accumulated synthetic live history, so its RSS and timing samples are not a controlled one-variable comparison with earlier reports. Reservations are not total process RSS. The correctness closures do not establish the outstanding release evidence.

Local candidate image: `slipstream-closure-candidate:20260906`, image ID `sha256:bb149a9be9786eb4df2315bb112ef40d5b5dd07fb01d45ed3192f0d70897328d`. Evidence is retained in `.codex-tmp/closure-20260906` and `output/closure-20260906`; original recordings are unchanged and excluded from commits.

## Reproduction and documentation cleanup

Run the normal Python and web checks, then the focused `tests/test_closure_lifetimes.py`, `tests/test_closure_publication.py`, and `web/tests/session-connection.test.mjs` cases. Browser tools use an isolated acceptance server and disposable data. Before starting that server, run `node web/tests/browser-closure-reconnect.mjs --seed <fresh-data-directory>` to create its three-event `SYNTHETIC-CLOSURE-BROWSER` fixture. This refuses to overwrite an existing file. After startup, run the same script with `<local-server-url> <fresh-data-directory> <output-directory>`; it changes only that disposable fixture to reproduce replacement and rejects a different source.

`tools/combined_p0_acceptance.py setup` accepts `--incident-dir` or `SLIPSTREAM_INCIDENT_DIR` for the owner's preserved FP3/Qualifying files; the former local path remains a compatibility fallback. Neither incident recording is bundled into the repository. Optional Playwright setup is documented in the README.

README, changelog, roadmap, architecture, protocol, deployment, and session-experience documentation now distinguish delivered branch behavior from remaining gates. The disk-package proposal and previous checkpoint are explicitly historical. Output artifacts and local server logs are excluded from Git/Docker context; existing local files were preserved.

## Shutdown follow-up for `6535b2b`

The subsequent closure review identified one new runtime regression: shutdown could repeatedly gather completed preparation-cleanup tasks without yielding to their registry-discard callbacks. Shutdown now captures each batch, awaits its completion, and explicitly retires that batch. Cleanup registered during the wait remains owned and is awaited in the next batch.

The supplied regression fails against the original Python 3.13.15 image and passes against the corrected image. It did not fail unchanged on local Python 3.11, so the maintained version explicitly exercises the immediate-completion scheduling boundary on both versions. A second regression verifies that shutdown waits for cleanup registered while it is already draining. The two publication setups now synchronize with the startup monitor and use consistent Practice/Qualifying fixtures; the queued-preparation setup waits for actual registration before closing its viewer. AST comparison confirms every existing test assertion in both files is unchanged. The architecture's Live position wording now reflects cursor-backed timing estimates without implying precise GPS. Gemini reviewed the supplied patch and suggested the additional cleanup-registration case; all conclusions were checked locally.

Final verification for this follow-up:

- Native Python 3.11: **418 passed, 1 existing protected-archive skip**. Python 3.13.15 in the rebuilt image: **419 passed, 1 skip**, including the separately invoked original incident check.
- The **24** shutdown/lifetime/publication checks passed **ten repeated Python 3.13 executions**. These are repetitions, not additional distinct tests.
- Python lint, web lint, TypeScript checking, production build, and **57 frontend tests** pass. Container lint used disposable inputs with Git's regular-file permissions because Windows bind mounts expose executable flags on every file.
- Actual Chromium **151.0.7922.34** passes all **13** checks/groups across versioned reconnect, original Qualifying replay controls, and combined live/download acceptance, with no page errors.
- The normal entrypoint serves the built UI and a playback-ready opening as UID **10001**. All **62** installed Python files and **three** built web assets match the final workspace.
- The normal entrypoint and synthetic harness exit cleanly with code **0** in **16.9 s** and **17.4 s**, respectively, using a **30-second** stop grace. An earlier harness stop with a **10-second** grace reached forced termination; these checks do not establish that ten seconds is sufficient for production shutdown.

Corrected local image: `slipstream-shutdown-candidate:20260906`, image ID `sha256:be49d007a3b125067d6b2980bb655125d0a5c9148d7f50e0030420299a2c3f51`. Local runtime identity and browser evidence are under `.codex-tmp/shutdown-20260906` and `output/shutdown-20260906`. The containers are stopped. This is local candidate validation, not a production deployment or hosted CI result.

The **1.085-second** first-seek measurement above remains historical evidence from the preceding candidate; performance was not remeasured for this narrow shutdown correction. The **300 ms** target, missing protected archive, actual Unraid/proxy checks, and genuine upstream observation remain outstanding. No release expectation or protected fixture was changed.

## Final branch acceptance — 6 September 2026

The owner confirmed satisfactory live timing, viewer delay, deltas, replay behavior,
and general performance during the Italian Grand Prix, after disabling the local
NordVPN route that caused F1 HTTP 403 responses. The live-race core was `586ebca`;
the subsequent interval and Driver Read fixes were tested locally as `f3be72d`.
That exact code is the branch's final tested candidate. Closure documentation is
the only subsequent change; no behavior, benchmark, or redesign work is included.

The owner authorized merging after the normal final checks, retaining the known
first unprepared seek limitation: **1.085 s** in the last recorded workload versus
the unchanged **300 ms** target. No new measurement or universal latency guarantee
is claimed. The missing owner **11353 OpenF1 archive** remains a coverage gap with
an existing skipped test, not a passed acceptance case. Actual Unraid hardware and
the production reverse proxy were not separately validated, restarted, or modified.
Earlier statements that genuine upstream observation was unperformed are superseded
by this live-race acceptance; other historical evidence is preserved.

Final normal checks passed: Python lint and **437 tests passed, 1 existing
protected-archive skip**; clean frontend installation, lint, TypeScript checks,
production build, and **58 tests passed**. The Windows clean install initially
encountered a native-module lock from the local Vite preview; stopping that preview
and using the installed Node 24.19 runtime resolved it. An existing Browserslist
advisory is confined to development tooling; `npm audit --omit=dev` reported zero
findings, and Node dependencies are not shipped in the Python runtime image.
No dependency or product behavior was changed as part of this final check.

Gemini supplied the bounded documentation and check-result review. Temporary logs,
build outputs and private incident recordings remain excluded from commits.
