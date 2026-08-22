"""Official pre-race context acquisition boundary.

Official context must contain separately attributed source evidence. Automated
fetching/parsing is not reliable enough in Milestone 3.5, so this module never
returns plausible sample values. Manual structured ingestion remains the
supported future path through ``OfficialPreRaceContext``.
"""

from .context_types import OfficialPreRaceContext


def acquire_pirelli_context_spike(
    url: str, session_cutoff: str | None = None
) -> OfficialPreRaceContext | None:
    """Return no context rather than inventing an attributed Pirelli outlook."""
    _ = (url, session_cutoff)
    return None
