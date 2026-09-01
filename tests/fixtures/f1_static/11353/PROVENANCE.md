# Official F1 Dutch Race 11353 compact fixture

These files are a compact, deterministic subset of the public official Formula 1
static archive for session `11353`, downloaded from:

`https://livetiming.formula1.com/static/2026/2026-08-23_Dutch_Grand_Prix/2026-08-23_Race/`

The small session, driver, clock, lap, status, track-status, and final TimingData
artifacts are retained verbatim. `TimingData.jsonStream`,
`RaceControlMessages.jsonStream`, and `WeatherData.jsonStream` retain only the
verbatim provider rows needed for the clock, lifecycle, final-boundary, control,
and weather acceptance case. No full-session recording, Position, CarData,
telemetry, radio, credential, or authenticated capture is included.

The selected lifecycle rows preserve the owner-pinned SessionTime cursors for
VER 3, BEA 87, STR 18, OCO 31, BOT 77, and ALB 23. The final `TimingData.json`
snapshot is used only at the source-provided terminal boundary.
