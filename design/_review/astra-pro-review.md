# Slipstream prototype review

## Decision

Keep the visual direction, especially the authored TV composition. Give mobile a dedicated information-architecture and responsive pass, rather than a sequence of spacing fixes. Repair intermediate desktop widths, preserve existing viewer context across presentation changes, and treat Story as a bounded new backend-derived capability—not code to copy out of the prototype engine.

## Review scope and limits

Reviewed the uploaded `prototypes.zip`: `web.html`, `tv.html`, `phone.html`, `states.html`, their styles/scripts, shared rendering/model code, and the three bundled Race/Qualifying/Practice recordings. Exercised playback, seeking, focused views, simulated-live delay controls, keyboard shortcuts, and a moving VSC transition. Captures cover phone widths 320–430, landscape 844×390, desktop widths 1024–1440, and TV 1920×1080.

The local browser harness rendered the supplied HTML/CSS/JavaScript and fonts, supplying query parameters through an in-memory shim because ordinary URL navigation was unavailable. The original archive and extracted source were not modified. Navigation destinations were inspected in source. These tests are not a production backend integration test, a physical TV-distance test, or an exhaustive accessibility audit.

Current production scope was checked against connected GitHub `rejozmathew/slipstream-f1`, default-branch `ROADMAP.md` and `ARCHITECTURE.md`, and earlier product requirements retrieved from the user's Library. Current repository documentation takes precedence over older milestone sequencing. In particular, public Live and independent viewer delay are already in the current M3.5 baseline; identity/persistent preferences and Sync Groups are separate following milestones.

Source locators below refer to files inside the uploaded archive. Screenshot filenames refer to the accompanying evidence ZIP.

## What should survive the next iteration

The restrained dark palette, racing-dashboard typography, stable timing order as the anchor, strong race-status rail, deliberate TV stages, large battle gap, compact tyre badges, and separation between live and replay are the strongest foundations. The design is not improved by making every surface more spacious or turning every driver into a large card.

Meaningful motion is useful: explain a change of order, identify a pit transition, draw attention to a flag change, then settle. Preserve the distinction between an event animation and a seek, where the interface should establish the destination state without replaying a burst of old notifications.

The States & Flows page is also a useful foundation. It explicitly covers library/downloads, opening, live lifecycle, missing capabilities, results, settings, and errors. Those designs need to be connected to real workflows; their presence should not be mistaken for finished integration, but they should not be discarded as though no state work exists.

## Confirmed findings and revision requirements

### M1 — Phone timing is over-constrained horizontally

**Evidence:** `phone.js:34–42`; `phone.css` compact-tower rules. Race rows reserve fixed widths for position, interval, gap, and tyre, leaving identity as the shrinking remainder. The intended gap-toggle element is always hidden. At 360 px, measured row/header content extends to approximately 366.8 px; at 320 px the right-hand columns are visibly clipped. See `phone-mid-320.png`, `phone-mid-360.png`.

**Revision:** Use a phone-specific row anatomy with a selectable primary GAP/INT value, stable numeric alignment, compound/age, and an identity width that cannot disappear. Put less frequently needed information in an expanded row or Driver view. Maintain a useful number of visible drivers rather than replacing the tower with oversized cards. Status chips need reserved space rather than collision with values.

### M2 — Phone navigation excludes important product capabilities

**Evidence:** `phone.js:54–90`; `phone.html` script/module list. Main destinations are ORDER, TRACK, STORY, MORE. Race More exposes Battle, Pit Lane, Driver, and conditional Result. Phone does not load the shared Strategy/Conditions/Race Control analysis module or server-context module. Story filters at HIGHLIGHT priority, so it is not a substitute for the full official Race Control log.

**Revision:** Provide a deliberate route to Timing, Strategy, official activity/control, Driver, Battle selection, session library, and settings. They do not all need permanent tabs. Make navigation session-aware: Qualifying should prioritize phase, cutline, current runs, and times; Practice should prioritize current runs, lap history, and supported pace evidence. A possible Race structure is Timing / Strategy / Track / Activity, with contextual Driver and Compare actions and a top-level session/app menu. This is an illustrative architecture, not a mandatory final tab naming decision.

### M3 — Follow and Driver Focus are conflated

**Evidence:** `phone.js:40, 94–113`: tapping a row toggles follow; the pinned follow bar must then be tapped to open More → Driver. The pinned bar remains visible even in that driver's own view. Desktop uses a more direct driver-opening interaction.

**Revision:** Make row tap open Driver Focus, and provide an explicit follow/pin action. Preserve clear followed state and an obvious clear/change action. Avoid displaying the same driver's summary twice when it provides no additional context. Provide a deliberate two-driver comparison flow, not just the automatically recommended pair.

### M4 — Phone has no real landscape composition

**Evidence:** `phone.css:4` fixes the application to a maximum 520 px width. There is no landscape layout. At 844×390 it remains a centered portrait-style strip with heavily constrained height. See `phone-mid-844.png`.

**Revision:** Author landscape behavior. Timing plus a small contextual panel, or a side-by-side Battle, can use the extra width. Reduce redundant chrome in short viewports. Do not simply stretch portrait or inherit TV.

### M5 — The phone replay transport is too compressed

**Evidence:** Compact transport styles hide timestamp, forward jump, and field controls; playback speed is visible in the status rail but lacks an obvious corresponding phone control. The scrubber competes with the Delay button. Replay delay presets include a LIVE label even while the viewing mode remains replay. See `phone-delay-sheet.png` and `phone-order-mid.png`.

**Revision:** Keep a minimal always-visible transport and put speed, exact time, larger scrubbing, and synchronization adjustments in an accessible Playback sheet. Mode-specific language must distinguish replay position, requested live delay, effective live delay, and return-to-live. Do not label a replay adjustment as entering Live unless it actually changes source/mode.

### M6 — Mobile takeover obscures leading drivers

**Evidence:** `phone.css` positions `#takeover` at top 50 px over the content. A moving VSC test covers the top timing rows. See `phone-vsc-takeover.png`.

**Revision:** Use a reserved notification region or a compact banner that does not cover current classification. The race-status rail already communicates urgency. A larger announcement should not remove the information needed to understand its impact.

### M7 — Phone Track and Story use space unevenly

**Evidence:** `phone-track-mid.png` shows map/ribbon label crowding and unused space below. `phone-story-mid.png` shows spacious historical cards, including older battle observations.

**Revision:** Prioritize the followed driver and nearby/relevant cars on the small map; label approximate positions and time-gap schematics separately. For Story, show recency, filters, and a deliberate compactness level. Historical battle observations must not read as current recommendations. Preserve scroll position while users read older activity.

### T1 — Team identity is omitted from TV and phone timing rows

**Evidence:** TV and phone use the code/surname driver renderer; desktop uses the team-aware renderer. Team data exists in the fixtures. See `tv-track-mid.png` and `web-mid-race.png`.

**Revision:** Add a secondary team label or an expanded identity treatment without sacrificing timing readability. Use full team identity in Driver/Following. A team-colour strip is supplementary, not a complete textual identifier.

**Theme-label clarification:** The active appearance/theme name belongs in Appearance settings and the TV settings overlay. It need not permanently occupy the race-status rail. Team names and appearance-theme names solve different problems.

### T2 — TV delay exists, but is not discoverable as a normal product control

**Evidence:** `tv.js:350–361`: live delay presets are 0, 5, 10, 30, 60, 120, 180, and 300 seconds, with one-second arrow adjustment while the panel is open. D and the Live badge open the panel. Review controls expose the simulated-live switch. A 30-second adjustment worked. See `tv-delay-30.png`.

**Revision:** Keep the underlying concept. Add a discoverable Sync/Delay control to a transient TV toolbar and retain a compact “30 s behind” indicator. Support pointer and keyboard operation, visible focus, an ordinary close action, Escape, and focus restoration. Requested versus effective delay needs an honest buffering state. Delay must not require leaving TV or controlling it from a separate phone.

### T3 — TV keyboard controls bypass mode restrictions

**Evidence:** `tv.js:378–393`. In simulated live, with the delay panel closed, ArrowRight still advances by 30 seconds and Space pauses the player, although the prototype's advertised live policy is delay-only. Escape did not dismiss the delay panel. Module chips are spans rather than ordinary clickable buttons.

**Revision:** Apply the same server/player capability checks to keyboard and pointer paths. Decide the actual product policy for live pause/seek; do not permit hidden shortcuts to contradict it. Make visible stage selectors real buttons. Handle Escape and focus. Hide or clearly gate unavailable stages.

### T4 — Entering TV drops viewer context

**Evidence:** `web.js:56` constructs `tv.html?s=<session>` only. The target creates a new player at its default point; cursor, live/replay mode, delay, speed, and follow state are not transferred.

**Revision:** TV is a presentation change for the current viewing session. Preserve the selected session, source, cursor, mode, delay, and relevant focus. A new independent window may intentionally diverge after opening, but it should begin from a coherent state. This does not require implementing M5 cross-device Sync Groups.

### T5 — TV currently scales a fixed canvas

**Evidence:** `tv.js:21–22` and `tv.css:8` scale a 1920×1080 canvas. The earlier product contract expressly requires true responsive implementation rather than fixed-stage scaling.

**Revision:** Preserve the authored composition, but implement suitable large-display breakpoints and readable minimum sizes. Define behavior for 720p/1366-class viewports and actual TV distance. A phone-sized viewport should be guided to the normal Session view, not shown a miniature TV canvas. Test safe edges and browser zoom.

### T6 — TV content scope must be reconciled with current contracts

**Evidence:** New Qualifying TV has cutline/spread/following stages; Practice has spread/track/following stages. Current `ARCHITECTURE.md` documents Qualifying Tower plus position-supported Track, and Practice Tower-only.

**Revision:** The new stages may be worthwhile. Treat them as deliberate additions with server-authored inputs and missing-data behavior, not as an automatically approved visual reskin. Do not run race Strategy/Battle concepts in non-race session families.

### W1 — Desktop Timing mode loses identity at intermediate widths

**Evidence:** At 1280 px the driver identity is squeezed; at 1024 px it collapses while secondary timing columns remain. See `web-timing-1280.png`, `web-timing-1024.png`.

**Revision:** Give identity a minimum width, budget columns per breakpoint, widen the timing zone when needed, and hide lower-priority columns before names. Where justified, horizontal scrolling must remain inside the timing panel rather than clipping the application. Test each tower mode independently.

### W2 — Race analysis hierarchy is map-heavy

**Evidence:** At 1440×1000, the default Race side panel foregrounds the map/ribbon and Story; current Strategy, Conditions, and official Race Control require further scrolling. See `web-mid-race.png`.

**Revision:** Retain the map but make its size adjustable and give a compact current race interpretation and latest important official message earlier placement. Preserve real split sizing, module reorder/hide, and useful layout presets; a good default is not a replacement for the existing layout capability.

### W3 — Strategy content is not yet a faithful production rendering

**Evidence:** The prototype has useful tyre/pit/strategy visuals, but some content is recomputed locally. `shared/analysis.js:198` hard-codes “No specific Pirelli strategy published” in the per-driver landscape whenever sample server context exists, while another renderer supports nonempty options. The bundled example's empty strategy-options list cannot establish that richer scenarios work.

**Revision:** Render the current backend RaceRead/Pirelli/actual-strategy contracts. Test multiple published options, display-only archival references, absent context, unknown estimates, consecutive same-compound stops, and provisional evidence. Preserve server-authored dry-rule semantics, evidence provenance, and versioned seasonal applicability. Do not equate a factual lane transit with Net Pit Loss or stationary stop duration.

## Story: feasible, but a new factual product feature

The archive demonstrates feasibility: the shared engine derives flags, pit events, timing improvements, lead/order changes, battles, penalties, deleted laps, qualifying phases, and results. Current Slipstream already has normalized history, canonical state, cursor-scoped session evidence, and a backend analytics layer. That is an appropriate basis for a Story feed.

The review did not establish an already-shipped generic Story API. Repository search returned no Story match; that is supporting evidence, not proof that no adjacent functionality exists. Treat Story as a small new backend feature with three renderers—desktop, phone, and TV—not as three independent frontend event engines. Template-based narration is sufficient for a useful first version; an LLM is not required.

### S1 — Confirmed pass appears before confirmation

`shared/engine.js:525–533` confirms a pass after five seconds, then dates the resulting event at its original occurrence time. `shared/story.js:41` filters by that earlier time rather than confirmation time.

Reproduction: at source time 1179, phone Story displays “HAM passes LIN.” The same event records `confirmedAt: 1184`, `t: 1179`, `id: 29`. The five-second confirmation is therefore silently borrowed from the future. This was reproduced in the rendered page, not merely inferred from an algorithm comment.

### S2 — Result narration borrows later classification

`shared/engine.js:578–589` constructs a race winner/top-three event from a snapshot 30 seconds after the flag but publishes it one second after the flag. Practice uses a snapshot up to 60 seconds later for an event dated two seconds after finish. Winner presentation also consults a later snapshot for details.

Even when the ultimate result is unchanged in this fixture, the implementation violates the rule that a delayed viewer must see only knowledge available at their source cursor. A podium cannot be treated as final simply because the leader has reached the flag.

### S3 — Deleted-lap impact looks ahead

`shared/engine.js:556–564` compares a snapshot before the message with one 12 seconds after it, then dates the position effect at the original message time. Publish the official deletion immediately when available; publish its confirmed positional effect only once that evidence exists.

### S4 — Other enrichment needs temporal review

The engine enriches pit-entry events after scanning later stop/exit data (`shared/engine.js:540–545`). Some renderers apply rejoin-time guards, so this is a field-by-field audit requirement rather than a blanket claim that every pit card leaks. Future sample-based map interpolation also needs separation from authoritative current facts. Do not carry wholesale offline preprocessing into a live/delayed backend.

### Recommended Story contract

Every event needs a stable identifier, session identity, occurrence time, available/confirmed time or source cursor, affected drivers, event type, priority, evidence basis, and correction/supersession information. The presentation rule is **available at or before the viewer cursor**, not merely “happened before the cursor.”

Deduplicate reconnects; rebuild deterministically after backward seeks; do not replay all old notifications on a seek. Keep bounded/history-query data outside the highest-frequency factual state payload. Use the same event interpretation for phone cards, TV ticker, desktop feed, and replay markers.

Prefer conservative language. A position change is not necessarily a physical overtake: pit cycles, timing corrections, penalties, lapping, and classification changes can reorder rows. Say “moves to P8” when causation is not established. Do not infer retirement from a quiet feed. Separate official announcements, observed facts, and derived interpretation.

### Story interaction and spoilers

Phone Story currently seeks ten seconds before the event, starts playback, and switches to Order. It does not preserve an obvious return path, and its “tap to replay” hint remains misleading in live mode where that callback does nothing.

Separate “inspect this event” from “replay this moment.” Preserve the previous watch point, playback state, and speed; offer return to that point. Full future highlight markers in completed-session review can be useful, but should be an explicit spoiler policy. Delayed-live viewing must never reveal later moments, flags, results, or derived narrative through any surface.

## Brand and motion treatment

The archive does not contain the provisional Slipstream icon. Desktop uses an SS placeholder, and branding is not coherent across the three presentations. The exact provisional asset should be supplied to the implementation; this review does not claim to have validated its geometry or animated it.

Use one swappable brand component. Suggested treatments:

- **Opening/connecting:** a wave or travelling highlight masked through the icon, accompanied by truthful phase text. Do not fabricate percentages. After initial opening, retain the last valid screen during reconnects rather than replacing everything with a logo.
- **Corner brand:** a subtle short shimmer, or a very low-amplitude optional wave. It must have less visual prominence than timing changes or race-control events. Branding motion is not a connection-health indicator.
- **Transitions:** short local changes rather than full-screen logo wipes between every tab, driver selection, or TV stage.
- **Reduced motion:** one consistent setting across map, row movement, ticker, director, callouts, and logo. Keep the information while reducing travelling/scaling effects. A static icon is a valid reduced-motion state.

Keep the current icon provisional and replaceable. Its final treatment need not block the structural mobile and synchronization work.

## Accessibility and small-text checks

A spot check found active navigation labels/hints using `#5b6674` against `#06080a` at 9–11 px. Calculated contrast is approximately 3.44:1; against `#0b0f14`, approximately 3.29:1. This is below the usual WCAG AA 4.5:1 normal-text threshold. Inactive-looking navigation that is still actionable is not a disabled-control exception. Raise essential secondary text contrast without making all metadata equally prominent.

Use generous targets for primary phone controls; 44 px is a useful design target, not the WCAG 2.2 AA minimum. The AA minimum is 24×24 CSS px with stated exceptions. Do not declare the 29–30 px tower rows nonconforming solely because of their height. Tiny timeline points need an equivalent usable list or scrub control.

Feed items and TV chips need meaningful semantic controls and keyboard behavior. Dialogs need focus entry/return and Escape. Absolute-positioned timing rows also warrant an assistive-technology reading-order check; this was not a complete screen-reader audit.

## Scope guardrails

Do not silently change provider selection, RaceState semantics, source/evidence cutoffs, status/lifecycle meaning, qualifying rules, or analytics formulas during a visual pass. Missing/unsupported values must remain unknown rather than being filled with plausible samples.

Connect library, downloads, settings, opening, reconnect, results, and failure designs to real application states. An attractive screenshot with all data available is not sufficient. Conversely, do not require M4 authentication, Admin pages, M5 device pairing, or cross-device synchronization simply to complete this presentation pass. Reserve coherent navigation space and honor the existing roadmap.

## Recommended next iteration

1. Freeze the successful TV visual direction and shared type/palette. Fix mobile rows/navigation/landscape, intermediate desktop Timing widths, and takeover obstruction.
2. Make viewer continuity and controls coherent: TV entry/exit, delay, replay/live terminology, keyboard restrictions, focus, session selection, and visible settings.
3. Map every current production capability to an appropriate desktop, phone, and TV entry point. Integrate current backend facts/analytics instead of prototype calculations.
4. Add Story as a bounded cursor-safe backend contract, beginning with official and well-supported observed events. Add uncertain causal inference only after validation.
5. Add the supplied icon and a consistent motion system, then validate the complete interaction on physical phone/TV setups.

Acceptance examples: no lost driver names at 320/360/390/430 and 1024/1280 widths; useful short-landscape layout; VSC does not cover leaders; TV entry preserves the same source moment; delay controls work without review/debug UI; no keyboard path bypasses capabilities; at cursor 1179 no event requiring 1184 is shown; flags/results do not leak across a 30-second viewer delay; unknown data remains unknown; repeated same-compound stops survive; non-race sessions do not gain race-only navigation; reduced motion retains every essential fact.

## Reference notes

Production: connected GitHub `rejozmathew/slipstream-f1/ROADMAP.md` and `ARCHITECTURE.md` inspected during review. Prior requirements: `Slipstream_Product_Requirements_v2.md`, `Slipstream_Claude_Design_Delta_v2.md`, and Race Intelligence & Strategy v2.1 cursor/evidence invariants. These are distinct from the prototype and should be treated as the integration contract.

External accessibility references: W3C Understanding WCAG 2.2, SC 1.4.3 Contrast (Minimum), SC 2.5.8 Target Size (Minimum), and SC 2.3.3 Animation from Interactions. This report uses those as design/test references, not as a claim of full conformance certification.
