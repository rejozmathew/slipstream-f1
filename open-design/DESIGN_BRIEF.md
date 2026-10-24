# Slipstream — First-Principles UI/UX Design Exploration

## Mission

Slipstream is a browser-first Formula 1 timing and race-intelligence product.

Its functional foundation now includes enough capability that the next design pass should not be incremental styling.

This exercise must ask from first principles:

**What should Slipstream feel like if it were designed today around the information and capabilities that now exist?**

The current UI is useful evidence of functionality, workflows and data.

It is not the aesthetic baseline that must be retained.

---

# Product Personality

Slipstream should feel unmistakably connected to Formula 1 without becoming a visual imitation of Formula 1's official products.

Avoid:

* generic enterprise dashboard aesthetics
* excessive card grids
* arbitrary red-on-black "F1 styling"
* neon gamer-dashboard aesthetics
* decoration that competes with live data
* motion merely because motion is possible
* making every number visually important
* shrinking information simply to fit more of it

The desired normal application experience is:

**premium, precise, extremely legible, calm, polished and approachable — a modern pit-wall intelligence product for a serious F1 fan.**

It should reveal sophistication progressively rather than presenting every user with maximum density immediately.

---

# Three Product Surfaces

Slipstream should be treated as one product expressed appropriately across three different viewing environments.

## 1. Normal Desktop Slipstream

Normal desktop Slipstream is the primary interactive intelligence workspace.

Priorities:

* clarity
* hierarchy
* rapid scanning
* precision
* rich analysis
* excellent data typography
* progressive disclosure
* intuitive navigation
* polished controls
* high information density without visual exhaustion

It should remain calm until something actually deserves attention.

Desktop should make sophisticated F1 information accessible without reducing the depth available to an expert user.

---

## 2. Phone Slipstream

Slipstream must be a first-class phone experience, not merely the desktop application compressed into a narrow viewport.

Primary reference viewport:

**390 × 844 CSS pixels**

The phone experience should preserve Slipstream's intelligence while deliberately changing hierarchy and interaction for a small touch display.

It is acceptable and expected for:

* information priority to change
* secondary evidence to move behind progressive disclosure
* dense tables to use different compositions
* navigation to change
* analytical surfaces to become staged or tabbed
* interactions to become touch-oriented
* desktop side-by-side layouts to become fundamentally different mobile compositions

Do not simply scale down or vertically stack the desktop interface.

Evaluate whether the existing mobile tab structures are actually the correct interaction model rather than automatically preserving them.

Important mobile considerations include:

* rapid access to the most important live information
* readable timing information
* touch target size
* one-handed interaction where practical
* avoiding excessive horizontal scrolling
* avoiding excessive vertical journeys through very long analytical pages
* keeping current session/race state visible
* efficient switching between Timing, Driver, Strategy, Battle and contextual information
* preserving the ability to drill deeper without overwhelming the primary screen

The desktop and phone experiences must clearly share one design system and one Slipstream identity.

---

## 3. Slipstream TV

TV Mode is not simply the desktop UI enlarged.

It is a living-room presentation surface and race companion designed primarily for a 16:9 display viewed from distance.

TV Mode does **not** require a phone implementation.

Priorities:

* viewing from distance
* obvious hierarchy
* excitement
* narrative
* movement
* transitions
* battles
* closing gaps
* strategy moments
* position and tyre changes
* race-control events
* driver/team identity
* strong use of the available 16:9 canvas

It should feel more like a premium sports-broadcast companion while remaining clearly part of the Slipstream product family.

Motion should communicate changing race state rather than act as decoration.

Normal Slipstream should feel composed and analytical.

TV Slipstream can feel alive and dramatic when the race provides a reason to do so.

---

# Design-System Requirement

The selected direction must function coherently across all of these families:

* Race timing
* Qualifying timing
* Practice timing
* Race Driver Focus
* Qualifying Driver Focus
* Practice Driver Focus
* Battle
* Strategy
* TV Mode
* Replay/session selection
* Settings
* responsive phone experiences
* future Login
* future Profile management
* future account/session management
* future deletion/privacy controls

A design direction that only makes the Race timing tower attractive is insufficient.

Likewise, a design direction that looks excellent on desktop but collapses on phone or cannot produce a convincing TV Mode is insufficient.

The system must accommodate fundamentally different information structures while remaining recognizably Slipstream.

---

# Existing Session Differences Matter

Do not assume Race, Qualifying and Practice are cosmetic variants of one timing page.

They communicate different information and should be evaluated independently.

Race includes richer race-state and strategy context.

Qualifying emphasizes:

* Q1/Q2/Q3 or SQ1/SQ2/SQ3 progression
* benchmark gaps
* cut-line context
* qualifying status
* latest attempts and sector evidence

Practice emphasizes:

* run classification
* lap performance
* gaps
* stint information
* conditions and contextual evidence

Likewise, Driver Focus is session-sensitive.

A Qualifying Driver page is structurally different from Race Driver Focus.

Practice has its own context.

The design system should make these differences feel intentional rather than inconsistent.

---

# Race Intelligence Surfaces

Battle and Strategy are important first-class product experiences.

They must not be treated as secondary screens simply because they exist only during Race/Sprint contexts.

## Strategy

Strategy should communicate complex tyre and race evidence with much stronger hierarchy than a conventional data table.

It should help the viewer understand:

* what was expected
* what has actually happened
* current tyre/stint context
* stop history
* relevant windows
* how driver strategies compare

## Battle

Battle should feel like observing an actual contest between two cars rather than merely looking at two data cards.

It should make:

* current gap
* gap trend
* relative tyre state
* track relationship
* strategy relationship
* battle significance

immediately understandable.

These principles apply differently to desktop, phone and TV.

---

# Milestone 4 Context

A subsequent implementation milestone will introduce or complete:

* users
* authentication/login
* profiles
* profile switching
* settings persistence
* account/session management
* deletion/account lifecycle
* related control-plane functionality

The design exploration occurs first so that Milestone 4 does not build new application surfaces against a visual system that is about to be replaced.

Concept work should therefore include enough Account/Profile/Settings thinking to establish the visual and interaction language those future screens should follow.

Do not implement Milestone 4 during this design exercise.

---

# Phase A — Full Current-Product Audit

Follow:

`open-design/CAPTURE_PLAYBOOK.md`

Inspect and capture the existing application before redesigning.

The running reference application is:

`http://localhost:3344/`

The audit should include desktop, phone and TV where appropriate.

Create a complete audit manifest and identify systemic problems rather than producing a disconnected list of cosmetic complaints.

The current application is evidence of:

* functionality
* available information
* navigation
* application states
* workflows
* existing constraints

It is **not** evidence that today's visual hierarchy or page composition is correct.

---

# Phase B — Three Genuinely Different Design Directions

After completing the audit, create THREE distinct design directions.

These must represent materially different approaches to:

* hierarchy
* density
* navigation
* surface treatment
* typography
* use of team identity
* color
* data emphasis
* motion
* progressive disclosure
* responsive behavior
* overall emotional character

Do not create three versions that differ mainly in palette, radius, shadows or superficial styling.

You may rename or refine the concepts, but useful conceptual starting points are:

## Direction A — Precision / Pit Wall

Highly controlled, sophisticated and restrained.

Exceptional data typography and hierarchy.

Feels like professional motorsport intelligence made approachable.

## Direction B — Modern Sports Intelligence

More expressive and accessible.

Stronger visual storytelling, driver/team identity and race narrative.

Feels closer to a premium contemporary sports product without becoming broadcast graphics.

## Direction C — Slipstream Signature

Invent a distinctive visual language specifically for Slipstream.

It should not feel like:

* an F1 clone
* an enterprise BI dashboard
* a generic SaaS template
* a gaming HUD

The goal is for a future screenshot to be recognizable as Slipstream.

---

# Initial Concept Comparison Screens

Do NOT build the entire product three times initially.

Instead, force every design direction to prove itself on a deliberately difficult cross-section of the product.

## Desktop

Each direction should demonstrate:

1. Race Session — populated timing/analysis view
2. Qualifying Session
3. Race Driver Focus
4. Qualifying Driver Focus
5. Strategy
6. Battle
7. Settings / Profile direction
8. TV Mode — Timing Tower
9. TV Mode — one highly visual Race state, preferably Battle or Track

These screens test:

* dense tabular data
* session-specific structures
* individual driver narrative
* strategy information
* comparison analytics
* ordinary application UI
* future account UI
* large-screen presentation

## Phone

Each direction must additionally demonstrate approximately **390 × 844** phone behavior on:

1. Race Session
2. Driver Focus
3. one difficult analytical surface — preferably Strategy or Battle

Do not simply show the desktop version stacked vertically.

The phone concept must demonstrate the direction's actual responsive interaction strategy.

---

# Phase C — Critique and Comparison

After generating the three directions, critique all three against the same criteria.

Assess:

* visual quality
* scanability
* information hierarchy
* ease of learning
* expert usefulness
* accessibility
* responsive quality
* touch usability
* scalability to every Slipstream screen
* TV suitability
* distinctiveness
* implementation practicality
* risk of visual fatigue during a two-hour race
* ability to support future Milestone 4 account surfaces
* consistency across Race / Qualifying / Practice
* consistency across desktop / phone / TV without making them artificially identical

Be critical.

Do not automatically recommend the most visually dramatic concept.

Produce a comparison and identify:

* strongest overall direction
* strongest individual ideas from each direction
* ideas worth combining
* unresolved questions
* implementation risks
* any areas where the current Slipstream UI is actually superior

---

# Phase D — Selected-Direction Expansion

Do not perform this phase until the user chooses or explicitly approves a direction.

Once a direction is selected:

* formalize `DESIGN.md`
* establish design tokens
* typography
* spacing
* component primitives
* navigation
* status treatments
* team/driver identity rules
* tyre-compound treatments
* timing towers
* tables
* charts
* panels
* forms
* controls
* responsive rules
* touch behavior
* TV motion principles

Then apply the selected system across the FULL audited screen inventory.

No meaningful screen captured during the baseline audit should be forgotten during final expansion.

Desktop and phone should be validated separately.

TV Mode should be treated as a related presentation system built from the same core identity.

---

# Implementation Boundary

During audit and concept exploration, work only beneath:

`open-design/`

Do not modify production Slipstream application source.

You may inspect Slipstream source to understand:

* product behavior
* data
* navigation
* conditional screens
* responsive behavior

but concept-generation writes must remain isolated under `open-design/`.

Concept artifacts may use real Slipstream data shapes or representative fixtures, but they must remain isolated from production.

Only after a design direction has been selected should a separate production implementation plan be created.

---

# Core Principle

Do not redesign Slipstream by asking:

**"How can the current interface look nicer?"**

Ask:

**"Given what Slipstream now knows and can do, what is the clearest, most engaging and most distinctive way for a Formula 1 fan to experience this information on desktop, phone and TV?"**
