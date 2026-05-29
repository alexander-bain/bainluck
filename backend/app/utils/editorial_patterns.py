"""
Shared editorial recall patterns for Discover feed.

These patterns identify "high-texture" culture/serendipity markets
(Taylor Swift, UFOs, etc.) that should always be recalled as Discover
candidates regardless of volume.

Extracted from routes/feed.py so polling tasks can precompute
the `is_editorial_recall` flag at ingest time instead of running
44 ILIKE scans on every feed request.
"""

# SQL-style ILIKE patterns (kept for backward compat with any
# remaining SQL usage).  The leading/trailing '%' mean "contains".
EDITORIAL_RECALL_PATTERNS: tuple[str, ...] = (
    "%aliens%",
    "%ufo%",
    "%extraterrestrial%",
    "%taylor swift%",
    "%bridesmaid%",
    "%bridesmaids%",
    "%wedding%",
    "%engaged%",
    "%engagement%",
    "%pregnant%",
    "%pregnancy%",
    "%beyonce%",
    "%kardashian%",
    "%xi jinping%",
    "%openai%",
    "%anthropic%",
    "%claude%",
    "%gpt%",
    "%gemini%",
    "%deepseek%",
    "%spacex%",
    "%starship%",
    "%best ai%",
    "%met gala%",
    "%attorney general%",
    "%fbi director%",
    "%save act%",
    "%recession%",
    "%eurovision%",
    "%oscars%",
    "%academy award%",
    "%grammy%",
    "%emmy%",
    "%survivor%",
    "%netflix%",
    "%spotify%",
    "%billboard%",
    "%rotten tomatoes%",
    "%hurricane%",
    "%earthquake%",
    "%wildfire%",
    "%outbreak%",
    "%pandemic%",
    "%hantavirus%",
)

# Pre-stripped lowercase tokens for fast Python `in` checks.
_EDITORIAL_RECALL_TOKENS: tuple[str, ...] = tuple(
    p.strip("%") for p in EDITORIAL_RECALL_PATTERNS
)


def matches_editorial_recall(name: str) -> bool:
    """Return True if *name* matches any editorial recall pattern (case-insensitive)."""
    lower = name.lower()
    return any(token in lower for token in _EDITORIAL_RECALL_TOKENS)
