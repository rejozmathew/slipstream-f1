# Working agreement

- Read `ARCHITECTURE.md` before coding and `docs/protocol.md` before changing state or transport contracts.
- Keep documentation proportional to the code; avoid speculative subsystems.
- Preserve `RaceState` as the canonical normalized boundary.
- Put provider-specific logic only in adapters.
- Never commit recordings, tokens, cookies, `.env` files, or authenticated captures.
- Do not copy code from AGPL projects, including slowlydev/f1-dash.
- Add a focused test and update a golden file for visible state changes.
- Version public API routes and event envelopes as documented in `docs/protocol.md`.
- Do not extract a common source interface until the public-live implementation has been validated against a real session capture.
- Treat public and authenticated live capabilities separately; never silently request or require protected topics.
