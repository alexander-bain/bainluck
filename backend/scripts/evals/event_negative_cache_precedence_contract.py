"""Authority for positive/stale/negative event-concept cache precedence."""

from __future__ import annotations


def decide(*, positive: bool, negative: bool, stale: bool, build: str) -> dict[str, str]:
    if positive:
        return {"response": "positive", "write": "none"}
    if negative:
        return {"response": "404", "write": "none"}
    if build == "success":
        return {"response": "live", "write": "positive_and_stale_clear_negative"}
    if build in {"exception", "none"} and stale:
        return {"response": "stale", "write": "none"}
    if build == "none":
        return {"response": "404", "write": "negative"}
    if build == "exception":
        return {"response": "error", "write": "none"}
    raise ValueError(build)
