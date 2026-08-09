"""Oracle for Alex's volume -> movement -> unknown trading ladder."""

from __future__ import annotations


def classify(*, volume: float | None, snapshots: int, distinct_moves: int, min_snapshots: int, min_moves: int) -> dict[str, str]:
    if volume is not None:
        return {
            "classification": "traded" if volume > 0 else "untraded",
            "provenance": "volume_proven",
        }
    if snapshots < min_snapshots:
        return {"classification": "unknown", "provenance": "insufficient_density"}
    if distinct_moves >= min_moves:
        return {"classification": "traded", "provenance": "movement_inferred"}
    return {"classification": "untraded", "provenance": "movement_inferred"}
