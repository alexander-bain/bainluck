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
from datetime import datetime, timezone

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


def _strip_noise_prefix(text: str) -> str:
    toks = text.split()
    while toks and toks[0] in _NOISE_PREFIX_TOKENS:
        toks.pop(0)
    return " ".join(toks)


def _family_descriptor(text: str) -> str:
    """Normalise a threshold metric phrase: drop numbers/thresholds and
    stopwords, keep the metric words (e.g. "30+ points" → "points")."""
    text = _NUM_RE.sub(" ", text.lower())
    text = re.sub(r"[^a-z ]+", " ", text)
    toks = [t for t in text.split() if t and t not in _DESC_STOPWORDS]
    return " ".join(toks)


def _award_entity(low: str) -> str | None:
    """Extract the subject of an award question when the market names one
    ("Will X win MVP" / "X to win MVP") — else None (candidate is in the
    outcome, e.g. a multi-outcome "NBA MVP" market)."""
    m = _WILL_WIN_RE.match(low)
    if m:
        return _titlecase(m.group("entity"))
    m = _TO_WIN_RE.match(low)
    if m:
        return _titlecase(m.group("entity"))
    return None


def _parse(market_name: str | None) -> tuple[str | None, str | None]:
    """Return ``(family_key, entity)`` for a market title.

    ``family_key`` is None when the title is not family-shaped.  ``entity``
    is the subject named in the TITLE (or None when the subject lives in the
    outcomes, e.g. a multi-candidate award market).
    """
    if not market_name:
        return None, None
    low = re.sub(r"\s+", " ", market_name.lower()).strip().rstrip("?").strip()
    if not low:
        return None, None

    # 1. "<entity> Next Team"
    m = _NEXT_TEAM_RE.match(low)
    if m:
        entity = _titlecase(m.group("entity"))
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
        return fk, _award_entity(low)

    # 3. Standalone awards (MVP, Cy Young, Heisman, ...)
    for kw, canon in _STANDALONE_AWARDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", low):
            return canon, _award_entity(low)

    # 4. Threshold / total: "<entity> to <verb> N <unit>"
    m = _TO_VERB_RE.match(low)
    if m:
        entity = _titlecase(m.group("entity"))
        desc = _family_descriptor(m.group("rest"))
        if entity and desc:
            return f"to {desc}", entity
        return None, None

    # 5. Over/Under threshold ladder: "<entity> Over/Under N <unit>"
    if _OVER_UNDER_RE.search(low) and _NUM_RE.search(low):
        parts = re.split(r"\b(?:over|under)\b", low, maxsplit=1)
        head = parts[0].strip() if parts else ""
        unit = _family_descriptor(parts[1]) if len(parts) > 1 else ""
        entity = _titlecase(head) if head else None
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


def _resolution_passed(resolution_date) -> bool:
    if not resolution_date:
        return False
    try:
        if isinstance(resolution_date, str):
            dt = datetime.fromisoformat(resolution_date.replace("Z", "+00:00"))
        elif isinstance(resolution_date, datetime):
            dt = resolution_date
        else:
            return False
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt < datetime.now(timezone.utc)
    except (ValueError, TypeError):
        return False


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
        primary = settled_won[0]
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
    families: "OrderedDict[str, list[dict]]" = OrderedDict()
    for m in markets or []:
        if not isinstance(m, dict):
            continue
        fk = resolve_family_key(m)
        if not fk:
            continue
        for row in _rows_for_market(m, fk):
            families.setdefault(fk, []).append(row)

    result: list[dict] = []
    for fk, rows in families.items():
        merged = _collapse_cross_source(rows)
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

        result.append(
            {
                "family_key": fk,
                "label": _family_label(fk),
                "entity_count": len(distinct),
                "sources": sorted({s for r in merged for s in r.get("sources", [])}),
                "rows": merged,
            }
        )

    result.sort(key=lambda f: -f["entity_count"])
    return result
