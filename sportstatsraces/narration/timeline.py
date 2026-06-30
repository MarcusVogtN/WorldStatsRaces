"""Sports timeline — direct reuse of the world-stats timeline builder.

The rank-1 crossover + curated big-mover logic is fully generic
(`races/narration/timeline.py::build_timeline`). Re-exported here so the
sports pipeline can import from a co-located module.
"""

from races.narration.timeline import build_timeline

__all__ = ["build_timeline"]
