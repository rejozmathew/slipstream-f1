# Slipstream UI Capture Playbook

## Purpose

Before proposing or generating any redesigned Slipstream UI, inspect the complete current application and create a systematic visual baseline.

The current application is functional evidence, not a visual design that must be preserved.

Do not begin redesign work until the baseline capture inventory is substantially complete.

## Environment

Reference application:

`http://localhost:3344/`

The application is already running locally.

The OpenDesign working directory is the dedicated Slipstream design-exploration worktree.

### Safety boundary

During the audit and concept phases:

* Do not modify production Slipstream application source.
* Do not refactor existing React components.
* Do not change backend behavior.
* Do not change API contracts.
* Write research, screenshots, prototypes and design artifacts only beneath `open-design/`.
* The running localhost application is read-only reference material.

---

# 1. Understand navigation before capturing

Open `http://localhost:3344/`.

First inspect the global shell and determine:

* primary navigation
* session/replay selector
* current session identity
* replay/live state
* session-specific navigation availability
* TV Mode navigation
* Settings navigation

Record the discovered structure in:

`open-design/research/current-ui/NAVIGATION.md`

Do not infer that every navigation option exists in every session type.

---

# 2. Session selection procedure

Slipstream's session picker follows:

**Season → Weekend → Session**

Open the session selector in the application header.

For this audit:

* use already-downloaded sessions marked `REPLAY`
* do not click `DOWNLOAD REPLAY`
* do not switch to `GO LIVE`
* prefer one weekend for which Race, Qualifying and Practice replays are all available
* if one weekend does not contain suitable examples of all three, use the best available replay for each type

Record the exact selected season, weekend, session name and session type.

After changing sessions, do not capture immediately.

Wait until:

1. the session picker/header reflects the selected session;
2. the connection state reports `REPLAY CONNECTED`;
3. `OPENING SESSION` is no longer visible;
4. the main timing content contains populated driver rows;
5. major analysis panels have finished rendering.

After those conditions are satisfied, allow the layout a short additional settling period before capture.

If a required screen cannot be obtained, record why instead of silently skipping it.

---

# 3. Race capture set

Select a representative Race replay containing rich data.

Capture the normal Session screen.

## Race timing tower modes

The Race timing tower has three distinct modes. Capture all three:

* STANDARD
* TIMING
* STRATEGY

Use the normal/balanced layout unless another configuration is required to make the screen usable.

Do not treat these as cosmetic variants; their information structures differ.

Suggested filenames:

`race/session-standard.png`

`race/session-timing.png`

`race/session-strategy-tower.png`

## Race Driver Focus

From the timing tower, select a representative circulating driver with useful stint/lap data.

Prefer a driver with:

* current tyre information
* several completed laps
* meaningful ahead/behind context
* pit/strategy evidence if available

Capture the Race Driver Focus page.

`race/driver-focus.png`

## Battle

Open `BATTLE`.

Capture a populated battle.

Prefer the Recommended battle when it provides a meaningful pair.

If Recommended has no stabilized battle, use Leader mode or choose a suitable pair rather than capturing only an empty state.

Capture:

`race/battle.png`

Also note the Recommended / Leader / Pinned interaction model.

## Strategy

Open `STRATEGY`.

Capture the complete strategy experience with as much Pirelli/current-race information populated as the selected replay permits.

`race/strategy.png`

## Race TV Mode

Open `TV MODE`.

Race TV Mode supports these presentation states:

* TOWER
* TRACK
* STRATEGY
* BATTLE
* DRIVER

Capture every available state individually.

Suggested filenames:

`tv-mode/race-tower.png`

`tv-mode/race-track.png`

`tv-mode/race-strategy.png`

`tv-mode/race-battle.png`

`tv-mode/race-driver.png`

If one or more states are missing from the TV footer because of current device preferences, record that fact.

If necessary, inspect Settings → Preferences and determine whether all Race TV states can safely be enabled for the audit. Record the original setting before changing it and restore it when the capture pass is complete.

Keep Auto Rotation OFF during deterministic screenshots.

---

# 4. Qualifying capture set

Select a representative Qualifying replay.

Wait for the qualifying timing data to populate.

Capture:

`qualifying/session.png`

The Qualifying tower must be treated as its own information architecture, not as a recolored Race tower.

Where reasonably possible, capture a state with rich qualifying evidence: Q1/Q2/Q3 results, tyre information, gaps and sector/latest-lap data.

If obtaining both an active qualifying phase and the completed/final qualifying state is straightforward using replay controls, capture both:

`qualifying/session-active.png`

`qualifying/session-final.png`

Do not block the entire audit if only one representative state is practical.

## Qualifying Driver Focus

Select a driver from the qualifying tower.

Capture the qualifying-specific Driver Focus page.

`qualifying/driver-focus.png`

This screen is structurally different from Race Driver Focus and must be reviewed independently.

## Qualifying TV Mode

Open TV Mode.

Capture:

* TOWER
* TRACK, if track-position data makes this state available

Suggested filenames:

`tv-mode/qualifying-tower.png`

`tv-mode/qualifying-track.png`

---

# 5. Practice capture set

Select a representative Practice replay.

Capture:

`practice/session.png`

The Practice timing tower is its own information structure and must be reviewed separately.

## Practice Driver Focus

Choose a representative driver.

Capture:

`practice/driver-focus.png`

Pay particular attention to the Practice-specific conditions/context treatment.

## Practice TV Mode

Open TV Mode.

Capture the available Practice presentation state:

`tv-mode/practice-tower.png`

---

# 6. Shared application surfaces

Capture the application-level surfaces that are not specific to a race session.

## Replay/session selector

Capture the session selector while open and populated.

`shared/replay-library.png`

## Settings

Inspect and capture:

* Profile
* Appearance
* Layouts
* Sync & Devices
* Preferences / TV Mode

Suggested filenames:

`settings/profile.png`

`settings/appearance.png`

`settings/layouts.png`

`settings/sync-devices.png`

`settings/preferences-tv.png`

Some account/control-plane surfaces are intentionally placeholders today. Do not treat placeholder content as a finished product requirement.

Milestone 4 will introduce users, authentication, profiles, account/session management, persistence and deletion. The redesign must therefore establish a visual and interaction language that those future surfaces can use.

## Replay controls

Capture at least one representative normal page with replay controls visible.

`shared/replay-controls.png`

---

# 7. Baseline screenshot rules

Use consistent desktop dimensions wherever possible.

Primary desktop reference:

**1440 × 900**

TV Mode reference:

**1920 × 1080 / 16:9**

Do not crop away important application chrome when evaluating global information architecture.

Additional detail crops may be created, but they do not replace full-screen captures.

Avoid captures while:

* loading
* reconnecting
* session switching
* data is visibly incomplete
* menus accidentally obscure the target UI

unless the purpose of the screenshot is specifically to document that state.

---

# 8. Audit manifest

Create:

`open-design/research/current-ui/AUDIT_MANIFEST.md`

For every capture record:

* filename
* session/weekend
* session type
* application view
* sub-mode/state
* viewport
* driver/pair if applicable
* whether data was fully populated
* anything unusual
* design/UX observations
* capture unavailable reason, if applicable

Also maintain a coverage checklist.

The audit is complete only when every required item above is either:

* captured, or
* explicitly marked unavailable with a reason.

---

# 9. Analysis after capture

After the screenshot inventory is complete, analyze the application across the whole set.

Evaluate:

* information hierarchy
* scanability
* density
* cognitive load
* typography
* spacing
* navigation
* discoverability
* consistency
* component reuse
* visual differentiation between session types
* driver/team identity
* tyre/compound communication
* status/alert communication
* meaningful use of color
* use of empty space
* accessibility
* large-screen behavior
* TV viewing distance
* motion opportunities
* data storytelling
* approachable presentation for serious F1 fans
* whether expert information remains accessible without dominating every screen

Distinguish between:

1. functionality that should be preserved;
2. information that should be preserved but reorganized;
3. existing interaction conventions worth preserving;
4. visual conventions that exist only because of the current implementation;
5. genuine UX problems;
6. opportunities to make Slipstream more distinctive.

Do not begin from the premise that the existing layout is correct.

The current product is the evidence base, not the design constraint.
# 10. Mobile / Phone Audit

Slipstream must remain a fully usable responsive application on phone-sized displays.

TV Mode is a large-screen presentation experience and does not need a phone layout.

Do not evaluate mobile merely by resizing the desktop screenshots. Inspect the application's actual responsive/mobile behavior.

Use a representative modern phone viewport, approximately:

**390 × 844 CSS pixels**

Also inspect a slightly narrower viewport if useful for identifying layout failures.

Capture at minimum:

## Race

* Race Session / Timing
* Race mobile Strategy
* Race mobile Map
* Driver Focus
* Battle
* full Strategy page if accessible and meaningfully different on phone

## Qualifying

* Qualifying Session / Timing
* Qualifying Session / Session context
* Qualifying Driver Focus

## Practice

* Practice Session / Timing
* Practice Driver Focus

## Shared

* Replay/session selector
* Settings
* primary navigation

Save beneath:

`open-design/research/current-ui/mobile/`

During the audit, evaluate:

* whether information priority changes appropriately for phone
* whether the desktop hierarchy survives at small sizes
* whether tables remain understandable
* whether horizontal scrolling is being used appropriately
* whether controls have adequate touch targets
* whether important live information remains visible without excessive scrolling
* whether navigation requires too many taps
* whether tabs are still the right mobile interaction model
* whether dense analytical screens should become staged/progressive experiences
* whether Driver, Battle and Strategy need materially different mobile compositions

The redesign must treat mobile as a first-class responsive expression of the same Slipstream design system, not as a reduced desktop afterthought.
