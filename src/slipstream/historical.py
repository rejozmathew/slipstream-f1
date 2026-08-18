"""Automated Historical Context generation spike (v2.1 Phase F)."""

from typing import Any
from .context_types import HistoricalContext

def generate_historical_context_spike(season: int, circuit_id: str, local_archive_path: str) -> HistoricalContext:
    """Bounded spike for generating HistoricalContext from a local archive.
    
    This checks if Y-1 data exists for the given circuit_id. If so, it computes
    stop distributions, compound sequences, and stint lengths.
    """
    # For the spike, we mock the computation of historical data.
    # In a full implementation, this would load the archive, filter by circuit,
    # and compute the true historical distributions.
    if season <= 2020:
        return HistoricalContext(
            season=season,
            circuit_id=circuit_id,
            comparability="INCOMPATIBLE",
            source_note="No prior season data available in local archive (Spike)",
        )
        
    return HistoricalContext(
        season=season - 1,
        circuit_id=circuit_id,
        comparability="LIMITED" if season == 2026 else "NORMAL",
        stop_distribution={"1": 12, "2": 6},
        compound_sequences=("M-H", "S-H-M", "M-H-M"),
        stint_lengths={"M": {"median": 18, "max": 25}, "H": {"median": 35, "max": 42}},
        source_note="Generated from local archive (Spike)",
        evidence_cutoff=None,
    )
