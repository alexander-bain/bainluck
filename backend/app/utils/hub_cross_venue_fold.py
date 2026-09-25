"""One question, one card: fold a hub section's Kalshi/Polymarket copies of one question (#8598).

The hub pools both venues' futures into one list and had no cross-venue fold, so
`/hub/esports` printed the same tournament question twice, side by side, with two
sets of numbers:

    TOURNAMENT WINNERS
        VALORANT Champions Shanghai Champion   (Kalshi)       Paper Rex 20% · 100 Thieves 16%
        VALORANT Champions 2026: Winner        (Polymarket)   Paper Rex 21% · 100 Thieves 15%
    AWARDS
        VALORANT Champions Shanghai MVP        (Kalshi)
        VALORANT Champions 2026 MVP            (Polymarket)

(production 2026-09-25, `sections.futures[14..15]`, `sections.awards[0,3]`). The
standing ruling is one number per question.

🔴 **WHY NOT `is_same_question`.** It refuses both pairs, correctly for a
matcher: one venue names the host city, the other the year, and the numeric
guard refuses "2026" against nothing. Discover's `_comparison_title` widening
cannot reach them either ("Shanghai" is still one side only). So this rule is
a stricter test the hub has the evidence for, and it takes SIX gates, all
required. A deduper that over-pairs deletes a card the reader wanted:

1. the venues differ — two listings from one venue are that venue's own call;
2. the same non-empty `canonical_market_key`. A BUCKET, not a question key
   (it holds the men's US Open beside the women's) — necessary, never enough;
3. both resolve within :data:`_MAX_RESOLUTION_GAP_DAYS` of each other — the
   same edition, and not the group stage beside the final;
4. the stated years agree, or one title states none. Two different years are
   two editions, always;
5. every word of the shorter title (years aside, "champion" read as "winner")
   is in the longer one. The longer side may add a qualifier ("Shanghai"); it
   may not differ ("Group A" vs "Group B", "Men's" vs "Women's", "Best
   Picture" vs "Best Cinematography" all fail here);
6. the two cards list the same field: at least :data:`_MIN_SHARED_NAMES`
   contender names in common, or, for a Yes/No card, the same outcome names.
   This is the row-level signal a title is only a candidate without (notice 40).
   It reads LISTED names, not only priced ones: a thin book can price two of a
   field and still name the rest.

🔴 **WHICH CARD STAYS: the one that prices more of its field.** A tie keeps the
earlier card. The Kalshi MVP book above prices two names (one off a zero bid,
#8210) where Polymarket prices four; keeping list order would keep the worse
card. Neither card's numbers are blended or changed; one is not drawn.

🔴 **SCOPED TO ONE SECTION**, like `grouped_field_legs`: this removes a
duplicate a reader meets inside one list. Fail-open: a row missing any input a
gate reads is kept.
"""

import re
from datetime import datetime
from typing import Any, Mapping

from app.utils.cross_source_matching import same_question_tokens

#: Gate 3. The two venues date one edition's close a day or two apart (Kalshi
#: 2026-10-19 02:00Z, Polymarket 2026-10-20 03:59Z for the pair above); the
#: group-stage rows of the same tournament close 18 days before its final.
_MAX_RESOLUTION_GAP_DAYS = 3

#: Gate 6. The VALORANT MVP pair shares three listed names (Asuna, xavi8k,
#: Cryocells) in its top ten; two different draws share none.
_MIN_SHARED_NAMES = 3

_YEAR_RE = re.compile(r"^(19|20)\d\d$")

#: Gate 5's one synonym. `same_question_tokens` already reads "winner" as
#: "win"; Kalshi calls the same side "Champion". The plural stays itself:
#: "Champions" is the tournament's NAME in "VALORANT Champions".
_TOKEN_SYNONYMS = {"champion": "win"}


def _parse_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _title_words(name: Any) -> tuple[frozenset[str], frozenset[str]] | None:
    """(years, words) of a title, or None when there is nothing to compare."""
    if not isinstance(name, str) or not name.strip():
        return None
    tokens = same_question_tokens(name)
    years = frozenset(t for t in tokens if _YEAR_RE.match(t))
    words = frozenset(_TOKEN_SYNONYMS.get(t, t) for t in tokens - years)
    return (years, words) if words else None


def _outcomes(row: Mapping[str, Any]) -> list[dict]:
    return [o for o in (row.get("top_outcomes") or ()) if isinstance(o, dict)]


def _listed_names(row: Mapping[str, Any]) -> frozenset[str]:
    return frozenset(
        str(o["name"]).strip().casefold()
        for o in _outcomes(row)
        if isinstance(o.get("name"), str) and o["name"].strip()
    )


def _priced_count(row: Mapping[str, Any]) -> int:
    return sum(1 for o in _outcomes(row) if o.get("probability") is not None)


def is_cross_venue_copy(a: Any, b: Any) -> bool:
    """Are `a` and `b` two venues' cards for ONE question? All six gates."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    source_a, source_b = a.get("source"), b.get("source")
    if not source_a or not source_b or source_a == source_b:
        return False
    key = a.get("canonical_market_key")
    if not key or key != b.get("canonical_market_key"):
        return False
    date_a, date_b = _parse_date(a.get("resolution_date")), _parse_date(
        b.get("resolution_date")
    )
    if date_a is None or date_b is None:
        return False
    try:
        gap_days = abs((date_a - date_b).total_seconds()) / 86400
    except TypeError:  # one naive, one aware — not comparable, keep both
        return False
    if gap_days > _MAX_RESOLUTION_GAP_DAYS:
        return False
    title_a, title_b = _title_words(a.get("name")), _title_words(b.get("name"))
    if title_a is None or title_b is None:
        return False
    (years_a, words_a), (years_b, words_b) = title_a, title_b
    if years_a and years_b and years_a != years_b:
        return False
    shorter, longer = sorted((words_a, words_b), key=len)
    if len(shorter) < 2 or not shorter <= longer:
        return False
    names_a, names_b = _listed_names(a), _listed_names(b)
    if not names_a or not names_b:
        return False
    if len(names_a) <= 2 and len(names_b) <= 2:
        return names_a == names_b
    return len(names_a & names_b) >= _MIN_SHARED_NAMES


def fold_cross_venue_copies(
    sections: Mapping[str, list] | None,
) -> dict[str, list]:
    """Return `sections` with each cross-venue duplicate pair drawn once.

    Per section, in order: a row that is a copy of a row already kept either
    replaces it in place (when it prices more of its field) or is dropped.
    Neither the mapping nor its lists are mutated — `build_hub`'s sections
    share list objects with a Redis-cached league payload (#3964).
    """
    folded: dict[str, list] = {}
    for name, rows in (sections or {}).items():
        kept: list = []
        for row in rows or []:
            twin_at = next(
                (i for i, k in enumerate(kept) if is_cross_venue_copy(k, row)), None
            )
            if twin_at is None:
                kept.append(row)
            elif _priced_count(row) > _priced_count(kept[twin_at]):
                kept[twin_at] = row
        folded[name] = kept
    return folded
