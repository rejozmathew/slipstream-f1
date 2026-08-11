# Architecture

```text
OpenF1 recording -> normalization -> event history -> replay clock -> RaceState
                                                                    |-> terminal
                                                                    |-> API v1
                                                                    `-> browser

F1 public SignalR -> versioned raw recording -> live normalization (next)
```

`RaceState` is an immutable snapshot. The reducer creates a new state for every event. Its canonical children include session, circuit, driver, weather, and race-control state. `ReplayController` owns cursor, source clock, pause/resume, batched advance, and time seek; seeking reconstructs state from the event history. `ReplayLibrary` merges a lightweight recent-season catalog with local recordings, then normalizes only the selected recording. The catalog supplies dates and preloaded historical circuit paths; local recordings overlay timing and replay capabilities. Raw OpenF1 responses and linked geometry remain versioned inputs; provider fields are translated only by the adapter.

Adapters own source specifics and the instance's one upstream connection. Normalization owns canonical fields and provenance. State owns no transport logic. Presentations read state, never upstream data.

The historical and live implementations expose capabilities: `historical_replay`, `live_timing`, `positions`, `intervals`, `location_xy`, `circuit_shape`, `race_control`, `weather`, `local_time`, and `authenticated`. Consumers use declared capabilities rather than source names. The common source interface is still deferred until the public live collector has been exercised during a session.

The API and browser are replay-backed. The circuit outline uses ordered historical coordinates linked by the OpenF1 meeting record. Normal recordings interpolate driver placement between lap boundaries; optional high-volume historical location captures carry exact per-car X/Y in the same canonical driver state. The browser selects the rendering path from `positionMode`, not the provider name. The public live collector keeps provider frames raw so its normalizer can be developed against our own real recording rather than copied or inferred payloads. One collector owns one concurrent upstream connection; reconnects may replace it but must never multiply it.

Race-control flags retain source scope. Only whole-track green, yellow, red, chequered, safety-car, and virtual-safety-car events may update `session.track_status`; driver and sector flags remain messages only.

Production deployment is one application container and one process. The browser compiles to static files during the image build; FastAPI serves those files at `/`, REST at `/api/v1/*`, and the replay WebSocket at `/api/v1/stream`. Reverse proxies are external deployment choices, not application services.
