# Race Intelligence & Strategy Charter

This folder contains the authoritative documentation for the server-side analytical models.

## Philosophy
1. **Fact First**: The `RaceState` is factual. Analytics are explicitly separated.
2. **Deterministic**: Analytics are derived deterministically based on context, rules, and model version.
3. **No Hindsight**: Evidence from the future is strictly prohibited.
4. **Server-Side Computation**: Clients (React, TV, Mobile) only render analytical truth; they do not calculate it.

## Model Registry
- [race-intelligence-v1](analytics/race-intelligence-v1.md): Initial strategy model (pre-v2.1).
- (Pending documentation will include `race-intelligence-v2.1` detailing enhanced gating, net pit-loss, and external contexts).

See the [CHANGELOG](../CHANGELOG.md) for recent updates.
