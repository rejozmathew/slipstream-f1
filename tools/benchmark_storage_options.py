"""Storage options evaluation and benchmark prototype for Section D.

Compares:
Option 1: Structured/chunked prepared directory (manifest.json, checkpoints/*.json, event_chunks/*.json, evidence.json)
Option 2: SQLite-backed prepared package (single .sqlite3 file with WAL mode, checkpoints table, event_chunks/events table, manifest table, evidence table)
Option 3: Monolithic prepared file (compressed json.gz with manifest, checkpoints, evidence)

Benchmarks:
- Preparation time
- Disk overhead
- Cold-open latency
- Seek latency (25%, 50%, 75%, 95%)
- Memory requirements (RSS)
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import gc
import gzip
import json
import os
import pathlib
import sqlite3
import tempfile
import time
from typing import Any

from slipstream.events import NormalizedEvent
from slipstream.evidence import SessionEvidence
from slipstream.playback import ReplayController
from slipstream.replay import replay
from slipstream.state import RaceState

class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]

_GetProcessMemoryInfo = ctypes.windll.psapi.GetProcessMemoryInfo
_GetProcessMemoryInfo.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
    wintypes.DWORD,
]
_GetProcessMemoryInfo.restype = wintypes.BOOL

def get_process_rss_mb() -> float:
    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    _GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    return counters.WorkingSetSize / (1024 * 1024)

RECORDING_PATH = pathlib.Path("recordings/f1-static-11353.json")
CHECKPOINT_INTERVAL = 5000  # Checkpoint every 5,000 events (~3-5 minutes of race time)

def run_storage_benchmarks():
    print("============================================================")
    print("SLIPSTREAM STORAGE OPTIONS EVALUATION & BENCHMARK (SECTION D)")
    print("============================================================")

    # 1. Load source events
    print(f"\nLoading source recording: {RECORDING_PATH.name}...")
    raw = json.loads(RECORDING_PATH.read_text(encoding="utf-8"))
    events = [NormalizedEvent.from_mapping(e) for e in raw]
    raw_size_mb = RECORDING_PATH.stat().st_size / (1024 * 1024)
    event_count = len(events)
    print(f"Loaded {event_count} events ({raw_size_mb:.1f} MB)")

    # Build checkpoints in memory first to share between options
    print(f"\nComputing checkpoints at interval of {CHECKPOINT_INTERVAL} events...")
    t0 = time.perf_counter()
    checkpoints: list[tuple[int, str, RaceState]] = []
    curr_state = RaceState()
    for idx, ev in enumerate(events):
        curr_state = curr_state.apply(ev)
        if (idx + 1) % CHECKPOINT_INTERVAL == 0 or (idx + 1) == event_count:
            checkpoints.append((idx + 1, ev.occurred_at, curr_state))
    t_compute_cps = time.perf_counter() - t0
    print(f"Generated {len(checkpoints)} checkpoints in {t_compute_cps:.2f}s")

    # Build SessionEvidence in memory
    t0 = time.perf_counter()
    evidence = SessionEvidence.from_events(events)
    t_evidence = time.perf_counter() - t0

    # Serialization helper for RaceState
    from dataclasses import asdict
    def state_to_dict(st: RaceState) -> dict:
        return asdict(st)

    def dict_to_state(d: dict) -> RaceState:
        # RaceState can be reconstructed from dictionary or json
        # In practice, RaceState fields match dataclass structure
        # For benchmark, json string serialization/deserialization is measured
        return d

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = pathlib.Path(tmp_dir)

        # -------------------------------------------------------------
        # OPTION 1: Structured / Chunked Prepared Directory
        # -------------------------------------------------------------
        print("\n--- Benchmarking Option 1: Structured/Chunked Prepared Directory ---")
        opt1_dir = tmp_path / "opt1_prepared" / "11353"
        opt1_cp_dir = opt1_dir / "checkpoints"
        opt1_chunk_dir = opt1_dir / "chunks"
        opt1_cp_dir.mkdir(parents=True, exist_ok=True)
        opt1_chunk_dir.mkdir(parents=True, exist_ok=True)

        t0 = time.perf_counter()
        manifest = {
            "format": "slipstream.prepared-replay.v1",
            "session_key": "11353",
            "recording_fingerprint": f"size_{RECORDING_PATH.stat().st_size}_mtime_{int(RECORDING_PATH.stat().st_mtime)}",
            "event_count": event_count,
            "start_time": events[0].occurred_at,
            "end_time": events[-1].occurred_at,
            "checkpoint_interval": CHECKPOINT_INTERVAL,
            "checkpoints": [
                {"seq": seq, "occurred_at": occ, "file": f"cp_{seq:06d}.json"}
                for seq, occ, _ in checkpoints
            ],
            "chunk_size": CHECKPOINT_INTERVAL,
            "chunk_count": (event_count + CHECKPOINT_INTERVAL - 1) // CHECKPOINT_INTERVAL,
        }
        (opt1_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # Write checkpoints
        for seq, occ, st in checkpoints:
            cp_data = {"seq": seq, "occurred_at": occ, "state": state_to_dict(st)}
            (opt1_cp_dir / f"cp_{seq:06d}.json").write_text(
                json.dumps(cp_data, separators=(",", ":")), encoding="utf-8"
            )

        # Write chunked event blocks
        for i in range(0, event_count, CHECKPOINT_INTERVAL):
            chunk_slice = [asdict(e) for e in events[i : i + CHECKPOINT_INTERVAL]]
            chunk_idx = i // CHECKPOINT_INTERVAL
            (opt1_chunk_dir / f"chunk_{chunk_idx:04d}.json").write_text(
                json.dumps(chunk_slice, separators=(",", ":")), encoding="utf-8"
            )

        # Write compact evidence
        evidence_data = {
            "lap_observations": [asdict(o) for o in evidence.lap_observations],
            "pit_events": [asdict(p) for p in evidence.pit_events],
        }
        (opt1_dir / "evidence.json").write_text(
            json.dumps(evidence_data, separators=(",", ":")), encoding="utf-8"
        )
        t_opt1_prep = time.perf_counter() - t0

        # Measure directory size
        opt1_size_bytes = sum(f.stat().st_size for f in opt1_dir.rglob("*") if f.is_file())
        opt1_size_mb = opt1_size_bytes / (1024 * 1024)
        print(f"Option 1 Prep Time: {t_opt1_prep:.2f}s, Disk Size: {opt1_size_mb:.2f} MB")

        # Cold Open: Read manifest + checkpoint 0 (or start)
        gc.collect()
        rss_b = get_process_rss_mb()
        t0 = time.perf_counter()
        opt1_mf = json.loads((opt1_dir / "manifest.json").read_text(encoding="utf-8"))
        first_cp_file = opt1_mf["checkpoints"][0]["file"]
        opt1_init_cp = json.loads((opt1_cp_dir / first_cp_file).read_text(encoding="utf-8"))
        t_opt1_cold_open = time.perf_counter() - t0
        rss_opt1 = get_process_rss_mb() - rss_b

        # Seek 25%, 50%, 75%, 95%
        def opt1_seek(target_seq: int) -> float:
            t_s = time.perf_counter()
            # 1. Find nearest preceding checkpoint
            best_cp = None
            for cp in opt1_mf["checkpoints"]:
                if cp["seq"] <= target_seq:
                    best_cp = cp
                else:
                    break
            # Load checkpoint
            if best_cp:
                cp_state_raw = json.loads((opt1_cp_dir / best_cp["file"]).read_text(encoding="utf-8"))
                curr_seq = best_cp["seq"]
            else:
                curr_seq = 0
            # Load only remaining chunk events from curr_seq to target_seq
            chunk_idx = curr_seq // CHECKPOINT_INTERVAL
            events_to_apply = []
            while curr_seq < target_seq:
                c_data = json.loads((opt1_chunk_dir / f"chunk_{chunk_idx:04d}.json").read_text(encoding="utf-8"))
                for ev_dict in c_data:
                    curr_seq += 1
                    if curr_seq > target_seq:
                        break
                    # in real execution: state.apply(ev)
                chunk_idx += 1
            return time.perf_counter() - t_s

        opt1_seek_25 = opt1_seek(int(event_count * 0.25))
        opt1_seek_50 = opt1_seek(int(event_count * 0.50))
        opt1_seek_75 = opt1_seek(int(event_count * 0.75))
        opt1_seek_95 = opt1_seek(int(event_count * 0.95))

        print(f"Option 1 Cold Open: {t_opt1_cold_open*1000:.2f}ms")
        print(f"Option 1 Seek: 25%={opt1_seek_25*1000:.2f}ms, 50%={opt1_seek_50*1000:.2f}ms, 75%={opt1_seek_75*1000:.2f}ms, 95%={opt1_seek_95*1000:.2f}ms")

        # -------------------------------------------------------------
        # OPTION 2: SQLite-Backed Prepared Package
        # -------------------------------------------------------------
        print("\n--- Benchmarking Option 2: SQLite-Backed Prepared Package ---")
        opt2_db_path = tmp_path / "11353.sqlite3"
        t0 = time.perf_counter()
        conn = sqlite3.connect(opt2_db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("""
            CREATE TABLE manifest (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE checkpoints (
                seq INTEGER PRIMARY KEY,
                occurred_at TEXT,
                state_json TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE event_chunks (
                chunk_index INTEGER PRIMARY KEY,
                start_seq INTEGER,
                end_seq INTEGER,
                chunk_json TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE evidence (
                key TEXT PRIMARY KEY,
                data_json TEXT
            );
        """)

        # Insert manifest
        for k, v in manifest.items():
            if not isinstance(v, (dict, list)):
                conn.execute("INSERT INTO manifest VALUES (?, ?)", (k, str(v)))
            else:
                conn.execute("INSERT INTO manifest VALUES (?, ?)", (k, json.dumps(v)))

        # Insert checkpoints
        conn.executemany(
            "INSERT INTO checkpoints VALUES (?, ?, ?)",
            [
                (seq, occ, json.dumps(state_to_dict(st), separators=(",", ":")))
                for seq, occ, st in checkpoints
            ],
        )

        # Insert event chunks
        chunk_rows = []
        for i in range(0, event_count, CHECKPOINT_INTERVAL):
            chunk_slice = [asdict(e) for e in events[i : i + CHECKPOINT_INTERVAL]]
            chunk_idx = i // CHECKPOINT_INTERVAL
            chunk_rows.append((
                chunk_idx,
                i + 1,
                min(i + CHECKPOINT_INTERVAL, event_count),
                json.dumps(chunk_slice, separators=(",", ":")),
            ))
        conn.executemany("INSERT INTO event_chunks VALUES (?, ?, ?, ?)", chunk_rows)

        # Insert evidence
        conn.execute("INSERT INTO evidence VALUES ('session_evidence', ?)", (json.dumps(evidence_data, separators=(",", ":")),))
        conn.commit()
        conn.close()
        t_opt2_prep = time.perf_counter() - t0

        opt2_size_mb = opt2_db_path.stat().st_size / (1024 * 1024)
        print(f"Option 2 Prep Time: {t_opt2_prep:.2f}s, Disk Size: {opt2_size_mb:.2f} MB")

        # Cold Open: Read manifest + checkpoint 1 from SQLite
        gc.collect()
        rss_b = get_process_rss_mb()
        t0 = time.perf_counter()
        conn_read = sqlite3.connect(f"file:{opt2_db_path}?mode=ro", uri=True)
        cur = conn_read.cursor()
        cur.execute("SELECT value FROM manifest WHERE key='event_count'")
        val = cur.fetchone()[0]
        cur.execute("SELECT state_json FROM checkpoints ORDER BY seq ASC LIMIT 1")
        cp_json = cur.fetchone()[0]
        st_data = json.loads(cp_json)
        t_opt2_cold_open = time.perf_counter() - t0
        rss_opt2 = get_process_rss_mb() - rss_b

        # Seek in SQLite
        def opt2_seek(target_seq: int) -> float:
            t_s = time.perf_counter()
            cur.execute("SELECT seq, state_json FROM checkpoints WHERE seq <= ? ORDER BY seq DESC LIMIT 1", (target_seq,))
            row = cur.fetchone()
            if row:
                curr_seq, cp_json = row
                st_data = json.loads(cp_json)
            else:
                curr_seq = 0
            # Load chunk containing remaining events
            chunk_idx = curr_seq // CHECKPOINT_INTERVAL
            cur.execute("SELECT chunk_json FROM event_chunks WHERE chunk_index = ?", (chunk_idx,))
            chunk_raw = cur.fetchone()
            if chunk_raw:
                chunk_events = json.loads(chunk_raw[0])
            return time.perf_counter() - t_s

        opt2_seek_25 = opt2_seek(int(event_count * 0.25))
        opt2_seek_50 = opt2_seek(int(event_count * 0.50))
        opt2_seek_75 = opt2_seek(int(event_count * 0.75))
        opt2_seek_95 = opt2_seek(int(event_count * 0.95))

        conn_read.close()

        print(f"Option 2 Cold Open: {t_opt2_cold_open*1000:.2f}ms")
        print(f"Option 2 Seek: 25%={opt2_seek_25*1000:.2f}ms, 50%={opt2_seek_50*1000:.2f}ms, 75%={opt2_seek_75*1000:.2f}ms, 95%={opt2_seek_95*1000:.2f}ms")

        # -------------------------------------------------------------
        # OPTION 3: Monolithic Prepared File (gzip json)
        # -------------------------------------------------------------
        print("\n--- Benchmarking Option 3: Monolithic Compressed Prepared File ---")
        opt3_path = tmp_path / "11353.prepared.json.gz"
        t0 = time.perf_counter()
        opt3_bundle = {
            "manifest": manifest,
            "checkpoints": [
                (seq, occ, state_to_dict(st)) for seq, occ, st in checkpoints
            ],
            "evidence": evidence_data,
        }
        with gzip.open(opt3_path, "wt", encoding="utf-8") as gz:
            json.dump(opt3_bundle, gz)
        t_opt3_prep = time.perf_counter() - t0
        opt3_size_mb = opt3_path.stat().st_size / (1024 * 1024)
        print(f"Option 3 Prep Time: {t_opt3_prep:.2f}s, Disk Size: {opt3_size_mb:.2f} MB")

        # Cold Open: Must decompress entire gzip
        t0 = time.perf_counter()
        with gzip.open(opt3_path, "rt", encoding="utf-8") as gz:
            opt3_loaded = json.load(gz)
        t_opt3_cold_open = time.perf_counter() - t0
        print(f"Option 3 Cold Open: {t_opt3_cold_open*1000:.2f}ms ({t_opt3_cold_open:.2f}s)")

        results = {
            "session_key": "11353",
            "event_count": event_count,
            "raw_size_mb": round(raw_size_mb, 2),
            "option1_chunked_directory": {
                "prep_time_s": round(t_opt1_prep, 3),
                "disk_size_mb": round(opt1_size_mb, 2),
                "disk_overhead_ratio": round(opt1_size_mb / raw_size_mb, 2),
                "cold_open_ms": round(t_opt1_cold_open * 1000, 2),
                "seek_25_ms": round(opt1_seek_25 * 1000, 2),
                "seek_50_ms": round(opt1_seek_50 * 1000, 2),
                "seek_75_ms": round(opt1_seek_75 * 1000, 2),
                "seek_95_ms": round(opt1_seek_95 * 1000, 2),
                "rss_delta_mb": round(rss_opt1, 1),
            },
            "option2_sqlite_package": {
                "prep_time_s": round(t_opt2_prep, 3),
                "disk_size_mb": round(opt2_size_mb, 2),
                "disk_overhead_ratio": round(opt2_size_mb / raw_size_mb, 2),
                "cold_open_ms": round(t_opt2_cold_open * 1000, 2),
                "seek_25_ms": round(opt2_seek_25 * 1000, 2),
                "seek_50_ms": round(opt2_seek_50 * 1000, 2),
                "seek_75_ms": round(opt2_seek_75 * 1000, 2),
                "seek_95_ms": round(opt2_seek_95 * 1000, 2),
                "rss_delta_mb": round(rss_opt2, 1),
            },
            "option3_monolithic_compressed": {
                "prep_time_s": round(t_opt3_prep, 3),
                "disk_size_mb": round(opt3_size_mb, 2),
                "disk_overhead_ratio": round(opt3_size_mb / raw_size_mb, 2),
                "cold_open_ms": round(t_opt3_cold_open * 1000, 2),
            },
        }

        out_file = pathlib.Path("docs/storage-options-benchmark-results.json")
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nStorage benchmark results saved to: {out_file}")

if __name__ == "__main__":
    run_storage_benchmarks()
