"""Event-group matcher (group_type="event" foundation, slice 1) — #999 / L2-62.

Associates child source markets (individual matches/fights) to an event concept by
**entrant-set overlap**, NOT by name tokens or Kalshi ticker prefixes. L2-61 proved
those don't work: Kalshi tennis tickers encode tour+date+players (never the
tournament), and the date-window spans concurrent events (Challengers). The
discriminator that DOES work: a match belongs to the event iff BOTH its
competitors are in the event's entrant list (the winner-field market's outcomes) —
e.g. "Sabalenka vs Osaka" (both in the Wimbledon field) associates, while a
concurrent Challenger "Bertran vs Soto" (neither in the field) does not.

Pure + generic (any individual-competitor domain). Slice-1 computes the
association on the fly (no new table/migration); persistence/backfill is a later
optimization the design (§7) leaves open.
"""

from __future__ import annotations

import re

from app.utils.name_normalization import strip_diacritics

_VS_RE = re.compile(r"\s+(?:vs\.?|v\.?|def\.?|beats?)\s+", re.IGNORECASE)


def player_key(name: str | None) -> str:
    """Normalize a competitor name to a comparison key (diacritic-free surname).

    "Iga Świątek" -> "swiatek"; "Coco Gauff" -> "gauff"; "Sabalenka" -> "sabalenka".
    Uses the LAST whitespace token so a field's full name matches a match's
    surname-only form."""
    n = strip_diacritics((name or "").strip()).lower()
    n = re.sub(r"[^a-z0-9 ]", "", n)
    toks = n.split()
    return toks[-1] if toks else ""


def entrant_key_set(entrant_names) -> set[str]:
    """The event's entrant keys from the winner-field competitor names."""
    keys = set()
    for name in entrant_names or []:
        k = player_key(name)
        if k:
            keys.add(k)
    return keys


def extract_match_players(market_name: str | None) -> tuple[str, str] | None:
    """Parse a 'A vs B' match market into (keyA, keyB), or None if not a match."""
    if not market_name:
        return None
    # strip a trailing ": Set 1 Winner" / round suffix before splitting on vs
    base = re.split(r"[:\-—]", market_name)[0]
    parts = _VS_RE.split(base)
    if len(parts) != 2:
        return None
    a, b = player_key(parts[0]), player_key(parts[1])
    if not a or not b:
        return None
    return a, b


def market_in_event(market_name: str | None, entrant_keys: set[str]) -> bool:
    """True iff BOTH competitors of a match market are in the event's entrant set.

    This is the concurrent-tournament guard: a Challenger match in the same
    date-window whose players aren't in the slam draw returns False."""
    if not entrant_keys:
        return False
    players = extract_match_players(market_name)
    if players is None:
        return False
    a, b = players
    return a in entrant_keys and b in entrant_keys
