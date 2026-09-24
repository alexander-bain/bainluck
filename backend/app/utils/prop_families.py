"""Prop-family detection over a set of futures/prop markets.

A "prop family" is a set of markets that are the same real-world QUESTION
SHAPE about different entities.  The canonical examples:

* **"X Next Team"** — one market per player ("LeBron James Next Team",
  "Kevin Durant Next Team" → family ``next team``).
* **Award races** — one market/outcome per candidate ("NBA MVP",
  "Rookie of the Year" → family ``mvp`` / ``rookie of the year``).
* **Threshold ladders** — same entity, multiple thresholds ("Player X to
  score 30+ points", "... 40+ points" → family ``to score points``).

Families are detected by PATTERN EXTRACTION (normalise a title → family
key) plus an OPTIONAL cached-LLM hint (``market_metadata['prop_family']``) —
never a hardcoded list of families.  Emitting is per-entity: each family
carries one row per distinct entity (name-keyed until a Person entity
exists).

This module follows the style of ``app.utils.cross_source_matching`` and
``app.utils.sport_keys``: pure logic, no DB access, no network, no Celery.
It reuses ``cross_source_matching.normalize_question`` for entity keying.

Two data bugs are folded in (both covered by tests):

a. **Cross-source duplicate families** — the same entity's question can
   appear on both Kalshi and Polymarket (two "LeBron Next Team" rows).
   ``group_prop_families`` collapses these into a single row with merged
   sources, preferring the coherent/settled field per the
   ``find_cross_source_markets`` conventions.

b. **Settled props labelled live** — a settled prop (an outcome graded
   ``is_winner=True``, a resolved market, or a passed ``resolution_date``)
   is labelled settled / WHAT-HIT with a ``result`` label, never shown as a
   live 100% row.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

from app.utils.cross_source_matching import normalize_question

__all__ = [
    "family_key",
    "extract_entity",
    "group_prop_families",
    "cached_family_key",
    "resolve_family_key",
    "PROP_FAMILY_METADATA_KEY",
]

# ---------------------------------------------------------------------------
# Pattern vocabulary (data-driven, generic — NOT a list of families)
# ---------------------------------------------------------------------------

# Leading tokens dropped when deriving an award role / family key so that
# "NBA Defensive Player of the Year" and "Defensive Player of the Year"
# collapse to the same family.  Kept deliberately small — leagues, orgs,
# season/year tokens, and articles only.
_NOISE_PREFIX_TOKENS = {
    "the", "a", "an", "mens", "womens", "men", "women",
    "nba", "nfl", "mlb", "nhl", "wnba", "mls", "epl", "ncaa", "ncaaf",
    "ncaab", "pga", "lpga", "atp", "wta", "uefa", "fifa", "f1",
    "2023", "2024", "2025", "2026", "2027", "2028", "2029", "2030",
}

# The same thing as ``_NOISE_PREFIX_TOKENS``, but for venues that write the
# league as a PHRASE instead of an abbreviation.  Kalshi does not write "NBA" —
# it writes "Pro Basketball", two tokens, so the single-token set above can
# never pop it and "Pro Basketball Sixth Man of the Year" got its own family
# beside the bare "Sixth Man of the Year" (#6630).
#
# MEASURED, not guessed: a census of ``futures_markets WHERE name ILIKE 'Pro %'``
# returns exactly four leading heads — ``pro football`` (671), ``pro basketball``
# (131), ``pro baseball`` (80) and ``pro patria`` (8, the Italian CLUB Pro
# Patria, which is why this list is a closed enumeration and not a ``pro \w+``
# pattern).  ``pro hockey`` is the venue's unlisted NHL analogue, carried here so
# the next award season does not re-open this issue; it matches nothing today.
#
# Blast radius is one call site: :func:`_strip_noise_prefix` is reached ONLY
# from the "... of the year" arm of :func:`_parse`, on the role span.  The 500+
# non-award "Pro X" rows ("Pro Baseball: 105+ MPH Pitch", "Pro Baseball #1
# Overall Pick") never reach it.
_LEAGUE_PHRASE_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("pro", "basketball"),
    ("pro", "football"),
    ("pro", "baseball"),
    ("pro", "hockey"),
)

# Standalone award keywords → canonical family key.  Longest / most specific
# first so "cy young" is not shadowed by a broader match.
_STANDALONE_AWARDS: list[tuple[str, str]] = [
    ("defensive player of the year", "defensive player of the year"),
    ("comeback player of the year", "comeback player of the year"),
    ("most improved player", "most improved player"),
    ("sixth man of the year", "sixth man of the year"),
    ("coach of the year", "coach of the year"),
    ("manager of the year", "manager of the year"),
    ("rookie of the year", "rookie of the year"),
    ("player of the year", "player of the year"),
    ("cy young", "cy young"),
    ("ballon dor", "ballon dor"),
    ("ballon d or", "ballon dor"),
    ("heisman", "heisman"),
    ("finals mvp", "finals mvp"),
    # The award spelled out.  Without it "MLS: 2026 Most Valuable Player",
    # "PLL: 2026 Jim Brown Most Valuable Player" and "WBC: Most Valuable
    # Player" are not family-shaped AT ALL (#6630) — they key to None and
    # their candidates never group.  Safe to fold onto "mvp" only because
    # families are sport-scoped below: MLS is soccer, PLL lacrosse, WBC
    # baseball, so this cannot merge a soccer MVP into a basketball one.
    ("most valuable player", "mvp"),
    ("mvp", "mvp"),
    ("dpoy", "defensive player of the year"),
    ("roy", "rookie of the year"),
]

# Quantity verbs that introduce a threshold / total prop.
_QUANTITY_VERBS = (
    "score", "scores", "reach", "reaches", "hit", "hits", "record", "records",
    "pass", "passes", "throw", "throws", "rush", "rushes", "make", "makes",
    "have", "has", "get", "gets", "total", "totals", "register", "registers",
    "surpass", "surpasses", "exceed", "exceeds", "finish", "finishes",
    "win", "wins", "collect", "collects", "tally", "tallies",
)

# Descriptor tokens dropped when normalising a threshold metric so that
# "to score 30+ points" and "to score 40 or more points" collapse.
_DESC_STOPWORDS = {
    "or", "more", "less", "fewer", "plus", "than", "the", "a", "an", "of",
    "in", "and", "at", "least", "most", "over", "under", "this", "next",
}

#: Longest leading ``"<qualifier>: "`` head treated as a category prefix
#: rather than part of the subject ("NBA Free Agency" is three).
_MAX_QUALIFIER_WORDS = 4

#: A trailing possessive on an entity lifted from "X's Next Team" /
#: "Austin Reaves' Next Team" — both the ``'s`` and the bare apostrophe
#: forms, straight and curly.
_POSSESSIVE_SUFFIX_RE = re.compile(r"['’]s$|['’]$")

_NEXT_TEAM_RE = re.compile(r"^(?P<entity>.+?)\s+(?:next|new)\s+team\b")
_OF_THE_YEAR_RE = re.compile(r"\b(?P<role>[a-z][a-z ]*?)\s+of the year\b")
_WILL_WIN_RE = re.compile(r"^will\s+(?P<entity>.+?)\s+(?:win|wins|to win)\b")
_TO_WIN_RE = re.compile(r"^(?P<entity>.+?)\s+to\s+win\b")
_TO_VERB_RE = re.compile(
    r"^(?P<entity>.+?)\s+to\s+(?P<rest>(?:" + "|".join(_QUANTITY_VERBS) + r")\b.*)$"
)
_OVER_UNDER_RE = re.compile(r"\b(?:over|under)\b")
_NUM_RE = re.compile(r"\d[\d,\.]*\+?")
_GENERIC_OUTCOME_RE = re.compile(
    r"^(?:yes|no|over|under|tie|draw|other|field|none|neither|any)\b", re.I
)

# Optional cached-LLM family-key hint location.  An offline sweep may write
# ``market_metadata['prop_family'] = {'family_key': '...'}`` (mirrors the
# ``discover_llm`` metadata convention).  Never computed inside a request.
PROP_FAMILY_METADATA_KEY = "prop_family"

_LABEL_OVERRIDES = {
    "next team": "Next Team",
    "mvp": "MVP",
    "finals mvp": "Finals MVP",
    "cy young": "Cy Young",
    "heisman": "Heisman",
    "ballon dor": "Ballon d'Or",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _titlecase(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return None
    return cleaned.title()


def _strip_colon_qualifier(text: str) -> str:
    """Drop a leading ``"<qualifier>: "`` segment from an entity label.

    Venues prefix the CATEGORY, not the subject: "NBA: Jaylen Brown Next
    Team", "NBA Free Agency: Mitchell Robinson Next Team", "MLB: Mike Trout
    Next Team".  The subject is what follows the colon.  Bounded to a short
    head so a colon inside a sentence-shaped title cannot eat the entity.
    """
    head, sep, rest = text.partition(":")
    if not sep:
        return text
    rest = rest.strip()
    if not rest or len(head.split()) > _MAX_QUALIFIER_WORDS:
        return text
    return rest


def _clean_entity(raw: str | None, source_is_cased: bool) -> str | None:
    """Normalise an entity span lifted out of a market title.

    Three things, in order: collapse whitespace, drop a category qualifier
    ("NBA Free Agency: X" → "X"), drop a trailing possessive ("Jaylen
    Brown's" / "Austin Reaves'" → the player).  Casing is taken from the
    SOURCE when the source is cased — venues write "LeBron James", "CJ
    Abrams", "Robert Williams III", and ``str.title()`` destroys all three
    (and upper-cases after an apostrophe: "Jaylen Brown'S").  Only an
    all-lower or all-upper title is re-cased here.
    """
    if not raw:
        return None
    text = re.sub(r"\s+", " ", raw).strip()
    text = _strip_colon_qualifier(text)
    text = _POSSESSIVE_SUFFIX_RE.sub("", text).strip()
    if not text:
        return None
    return text if source_is_cased else _titlecase(text)


def _is_cased(text: str) -> bool:
    """True when the source string carries deliberate casing (mixed case) —
    an all-lower or SHOUTED title tells us nothing and gets title-cased."""
    return any(c.islower() for c in text) and any(c.isupper() for c in text)


def _entity_span(cleaned: str, low: str, match: re.Match, group: str = "entity") -> str | None:
    """The matched group taken from the ORIGINAL-cased string.

    ``low`` is ``cleaned.lower()``, which is length-preserving for every
    character the venues actually use, so the match offsets transfer.  If a
    lowercasing ever changes the length (a non-ASCII special case), fall
    back to the lowered group rather than slicing at the wrong offsets.
    """
    raw = (
        cleaned[match.start(group):match.end(group)]
        if len(cleaned) == len(low)
        else match.group(group)
    )
    return _clean_entity(raw, _is_cased(cleaned))


def _strip_noise_prefix(text: str) -> str:
    """Drop leading league/org/season noise from an award role span.

    Single tokens ("NBA", "2026") and multi-token league phrases ("Pro
    Basketball") both, interleaved, leading-anchored — a phrase is only noise
    at the FRONT, so "Dave Pietramala Defensive Player" keeps its whole name.

    🔴 The anchoring is load-bearing for the WNBA.  "Women's Pro Basketball
    Defensive Player of the Year" reaches here as ``s pro basketball defensive
    player`` — ``_OF_THE_YEAR_RE``'s role class excludes the apostrophe, so the
    span starts mid-word at ``s``.  ``s`` is not noise, the loop stops on it,
    and the women's award keeps a family of its own.  That is the CORRECT
    outcome and nothing else preserves it: the men's and women's markets both
    carry ``llm_sport_category='basketball'``, so the sport scope below cannot
    tell them apart.  Do not "clean up" that apostrophe artefact without first
    giving the scope a league discriminator — it is the only thing standing
    between the WNBA and NBA races sharing one card.
    """
    toks = text.split()
    while toks:
        if toks[0] in _NOISE_PREFIX_TOKENS:
            toks.pop(0)
            continue
        phrase = next(
            (p for p in _LEAGUE_PHRASE_PREFIXES if tuple(toks[: len(p)]) == p),
            None,
        )
        if phrase is None:
            break
        del toks[: len(phrase)]
    return " ".join(toks)


def _family_descriptor(text: str) -> str:
    """Normalise a threshold metric phrase: drop numbers/thresholds and
    stopwords, keep the metric words (e.g. "30+ points" → "points")."""
    text = _NUM_RE.sub(" ", text.lower())
    text = re.sub(r"[^a-z ]+", " ", text)
    toks = [t for t in text.split() if t and t not in _DESC_STOPWORDS]
    return " ".join(toks)


def _award_entity(low: str, cleaned: str) -> str | None:
    """Extract the subject of an award question when the market names one
    ("Will X win MVP" / "X to win MVP") — else None (candidate is in the
    outcome, e.g. a multi-outcome "NBA MVP" market)."""
    m = _WILL_WIN_RE.match(low)
    if m:
        return _entity_span(cleaned, low, m)
    m = _TO_WIN_RE.match(low)
    if m:
        return _entity_span(cleaned, low, m)
    return None


def _parse(market_name: str | None) -> tuple[str | None, str | None]:
    """Return ``(family_key, entity)`` for a market title.

    ``family_key`` is None when the title is not family-shaped.  ``entity``
    is the subject named in the TITLE (or None when the subject lives in the
    outcomes, e.g. a multi-candidate award market).
    """
    if not market_name:
        return None, None
    # ``cleaned`` keeps the venue's own casing; ``low`` is the matching
    # surface.  They are the same length, so a match on ``low`` addresses
    # the same span in ``cleaned`` (see :func:`_entity_span`).
    cleaned = re.sub(r"\s+", " ", market_name).strip().rstrip("?").strip()
    low = cleaned.lower()
    if not low:
        return None, None

    # 1. "<entity> Next Team"
    m = _NEXT_TEAM_RE.match(low)
    if m:
        entity = _entity_span(cleaned, low, m)
        return ("next team", entity) if entity else (None, None)

    # 2. Award: "... of the year"
    m = _OF_THE_YEAR_RE.search(low)
    if m:
        role_raw = m.group("role")
        # Drop any leading entity/verb clause ("Nikola Jokic to win rookie" ->
        # "rookie") so the family key is the award role, not the candidate.
        vm = re.search(r"\b(?:win|wins|for)\b\s+(.*)$", role_raw)
        if vm:
            role_raw = vm.group(1)
        role = _strip_noise_prefix(role_raw).strip()
        fk = f"{role} of the year" if role else "of the year"
        return fk, _award_entity(low, cleaned)

    # 3. Standalone awards (MVP, Cy Young, Heisman, ...)
    for kw, canon in _STANDALONE_AWARDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", low):
            return canon, _award_entity(low, cleaned)

    # 4. Threshold / total: "<entity> to <verb> N <unit>"
    m = _TO_VERB_RE.match(low)
    if m:
        entity = _entity_span(cleaned, low, m)
        desc = _family_descriptor(m.group("rest"))
        if entity and desc:
            return f"to {desc}", entity
        return None, None

    # 5. Over/Under threshold ladder: "<entity> Over/Under N <unit>"
    ou = _OVER_UNDER_RE.search(low)
    if ou and _NUM_RE.search(low):
        head_src = (cleaned if len(cleaned) == len(low) else low)[: ou.start()]
        head = head_src.strip()
        unit = _family_descriptor(low[ou.end():])
        entity = _clean_entity(head, _is_cased(cleaned)) if head else None
        fk = ("over under " + unit).strip()
        return fk, entity

    return None, None


def _is_generic_outcome(name: str | None) -> bool:
    n = (name or "").strip()
    if not n:
        return True
    if _GENERIC_OUTCOME_RE.match(n):
        return True
    if re.fullmatch(r"[\d,\.\+\s%$-]+", n):
        return True
    return False


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_resolution(resolution_date) -> datetime | None:
    if not resolution_date:
        return None
    try:
        if isinstance(resolution_date, str):
            dt = datetime.fromisoformat(resolution_date.replace("Z", "+00:00"))
        elif isinstance(resolution_date, datetime):
            dt = resolution_date
        else:
            return None
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _resolution_passed(resolution_date) -> bool:
    dt = _parse_resolution(resolution_date)
    return dt is not None and dt < datetime.now(timezone.utc)


def _settled_status(market: dict, outcome: dict | None) -> tuple[bool, str | None]:
    """Bug (b): decide the per-row settled flag + result label.

    A row is settled when its outcome is graded a winner, its market status
    is a terminal state, or its resolution date has passed.  A settled row
    must never be surfaced as a live 100% probability.
    """
    settled = False
    result: str | None = None

    if outcome is not None and outcome.get("is_winner"):
        settled = True
        result = "won"

    status = (market.get("status") or "").lower()
    if status in ("resolved", "settled", "closed", "completed"):
        settled = True

    if not settled and _resolution_passed(market.get("resolution_date")):
        settled = True

    if settled and result is None and outcome is not None and "is_winner" in outcome:
        result = "won" if outcome.get("is_winner") else "lost"

    return settled, result


def _market_row_prob(outcomes: list[dict]) -> tuple[float | None, str | None, dict | None]:
    """For a single-entity market, derive the representative probability.

    Prefers a "Yes" outcome (binary "Will X ...?" markets); otherwise uses
    the strongest (highest-probability) meaningful outcome and returns its
    name as ``top_outcome`` (e.g. the leading destination in a Next-Team
    market).  Also returns any graded winner outcome for settled labelling.
    """
    yes_outcome: dict | None = None
    winner: dict | None = None
    best: dict | None = None
    best_prob = -1.0
    for o in outcomes:
        p = _to_float(o.get("probability"))
        nm = (o.get("name") or "").strip().lower()
        if o.get("is_winner"):
            winner = o
        if nm == "yes":
            yes_outcome = o
        if p is not None and p > best_prob:
            best_prob = p
            best = o
    if yes_outcome is not None:
        return _to_float(yes_outcome.get("probability")), None, (winner or yes_outcome)
    if best is not None:
        return _to_float(best.get("probability")), best.get("name"), winner
    return None, None, winner


def _make_row(
    *,
    entity: str,
    market_id,
    outcome_id,
    probability: float | None,
    source: str,
    group_id,
    market: dict,
    settled: bool,
    result: str | None,
    top_outcome: str | None,
) -> dict:
    source = (source or "").lower()
    return {
        "entity": entity,
        "entity_key": normalize_question(entity or ""),
        "market_id": market_id,
        "outcome_id": outcome_id,
        "probability": probability,
        "source": source,
        "sources": [source] if source else [],
        "cross_source": {source: probability} if source else {},
        "group_id": group_id,
        "status": "settled" if settled else ((market.get("status") or "open").lower()),
        "settled": settled,
        "result": result,
        "top_outcome": top_outcome,
        # Internal, popped before the payload is emitted (like entity_key).
        "_resolves_at": _parse_resolution(market.get("resolution_date")),
    }


def _rows_for_market(market: dict, fk: str) -> list[dict]:
    name = market.get("name") or market.get("market_name") or ""
    source = (market.get("source") or "").lower()
    group_id = market.get("group_id")
    market_id = market.get("market_id", market.get("id"))
    outcomes = market.get("outcomes") or []
    _, entity_from_name = _parse(name)
    meaningful = [o for o in outcomes if not _is_generic_outcome(o.get("name"))]

    # One-entity market: the subject is named in the title (Next Team,
    # "X to win MVP", "X to score 30+ points").  Emit a single row.
    if entity_from_name:
        prob, top_outcome, winner = _market_row_prob(outcomes)
        settled, result = _settled_status(market, winner)
        return [
            _make_row(
                entity=entity_from_name, market_id=market_id, outcome_id=None,
                probability=prob, source=source, group_id=group_id, market=market,
                settled=settled, result=result, top_outcome=top_outcome,
            )
        ]

    # Multi-candidate market (award race): one row per meaningful outcome.
    if meaningful:
        rows = []
        for o in meaningful:
            settled, result = _settled_status(market, o)
            rows.append(
                _make_row(
                    entity=extract_entity(name, o.get("name")),
                    market_id=market_id, outcome_id=o.get("outcome_id", o.get("id")),
                    probability=_to_float(o.get("probability")), source=source,
                    group_id=group_id, market=market, settled=settled,
                    result=result, top_outcome=None,
                )
            )
        return rows

    # Fallback: single row keyed on the (stripped) market name.
    prob, top_outcome, winner = _market_row_prob(outcomes)
    settled, result = _settled_status(market, winner)
    return [
        _make_row(
            entity=extract_entity(name, None), market_id=market_id, outcome_id=None,
            probability=prob, source=source, group_id=group_id, market=market,
            settled=settled, result=result, top_outcome=top_outcome,
        )
    ]


def _merge_rows(group: list[dict]) -> dict:
    """Bug (a): collapse duplicate rows for the same entity across sources
    into ONE row, merging the source set + per-source probabilities.

    Coherence/settled preference mirrors ``find_cross_source_markets``:
    a settled ruling wins ("settled means settled"); otherwise the highest
    valid probability is taken as the primary field.
    """
    if len(group) == 1:
        return group[0]

    def prob_key(r: dict) -> float:
        p = r.get("probability")
        return p if p is not None else -1.0

    settled_won = [r for r in group if r.get("settled") and r.get("result") == "won"]
    settled_any = [r for r in group if r.get("settled")]
    if settled_won:
        # Among rows that AGREE the question is graded won, take the one whose
        # price says so most clearly (a graded winner reads 1.00; a stale book
        # left at 0.99 is the less coherent field).  Positional choice here
        # kept whichever source happened to be listed first — with the
        # Jaylen Brown pair that was Kalshi's 0.99, so a settled row printed
        # 99% beside its own WON badge.
        primary = max(settled_won, key=prob_key)
    elif settled_any:
        primary = max(settled_any, key=prob_key)
    else:
        primary = max(group, key=prob_key)

    merged = dict(primary)
    sources: list[str] = []
    cross: dict[str, float | None] = {}
    market_ids: list = []
    for r in group:
        for s in r.get("sources", []):
            if s and s not in sources:
                sources.append(s)
        cross.update(r.get("cross_source") or {})
        if r.get("market_id") is not None:
            market_ids.append(r["market_id"])
    merged["sources"] = sorted(sources)
    merged["cross_source"] = cross
    merged["merged_market_ids"] = market_ids

    if settled_won:
        merged.update({"settled": True, "status": "settled", "result": "won"})
    elif settled_any:
        merged["settled"] = True
        merged["status"] = "settled"
        if merged.get("result") is None:
            merged["result"] = primary.get("result")
    return merged


#: How long a settled row may sit in a family that is still being traded.
#: A family key is the question SHAPE, not the season, so last season's graded
#: award and this season's open one land in the same family — and
#: :func:`_merge_rows`'s "a settled ruling wins" then printed the Chiefs' MVP
#: card as "Patrick Mahomes OUT 100%" off Polymarket's 2024-season market
#: (resolved 2025-02-09) instead of the open 2026 market's 8.5% (#2311 after-
#: check, 2026-09-24).  Resolution-date GAPS cannot tell seasons apart: the
#: same open 2026 MVP question carries 2027-03-01 on Polymarket and 2028-02-12
#: on Kalshi (#2644).  AGE can: a question graded months ago while its family
#: still trades is a finished earlier question, not a venue lagging on the same
#: one — the settled-events backfill corrects a lagging Kalshi row within
#: hours (gotcha #33), so the merge's settled preference keeps its real case.
PRIOR_RESULT_MAX_AGE_DAYS = 90


def _drop_earlier_results(rows: list[dict], now: datetime | None = None) -> list[dict]:
    """Remove settled rows of an EARLIER question from a family still trading.

    Only bites when the family has at least one live row: an all-settled
    family is a results card and is left as it was.  A settled row with no
    resolution date cannot be aged and is kept.
    """
    if all(r.get("settled") for r in rows):
        return rows
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=PRIOR_RESULT_MAX_AGE_DAYS)
    return [
        r for r in rows
        if not (r.get("settled") and r.get("_resolves_at") and r["_resolves_at"] < cutoff)
    ]


def _collapse_cross_source(rows: list[dict]) -> list[dict]:
    groups: "OrderedDict[str, list[dict]]" = OrderedDict()
    for r in rows:
        groups.setdefault(r["entity_key"], []).append(r)
    return [_merge_rows(grp) for grp in groups.values()]


def _family_label(fk: str) -> str:
    if fk in _LABEL_OVERRIDES:
        return _LABEL_OVERRIDES[fk]
    return " ".join(
        w.upper() if w in ("mvp", "roy", "dpoy") else w.capitalize()
        for w in fk.split()
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def family_key(market_name: str) -> str | None:
    """Normalise a market/prop title into a family key, or None if the title
    is not family-shaped.

    Examples::

        family_key("LeBron James Next Team")     -> "next team"
        family_key("Kevin Durant Next Team")     -> "next team"
        family_key("NBA MVP")                    -> "mvp"
        family_key("Rookie of the Year")         -> "rookie of the year"
        family_key("Player X to score 30+ points") -> "to score points"
        family_key("Los Angeles Lakers")         -> None
    """
    return _parse(market_name)[0]


def extract_entity(market_name: str, outcome_name: str | None = None) -> str:
    """Return the per-row entity label (player / team / candidate).

    Prefers the subject named in the market TITLE ("LeBron James Next Team"
    → "Lebron James").  When the title names no subject (a multi-candidate
    award market), falls back to a non-generic outcome name, then to the
    raw title.
    """
    _, entity = _parse(market_name)
    if entity:
        return entity
    if outcome_name and not _is_generic_outcome(outcome_name):
        return re.sub(r"\s+", " ", outcome_name).strip()
    return re.sub(r"\s+", " ", (market_name or "")).strip()


def cached_family_key(market: dict) -> str | None:
    """OPTIONAL LLM hook: read a cached family-key hint written offline.

    An async/offline sweep may cache an LLM-derived family key under
    ``market_metadata['prop_family']['family_key']`` (or a top-level
    ``family_key_hint``).  This is consumed ONLY when present — it is never
    computed inside a request.  Returns None when no hint exists, so pattern
    extraction is used.
    """
    md = market.get("market_metadata")
    if isinstance(md, dict):
        pf = md.get(PROP_FAMILY_METADATA_KEY)
        if isinstance(pf, dict):
            fk = pf.get("family_key")
            if isinstance(fk, str) and fk.strip():
                return fk.strip().lower()
    hint = market.get("family_key_hint")
    if isinstance(hint, str) and hint.strip():
        return hint.strip().lower()
    return None


def resolve_family_key(market: dict) -> str | None:
    """Family key for a market dict — cached LLM hint first, then pattern."""
    name = market.get("name") or market.get("market_name") or ""
    return cached_family_key(market) or family_key(name)


def family_scope(market: dict) -> str | None:
    """The sport a market belongs to, or None when the venue never said.

    The family key is the QUESTION SHAPE and is deliberately sport-free, so
    two sports' awards land on it: production carries six live markets keyed
    ``defensive player of the year`` across basketball, football and the WNBA.
    This is the discriminator that keeps them apart — see
    :func:`_scoped_buckets` for when it is allowed to bite.
    """
    for field in ("sport", "llm_sport_category"):
        value = market.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def _scoped_buckets(
    fk: str, scoped_rows: list[tuple[str | None, dict]]
) -> list[tuple[str, str | None, list[dict]]]:
    """Split one family key's rows by sport — but only on a real disagreement.

    Returns ``(emitted_key, scope, rows)`` per bucket.

    A scope splits a family ONLY when two different sports are actually
    present.  When a family is single-sport — or the venue named no sport at
    all — this returns exactly one bucket carrying the BARE family key, so the
    served payload is byte-for-byte what it was.  That matters twice over:
    ``llm_sport_category`` is null on 793 of 541,777 served rows (0.15%), and
    an unconditional ``(sport, fk)`` key would have split every family that
    straddled one of those nulls into two cards — trading this bug for its
    mirror image.  It also keeps the emitted key UNIQUE per family, which the
    page relies on (``TeamPropFamilies.tsx`` uses it as its React key).

    In the genuine multi-sport case the rows that named no sport cannot be
    attributed to either side, so they stay their own bucket under the bare
    key rather than being guessed into the larger one.
    """
    scopes: list[str] = []
    for scope, _row in scoped_rows:
        if scope and scope not in scopes:
            scopes.append(scope)

    if len(scopes) <= 1:
        return [(fk, scopes[0] if scopes else None, [r for _s, r in scoped_rows])]

    buckets: "OrderedDict[str | None, list[dict]]" = OrderedDict()
    for scope, row in scoped_rows:
        buckets.setdefault(scope, []).append(row)
    return [
        (fk if scope is None else f"{scope}:{fk}", scope, rows)
        for scope, rows in buckets.items()
    ]


def group_prop_families(markets: list[dict]) -> list[dict]:
    """Group markets into prop families with per-entity rows.

    Each market dict should carry at least ``name`` (or ``market_name``),
    ``market_id`` (or ``id``), ``source``, ``group_id``, ``status``, and
    either ``outcomes`` (list of ``{name, probability, is_winner,
    outcome_id}``) or a market-level probability via its outcomes.  Optional:
    ``resolution_date`` and ``market_metadata`` (for the cached LLM hint).

    Returns a list of families::

        {
          "family_key": "next team",
          "label": "Next Team",
          "entity_count": 3,
          "sources": ["kalshi", "polymarket"],
          "rows": [ {entity, market_id, probability, source, sources,
                     cross_source, status, settled, result, ...}, ... ],
        }

    Only families with >= 2 DISTINCT entities are emitted (a single market
    is not a family).  Cross-source duplicate entity rows are collapsed
    (bug a); settled rows are labelled settled, not live (bug b).
    """
    families: "OrderedDict[str, list[tuple[str | None, dict]]]" = OrderedDict()
    for m in markets or []:
        if not isinstance(m, dict):
            continue
        fk = resolve_family_key(m)
        if not fk:
            continue
        scope = family_scope(m)
        for row in _rows_for_market(m, fk):
            families.setdefault(fk, []).append((scope, row))

    result: list[dict] = []
    buckets = [
        (emitted_key, fk, scope, rows)
        for fk, scoped_rows in families.items()
        for emitted_key, scope, rows in _scoped_buckets(fk, scoped_rows)
    ]
    for emitted_key, fk, scope, rows in buckets:
        merged = _collapse_cross_source(_drop_earlier_results(rows))
        distinct = {r["entity_key"] for r in merged if r.get("entity_key")}
        if len(distinct) < 2:
            continue

        # Settled rows sink below live rows; live rows by probability desc.
        merged.sort(
            key=lambda r: (
                bool(r.get("settled")),
                r.get("probability") is None,
                -(r.get("probability") or 0.0),
            )
        )
        for r in merged:
            r.pop("entity_key", None)
            r.pop("_resolves_at", None)

        result.append(
            {
                # The emitted key carries the scope ONLY when a sport actually
                # split this family, so it stays unique per card; the LABEL is
                # always derived from the bare key, because a reader is owed
                # "Defensive Player Of The Year", never "football:defensive…".
                "family_key": emitted_key,
                "label": _family_label(fk),
                "sport": scope,
                "entity_count": len(distinct),
                "sources": sorted({s for r in merged for s in r.get("sources", [])}),
                "rows": merged,
            }
        )

    result.sort(key=lambda f: -f["entity_count"])
    return result
