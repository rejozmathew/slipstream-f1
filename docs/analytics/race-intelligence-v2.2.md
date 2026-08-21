# Race Intelligence v2.2

This document details the updated Strategy and Analytics model implemented in Slipstream v2.2.

## Major Changes from v2.1
- **Enhanced Gating**: Strategy is now strictly gated by race phase proxying.
- **Terminal Status Propagation**: A terminal driver gets no future Strategy and is ineligible for Battles.
- **Strategy Archetype**: Added `strategyArchetype` (ONE_STOP, TWO_STOP, THREE_STOP, UNKNOWN) and expected total stops / remaining stops tracking upstream of phase heuristics.
- **Deterministic RaceRead**: Created a clean projection layer (`raceRead`) independent of state, resolving React/frontend layout assumptions and pushing logic upstream.
- **Contract Integrity**: Mirrored TypeScript definitions with backend models to resolve shape mismatches.
