# Slipstream session redesign — independent review

**Reviewed:** 3 October 2026 (America/Chicago)  
**Target:** `C:\GitClone\slipstream-f1-redesign\design`, branch `design/session-redesign`  
**Baseline:** `C:\GitClone\slipstream-f1-session-design-baselines`  
**Decision:** Keep the TV visual direction, but do not implement the prototype semantics unchanged. The phone needs another design pass, and the “keep every piece of information” claim is not yet met.

The strongest part is the TV composition: a persistent order, one large feature, a clear flag rail and a recent-story ticker. It gives the race a readable hierarchy. The story timeline is also a worthwhile addition. The main problems are information removed from existing views, conclusions shown before their evidence arrives, inconsistent live/replay behavior, and a phone layout that compresses the display without sufficiently prioritizing the person using it.

## Scope, evidence and limits

I read the current files on disk, starting with `REVIEW-BRIEF.md`; this is not a Git-diff review. I compared prototype code with baseline views/components and inspected existing prototype captures and baseline screenshots. In-memory Node checks exercised the actual data/engine and selected rendering methods; raw-recording checks covered race pit observations, battle eligibility, pass confirmation, qualifying changes and results.

**Browser limitation:** I attempted to open the prototypes, then checked again after the owner opened the tabs. The browser tool could list them but rejected both navigation and access to the existing `file://` tabs under its URL security policy. Therefore this report does **not** claim a fresh interactive browser run, a current 390×844 layout measurement, animation observation, measured frame rate, or a physical three-metre TV legibility test. Findings distinguish source/data verification from visual evidence in existing captures and design judgments. Reproduction URLs below are instructions for the next interactive pass, not a claim that I successfully opened every URL.

Source-path convention: `prototypes/...` is relative to the reviewed `design` directory. Bare prototype filenames and `shared/...` are relative to `design/prototypes`. Baseline `web/...` and `src/...` paths are relative to the baseline checkout.

Older captures are not treated as proof of the current desktop layout or of missing controls subsequently added to source. I did not regenerate recordings, data, screenshots or videos; change existing files; install dependencies; start application servers; or commit. This report is the only file created.

A bounded review of the stint-aggregation code was successfully delegated to **Gemini `gemini-3.8-flash-low` through the local Antigravity proxy**, after API/model discovery. Its temporal-data concern was independently checked against the recording. Unsupported suggestions were discarded.

**Severity:** blocker = must resolve before implementing the affected contract; major = incorrect meaning, loss of material information or broken core behavior; minor = a narrower omission or usability issue. Design-question severities indicate the importance of resolving the decision, not an already demonstrated runtime failure.

### What already works or should be retained

- Keep the persistent TV tower and feature-area moment cards. The TV DOM confines takeovers to the feature stage, leaving the order separate.
- Keep plain sector times, explicit approximate-position labels, the no-outline track line, and the time-based order ribbon. These are useful, honest alternatives to unavailable telemetry.
- Pit-lane time is explicitly distinguished from stationary time.
- For the supplied full race, the initial position snapshot matches the actual start grid for all 22 drivers; I found no incorrect “places gained” result.
- Consecutive same-compound stops are retained in the observed sequence: PIA’s M → H → H is preserved.
- The qualifying post-flag changes are useful and supported: LAW moves into P10 around t=1297, then BOR’s 1:36.814 at raw t=1344.617 restores BOR to P10 and moves LAW to P11. Final elimination membership and pole match this recording. The separate problem is how settlement is established (I-Q1).

### Retention-map assessment

| Area in the brief | Assessment |
|---|---|
| Desktop header, navigation, connection and library entry | Present; changing to TV loses viewer context (A5). |
| Brand and team identity | Desktop has the SS monogram and team text. TV/phone need a deliberate identity treatment (A-Q1, A-Q2). |
| Session/status strip | Rich desktop/TV rail; phone hides the meeting/session identity (G1). |
| Standard / Timing / Strategy tower | Desktop mostly retained; strategy INT is missing (A4), and narrower splits can collapse the driver column (F1). |
| TV timing information | Several old columns have no equivalent full timing view (A2). |
| Pirelli / Race now | Broad sections exist; contextual driver/pair relationships are lost (A3), and client reconstruction changes factual meaning (B1, B5). |
| Map, provenance and coverage | Useful fallbacks exist; capability consistency and coverage definitions still need work (I2). |
| Conditions and race control | Present in desktop Session. Practice Driver Focus loses its old conditions/pit-history context (A4). Known phone additions are excluded from this review. |
| Driver / Battle / Strategy deep pages | Substantial content exists, but “same sections” is false for qualifying focus and published strategy context (A1, A3). |
| Replay/live controls | Desktop/phone controls are present in source; TV contracts are incomplete and live hotkeys remain unsafe (E1, E2). |
| TV rotation, following, alerts, preferences | Direction is strong. Review controls demonstrate part of it; result eligibility and product-control inventory need resolution (E3, E-Q1). |
| Phone | Review focuses on existing screens and behavior, not the acknowledged missing strategy/conditions/race-control work. |
| Settings | Illustrative design exists; layout sizing, rotation interval and driver/pair selectors need an explicit retained inventory (E-Q1). |

The brief’s acknowledged weather-chip clipping, labelled server-analytics placeholders, unfinished hub/README/implementation notes, illustrative library/download states, and incomplete phone content are **not** reported as new bugs.

## A. Retention

### Bugs

#### A1 — Qualifying Driver Focus loses the information that explains an attempt

- **Severity:** major.
- **Where / reproduce:** `prototypes/web.js:334–375`; baseline `web/views/DriverFocusView.tsx:34–64`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/web.html?s=kl-2026-qualifying&t=1330&view=driver&driver=1&play=0`.
- **Saw vs expected:** Source now renders generic driver/stint facts, segment times and a recent lap chart. The baseline has Q status, teammate comparison, and classified attempt history with phase, sectors, compound and tyre usage. I also inspected the baseline qualifying Driver Focus capture, which visibly includes Q status, teammate comparison and sector-bearing lap history. Those sections have no equivalent current prototype rendering.
- **Why it matters:** A best time alone does not explain whether an attempt was representative, an in/out lap, or competitive against a teammate.
- **Suggested fix:** Restore a qualifying-specific focus from the existing server qualifying model. Keep the chart as an addition to the attempt history, not its replacement.

#### A2 — The persistent TV tower removes existing timing views

- **Severity:** major.
- **Where / reproduce:** `prototypes/tv.js:44–50`; baseline `web/components/timing/TimingTower.tsx:106–135` and `web/views/TVModeView.tsx:169`. URLs: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/tv.html?s=kl-2026-qualifying&t=1330&play=0` and `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/tv.html?s=kl-2026-practice-2&play=0`.
- **Saw vs expected:** Qualifying reduces Q1/Q2/Q3 plus interval to one current-segment best and gap. Practice loses last lap, interval, stint and stops from the order. Race loses last lap from its tower. Selected-driver detail restores some single-driver facts, but there is no equivalent full-field timing view; the TV qualifying DriverCard also lacks a segment table.
- **Why it matters:** The new composition is better for following action, but viewers lose comparisons previously available on TV.
- **Suggested fix:** Retain the default compact order and add a reachable full timing/detail feature or viewer-controlled secondary metric view for each session kind. Do not squeeze every old column into the default 760/800px tower.

#### A3 — Published strategy context becomes generic or disappears

- **Severity:** major.
- **Where / reproduce:** `prototypes/web.js:184–201,368,379–405`, `shared/analysis.js:194–202`; baseline `web/components/analysis/PublishedStrategy.tsx:108–138`, `web/views/BattleView.tsx`, `web/views/StrategyView.tsx`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/web.html?s=hungaroring-2026-race&t=2400&view=battle&play=0`; also use `view=driver&driver=1` and `view=strategy`.
- **Saw vs expected:** Battle omits its published-strategy comparison. Driver substitutes generic Pirelli content for the driver’s relationship/window/tyre-bank context. The landscape has “see options” and an empty published-window cell when options exist, instead of the baseline’s actual driver-specific interpretation.
- **Why it matters:** This removes existing server explanations at exactly the points where the viewer compares drivers and strategies.
- **Suggested fix:** Carry over server-authored `pirelliReferences`, option relationships, window states and tyre-bank content. Hungary’s supplied context has no options: the valid-options/window case is an uncovered supported baseline state, **not** a demonstrated missing value in this particular recording. Include that state before approving retention.

#### A4 — Smaller desktop retention omissions remain

- **Severity:** minor.
- **Where / reproduce:** `prototypes/web.js:74,371–372`; baseline `web/components/timing/TimingTower.tsx:79–88,151–152` and `web/views/DriverFocusView.tsx:101,107`. URLs: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/web.html?s=hungaroring-2026-race&t=2400&tower=strategy&play=0`; `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/web.html?s=kl-2026-practice-2&view=driver&driver=1&play=0`.
- **Saw vs expected:** The strategy tower drops INT. Practice Driver Focus no longer has the conditions panel or factual pit history that the baseline provides.
- **Why it matters:** These facts still exist; users must change context or cannot reach the equivalent detail.
- **Suggested fix:** Restore INT as a supported strategy column and restore practice conditions/pit history. This is separate from the acknowledged phone retention work.

#### A5 — Switching to TV resets the viewer into a different experience

- **Severity:** major.
- **Where / reproduce:** `prototypes/web.js:56`, `tv.js:201–205`, `shared/player.js:17–19`; baseline `web/components/shell/AppShell.tsx:27,85,95`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/web.html?s=hungaroring-2026-race&t=2400&live=1`. Set a delay, then choose TV MODE.
- **Saw vs expected:** The link contains only `tv.html?s=...`. Destination defaults are replay, first moment/start, 10×, autoplay and zero delay. The baseline changes view while retaining one session controller. Expected: the same mode, cursor, delay and playback state.
- **Why it matters:** A posture change can silently leave delayed live coverage for an unrelated point in a replay.
- **Suggested fix:** Preserve one viewer/controller in React. For document-to-document prototypes, serialize and restore the full viewer context. Also retain followed driver and motion preference.

### Design questions

#### A-Q1 — Team names need to be part of default identity

- **Severity:** major.
- **Where / reproduce:** `shared/tower.js:303–305,329–331`, `tv.js:45–50`, `phone.js:34–38`. URLs: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/tv.html?s=hungaroring-2026-race&t=2400&play=0`; `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/phone.html?s=hungaroring-2026-race&t=1101&play=0`.
- **Saw vs expected:** Teams are **not missing everywhere**: desktop session rows and Driver/Battle details render them. TV and phone order rows use code, surname and colour only. The owner wants team identity without having to open a feature.
- **Why it matters:** Colour alone requires prior knowledge and is not sufficient identification.
- **Suggested fix:** On TV, use a readable team subline or an explicit identity/detail mode. On phone, provide a compact team label and fuller identity in a row sheet; consider trading duplicated code/surname space for it. Confirm the balance at actual target sizes.

#### A-Q2 — Reserve a real brand/icon slot in all three postures

- **Severity:** minor.
- **Where / reproduce:** `web.html:14`, `tv.html:14–30`, `phone.html:14–39`, `shared/rail.js:22–32`; baseline `web/components/shell/AppShell.tsx:89`, `TVModeView.tsx:166`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/tv.html?s=hungaroring-2026-race&t=2400&play=0`.
- **Saw vs expected:** Desktop retains the SS monogram. TV and phone have no persistent brand slot. The inspected baseline uses the SS mark; I did not establish that the owner’s newer custom icon was already integrated there.
- **Why it matters:** The redesign should accommodate the owner’s icon rather than make later insertion compete with race status.
- **Suggested fix:** Specify a stable compact icon slot, dimensions, light/dark treatment and static fallback now. Animate it only briefly, if at all, and respect reduced motion. Do not use it as an unlabelled live/connection indicator.

#### A-Q3 — Raw lap times are not the same information as the old pace-delta chart

- **Severity:** minor.
- **Where / reproduce:** The brief’s Driver-page retention row; `prototypes/web.js` Driver Focus and `shared/analysis.js` lap chart. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/web.html?s=hungaroring-2026-race&t=2400&view=driver&driver=1&play=0`.
- **Saw vs expected:** The brief deliberately replaces server pace-delta trend with “lap times this stint.” This is a stated design substitution, not an accidental missing placeholder.
- **Why it matters:** Raw lap times answer how long laps took; normalized/server pace context answers a different question. The keep-everything requirement needs an explicit decision here.
- **Suggested fix:** Retain both through a chart mode or secondary section, using the server’s existing evidence/quality labels. If one is removed, record the owner-approved reason.

## B. Data honesty

### Bugs

#### B1 — Future tyre observations change present strategy and dry-rule status

- **Severity:** major.
- **Where / reproduce:** `shared/analysis.js:47–70`, related aggregation in `shared/engine.js:158–168`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/web.html?s=hungaroring-2026-race&t=743&view=driver&driver=18&play=0`.
- **Saw vs expected:** At t=743, STR’s current tyre is SOFT, but the reconstructed sequence is already SOFT → MEDIUM and the dry requirement is satisfied. Raw lane time arrives at t=742.986; MEDIUM arrives only at t=747.641. The cache merges later fields onto the earliest timestamp. HUL’s second stop has a longer example at t=3450: the future SOFT observation arrives at t=3464.3.
- **Why it matters:** Panels contradict one another, and simulated live knows facts real live cannot yet know.
- **Suggested fix:** Fold observations only through the viewer cursor or retain availability timestamps for every field. Keep the next compound unknown until observed. Render the server’s existing actual-strategy/dry-rule contract.

#### B2 — A pinned nonadjacent pair displays the wrong gap

- **Severity:** major.
- **Where / reproduce:** `shared/modules.js` BattleView, especially `const iv = b.intVal`; `web.js` pinned-pair selection. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/web.html?s=hungaroring-2026-race&t=2400&view=battle&battle=pinned&pair=81,3&play=0`.
- **Saw vs expected:** In-memory rendering of PIA versus VER shows **4.176 seconds**, labelled VER behind PIA. At this cursor PIA is P1 and VER is P3; VER’s gap to PIA is **4.932 seconds**. The displayed 4.176 is VER’s interval to P2.
- **Why it matters:** A prominent, precise number answers the wrong comparison.
- **Suggested fix:** Use server pair-gap semantics for arbitrary pairs. Use interval-to-ahead only when adjacency is established. Handle lap differences, stale/missing gaps and reversed order explicitly.

#### B3 — “Gap at each lap” reads beyond the cursor

- **Severity:** major.
- **Where / reproduce:** `shared/vm.js:121–142`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/web.html?s=hungaroring-2026-race&t=176.6&view=battle&battle=pinned&pair=81,1&play=0`.
- **Saw vs expected:** Samples become eligible at `sec <= uptoT`, but their values come from `snapshot(sec + 4)`. At t=176.6, NOR’s available interval behind PIA is 0.972; the plotted L2 sample is already 0.942 from t=180.6. The samples also follow leader lap boundaries rather than each selected driver’s completed-lap evidence.
- **Why it matters:** The graph and CLOSING/OPENING label can anticipate data and overstate their lap provenance.
- **Suggested fix:** Use the existing server completed-gap history with its event/cursor limit (`src/slipstream/analytics.py:590–639`). Never query beyond the viewer cursor; show gaps/discontinuities where comparable evidence is unavailable.

#### B4 — Stopping erases the driver’s final stint from the new chart

- **Severity:** major.
- **Where / reproduce:** `shared/analysis.js:211–214`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/web.html?s=hungaroring-2026-race&t=4830&view=strategy&play=0`.
- **Saw vs expected:** For an open stint, `r.out ? x.from : now` makes its width zero when the car stops. At t=4830, PIA has completed L55, has a 22-lap HARD stint from the L33 stop, and sequence M → H → H. The third segment vanishes instead of ending at the last observed lap.
- **Why it matters:** Historical information disappears exactly when it helps explain the retirement/stoppage.
- **Suggested fix:** Preserve completed running through the driver’s last known lap/progress; add a stopped/retired endpoint. Keep STOPPED reversible and distinct from terminal classifications.

#### B5 — Race-now population labels lose lifecycle meaning

- **Severity:** major.
- **Where / reproduce:** `shared/analysis.js:80–110`, `shared/vm.js:61–71`; baseline `web/components/analysis/PublishedStrategy.tsx:79–103`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/web.html?s=hungaroring-2026-race&t=6150&view=strategy&play=0`.
- **Saw vs expected:** An in-memory check at t=6150 has session FINISHED but returns **19 running**. At t=4830, STOPPED PIA is pooled with retired PER and BOT as “3 cars out.” The model also lacks the baseline’s unknown dry-rule population.
- **Why it matters:** “Running,” “stopped,” “retired” and “classified” have different meanings. Missing evidence must not become a definitive “needs another compound.”
- **Suggested fix:** Render server-authored `raceRead` populations and dry-rule states, including unknown and final classifications, rather than deriving all groups from `!r.out`.

### Design questions

#### B-Q1 — Define what “completed stop” means

- **Severity:** minor.
- **Where / reproduce:** `shared/modules.js` PitBoard and `shared/analysis.js` Race now. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/tv.html?s=hungaroring-2026-race&t=730&module=pits&play=0`.
- **Saw vs expected:** STR’s raw pit count becomes 1 at entry t=721.046; exit is t=742.895. A “completed stops” count can therefore advance while the stop is still happening.
- **Why it matters:** This is an inherited source/wording issue, not a newly lost redesign capability. Repeating it in larger graphics makes it more prominent.
- **Suggested fix:** Either label the counter according to its actual source meaning or author completed-stop semantics from explicit exit evidence. Keep an ongoing stop separate.

## C. Story layer

### Bugs

#### C1 — Confirmed passes are announced before their confirmation exists

- **Severity:** blocker for implementing the story contract.
- **Where / reproduce:** `shared/engine.js:526–536`, `eventsBetween` at `:240`, `shared/story.js:43`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/tv.html?s=hungaroring-2026-race&t=1178&speed=1`; inspect the desktop Story at `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/web.html?s=hungaroring-2026-race&t=1179&play=0`.
- **Saw vs expected:** “HAM passes LIN” is stored with `t=1179` and `confirmedAt=1184`. Consumers filter only on `t`, publishing the confirmed conclusion five seconds early. RUS/STR at t=100/105 is another example. LEC/ANT moving ahead of PIA at t=4768/4769 are also labelled passes during YELLOW using order persistence; the available evidence has not established the cause. PIA’s explicit STOPPED observation arrives much later. This does not prove an illegal overtake or a known stopped-car gain.
- **Why it matters:** Offline precomputation disguises a live-data impossibility. Merely moving this algorithm to the server would preserve the error.
- **Suggested fix:** Separate occurrence time from availability/confirmation time. Before confirmation, use provisional order-change language; publish “passes” only when justified. Treat persistence and cause confidence as separate requirements. Gate feed, ticker, markers, cards and motion on the same availability contract. Remove other future lookups, including the WINNER card’s `snapshot(event time + 20)`.

#### C2 — Battle stories and highlights ignore the green-only rule

- **Severity:** major.
- **Where / reproduce:** `shared/vm.js:55,89`; `shared/engine.js` battle-run generation around `:606–633`. URLs: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/web.html?s=hungaroring-2026-race&t=4766&play=0`; `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/web.html?s=hungaroring-2026-race&t=4809&play=0`. In Story choose **EVERYTHING**; the HUL/LAW event is below the default HIGHLIGHTS threshold.
- **Saw vs expected:** At t=4766, YELLOW, ANT/HUL/STR have `battle=true`. At t=4808.9, VSC, the story generates HUL on LAW, “within 1s for 3 laps.” Raw/status evidence has yellow from t=4762, VSC from t=4777, VSC ending at t=4855 and green at t=4866.
- **Why it matters:** Neutralized proximity is presented as green-running battle evidence. Story, tower and the stated rule disagree.
- **Suggested fix:** Use one server eligibility predicate requiring GREEN and suitable active, same-lap evidence. Suspend/reset qualifying battle runs across caution periods. Keep manual pair comparison available, but label its context accurately.

#### C3 — A seek while Story is hidden can reappear as news

- **Severity:** minor.
- **Where / reproduce:** `shared/story.js:40–56`, `phone.js:159`, and `web.js` view-specific feed rendering. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/phone.html?s=hungaroring-2026-race&t=100&tab=story&play=0`. Visit Order, seek forward across events, then reopen Story.
- **Saw vs expected:** The feed receives `jumped` only when rendered. If hidden during the jump, its old `lastT` remains. An in-memory reproduction of the render sequence assigns `is-new` to historical events on return.
- **Why it matters:** It violates “a jump is not news” even though the visible tower may have snapped correctly.
- **Suggested fix:** Store a navigation/cursor generation independent of visibility. Invalidate feed/ticker baselines on every jump and initialize newly revealed panels silently.

### Design questions

#### C-Q1 — Make event labels understandable without decoding colour

- **Severity:** minor.
- **Where / reproduce:** `shared/engine.js` `SS.describe` cases PIT_OUT, STOPPED and OUT_OF_DROP_ZONE; existing phone Story and TV qualifying captures. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/phone.html?s=hungaroring-2026-race&t=3930&tab=story&play=0`.
- **Saw vs expected:** “OUT” labels both leaving the pits and being out of the race; colour and the longer sentence carry the distinction. “SAFE” labels moving above the cut before settlement, although another late lap can displace that driver.
- **Why it matters:** A glanceable story should not need colour or detailed reading to undo an ambiguous headline.
- **Suggested fix:** Use “PIT EXIT” and “RETIRED”/“STOPPED” as appropriate. Before settlement prefer “ABOVE CUT” or “PROVISIONALLY SAFE”; reserve definitive advancement language for the settled state.

## D. Motion

### Bugs

#### D1 — An old rail animation can overwrite the status after a seek

- **Severity:** major.
- **Where / reproduce:** `shared/rail.js:68–98`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/tv.html?s=hungaroring-2026-race&t=4776&speed=1`. During the VSC wipe, jump back into green running.
- **Saw vs expected:** The instant/jump branch applies the new status but does not cancel the pending wipe or its completion callback. A direct in-memory test applied VSC animation → instant GREEN: status was GREEN after the jump, then became VSC again with `rail-blink` when the old callback finished.
- **Why it matters:** The rail can use a stale flag colour while its current text/state belongs to another cursor.
- **Suggested fix:** Cancel in-flight animations and timers on every replacement/jump; guard completion callbacks with a generation token. Apply text, colour and status atomically.

#### D2 — Reduced motion only covers part of the animation system

- **Severity:** major.
- **Where / reproduce:** `shared/tokens.css:80–84`, `shared/components.css:82,177–207,344,377`, `shared/tower.js:239`; phone preference handling. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/tv.html?s=hungaroring-2026-race&t=3880&speed=2&reduced=1`; also the qualifying cut transition with `reduced=1`.
- **Saw vs expected:** Reordered rows and rail/card travel have explicit reduced branches, but the CSS preference mostly sets an unused `--t-move`. Feed/ticker travel, chip entrance, position pulses, VSC-ending stripe motion and the tower’s same-index divider-shift transition are not comprehensively disabled. Phone reads the initial system/query preference but exposes no motion toggle.
- **Why it matters:** The declared reduced-motion contract is broader than “rows mostly snap.”
- **Suggested fix:** Apply one motion policy to CSS and Web Animations, including divider movement and already-running effects. Replace movement with a static outline where appropriate; make the preference reachable on phone and respond to system preference changes.

### Design questions

#### D-Q1 — Preserve cause-aware motion, but define behavior at fast replay speeds

- **Severity:** minor.
- **Where / reproduce:** `shared/tower.js:12–30,51`, `shared/story.js` takeover queue. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/tv.html?s=hungaroring-2026-race&t=1101&speed=10`.
- **Saw vs expected:** The cause-specific durations/easings are a thoughtful design. TV multiplies them by 1.35: a one-place pass is about 702ms; a one-place pit move about 1.22s, with longer moves exceeding two seconds. Cards hold for several wall-clock seconds regardless of replay speed.
- **Why it matters:** At accelerated replay, several later race events can arrive before a visual explanation finishes. This is a design risk, not an observed fresh-browser defect.
- **Suggested fix:** Specify coalescing/priority rules for accelerated playback, cancel superseded explanations, and test normal speed, 10× and 120×. Preserve chronological truth rather than queueing every dramatic card.

## E. TV

### Bugs

#### E1 — Live mode still accepts replay keyboard commands

- **Severity:** major.
- **Where / reproduce:** `prototypes/tv.js:378–393`, `shared/player.js:20–34`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/tv.html?s=hungaroring-2026-race&t=2400&live=1`. With the delay panel closed, use Left/Right, Space, or brackets.
- **Saw vs expected:** The review buttons disable some live actions, but the global keys unconditionally call skip, toggle and setSpeed. The player has no corresponding mode guard. The LIVE badge does not disclose the resulting replay-like seek/pause/speed state.
- **Why it matters:** A solid LIVE badge can be attached to a manually displaced or accelerated cursor.
- **Suggested fix:** Enforce mode restrictions in the controller and command layer, not only disabled buttons. In live mode, allow only intentional delay adjustment and Go Live. Keep simulation controls clearly separate.

#### E2 — TV does not fulfill the stated delay/transport contract

- **Severity:** major.
- **Where / reproduce:** `prototypes/tv.js:348–375`, `tv.html` review controls. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/tv.html?s=hungaroring-2026-race&t=2400&live=1`; press D. Repeat without `live=1`.
- **Saw vs expected:** Live provides immediate presets and one-second arrow nudges, but no custom M:SS field plus Apply. In replay D does nothing; there is no replay sync-delay control. The TV speed select exposes 1/2/5/10/20/60, not the claimed 0.5–120× range.
- **Why it matters:** Matching a TV broadcast is a core use case, and repeated arrow presses are a poor substitute for entering a known delay.
- **Suggested fix:** Specify a remote/keyboard-accessible product transport with custom delay, Apply, explicit Go Live, replay speed range and replay sync. Do not treat the review drawer as the completed product control design.

#### E3 — Manually pinning Result can declare a mid-race winner

- **Severity:** major.
- **Where / reproduce:** `prototypes/tv.js` manual `direct()` branch and numeric pin handlers; `shared/modules.js` RaceResult. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/tv.html?s=hungaroring-2026-race&t=2400&module=result&play=0`. The phone URL `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/phone.html?s=hungaroring-2026-race&t=2400&tab=more&more=result&play=0` exposes the same renderer.
- **Saw vs expected:** Automatic rotation checks availability; explicit pins do not. An in-memory render at t=2400 has GREEN, `finished=false`, PIA leading, and still emits **WINNER** in the podium.
- **Why it matters:** A dim/unavailable module chip is not a guard against an incorrect race conclusion.
- **Suggested fix:** Enforce eligibility in navigation and the renderer. Before completion show a clearly labelled current order, or reject the result view. Separate provisional chequered classification from final results.

### Design questions

#### E-Q1 — Finish the TV interaction and legibility specification

- **Severity:** major.
- **Where / reproduce:** `prototypes/tv.css:25–41`, `tv.js` stage chips/director, `states.html#settings`; baseline `web/components/settings/TVPreferencesSettings.tsx` and `web/components/settings/LayoutEditor.tsx`. URLs: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/tv.html?s=hungaroring-2026-race&t=3912&module=battle&play=0`; `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/states.html#settings`.
- **Saw vs expected:** The existing battle capture has excellent large-number hierarchy. Secondary labels are much smaller; stage controls are spans with keyboard shortcuts/review selectors rather than a complete focusable remote interface. Settings do not show the full retained inventory of rotation interval, selected driver/pair and module sizing.
- **Why it matters:** Attractive TV screenshots do not establish couch-distance readability or discoverable pin/exit/follow controls.
- **Suggested fix:** Keep the composition; test names, tyres, penalties and ticker at three metres on the intended display. Define focused/selected/disabled states, accessible buttons, exit/back, holds and pin behavior. Carry the old preference inventory into the new settings. These need interaction validation; inert illustrative controls alone are not counted as bugs.

## F. Desktop

### Bugs

#### F1 — Supported split presets can collapse timing identity

- **Severity:** major.
- **Where / reproduce:** `prototypes/web.js:73`, `web.css:4,63,75`, `shared/components.css:131–141`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/web.html?s=hungaroring-2026-race&t=2400&tower=timing&split=analysis&play=0`, at 1440px wide.
- **Saw vs expected:** Source-defined timing columns consume 628px before the driver column. The 45% tower is about 648px wide; its 24px internal padding leaves less than those fixed columns alone. The flexible driver column therefore cannot retain a useful width. Horizontal overflow is hidden. The 1100px supported minimum has the same issue even in the balanced split.
- **Why it matters:** Driver identity can disappear while precise times remain visible. A supported layout must not silently sacrifice the row’s meaning.
- **Suggested fix:** Give each tower view a minimum usable width and constrain split presets accordingly, or use a deliberate compact/horizontal-scroll treatment. This is a source-verified sizing conflict; fresh-browser pixel measurements remain outstanding.

### Design questions

#### F-Q1 — Restore analytical hierarchy without losing the new story

- **Severity:** minor.
- **Where / reproduce:** `prototypes/web.js:123–177`, `web.css:75`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/web.html?s=hungaroring-2026-race&t=2400&play=0`.
- **Saw vs expected:** The default race stack is track/ribbon, then Story, then strategy, conditions and race control. The baseline capture puts strategy context directly beside the tower. The new feed can move old operational information substantially further down the scroll.
- **Why it matters:** Information can technically remain present while becoming much harder to consult during a race.
- **Suggested fix:** Offer an intentional default/preset that keeps compact Race now and conditions near the top, with Story expandable or separately reachable. Preserve module ordering/sizing controls. Avoid using large charts and tall feed history as the only default hierarchy.

## G. Phone

### Bugs

#### G1 — The main phone screen does not identify the session being watched

- **Severity:** major.
- **Where / reproduce:** `shared/components.css:63,120–128`, `prototypes/phone.html`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/phone.html?s=hungaroring-2026-race&t=1101&play=0`.
- **Saw vs expected:** The current source hides the meeting/session and local-clock rail elements on phone. The existing order/track captures show flag, lap and replay state, but no meeting/session identity; there is no alternative session header in the page. The baseline phone capture identifies the event and session above timing.
- **Why it matters:** A flag and lap count cannot tell a user whether they opened the intended race or session.
- **Suggested fix:** Add a compact persistent meeting/session identity, ideally with the brand/session-picker affordance. This concerns an existing screen, not the acknowledged missing phone panels.

#### G2 — Live Story invites an action that deliberately does nothing

- **Severity:** minor.
- **Where / reproduce:** `prototypes/phone.html` Story heading, `phone.js:119–122`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/phone.html?s=hungaroring-2026-race&t=2400&live=1&tab=story`.
- **Saw vs expected:** The heading always says “tap to replay a moment,” while its handler immediately returns in live mode.
- **Why it matters:** The phone supplies neither the promised replay nor an explanation of why tapping is ineffective.
- **Suggested fix:** Make the instruction mode-specific. Live can say that moments will be replayable when the recording is available, or provide the same clear explanation used on desktop.

### Design questions

#### G-Q1 — Redesign the phone’s priorities, not just its scale

- **Severity:** major.
- **Where / reproduce:** `prototypes/phone.js:34–43`, `phone.css:26–40,90–115`; existing `ph-race-order.png`, `ph-race-track.png`, `ph-race-battle.png`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/phone.html?s=hungaroring-2026-race&t=1101&follow=44&play=0`, target 390×844.
- **Saw vs expected:** The order uses 29/30px clickable rows, small secondary text, both INT and GAP, plus a followed-driver strip and transport. `gapToggle` exists but is hidden. The track capture leaves a large quiet area below a compact visualization. The result is dense where a thumb must act and underused where context could help.
- **Why it matters:** This supports the owner’s concern about the phone direction independently of its known unfinished content. A condensed desktop tower is not yet a strong phone workflow.
- **Suggested fix:** Make the primary task “find/follow my driver and understand the latest change.” Use a readable default row, an explicit gap/interval switch, team-aware identity and a detail sheet. Offer dense mode separately. Keep the tab bar stable, simplify transport, and use track space for selected-driver context. Test touch targets, safe areas, text enlargement and both replay/live bottom bars before approving the layout.

## H. Feasibility for the React app

### Design questions / implementation requirements

#### H1 — Author one causal story contract before building the timeline

- **Severity:** major.
- **Where / reproduce:** `shared/engine.js`, `shared/vm.js`, `shared/tower.js`; baseline `ARCHITECTURE.md:67,123–141`, `web/components/analysis/RaceControl.tsx`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/web.html?s=hungaroring-2026-race&t=3880&speed=1`.
- **Saw vs expected:** The baseline has recent raw race-control messages, not a unified causal story timeline. The prototype adds one, but story, tower cause classification, stint summaries and pair selection still contain separate interpretations.
- **Why it matters:** The “other feed” can be race control, combined with normalized timing/state transitions and existing `SessionEvidence`. No telemetry, radio, generative narration or new external feed is necessary. Independent frontend rules would make surfaces disagree.
- **Suggested fix:** Extend the synchronized server analytics/evidence contract with stable event ID, event kind, affected drivers, occurrence time, availability/confirmation time, cause, provisional/confirmed/corrected state, evidence references, priority and correction linkage. Keep raw Race Control alongside Story. Use neutral “order changed” wording until a cause is established. Author pass confirmation, pit/stopped/classification causes, battle eligibility and qualifying settlement on the server.

The same implementation pass should provide lap-scoped PB/session-best flags, interval trend with its evidence window/sample count, and supported position coverage with missing reasons. Reuse existing `raceRead`, actual strategy, published strategy and qualifying contracts.

The key acceptance test is simple: **truncate a recording at time T; factual state, story and live-position estimation at T must agree with the full recording viewed at T.** Labelled replay-position interpolation is an explicit exception: the ground rules permit it to use the surrounding recorded crossings. Run it around pit fields, pass confirmation, final laps, penalties and qualifying settlement. Separately test backward seek, delay change, reconnect and hidden-tab return for silent restoration.

#### H2 — Separate factual rendering from animation frames

- **Severity:** minor.
- **Where / reproduce:** `shared/player.js:51–83`, `shared/tower.js`, `prototypes/tv.js` frame listener. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/tv.html?s=hungaroring-2026-race&t=3880&speed=10`.
- **Saw vs expected:** Keyed rows, changed-cell updates and transform-based movement are sensible for 22 drivers. However the player emits every animation frame even paused; consumers rebuild view models, scan events and sometimes replace whole feature HTML repeatedly.
- **Why it matters:** Twenty-two transforms are unlikely to be the only cost. Recreating analysis and DOM at frame rate is unnecessary work, especially on TV hardware.
- **Suggested fix:** Render factual state on meaningful snapshot revisions; memoize derived state/rows and virtualize long histories if needed. Animate only map interpolation/transforms between updates. Profile frame time, long tasks and memory on the target device. No measured performance claim is made here.

## I. Prototype code that would mislead a port

### Bugs / port hazards

#### I1 — Simulated-live interpolation uses a future crossing

- **Severity:** major.
- **Where / reproduce:** `shared/engine.js:225–232`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/tv.html?s=hungaroring-2026-race&t=2400&live=1`.
- **Saw vs expected:** The live rate uses the next recorded crossing and its timestamp. Capping at the next timing point prevents overshoot, but does not make the rate knowable in live operation.
- **Why it matters:** The demo promises a degree of live smoothness based on information production does not yet possess.
- **Suggested fix:** Replay may interpolate between known crossings. Live must estimate from past observations only, with a freshness limit, uncertainty and a stop at the last defensible boundary. Treat this demo motion as illustrative until that behavior is tested.

#### I2 — Position capability is not applied consistently across features

- **Severity:** major.
- **Where / reproduce:** `prototypes/tv.js` driver-map construction around `:96–102`; `shared/track.js:167,234–240`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/tv.html?s=hungaroring-2026-race&t=2400&map=none&module=driver&follow=1&play=0`.
- **Saw vs expected:** The main Track feature respects the no-position scenario, but Following constructs and renders a map/line independently of that capability. Separately, map coverage counts all pit-list entries as positioned cars before verifying their positions.
- **Why it matters:** A fallback demo can claim positions are unavailable in one view while plotting them in another; pit-list membership is not the same as known position coverage.
- **Suggested fix:** Pass one stable session capability object to every feature and use the same fallback and provenance vocabulary. Source coverage from the server’s supported-position definition, distinguishing positioned, pit-listed, stopped and unpositioned drivers.

### Design questions / port hazards

#### I-Q1 — Qualifying settlement and cut sizes need authoritative evidence

- **Severity:** major.
- **Where / reproduce:** `shared/engine.js:77–79,505–522`. URL: `file:///C:/GitClone/slipstream-f1-redesign/design/prototypes/tv.html?s=kl-2026-qualifying&t=2617&speed=1`; also inspect Q1 t=155 and Q2 t=1418.
- **Saw vs expected:** Settlement uses a +150s timeout, or an earlier branch when no active car says ON_TRACK. At the emitted Q1/Q2/Q3 settlements, four/seven/seven cars respectively still have ON_TRACK activity. Cut sizes are hardcoded to the 22-car profile.
- **Why it matters:** Final membership/pole happen to match this recording, so this is **not** a reported wrong-result bug. The recording does not prove the algorithm knows all relevant laps and corrections are settled, and the hardcoded cut policy does not generalize.
- **Suggested fix:** Use server phase policy and eligible-field metadata, explicit phase closure, completed-final-lap evidence and provisional/settled states. Define behavior for stale activity and later corrections. Do not call a timeout proof of finality.

## Verification still required before sign-off

The source/data findings above are actionable now. A supported browser session is still needed for these checks:

| Check | Required pass |
|---|---|
| Current desktop at 1440×900 and 1100px, each split/tower view | No lost driver identity, clipped controls or inaccessible analysis. |
| Current phone at 390×844, live and replay, with/without follow | Readable identity, usable targets, delay sheet/error feedback, safe-area fit, no overlap. |
| Start, pit cycle, lead change, yellow/VSC, chequered and post-flag qualifying | Cause wording, motion and cards agree with facts at the cursor. |
| Seek during an active wipe/card/reorder; hidden-tab seek; reconnect with delay | No old effects, stale flag colour, new-history animation or mistaken live-edge copy. |
| Reduced motion from system and toggle | No unintended travel, pulse/stripe animation or deferred effects. |
| TV at 1920×1080 and about three metres | Secondary facts and ticker readable; pins, holds, delay and exit discoverable. |
| States/settings flows | Retained controls and lifecycle meanings are represented; illustrative screens are not mistaken for working persistence. |

Existing visual evidence inspected includes prototype phone order/track/battle/story, TV battle/qualifying, and the VSC filmstrip, the current-session Hungary evidence capture, and baseline qualifying Driver Focus, phone qualifying tower and TV tower captures under `output/playwright`. These support visual comparison, not a claim of fresh runtime verification.

## Top five changes before implementation

1. **Make all explanations causal and server-owned.** Separate occurrence from availability; remove future tyre/gap/pass/position reads; share battle and qualifying rules. Require the truncated-recording test before porting Story.
2. **Close the retention map with actual fields and reachable screens.** Restore qualifying attempt/teammate detail, TV timing alternatives, published strategy relationships and the smaller desktop omissions. Preserve viewer context when entering TV.
3. **Give phone its own hierarchy.** Restore session identity, make follow/detail interactions comfortable, simplify the gap/interval and transport presentation, and provide a deliberate team-and-brand treatment.
4. **Finish TV as an operable product while keeping its visual direction.** Enforce live restrictions and result eligibility; complete delay/replay controls; preserve preferences; validate secondary text at viewing distance.
5. **Make navigation and motion truthful under interruption.** Cancel stale rail/card/row effects, restore history silently after jumps, complete reduced-motion handling, and constrain desktop splits so formatting cannot erase driver identity.
