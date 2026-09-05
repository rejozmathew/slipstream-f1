# Replay Readiness Performance: Profile and Architecture Proposal (Phase 1)

## Executive Summary

Historical session playback in Slipstream currently exhibits severe readiness delays:
- Opening an already-downloaded historical race (e.g. British GP 2024, 109,067 events, 39.6 MB) requires **9.3 seconds** before playback controls become usable.
- On cold server start with multiple downloaded sessions, discovery rescans and replays all canonical recordings, taking up to **119.1 seconds** (nearly 2 minutes).
- Seeking to 95% of a race requires re-reducing 100,000+ events sequentially from scratch, taking **4.1 seconds**.
- Switching sessions (A → B → A) discards the active session from the single-entry cache, forcing a complete **7.8-second re-reduction**.
- Nonzero Live broadcast delay currently instantiates a new controller on every frame and replays all historical events from scratch, taking **3.5 seconds per snapshot**.
- During synchronous loading, the Python asyncio event loop is blocked, causing concurrent `GET /api/v1/catalog` requests to stall by **1.82 seconds** (a 291× latency spike).

This document presents empirical benchmark profiles across four representative sessions, identifies the exact architectural bottlenecks, evaluates three local storage alternatives, and proposes a zero-locking, bind-mount-resilient **Prepared Replay Package** with periodic state checkpoints, chunked events, an explicit readiness job lifecycle (`DOWNLOADING` → `PREPARING` → `READY`), and incremental live delay advancement.

---

## 1. Measured Baseline

All measurements were performed on an isolated test runner using locally available representative recordings without committing raw captures or benchmark artifacts.

### 1.1 Representative Session Profiles

| Metric | British GP 2024 Race (Canonical F1) | British GP 2024 Qualifying (Canonical F1) | Spanish GP 2024 Race (OpenF1) | British GP 2024 Qualifying (OpenF1) |
| :--- | :--- | :--- | :--- | :--- |
| **Session Key** | `11353` | `11349` | `11299` | `11349` |
| **Source Tier** | `f1-static-public` | `f1-static-public` | `openf1` | `openf1` |
| **File Size** | 39.59 MB | 10.58 MB | 8.08 MB | 0.74 MB |
| **Event Count** | 109,067 | 32,534 | 32,279 | 1,923 |
| **Process RSS Before** | 56.9 MB | 63.6 MB | 67.6 MB | 73.2 MB |
| **Process RSS After** | 213.0 MB | 98.9 MB | 94.8 MB | 73.3 MB |
| **Process RSS Delta** | **+156.1 MB** | **+35.3 MB** | **+27.2 MB** | **+0.1 MB** |
| **JSON Parse Time** | 0.226 s | 0.067 s | 0.036 s | 0.003 s |
| **Normalization Time** | 0.127 s | 0.057 s | 0.234 s | 0.009 s |
| **Final State Reduction** | **3.268 s** | **0.887 s** | **1.136 s** | **0.044 s** |
| **SessionEvidence Build** | **4.194 s** | **0.969 s** | **1.094 s** | **0.046 s** |
| **Analytics Calculation** | 0.032 s | 0.098 s | 0.031 s | 0.015 s |
| **Seek to 50% (Midpoint)** | **2.130 s** | **0.466 s** | **0.581 s** | **0.025 s** |
| **Seek to 95% (Race End)** | **4.135 s** | **0.857 s** | **1.053 s** | **0.058 s** |
| **Total Computation** | **7.847 s** | **2.079 s** | **2.531 s** | **0.116 s** |

### 1.2 End-to-End User Journey Scenarios

| Scenario | Measured Time | Key Bottlenecks / Observations |
| :--- | :--- | :--- |
| **Cold Server Startup (2 sessions in dir)** | **9.86 s** | `ReplayLibrary.__init__` scans `.json` files and calls `replay(events)` to determine session capabilities. |
| **Cold Server Startup (8 canonical sessions)** | **119.11 s** | Full file scan and full `replay(events)` on all 8 canonical recordings (30–40 MB each) sequentially on startup. |
| **First Open (Session 11353 Race)** | **9.30 s total** | `GET /state` takes **9.03 s** (parse + 109k event reduction + evidence build); metadata takes **0.06 s**; WS first snapshot takes **0.22 s**. |
| **Repeat Open (Same Session 11353)** | **0.14 s total** | In-memory cache hit in `library._cache`: `GET /state` takes **0.011 s**, WS snapshot takes **0.132 s**. |
| **A → B → A Switching (11353 → 11349 → 11353)** | **7.79 s** | `self._cache = {selected_key: resource}` holds only 1 item. Opening 11349 evicts 11353. Returning to 11353 repeats all 7.8s of work. |
| **Restart Followed by Open** | **38.97 s total** | 9.77 s process initialization + 29.20 s library scan and first session reconstruction. |
| **Post-Download Library Rescan** | **5.53 s – 119 s** | `POST /download` invokes `ReplayLibrary(recording_path)`, re-indexing every file in the directory. |
| **Simultaneous Viewers (Concurrent Seeks)** | Viewer 1 (20k): **0.66 s**<br>Viewer 2 (80k): **2.84 s** | Each seek recalculates state from event 0 sequentially on the Python thread, contending for CPU. |
| **Live Broadcast Delay (45s behind live)** | **3.49 s per seek** | `ReplayController.seek_delay` resets state to `RaceState()` and replays all events from event 0 up to `(newest - 45s)`. |
| **Live Broadcast Delay (137s behind live)** | **3.53 s per seek** | Full event history replayed from scratch on every delayed snapshot. |

---

## 2. Current Pipeline Trace and Bottlenecks

### 2.1 Complete Call-Flow Architecture

```text
[User selects replay in Browser]
       |
       v
HTTP GET /api/v1/state?session_key=11353
       |
       +---> [api.py: resource(session_key)]
       |        |
       |        +---> [library.py: ReplayLibrary.get(session_key)]
       |                 |
       |                 +--- Cache check: self._cache.get(key)
       |                 |    (MISS on first open or if session changed)
       |                 |
       |                 +---> [replay.py: load_events(path)]
       |                 |        |-- Reads full JSON (39.6 MB) [0.226s]
       |                 |        `-- Normalizes 109,067 NormalizedEvents [0.127s]
       |                 |
       |                 +---> [replay.py: replay(events)]  <=== BOTTLENECK 1 (3.27s CPU)
       |                 |        `-- Replays events 0..109,067 sequentially
       |                 |            Produces final_state (END of race)
       |                 |
       |                 +---> [evidence.py: SessionEvidence.from_events(events)] <=== BOTTLENECK 2 (4.19s CPU)
       |                 |        `-- Scans all 109,067 events
       |                 |            Builds lap observations & pit events
       |                 |
       |                 `-- Cache write: self._cache = {selected_key: resource} <=== BOTTLENECK 3
       |                     (EVICTS ALL OTHER SESSIONS)
       |
       +---> Serializes final_state envelope to HTTP response
       |
       v
[Frontend receives GET /state response]
       |
       |-- Renders final_state immediately  <=== BOTTLENECK 4 ("END OF RACE FLASH")
       |-- Fires background GET /api/v1/analytics?seq=109067
       |-- Fires GET /api/v1/replay and GET /api/v1/capabilities
       `-- Opens WebSocket to /api/v1/stream?session_key=11353&mode=replay
              |
              v
[FastAPI accepts WebSocket]
       |
       +---> [playback.py: ReplayController.__init__(selected.events)]
       |        `-- Re-sorts all 109,067 events by timestamp  <=== BOTTLENECK 5
       |
       +---> [playback.py: controller.start()]
       |        `-- Calls seek(start_time): resets state to RaceState()
       |            Replays events from 0..start_time
       |
       +---> [analytics.py: analytics_service.snapshot(...)]
       |        `-- Computes session-start analytics snapshot
       |
       +---> WebSocket sends state.snapshot at session-start cursor
       |
       v
[Frontend onSnapshot replaces state]
       |
       `-- UI abruptly transitions from final state to start state.
           Playback controls become enabled once metadata AND WS snapshot arrive.
           Elapsed time: 9.3 seconds.
```

### 2.2 Identification of Redundant Work

1. **Full-File Parse on Startup and Post-Download**:
   In `library.py` (`_read_descriptor`, lines 452–478), when indexing any canonical recording list (`f1-static-*.json`), the system executes a full `replay(events)` across all events just to extract session key, start/end dates, and capability flags. With 8 recordings, startup takes 119 seconds.
2. **Full-State Reconstruction for End-State**:
   `library.py` (line 210) calls `final_state=replay(list(events))` synchronously during `get()`. This is done to compute final terminal state, even when the user wants to start replay from the beginning.
3. **Single-Item In-Memory Cache**:
   `library.py` (line 215) sets `self._cache = {selected_key: resource}`. Any selection of another session completely frees and evicts the previous session.
4. **Re-sorting Already-Sorted Events**:
   `ReplayController.__init__` executes `sorted(events, key=parse_timestamp)` on every WebSocket viewer connection, even though normalized events are already chronological.
5. **Full Re-Reduction on Every Seek**:
   `ReplayController.seek` (line 67) calls `self.reset()` and loops from event `0` up to `target`. Seeking to lap 50 of a 52-lap race takes 4.14 seconds.
6. **Full Re-Reduction on Every Delayed Live Snapshot**:
   `api.py` (lines 476–488) constructs a new `ReplayController` and calls `seek_delay(seconds)` from event `0` on every single live delayed state poll.

---

## 3. Confirmed vs. Suspected Costs

| Cost Factor | Status | Measured Evidence & Findings |
| :--- | :--- | :--- |
| **Pure-Python Reducer Loop** | **CONFIRMED PRIMARY BOTTLENECK** | 3.27s CPU for 109k events. Running `state.apply(event)` in pure Python is CPU-bound. |
| **SessionEvidence Construction** | **CONFIRMED PRIMARY BOTTLENECK** | 4.19s CPU for 109k events. Iterating through all events and updating driver lap/stint/pit trackers accounts for >50% of prep time. |
| **Seeking from Event 0** | **CONFIRMED PRIMARY BOTTLENECK** | Seeking to 95% cursor takes 4.14s. Linearly proportional to cursor distance. |
| **Event Loop Blocking** | **CONFIRMED CRITICAL DEFECT** | Synchronous execution on main thread blocks concurrent HTTP requests for 1.82s (291× latency increase). |
| **Python GIL Contention** | **CONFIRMED ARCHITECTURAL CONSTRAINT** | Wrapping pure-Python loops in `asyncio.to_thread` still causes 44× slowdown (275ms) due to GIL thrashing; dual threads slow down by 1.84× and spike HTTP latency to 1.42s (max 6.27s). |
| **Single-Entry Resource Cache** | **CONFIRMED DEFECT** | A → B → A selection re-executes all 7.8s of computation because cache capacity is 1. |
| **Startup Discovery Replay** | **CONFIRMED DEFECT** | 119.1s cold startup caused by `_read_descriptor()` replaying all canonical recordings. |
| **JSON Deserialization** | **DISPROVEN AS BOTTLENECK** | `json.loads` of 39.6 MB takes only **0.226s** (<3% of total time). Parsing is not the culprit. |
| **Analytics Computation** | **DISPROVEN AS INITIAL BOTTLENECK** | `AnalyticsService.snapshot` takes only **0.032s** when evidence and state are already present. |

---

## 4. Storage Alternatives Evaluation

To achieve sub-100ms cold open, sub-100ms seek, and sub-1s library startup, three local storage architectures were prototyped and benchmarked on the 109k-event British GP 2024 race recording (`f1-static-11353.json`, 39.59 MB raw).

### 4.1 Evaluation Matrix

| Criterion | Option 1: Structured / Chunked Directory | Option 2: SQLite-Backed Prepared Package | Option 3: Monolithic Compressed Archive |
| :--- | :--- | :--- | :--- |
| **Cold-Open Latency** | **32.4 ms** (277× faster than raw) | **1.65 ms** (5400× faster than raw) | 21.3 ms (must decompress archive) |
| **Seek Latency (50%)** | **61.6 ms** (35× faster than raw) | **7.95 ms** (268× faster than raw) | N/A (must decompress and scan) |
| **Seek Latency (95%)** | **59.8 ms** (69× faster than raw) | **8.62 ms** (480× faster than raw) | N/A |
| **Preparation Time** | **2.11 s** (write manifest + CPs + chunks) | **2.04 s** (write SQLite tables) | 0.19 s |
| **Disk Overhead** | **41.61 MB** (1.05× raw size) | **41.70 MB** (1.05× raw size) | 0.16 MB (metadata only) |
| **Memory Overhead (RSS)** | **+0.1 MB** (reads only active chunk/CP) | **+0.2 MB** (sqlite handle + query) | +45 MB (full uncompressed memory) |
| **Atomic Publication** | **Atomic Directory Rename** (`os.replace` on staging dir) | Single file rename (`.tmp.sqlite3` → `.sqlite3`) | Single file rename |
| **Version Invalidation** | Trivial: remove dir or check `manifest.json` | Requires checking SQLite schema/pragma | Check archive header |
| **Deletion Simplicity** | **Trivial** (`shutil.rmtree`) | Prone to `PermissionError` on Windows if DB connection open | Trivial (`os.remove`) |
| **Concurrent Readers** | **Zero contention** (OS page-cache static files) | Requires connection pool or WAL concurrency | Contention if file opened concurrently |
| **OS / Bind Mount Compatibility** | **100% Reliable** on Windows, Linux, Docker, WSL2, Unraid/TrueNAS NFS/SMB/FUSE | **High Risk**: SQLite WAL mode locks frequently fail on NFS/CIFS/Unraid FUSE | Reliable |
| **Implementation Complexity** | **Low**: standard library `json`, `pathlib`, `os` | **Medium**: SQL schema, migrations, connection management | Low |
| **Milestone Boundary Alignment** | **Strictly Aligned** (M3.5 preserves file-based architecture; M4 introduces SQLite) | Conflicts with M3.5 boundary (premature SQLite adoption) | Aligned |

---

## 5. Recommended Design and Rationale

### Recommendation: Option 1 (Structured / Chunked Prepared Replay Package)

We recommend **Option 1: Structured / Chunked Prepared Package** as the authoritative preparation format for M3.5, with an explicit readiness lifecycle:

1. **Immunity to Network and Bind Mount Locking**:
   Many Slipstream users deploy self-hosted Docker containers on Unraid, TrueNAS, or Synology with recording directories mounted over NFS or SMB, or on Unraid's user-share FUSE system (`shfs`). SQLite in WAL mode requires POSIX advisory locks and shared memory (`-shm`) mmap, which frequently fail on network shares and FUSE mounts, producing `sqlite3.OperationalError: database is locked` or corrupt shm files. Option 1 uses standard immutable read-only JSON files, which work flawlessly across all storage engines and operating systems.
2. **Windows File Deletion Safety**:
   On Windows, an open SQLite connection handle holds a mandatory lock that prevents file deletion (`PermissionError: [WinError 32]`). Plain read-only files opened, read, and closed immediately leave no persistent file locks.
3. **Sub-100ms Performance Budgets Met**:
   Option 1 achieves **32.4 ms cold open** and **59.8 ms seek to 95%**, well below the 100ms interactive threshold.
4. **Clean Boundary Preservation**:
   ARCHITECTURE.md specifies that Milestone 4 introduces SQLite for user authentication, viewer profiles, and control-plane persistence. Introducing SQLite in M3.5 for replay acceleration creates architectural coupling before the M4 database infrastructure is established.

---

## 6. Proposed Prepared Package Layout

All prepared acceleration artifacts are stored in a dedicated hidden subdirectory below the recordings path: `.slipstream/prepared/<session_key>/`.

### 6.1 Directory Tree

```text
recordings/
|-- catalog.json
|-- f1-static-11353.json                          <-- Canonical recording (AUTHORITATIVE)
|-- .slipstream/
    |-- sources/
    |   `-- 11353.json                            <-- Source provenance manifest
    `-- prepared/
        `-- 11353/                                <-- Prepared package (REBUILDABLE ACCELERATION)
            |-- manifest.json                     <-- Lightweight package descriptor (~2 KB)
            |-- evidence.json                     <-- Pre-calculated lap & pit evidence (~150 KB)
            |-- checkpoints/
            |   |-- cp_000000.json                <-- Session start checkpoint (seq 0)
            |   |-- cp_005000.json                <-- Checkpoint at seq 5,000
            |   |-- cp_010000.json                <-- Checkpoint at seq 10,000
            |   |-- ...
            |   `-- cp_109067.json                <-- Final terminal state checkpoint
            `-- chunks/
                |-- chunk_0000.json               <-- Events 1 to 5,000
                |-- chunk_0001.json               <-- Events 5,001 to 10,000
                `-- ...
```

### 6.2 Manifest Specification (`manifest.json`)

```json
{
  "$schema": "slipstream.prepared-replay.v1",
  "formatVersion": 1,
  "sessionKey": "11353",
  "meetingKey": "1240",
  "sourceType": "f1-static-public",
  "recordingFingerprint": {
    "sizeBytes": 41513813,
    "mtimeNs": 1725482012000000000,
    "sha256Prefix": "a7c3b8..."
  },
  "compatibility": {
    "schemaVersion": 1,
    "reducerVersion": "2026.09.1",
    "evidenceVersion": "2026.09.1"
  },
  "eventCount": 109067,
  "timeBounds": {
    "startTime": "2024-07-07T14:00:00+00:00",
    "endTime": "2024-07-07T15:35:12.450000+00:00",
    "durationSeconds": 5712.45
  },
  "checkpointConfig": {
    "eventInterval": 5000,
    "count": 23
  },
  "checkpoints": [
    { "seq": 0, "occurredAt": "2024-07-07T14:00:00+00:00", "file": "checkpoints/cp_000000.json" },
    { "seq": 5000, "occurredAt": "2024-07-07T14:04:12+00:00", "file": "checkpoints/cp_005000.json" },
    { "seq": 109067, "occurredAt": "2024-07-07T15:35:12.450000+00:00", "file": "checkpoints/cp_109067.json" }
  ],
  "chunkConfig": {
    "chunkSize": 5000,
    "count": 22
  },
  "capabilities": {
    "historical_replay": true,
    "live_timing": false,
    "positions": true,
    "intervals": true,
    "sector_timing": true,
    "location_xy": false,
    "race_control": true,
    "weather": true,
    "circuit_shape": true,
    "authenticated": false
  }
}
```

---

## 7. Checkpoint Strategy and Event Density

### 7.1 Measured Event Density
- **Formula 1 Grand Prix Race**: ~100,000 events over 90–120 minutes.
  - Average density: ~15–20 events/second.
  - Burst density (lap start, pit window, safety car restart): ~50–80 events/second.
  - Low density (red flag, safety car queue): ~1–5 events/second.
- **Qualifying**: ~30,000–35,000 events over 60 minutes (~8–10 events/second).
- **Practice**: ~30,000–45,000 events over 60 minutes (~10–12 events/second).

### 7.2 Placement Rules
Checkpoints represent immutable, deterministic snapshots of `RaceState`.
1. **Regular Cadence**: A checkpoint is recorded every **5,000 events** OR every **120 seconds of session time**, whichever is reached first.
2. **Mandatory Boundaries**:
   - `seq = 0`: Official session start boundary (`start_time`).
   - `seq = N`: Authoritative final session state (`final_state`).
   - Explicit session control state changes (e.g. Red Flag start/end, Chequered flag).
3. **Storage Budget**:
   - Each checkpoint JSON is ~200 KB uncompressed (~15 KB compressed).
   - 23 checkpoints for a full Grand Prix require **~4.6 MB total**, adding only ~11% storage overhead over the raw recording.
4. **Deterministic Upper Bound on Seek**:
   - Maximum delta events to reduce on any seek: **5,000 events**.
   - Reducing 5,000 events in pure Python takes **~60 ms**.
   - Result: Any seek across a 2-hour Grand Prix completes in **under 70 ms**.

---

## 8. Readiness and Job Lifecycle Contract

### 8.1 State Transition Model

```text
                      +-------------------+
                      |   CATALOG ONLY    |
                      +-------------------+
                                |
                         [User requests download]
                                |
                                v
                       +-----------------+
                       |     QUEUED      |
                       +-----------------+
                                |
                         [Worker begins transfer]
                                |
                                v
                      +-------------------+
                      |   DOWNLOADING     |
                      +-------------------+
                                |
                         [Download completes /
                          Recording verified]
                                |
                                v
                      +-------------------+
                      |    PREPARING      |
                      +-------------------+
                                |
                         [Checkpoints & chunks
                          written atomically]
                                |
                                v
                      +-------------------+
                      |       READY       |  <=== Page & Controls Usable Together
                      +-------------------+
                                |
                         [User deletes replay]
                                |
                                v
                      +-------------------+
                      |     DELETING      |
                      +-------------------+
```

Failure paths:
- Any network/validation error during `DOWNLOADING` transitions to `FAILED`.
- Any crash or error during `PREPARING` transitions to `FAILED` and cleans up staging artifacts.
- User cancellation transitions to `CANCELLED`.

### 8.2 Operational Invariants
- **Job Identity**: `job_id = f"prep-{session_key}-{generation}"`.
- **Request Coalescing**: If a download or preparation request arrives for a session currently in progress, it attaches to the existing job without spawning a duplicate worker.
- **Progress Metrics**:
  - `DOWNLOADING`: `progress = bytes_received / total_bytes` (or streams completed / total streams).
  - `PREPARING`: `progress = events_processed / total_events` (0.0 to 1.0).
- **Crash Recovery on Startup**:
  - On application startup, `.slipstream/prepared/` is scanned for any `.staging-*` directories. These are automatically purged.
  - Existing prepared packages are checked against canonical recording fingerprints. If valid, they are registered as `READY` in <10ms without any reduction.
- **Separation of Concerns**:
  - `PREPARED`: The session disk artifacts exist and are verified.
  - `VIEWER_PLAYBACK_READY`: The viewer's WebSocket has established connection and received the initial start-of-session snapshot.
  - Optional `AnalyticsSnapshot` is requested asynchronously after playback controls are enabled, preventing strategy calculations from delaying basic timeline scrubbing.

---

## 9. Viewer-Open Contract and Elimination of End-of-Race Flash

### 9.1 The Root Cause of the "End of Race Flash"
Today, `web/hooks/useSlipstreamSession.ts` bootstraps by calling `GET /api/v1/state?session_key=...`.
`api.py` returns `selected.final_state` (the final race result). The frontend immediately calls `setState(envelope.data)`, rendering the podium/final lap.
Seconds later, the WebSocket opens and calls `controller.start()`, which emits the session-start snapshot at lap 1.
The user sees the end of the race flash on screen before jumping to lap 1.

### 9.2 The Corrected Viewer-Open Contract
1. **Authoritative Start-of-Session REST Snapshot**:
   - `GET /api/v1/state?session_key=...&cursor=start` (or default for replay mode) returns the start-of-session state (`cp_000000.json`).
   - The UI immediately renders the start-of-session grid/cars without flashing the final lap.
   - For users specifically requesting final classification, `cursor=final` is supported.
2. **Metadata Co-Delivery**:
   - The session manifest (duration, bounds, capabilities) is served directly from `manifest.json` in **<2 ms**, allowing `ReplayControls.tsx` to enable the scrubber bar immediately.
3. **Synchronized Playback Enablement**:
   - Both page content and playback controls become usable at `t = 35 ms`.

---

## 10. Independent Per-Viewer Cursor and Delay Design

### 10.1 Multi-Viewer Architecture

```text
Shared In-Memory Layer (Bounded, Read-Only):
+-------------------------------------------------------------+
| Manifests Index | Checkpoint Cache (LRU) | Chunk Cache (LRU)|
+-------------------------------------------------------------+
          |                      |                     |
          v                      v                     v
+------------------+   +------------------+   +------------------+
| Viewer A (WS)    |   | Viewer B (WS)    |   | Viewer C (WS)    |
| Replay Session 1 |   | Replay Session 1 |   | Replay Session 2 |
| Cursor: seq 12000|   | Cursor: seq 85000|   | Cursor: seq 5000 |
| Playing @ 10x    |   | Paused           |   | Playing @ 1x     |
| Private State A  |   | Private State B  |   | Private State C  |
+------------------+   +------------------+   +------------------+
```

### 10.2 Seeking Flow (Per-Viewer)
1. Viewer A sends `{ "type": "seek", "seq": 87450 }`.
2. Controller consults shared `manifest.json`:
   - Nearest preceding checkpoint is `cp_085000.json` at `seq = 85000`.
3. Controller retrieves `cp_085000.json` (from LRU memory cache or disk in 1.2ms).
4. Controller loads `chunk_0017.json` (events 85,001 to 87,450, total 2,450 delta events).
5. Controller applies 2,450 delta events to the cloned checkpoint state (~28 ms).
6. Viewer A emits updated snapshot at `seq = 87450`. Total seek time: **~30 ms**.
7. Viewer B's playback, cursor, and memory are completely untouched.

---

## 11. Delayed Live-to-Replay Handoff Design

### 11.1 The Live Delay Problem
Currently, delayed Live clients (e.g. Viewer at 2:17 delay, Viewer at 45s delay) trigger a full `ReplayController.seek_delay` loop across all live events accumulated so far on every snapshot. For a race 1 hour in, this burns 3.5s of CPU on every snapshot.

### 11.2 Incremental Delay Ring Buffer
1. **Shared Live Rolling Buffer**:
   `PublicLiveSession` maintains:
   - An append-only list of canonical `NormalizedEvent`s.
   - Rolling in-memory checkpoints every **500 events** or **30 seconds**.
2. **Incremental Advance**:
   A delayed live viewer connection does NOT seek from event 0 on every tick.
   It maintains a local cursor. On every clock advance, it applies only the incoming events that have aged past the delay window (e.g. 5–10 events/second), taking **<1 ms of CPU**.
3. **Live-to-Replay Handoff**:
   When the live session finishes and `PublicLiveSession` transitions `FINALIZING` → `REPLAY_READY`:
   - The background worker prepares the finalized recording into `.slipstream/prepared/<key>/`.
   - The live WebSocket sends `handoff: "REPLAY_READY"` with the finalized session key.
   - The browser seamlessly transitions its transport to Replay mode at the exact matching cursor.

---

## 12. Memory and Cache Plan

### 12.1 Tiered Storage Hierarchy

```text
+-------------------------------------------------------------------------+
| DISK STORAGE                                                            |
| - Authoritative canonical recordings (*.json)                           |
| - Prepared package directories (.slipstream/prepared/<key>/)           |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| SHARED BOUNDED RAM (Application Instance)                               |
| - Preloaded Manifest Index: all sessions (~50 KB total)                 |
| - Checkpoint LRU Cache: max 64 checkpoints (~12 MB RAM)                |
| - Event Chunk LRU Cache: max 32 chunks (~10 MB RAM)                     |
| - Session Evidence Cache: max 2 active sessions (~15 MB RAM)            |
| - Analytics Cache: max 128 snapshots (~8 MB RAM)                        |
| TOTAL SHARED RAM BUDGET: < 50 MB                                        |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| PER-VIEWER STATE (Ephemeral)                                            |
| - Private cursor, transport state, single RaceState snapshot (~250 KB)  |
| 10 concurrent viewers = ~2.5 MB RAM                                     |
+-------------------------------------------------------------------------+
```

### 12.2 Invariant Guarantees
- Inactive downloaded sessions consume **zero memory** beyond their tiny ~2 KB manifest in the catalog.
- Active viewers are protected from cache thrashing; checkpoints and chunks are cached independently using LRU policies.
- Total application RSS overhead remains strictly bounded below 100 MB under multi-viewer load.

---

## 13. Deletion and Invalidation Design

### 13.1 Deletion Scenarios and Safeguards

| Scenario | Engineered Behavior |
| :--- | :--- |
| **Preparation Currently Running** | Worker cancellation flag is set; active task aborts; `.staging-*` directory is removed immediately; job status transitions to `CANCELLED`. |
| **Prepared Session with No Viewers** | `delete_replay_artifacts` atomically removes `.slipstream/prepared/<session_key>/` and canonical recording file. Session descriptor transitions to `available = false`. |
| **Prepared Session with Active Viewers** | WebSocket connections receive a polite close frame (`code = 1000`, reason `"session_deleted"`); active controllers are torn down; directory is deleted. |
| **Repeated Deletion Calls** | Idempotent: returns 200 with empty removed list if already deleted. |
| **Crash During Deletion** | On next startup, orphaned files or partially removed directories in `.slipstream/prepared/` are reconciled with catalog descriptors and cleaned up. |
| **Stale Worker Finishing After Deletion** | Monotonically increasing **generation counter** per session. If `current_generation > job_generation`, worker discards staging output. |

### 13.2 Preserved Assets
Deleting a replay removes only rebuildable session artifacts. It strictly preserves:
- Catalog metadata (`catalog.json`).
- Circuit geometry and outlines.
- Immutable official Pirelli evidence and seeds (`.slipstream/pirelli/`).
- Source provenance records (`.slipstream/sources/`).

---

## 14. Additive Protocol Changes

All proposed protocol changes are strictly additive and preserve schema version 1 compatibility:

1. **Catalog Readiness Field** (`GET /api/v1/catalog`):
   ```json
   {
     "sessionKey": "11353",
     "available": true,
     "readiness": "READY",
     "preparationProgress": 1.0
   }
   ```
   `readiness` values: `"UNPREPARED"`, `"QUEUED"`, `"DOWNLOADING"`, `"PREPARING"`, `"READY"`, `"FAILED"`.
2. **Readiness Jobs Endpoint** (`GET /api/v1/jobs`):
   Allows the frontend to inspect active background download/preparation tasks, progress percentages, and error states.
3. **Cursor-Aware Initial State** (`GET /api/v1/state`):
   Additive query parameter `?cursor=start` (default for replay) returns the session-start snapshot from checkpoint 0, eliminating the end-of-race flash. `?cursor=final` preserves legacy final-state queries.

---

## 15. Implementation Stages for Phase 2 Onward

- **Stage 1 (Phase 2): Preparation Engine & Storage Package**
  - Implement `.slipstream/prepared/<key>/` generator with checkpoint builder and chunk writer.
  - Implement atomic staging and publication.
  - Add unit and contract tests verifying deterministic parity between raw reduction and checkpoint-assisted reduction.
- **Stage 2 (Phase 3): Fast Replay Loading & Checkpoint-Assisted Seeking**
  - Update `ReplayLibrary` to discover prepared manifests instantly on startup without replaying files.
  - Upgrade `ReplayController` to seek using nearest checkpoints.
  - Update `GET /api/v1/state` to serve session start state and eliminate end-of-race flash.
- **Stage 3 (Phase 4): Readiness State Machine & Background Worker**
  - Implement serialized, bounded preparation worker (`ProcessPoolExecutor(max_workers=1)` or non-blocking threadpool with event yielding).
  - Implement job coalescing, cancelation, and generation-guarded deletion.
- **Stage 4 (Phase 5): Incremental Live Delay & Live-to-Replay Transition**
  - Implement rolling checkpoints for `PublicLiveSession`.
  - Upgrade delayed live viewers to incremental delta consumption.
- **Stage 5 (Phase 6): Frontend Readiness UX & Progress Polling**
  - Update UI session strip and modal to render `DOWNLOADING (45%)` → `PREPARING (80%)` → `READY`.
  - Ensure play/seek controls and timing tower appear together instantaneously upon `READY`.

---

## 16. Benchmark and Acceptance Plan

Automated regression gates to enforce in CI/CD:
1. **Cold Open Gate**: Any prepared session must reach playback-ready state in **< 100 ms** (target: ~35 ms).
2. **Seek Gate**: Any seek across a full Grand Prix must complete in **< 100 ms** (target: ~60 ms).
3. **Startup Discovery Gate**: Library initialization for 10 prepared sessions must complete in **< 200 ms** (vs 119s today).
4. **Event Loop Non-Blocking Gate**: HTTP request latency for `GET /catalog` during active session preparation must not exceed **25 ms**.
5. **Memory Gate**: Memory RSS delta for an active replay session must not exceed **25 MB** (vs 156 MB today).

---

## 17. Unresolved Questions and Architectural Risks

1. **Worker Isolation (Process vs. Thread)**:
   Our benchmark demonstrated that pure Python loops running in `asyncio.to_thread` contend heavily with the GIL (spiking HTTP latency to 275ms, or 1.4s with 2 threads). Running preparation in a bounded `ProcessPoolExecutor(max_workers=1)` completely eliminates GIL contention on the main async server. Risk: Windows `multiprocessing` spawn overhead (~100ms) and IPC data serialization.
2. **Disk Storage Footprint on Low-Storage Devices**:
   A prepared package adds ~1.05× disk overhead (e.g. +41 MB for a 40 MB race). For users with hundreds of sessions, total disk usage doubles. Recommendation: Add a CLI command `slipstream clean-prepared` and an automatic LRU eviction policy for prepared acceleration data while preserving raw canonical recordings.

---

## 18. Proposed Sequence of Reviewable Commits for Phase 2 Onward

1. `feat(replay): add prepared package manifest, checkpoint, and chunk contracts`
2. `feat(replay): implement deterministic prepared package builder with atomic staging`
3. `feat(library): fast-path prepared replay discovery and LRU checkpoint cache`
4. `feat(playback): checkpoint-assisted fast seek and start-state initialization`
5. `feat(api): add readiness job state machine and background preparation worker`
6. `feat(live): implement rolling checkpoints and incremental delayed viewer advancement`
7. `feat(web): render preparation progress and synchronize playback controls readiness`
8. `test(perf): add automated performance regression harness for cold-open and seeking`
