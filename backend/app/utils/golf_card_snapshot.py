"""The receipt that binds the progression table to the exact card it is quoting.

UX-P271 / CERT-746. UX-P270 made `GET /api/futures/{id}/progression` adopt the win
numbers `GET /api/golf` publishes, so that `/categories/golf` stops printing two
different probabilities for one golfer. CERT-746 withheld the token because
adopting *the card* and adopting *the card the browser is holding* are not the same
thing:

    `/api/golf` ships `public, max-age=300, stale-while-revalidate=60`, so the page
    can render a card response up to 360 s old out of an HTTP cache, while the
    progression request — which carries no `Cache-Control` at all — reads Redis at
    request time. If the hourly precompute lands in between, the card shows
    snapshot N and the table adopts snapshot N+1, and one golfer has two numbers
    again.

Both facts were re-measured against production rather than taken from the block:
`/api/golf` answers with `cache-control: public, max-age=300,
stale-while-revalidate=60`, and `/api/futures/{id}/progression` answers with no
`Cache-Control` header whatsoever.

UX-P270's page-side fingerprint cannot see this. It is computed from the card
response alone, so when the card is stale and the table is fresh the fingerprint is
perfectly stable — it is a hash of snapshot N either way — and no refetch is
triggered. A fingerprint over one of two clocks cannot detect that they disagree.

THE BIND. A snapshot is named by a receipt over its own contents, and the page
sends the receipt of the card it is actually holding. The endpoint then adopts
*that* snapshot rather than whatever Redis holds now, so the two numbers come from
the same bytes by construction, at any card age within the HTTP cache window.
Content-addressing rather than a counter is deliberate: two consecutive precomputes
that publish identical win numbers — the common case in a quiet market — produce
one receipt, so a client holding the older bytes still binds and no refetch is
spent proving that nothing moved.

WHAT MAKES IT IMMUTABLE. A receipt names its contents, so a registered snapshot can
never be rewritten to mean something else; a changed number is a different receipt
under a different key. The previous snapshot therefore stays readable for its whole
TTL after the next precompute overwrites the card key, which is precisely the
window CERT-746 named.

THE ONE RESIDUAL, STATED RATHER THAN HIDDEN. Redis here is a single ~100 MB LRU
shared with Celery, so a snapshot can be evicted before `SNAPSHOT_TTL_S` elapses.
An unresolvable receipt must not silently adopt a *different* snapshot — that is
the defect — so the endpoint echoes the receipt it actually applied and the page
converges on a mismatch by re-reading the card past its HTTP cache. Loud and
bounded, rather than quietly wrong.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Optional

# Non-decomposable letters that NFD normalization can't handle.
# Must be transliterated before NFD strip — used in `progression_name_key()`.
_MERGE_KEY_TRANSLITERATIONS = str.maketrans({
    "ø": "o", "Ø": "O",
    "đ": "d", "Đ": "D",
    "ł": "l", "Ł": "L",
    "æ": "ae", "Æ": "AE",
})

#: The field each tournament entry in the `GET /api/golf` payload is stamped with.
#: The page reads it and hands it back on the progression request; it is opaque to
#: the client, which is the point — the client never re-derives a name key, so no
#: second normalizer can drift from `progression_name_key`.
CARD_RECEIPT_FIELD = "win_receipt"

#: Registered snapshots are content-addressed under this prefix.
SNAPSHOT_KEY_PREFIX = "bainluck:golf:cardwin:"

# --- How long a registered snapshot has to stay resolvable --------------------
# Derived, not chosen. A card response reaching a browser can be this old:
#
#     the Redis card key's own TTL      (precompute_category_pages.CACHE_TTL)
#   + the HTTP freshness window         (http_cache_policy CACHE_RULES["/api/golf"])
#   + the stale-while-revalidate window (http_cache_policy, fixed at 60)
#
# so a snapshot must outlive that sum or the bind expires before the card does.
# `test_snapshot_ttl_outlives_every_card_a_browser_can_hold` asserts each mirror
# below still equals the constant it mirrors, and goes red the day one is raised.
CARD_CACHE_TTL_S = 7200
CARD_HTTP_MAX_AGE_S = 300
CARD_HTTP_SWR_S = 60
SNAPSHOT_TTL_S = CARD_CACHE_TTL_S + CARD_HTTP_MAX_AGE_S + CARD_HTTP_SWR_S


def progression_name_key(raw_name: str) -> str:
    """The name half of `_progression_merge_key`, callable on a bare string.

    Split out (UX-P270) so a participant row and a `GET /api/golf` card golfer —
    which is a name in a JSON payload, not a `FuturesOutcome` — can be keyed by
    the SAME normalizer instead of a second one written to look like it. That is
    not a theoretical concern: a hand-written normalizer built on NFD + combining
    marks joins 13 of 15 golfers on the worked tournament and silently drops both
    Højgaards, because `ø` has no combining-mark decomposition. This one
    transliterates it (`_MERGE_KEY_TRANSLITERATIONS`) and joins 15 of 15.

    Lives here rather than in `routes/futures.py` (UX-P271) because the receipt is
    computed over keys this produces, and a receipt whose normalizer could drift
    from the endpoint's would name a map the endpoint cannot apply.
    """
    name = raw_name or ""
    # Strip "Yes: " / "No: " prefixes (Kalshi format)
    name = re.sub(r"^(?:Yes|No)\s*[-:]\s*", "", name, flags=re.IGNORECASE)
    # Strip wrapping quotes (Polymarket NegRisk format)
    name = re.sub(r'^"(.*)"$', r"\1", name)
    # Convert "Last, First" to "First Last" (DataGolf format)
    comma_match = re.match(r"^(\w[\w'-]+),\s+(\w[\w'-]+.*)$", name, flags=re.UNICODE)
    if comma_match:
        name = f"{comma_match.group(2)} {comma_match.group(1)}"
    # Strip diacritics: transliterate non-decomposable letters first (ø→o, đ→d),
    # then NFD decomposition + remove combining marks for the rest (ü→u, é→e)
    name = name.translate(_MERGE_KEY_TRANSLITERATIONS)
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower().strip()
    # Remove Jr./Sr./III suffixes
    name = re.sub(r"\b(?:jr|sr|iii|ii|iv)\.?\b", "", name)
    # Remove non-alphanumeric (keep spaces)
    name = re.sub(r"[^a-z0-9\s]", "", name).strip()
    name = re.sub(r"\s+", " ", name)
    return f"name:{name}"


def card_win_map(tournament_entry: Any) -> dict[str, float]:
    """The win probabilities one `GET /api/golf` tournament entry publishes.

    The SINGLE definition of "what the card says", used to compute the receipt, to
    register the snapshot, and to apply it. If the receipt were computed over one
    reading of the payload and the adoption performed over another, the receipt
    would name numbers nobody serves.

    Skips anything malformed rather than raising: a single bad golfer entry must
    not cost the whole table its authority.
    """
    published: dict[str, float] = {}
    if not isinstance(tournament_entry, dict):
        return published
    for golfer in tournament_entry.get("golfers") or []:
        if not isinstance(golfer, dict):
            continue
        prob = golfer.get("probability")
        name = golfer.get("name")
        if not name or not isinstance(prob, (int, float)) or isinstance(prob, bool):
            continue
        published[progression_name_key(name)] = float(prob)
    return published


def card_win_receipt(win_map: dict[str, float]) -> str:
    """A stable content address for one tournament's published win numbers.

    Canonical (sorted keys, fixed separators, `repr`-free float encoding) so that
    the same numbers always produce the same receipt regardless of dict ordering,
    and so two processes — the worker that registers a snapshot and the web dyno
    that resolves one — cannot disagree about what a payload is called.
    """
    canonical = json.dumps(
        {k: float(v) for k, v in sorted(win_map.items())},
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def snapshot_key(receipt: str) -> str:
    """The Redis key one registered snapshot lives at."""
    return f"{SNAPSHOT_KEY_PREFIX}{receipt}"


def snapshot_body(tournament_name: Optional[str], win_map: dict[str, float]) -> str:
    """The registered value: the win map plus the tournament it belongs to.

    The tournament name is stored so that resolving a receipt can refuse a
    snapshot belonging to a DIFFERENT tournament. Without it, a receipt is a
    caller-supplied pointer into a shared namespace, and one page could make
    another tournament's numbers appear in its table.
    """
    return json.dumps(
        {"tournament": tournament_name or "", "wins": win_map},
        separators=(",", ":"),
        sort_keys=True,
    )


def stamp_card_payload(payload: Any) -> list[tuple[str, str]]:
    """Stamp every tournament entry with its receipt; return the snapshots to register.

    Mutates `payload` in place — each tournament entry gains
    `CARD_RECEIPT_FIELD` — and returns `(redis_key, redis_value)` pairs for the
    caller to write. Returning the writes rather than performing them keeps this
    function pure enough to test without Redis, and lets the sync worker and the
    async route each use their own client.

    A tournament with no publishable golfers is stamped `None` rather than with the
    receipt of the empty map: there is nothing to bind to, and an empty-map receipt
    would be shared by every such tournament.
    """
    writes: list[tuple[str, str]] = []
    if not isinstance(payload, dict):
        return writes
    for entry in payload.get("tournaments") or []:
        if not isinstance(entry, dict):
            continue
        win_map = card_win_map(entry)
        if not win_map:
            entry[CARD_RECEIPT_FIELD] = None
            continue
        receipt = card_win_receipt(win_map)
        entry[CARD_RECEIPT_FIELD] = receipt
        writes.append((snapshot_key(receipt), snapshot_body(entry.get("name"), win_map)))
    return writes


def resolve_snapshot(
    raw: Any, receipt: str, tournament_name: Optional[str]
) -> Optional[dict[str, float]]:
    """The win map a registered snapshot holds, or None if it cannot be trusted.

    Refuses — rather than guesses — when the stored bytes are unparseable, belong
    to a different tournament, or do not actually hash to the receipt they were
    filed under. The last check is what makes the address content-addressed in
    practice and not just in intent: a snapshot that does not reproduce its own
    receipt is treated as absent, and the caller falls back and says so.
    """
    if not raw or not receipt:
        return None
    try:
        body = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(body, dict):
        return None
    stored_tournament = body.get("tournament") or ""
    wins = body.get("wins")
    if not isinstance(wins, dict) or not wins:
        return None
    if tournament_name and stored_tournament and stored_tournament != tournament_name:
        return None
    try:
        win_map = {
            str(k): float(v)
            for k, v in wins.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        }
    except (TypeError, ValueError):
        return None
    if not win_map or card_win_receipt(win_map) != receipt:
        return None
    return win_map
