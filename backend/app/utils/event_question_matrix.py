"""The Game / Series question matrix (#10238 → #10312): additive annotation.

PILLARS: MATCHING / FORMATTING / TRUTH. A reader browses Game and Series
questions with their real sides, units, periods and source evidence, and
finishing a Game does not finish an open Series.

This module builds two additive keys:

* ``game_question_matrix`` on ``GET /api/events/{id}/game-markets``, from the
  six FINAL served lists of ``_build_game_markets`` (``totals``,
  ``team_totals``, ``spreads``, ``period_markets``, ``matchups``, ``other``)
  plus the legs that function already loaded;
* ``series_question_matrix`` on ``GET /api/events/{id}/related-futures``, from
  the served ``series_markets`` card plus the legs it was built from.

Contract: ``10238.v1`` (Authority, frozen) with Live's riders R1–R6 and
Authority note A1, all binding. Section marks below (§4.2, R3 …) point into
that text.

Pure: no I/O, no provider query, no clock read. The route hands in its own
rows, its own loaded legs and its own decision functions — `_verdict_is_provable`,
`_pregame_mark_is_pregame`, the two period extractors, `_row_market_ids`,
`_settled_before_the_game` — so every decision the old card makes is asked
through the SAME function here and never re-spelled (CERT-2486). The
comparison object, the pin reader and the probability parser are #10236's,
imported, never copied (F4). Nothing built here flows back into any served
list, so every legacy key stays byte-identical.

🔴 WHAT THIS DOES NOT DO, ON PURPOSE. It never blends (U5 / R4: two rows that
type to one question are ``unblended_equivalents``, value null), never reads
``probability_change_24h``, ``movement``, ``opening_probability`` or
``last_updated``, never computes a complement, never renormalises a squeezed
field (F3: the display value is published and the raw leg sits beside it),
and never reads a Series clock (U2: every Series comparison is
``series_baseline_unsupported``).
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any, Callable, Iterable, Optional

from app.utils.event_props_matrix import _comparison, _finite_probability, pin_evidence
from app.utils.final_score_margin import _MARGIN_RE, _SPORT_SCORING_UNIT, _singular
from app.utils.market_shape import _DRAW_TOKENS, _TOP_N_RE, _norm, venue_leg_count
from app.utils.team_side import resolve_team_side

CONTRACT = "10238.v1"
COVERAGE_SCOPE = "rows_served_by_this_response"

# The server order of questions: source array first (§1), then market id, then key.
ARRAY_ORDER = (
    "totals",
    "team_totals",
    "spreads",
    "period_markets",
    "matchups",
    "other",
    "series_markets",
)

KINDS = ("count_threshold", "signed_handicap", "named_options", "rank_predicate")

# §4.4 — the closed untyped set, in the order a refused row is tested. A row
# is counted once, under the FIRST reason it hits.
UNTYPED_REASONS = (
    "untyped_period",
    "untyped_unit",
    "untyped_subject",
    "untyped_predicate",
)

# §6 — the two reasons 10238 adds to #10236's comparison set.
LEG_IS_COMPLEMENT = "leg_is_complement"
SERIES_BASELINE_UNSUPPORTED = "series_baseline_unsupported"

# Unit per sport family comes from `_SPORT_SCORING_UNIT` (singular); plural here.
_UNIT_PLURAL = {"goal": "goals", "run": "runs", "point": "points"}

_FULL_GAME_TYPES = ("game_total", "team_total", "spread")
_PERIOD_TYPES = (
    "half_total", "quarter_total", "half_spread", "quarter_spread",
    "half_winner", "quarter_winner",
)
_COUNT_PERIOD_TYPES = ("half_total", "quarter_total")
_HANDICAP_PERIOD_TYPES = ("half_spread", "quarter_spread")

# §4.3 period table: the served ticker label → period key / label.
_PERIOD_BY_LABEL = {
    "1H": ("half_1", "1st half"),
    "2H": ("half_2", "2nd half"),
    "1Q": ("quarter_1", "1st quarter"),
    "2Q": ("quarter_2", "2nd quarter"),
    "3Q": ("quarter_3", "3rd quarter"),
    "4Q": ("quarter_4", "4th quarter"),
}
_FULL_GAME = ("full_game", "Game")
_FIRST_FIVE = ("first_5_innings", "First 5 innings")
_FIRST_HALF_NAME_RE = re.compile(r"1st half|first half|\b1h\b")
_FIRST_FIVE_NAME_RE = re.compile(r"first 5|1st 5")

# §4.1 signed handicap: exactly one signed number in the leg name.
_SIGNED_NUMBER_RE = re.compile(r"[+-]\d+(?:\.\d+)?")

# A4 — THE UNIT IS PROVEN BY THE MARKET'S OWN NAME, NEVER BY THE SPORT ALONE.
#
# The route classifies `Pro Baseball All-Star Game: Total Home Runs` as a
# `game_total` and its 2.5 line sits inside baseball's band, so a unit read off
# the sport would label it "3+ runs"; `Total Cards O/U 4.5` would read "5+
# goals" and `Corners Handicap` "-1.5 goals". So a typed question's unit is
# admitted only when the stored market name (the segment after its last `:`)
# says it, in one of the spellings below, and the noun is the sport's own
# scoring unit. Each spelling is pinned to a real retained market name in
# `test_event_question_matrix_10238.py::TestEveryAdmittedSpelling` (A3); a
# spelling with no retained name is not admitted (`: Goals` as a team stat
# segment, `Puck Line`).
#
# A period token the §4.3 table reads, as it leads a market-name segment.
_PERIOD_TOKEN = (
    r"(?:(?:1st|2nd|first|second)\s+half|[12]h"
    r"|(?:1st|2nd|3rd|4th)\s+quarter|[1-4]q"
    r"|(?:1st|first)\s+5(?:\s+innings)?)"
)
# count: `Total Points` / `Team Total Runs` / `Total Goals` ending the segment.
_TOTAL_PHRASE_RE = re.compile(
    r"\btotal\s+(points|runs|goals)(?:\s+o/u\s+\d+(?:\.\d+)?)?\s*$"
)
_TOTAL_PHRASE_NOUNS = ("points", "runs", "goals")
# count: a team-total stat segment that is exactly the unit (`Cubs at Cardinals: Runs`).
_TEAM_SEGMENT_NOUNS = ("points", "runs")
# count: the bare over/under shape (`Cardinals vs. Reds: O/U 10.5`), which names
# no stat at all, so the scoring unit is the only thing it can count.
_BARE_OU_RE = re.compile(rf"^(?:{_PERIOD_TOKEN}\s+)?o/u\s+\d+(?:\.\d+)?$")
# signed handicap: the bare handicap noun, after a leading period token and a
# trailing line are stripped (`1st Half Spread`, `First 5 Spread`, `Handicap -1.5`).
_HANDICAP_NOUNS = ("spread", "run line", "handicap")
_LEADING_PERIOD_RE = re.compile(rf"^{_PERIOD_TOKEN}\s+")
_TRAILING_LINE_RE = re.compile(r"\s*[+-]?\d+(?:\.\d+)?$")

# A5 — THE TWO SPELLINGS THAT NAME NO STAT MUST NAME THE GAME. A bare
# `O/U <line>` or a bare `Spread` says nothing about WHAT is counted, and the
# stat can sit before the last `:` (`Utah State Total Receptions: O/U 19.5` is
# a real retained name, a `game_total` inside football's band). So those two
# spellings prove the unit only when everything before the last `:` is this
# event's matchup: exactly one separator, and each side's words a subset of a
# DIFFERENT team's. That is proof the prefix names the game, not a denylist of
# stat nouns.
_MATCHUP_SEPARATOR_RE = re.compile(r"\s(?:vs\.|vs|v|at|@)\s")
_WORD_RE = re.compile(r"\w+")

# The Series card caps each market at ten legs (`outcomes_list[:10]`); §7
# lists missing legs only at or below that size and never calls a capped
# array complete.
_LIST_CAP = 10


def question_market_facts(market: Any) -> dict:
    """G0 / A1 — the facts the matrix reads off one market, taken in the route's
    plain-list pass before any commit boundary (gotcha #6). ``market_metadata``
    is read through ``__dict__`` the way the file's other pre-commit snapshots
    are, so an expired row reads as absent rather than lazy-loading."""
    return {
        "name": market.name,
        "external_id": market.external_id,
        "status": market.status,
        "mutually_exclusive": market.mutually_exclusive,
        "market_metadata": market.__dict__.get("market_metadata"),
    }


# ── small readers ────────────────────────────────────────────────────────────


def _meta(facts: Optional[dict]) -> dict:
    meta = (facts or {}).get("market_metadata")
    return meta if isinstance(meta, dict) else {}


def _status(facts: Optional[dict]) -> Optional[str]:
    status = (facts or {}).get("status")
    return status if isinstance(status, str) else None


def _round4(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 4)


def _raw(leg: Any) -> Optional[float]:
    """The loaded leg's own stored price, ``None`` when absent (0.0 is real)."""
    return None if leg is None else _finite_probability(leg.current_probability)


def _leg_reads_under(name: Optional[str]) -> bool:
    """Is this totals leg an UNDER leg published on its sibling's OVER axis (F2)?

    This is the route's own test, spelled where it builds every totals row
    (`_build_game_markets`, the `game_total`/`team_total` branch): ``is_under
    and not is_over``. The route keeps the answer in a local and never puts it
    on the served row, so it is read again here from the same stored name with
    the same expression; ``test_event_question_matrix_10238.py`` pins the two
    against each other on the served payload.
    """
    name_lower = (name or "").lower().strip()
    is_over = (
        name_lower.startswith("over")
        or "yes" in name_lower
        or re.match(r"^\d+\+", name_lower)
    )
    is_under = name_lower.startswith("under") or name_lower == "no"
    return bool(is_under and not is_over)


def _axis_label(entry: dict) -> Optional[str]:
    """F2 — the option label names the axis its published value is on.

    A totals row built from an UNDER leg publishes its sibling's OVER axis, but
    its served name is still the under leg's own ("Under", "No"). Copied
    verbatim it labels the over value as the under one: "8+ runs · Under 41%"
    where 41% is the chance of 8 or more, and "Over 57% / Under 57%" side by side
    on a team total. Rows the route does not invert keep their served name.
    """
    label = entry["label"]
    if not entry["total_axis"] or not _leg_reads_under(label):
        return label
    stripped = label.strip()
    if stripped.lower() == "no":
        return "Yes"
    return "Over" + stripped[len("under"):]


def _is_half_line(threshold: Any) -> bool:
    """A line of the form k.5 with k ≥ 0 — non-integer, so no push (§4.1)."""
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        return False
    t = float(threshold)
    return math.isfinite(t) and t >= 0 and t - math.floor(t) == 0.5


def _team_name(side: str, home_team: Optional[str], away_team: Optional[str]) -> Optional[str]:
    return home_team if side == "home" else away_team if side == "away" else None


def _last_segment(market_name: Optional[str]) -> str:
    return " ".join(str(market_name or "").rsplit(":", 1)[-1].split()).lower()


def _prefix_is_the_matchup(
    market_name: Optional[str], home_team: Optional[str], away_team: Optional[str],
) -> bool:
    """A5: is everything before the market name's last `:` this event's game?"""
    name = str(market_name or "")
    if ":" not in name:
        return False
    prefix = name.rsplit(":", 1)[0].lower()
    parts = _MATCHUP_SEPARATOR_RE.split(prefix)
    if len(parts) != 2:
        return False
    home = set(_WORD_RE.findall((home_team or "").lower()))
    away = set(_WORD_RE.findall((away_team or "").lower()))
    left, right = (set(_WORD_RE.findall(part)) for part in parts)
    if not (left and right and home and away):
        return False
    return (left <= home and right <= away) or (left <= away and right <= home)


def _count_unit_proven(
    market_name: Optional[str], unit: str, home_team: Optional[str], away_team: Optional[str],
) -> bool:
    """A4: does the stored market name say this count is in ``unit``?"""
    segment = _last_segment(market_name)
    plural = _UNIT_PLURAL.get(unit)
    match = _TOTAL_PHRASE_RE.search(segment)
    if match is not None:
        return match.group(1) == plural and plural in _TOTAL_PHRASE_NOUNS
    if segment == plural:
        return plural in _TEAM_SEGMENT_NOUNS
    return (
        _BARE_OU_RE.match(segment) is not None
        and _prefix_is_the_matchup(market_name, home_team, away_team)
    )


def _handicap_unit_proven(
    market_name: Optional[str], home_team: Optional[str], away_team: Optional[str],
) -> bool:
    """A4: is the market a bare handicap on the scoring unit, with no other
    stat noun (`Corners Handicap` is not)? A5: and is it this game's?"""
    segment = _TRAILING_LINE_RE.sub("", _LEADING_PERIOD_RE.sub("", _last_segment(market_name)))
    return segment in _HANDICAP_NOUNS and _prefix_is_the_matchup(market_name, home_team, away_team)


def _period(
    market_type: Optional[str],
    served_period: Optional[str],
    facts: Optional[dict],
    sport_prefix: Optional[str],
    period_from_ticker: Callable[[Optional[str]], Optional[str]],
    period_from_name: Callable[[str, str], Optional[str]],
    leg_name: Optional[str] = None,
) -> Optional[tuple[str, str]]:
    """§4.3's period table, or ``None`` when the evidence names no period.

    A4: a full-game type is ``full_game`` only when neither the market's name
    NOR the leg's own name states a period — `Boston Celtics -3.5 1st half`
    on a market called `Spread` is not a full-game line."""
    name = (facts or {}).get("name") or ""
    lname = name.lower()
    baseball = sport_prefix == "baseball"
    if baseball and _FIRST_FIVE_NAME_RE.search(lname):
        return _FIRST_FIVE
    if market_type in _FULL_GAME_TYPES:
        return _FULL_GAME if period_from_name(name, leg_name or "") is None else None
    if market_type in _PERIOD_TYPES and not baseball:
        ticker_label = period_from_ticker((facts or {}).get("external_id"))
        if ticker_label in _PERIOD_BY_LABEL:
            return _PERIOD_BY_LABEL[ticker_label]
        if served_period == "1H" and _FIRST_HALF_NAME_RE.search(lname):
            return _PERIOD_BY_LABEL["1H"]
    return None


def _period_obj(period: Optional[tuple[str, str]]) -> Optional[dict]:
    return None if period is None else {"key": period[0], "label": period[1]}


def _quantity(unit: str) -> dict:
    plural = _UNIT_PLURAL.get(unit, unit + "s")
    return {"key": plural, "singular": unit, "plural": plural, "integer": True}


def _named_sides(
    legs: list,
    mutually_exclusive: Any,
    matchup_type: Optional[str],
    home_team: Optional[str],
    away_team: Optional[str],
) -> dict:
    """§4.3 — each loaded leg's side, keyed by outcome id, when PROVEN.

    Read off the stored names of every leg the route loaded for the market,
    never the served subset, so a missing leg can carry its proven side too.
    Unproven legs are ``category`` (or ``contender`` for a matchup). No side is
    ever read from the strings "Home"/"Away", from price or from order.
    """
    if matchup_type == "3ball":
        return {leg.id: "contender" for leg in legs}
    resolved = {leg.id: resolve_team_side(leg.name, home_team, away_team) for leg in legs}
    if len(legs) == 3 and mutually_exclusive is True:
        draws = [leg.id for leg in legs if _norm(leg.name) in _DRAW_TOKENS]
        homes = [lid for lid, side in resolved.items() if side == "home" and lid not in draws]
        aways = [lid for lid, side in resolved.items() if side == "away" and lid not in draws]
        if len(draws) == 1 and len(homes) == 1 and len(aways) == 1:
            return {draws[0]: "draw", homes[0]: "home", aways[0]: "away"}
    if len(legs) == 2:
        sides = list(resolved.values())
        if None not in sides and sides[0] != sides[1]:
            return dict(resolved)
    fallback = "contender" if matchup_type == "h2h" else "category"
    return {leg.id: fallback for leg in legs}


def _three_way_proven(sides: dict) -> bool:
    return sorted(sides.values()) == ["away", "draw", "home"]


def _completeness(
    *,
    returned: int,
    loaded: int,
    declared: Optional[int],
    meta: dict,
    three_way: bool,
) -> Optional[bool]:
    """§7: ``True`` only with an exhaustive proof and nothing held back; ``False``
    when something is provably held back; otherwise unknown. A capped array
    never claims complete."""
    if returned < loaded or (declared is not None and declared > loaded) or loaded > _LIST_CAP:
        return False
    if returned != loaded:
        return None
    shape = meta.get("shape") if isinstance(meta.get("shape"), dict) else {}
    if (
        declared == loaded
        or (shape.get("exhaustive") is True and shape.get("outcome_count") == loaded)
        or three_way
    ):
        return True
    return None


def _lifecycle(won_any: bool, statuses: list) -> dict:
    """§6 — from the question's OWN market(s), never the event."""
    distinct = set(statuses)
    market_status = statuses[0] if len(distinct) == 1 else None
    if won_any:
        state = "settled"
    elif distinct == {"open"}:
        state = "open"
    elif "suspended" in distinct:
        state = "suspended"
    else:
        state = "unknown"
    return {"state": state, "market_status": market_status}


def _source_totals(options: list) -> list:
    """§4.2 — per source, only when EVERY returned option carries that source's
    raw value. The client never sums."""
    if not options:
        return []
    per_option: list[dict] = []
    for option in options:
        by_source: dict = {}
        for ev in option["source_evidence"]:
            if ev["raw_probability"] is None or not ev.get("source"):
                continue
            by_source.setdefault(ev["source"], []).append(ev["raw_probability"])
        per_option.append(by_source)
    common = set(per_option[0])
    for by_source in per_option[1:]:
        common &= set(by_source)
    out = []
    for source in sorted(common):
        values = [v for by_source in per_option for v in by_source[source]]
        out.append({"source": source, "raw_sum": round(sum(values), 4), "legs": len(values)})
    return out


def _unavailable(reason: str) -> dict:
    return {
        "state": "unavailable",
        "reason": reason,
        "baseline": None,
        "latest": None,
        "delta_points": None,
    }


def _empty_coverage() -> dict:
    return {
        "scope": COVERAGE_SCOPE,
        "questions": 0,
        "options": 0,
        "by_kind": {k: 0 for k in KINDS if k != "named_options"},
        "untyped": {r: 0 for r in UNTYPED_REASONS},
        "build_errors": 0,
    }


def _finish(display_scope: str, questions: list, coverage: dict, series_count: Optional[dict]) -> Optional[dict]:
    if not questions:
        return None
    questions.sort(
        key=lambda q: (
            ARRAY_ORDER.index(q["source_array"]),
            min(q["_market_ids"]) if q["_market_ids"] else 0,
            q["question_key"],
        )
    )
    for q in questions:
        q.pop("_market_ids", None)
        if q["kind"] != "named_options":
            coverage["by_kind"][q["kind"]] += 1
    coverage["questions"] = len(questions)
    coverage["options"] = sum(len(q["options"]) for q in questions)
    return {
        "contract": CONTRACT,
        "display_scope": display_scope,
        "questions": questions,
        "series_markets_count": series_count,
        "coverage": coverage,
    }


# ── the Game matrix ──────────────────────────────────────────────────────────


def build_game_question_matrix(
    *,
    served: dict,
    outcomes: Iterable,
    market_facts: dict,
    observed: Callable[[Any], Optional[str]],
    markets_with_a_winner: set,
    verdict_is_provable: Callable[[dict, bool], bool],
    is_pregame: Callable[[Any, Any], bool],
    period_from_ticker: Callable[[Optional[str]], Optional[str]],
    period_from_name: Callable[[str, str], Optional[str]],
    row_market_ids: Callable[[dict], set],
    sport_prefix: Optional[str],
    home_team: Optional[str],
    away_team: Optional[str],
    commence_time: Any,
) -> Optional[dict]:
    """``game_question_matrix`` for one ``/game-markets`` build, or ``None``.

    ``served`` maps the six source-array names to the route's FINAL served
    lists. ``outcomes`` is every leg the route loaded (``market_id IN`` its
    markets). ``market_facts`` is the G0 snapshot by market id.
    """
    legs_by_id: dict = {}
    legs_by_market: dict = defaultdict(list)
    for leg in outcomes:
        legs_by_id[leg.id] = leg
        legs_by_market[leg.market_id].append(leg)

    coverage = _empty_coverage()
    unit = _SPORT_SCORING_UNIT.get(sport_prefix or "")

    typed: dict = {}  # proposition_key → {"kind", "info", "entries"}
    named_entries: list = []  # (entry, untyped_reason | None)

    entries, coverage["build_errors"] = _served_entries(served, row_market_ids)
    for entry in entries:
        try:
            facts = market_facts.get(entry["market_ids"][0]) if entry["market_ids"] else None
            verdict = _type_entry(
                entry, facts, unit, sport_prefix, home_team, away_team,
                period_from_ticker, period_from_name,
            )
        except Exception:
            coverage["build_errors"] += 1
            continue
        if verdict is None:
            named_entries.append((entry, None))
        elif "reason" in verdict:
            coverage["untyped"][verdict["reason"]] += 1
            named_entries.append((entry, verdict["reason"]))
        else:
            slot = typed.setdefault(
                verdict["proposition_key"],
                {"kind": verdict["kind"], "info": verdict, "entries": []},
            )
            slot["entries"].append(entry)

    served_ids = {
        cid
        for slot in typed.values()
        for entry in slot["entries"]
        for cid in entry["contributor_ids"]
    } | {cid for entry, _ in named_entries for cid in entry["contributor_ids"]}

    shared = {
        "legs_by_id": legs_by_id,
        "legs_by_market": legs_by_market,
        "market_facts": market_facts,
        "observed": observed,
        "markets_with_a_winner": markets_with_a_winner,
        "verdict_is_provable": verdict_is_provable,
        "is_pregame": is_pregame,
        "commence_time": commence_time,
        "home_team": home_team,
        "away_team": away_team,
        "served_ids": served_ids,
        "sport_prefix": sport_prefix,
        "period_from_ticker": period_from_ticker,
        "period_from_name": period_from_name,
    }

    questions: list = []
    for proposition_key, slot in typed.items():
        try:
            questions.append(_typed_question(proposition_key, slot, shared))
        except Exception:
            coverage["build_errors"] += len(slot["entries"])

    for group in _named_groups(named_entries):
        try:
            questions.append(_named_question(group, shared))
        except Exception:
            coverage["build_errors"] += len(group)

    _link_complements(questions)
    return _finish("game", questions, coverage, None)


def _served_entries(served: dict, row_market_ids: Callable[[dict], set]) -> tuple[list, int]:
    """Flatten the six served lists into one entry per served option row.

    Returns ``(entries, errors)``: a row that cannot be read is counted and
    skipped (gotcha #42), and its siblings are flattened as usual."""
    entries: list = []
    errors = 0
    for array in ("totals", "team_totals", "spreads", "period_markets", "other"):
        for row in served.get(array) or []:
            try:
                entries.append(_row_entry(array, row, row_market_ids))
            except Exception:
                errors += 1
    for index, matchup in enumerate(served.get("matchups") or []):
        for row in matchup.get("outcomes") or []:
            try:
                entries.append(_matchup_entry(index, matchup, row))
            except Exception:
                errors += 1
    return entries, errors


def _row_entry(array: str, row: dict, row_market_ids: Callable[[dict], set]) -> dict:
    market_type = (
        "spread" if array == "spreads"
        else "team_total" if array == "team_totals"
        else row.get("market_type")
    )
    total_axis = array in ("totals", "team_totals") or market_type in _COUNT_PERIOD_TYPES
    contributors = [int(c) for c in row.get("contributor_outcome_ids") or []]
    if not contributors:
        raise ValueError("served row carries no contributor identity")
    return {
        "array": array,
        "row": row,
        "market_type": market_type if array != "other" else None,
        "market_ids": sorted(row_market_ids(row)),
        "contributor_ids": contributors,
        "label": row.get("outcome_name"),
        "market_name": row.get("market_name"),
        "source": row.get("source"),
        "observed_at": row.get("observed_at"),
        "value_key": "over_probability" if total_axis else "probability",
        "total_axis": total_axis,
        "matchup": None,
    }


def _matchup_entry(index: int, matchup: dict, row: dict) -> dict:
    market_id = matchup.get("_market_id")
    contributors = [int(c) for c in row.get("contributor_outcome_ids") or []]
    if not contributors:
        raise ValueError("served matchup leg carries no contributor identity")
    return {
        "array": "matchups",
        "row": row,
        "market_type": None,
        "market_ids": [market_id] if market_id is not None else [],
        "contributor_ids": contributors,
        "label": row.get("name"),
        "market_name": matchup.get("market_name"),
        "source": matchup.get("source"),
        "observed_at": row.get("observed_at"),
        "value_key": "probability",
        "total_axis": False,
        "matchup": {"index": index, "type": matchup.get("type")},
    }


def _type_entry(
    entry: dict,
    facts: Optional[dict],
    unit: Optional[str],
    sport_prefix: Optional[str],
    home_team: Optional[str],
    away_team: Optional[str],
    period_from_ticker: Callable,
    period_from_name: Callable,
) -> Optional[dict]:
    """§4.1 — a typed proposition, ``{"reason": ...}`` for a refusal, or
    ``None`` for a row that is named_options by nature (never a refusal)."""
    array, market_type, row = entry["array"], entry["market_type"], entry["row"]
    if array == "matchups":
        return None
    if array == "other":
        return _type_rank(entry, facts)
    period = _period(
        market_type, row.get("period"), facts, sport_prefix, period_from_ticker, period_from_name,
        row.get("outcome_name"),
    )
    market_name = (facts or {}).get("name")
    if array in ("totals", "team_totals") or market_type in _COUNT_PERIOD_TYPES:
        return _type_count(entry, period, unit, market_name, home_team, away_team)
    if array == "spreads" or market_type in _HANDICAP_PERIOD_TYPES:
        return _type_handicap(entry, period, unit, market_name, home_team, away_team)
    return None  # period winners: named options


def _type_count(entry, period, unit, market_name, home_team, away_team) -> dict:
    row = entry["row"]
    if period is None:
        return {"reason": "untyped_period"}
    if unit is None or not _count_unit_proven(market_name, unit, home_team, away_team):
        return {"reason": "untyped_unit"}
    side = "game"
    if entry["array"] == "team_totals":
        side = row.get("team_side")
        if side not in ("home", "away"):
            return {"reason": "untyped_subject"}
    threshold = row.get("threshold")
    # O/U k.5 is the only admitted count spelling. The `^N+` leg spelling of
    # §4.1 has no real scoring-unit totals market retained in the repo's
    # fixtures, so per the 10236 A3 rule it is refused rather than shipped on a
    # guess; an integer line falls here too.
    if not _is_half_line(threshold):
        return {"reason": "untyped_predicate"}
    bound = int(math.floor(float(threshold))) + 1
    quantity = _quantity(unit)
    subject_label = _team_name(side, home_team, away_team)
    noun = quantity["singular"] if bound == 1 else quantity["plural"]
    label = f"{bound}+ {noun}"
    if subject_label:
        label = f"{subject_label} {label}"
    if period != _FULL_GAME:
        label = f"{label} · {period[1]}"
    return {
        "kind": "count_threshold",
        "proposition_key": f"count|{quantity['key']}|{side}|{period[0]}|ge:{bound}",
        "label": label,
        "quantity": quantity,
        "period": period,
        "subject": {"side": side, "label": subject_label},
        "predicate": {"relation": "ge", "bound": bound, "line": float(threshold)},
        "option_side": "over",
    }


def _type_handicap(entry, period, unit, market_name, home_team, away_team) -> dict:
    row = entry["row"]
    name = entry["row"].get("outcome_name") or ""
    side: Optional[str] = None
    line: Optional[float] = None
    predicate_ok = False
    subject_evaluable = False
    # The margin-strict branch proves its unit from the leg's own words; the
    # signed-number branch proves it from the market's name (A4).
    unit_proven = unit is not None

    signed = _SIGNED_NUMBER_RE.findall(name)
    if len(signed) == 1:
        token = signed[0]
        value = float(token)
        before = name[: name.index(token)]
        subject_evaluable = True
        side = resolve_team_side(before, home_team, away_team)
        predicate_ok = (
            abs(value) == row.get("threshold")
            and _is_half_line(abs(value))
        )
        line = value
        unit_proven = unit is not None and _handicap_unit_proven(market_name, home_team, away_team)
    elif not signed:
        match = _MARGIN_RE.match(name)
        if match is not None:
            subject_evaluable = True
            side = resolve_team_side(match.group("team"), home_team, away_team)
            strict = match.group("strict")
            predicate_ok = (
                strict is not None
                and _is_half_line(float(strict))
                and unit is not None
                and _singular(match.group("unit")) == unit
            )
            line = -float(strict) if strict is not None else None

    if period is None:
        return {"reason": "untyped_period"}
    if not unit_proven:
        return {"reason": "untyped_unit"}
    if subject_evaluable and side is None:
        return {"reason": "untyped_subject"}
    if not predicate_ok or side is None or line is None:
        return {"reason": "untyped_predicate"}

    quantity = _quantity(unit)
    team = _team_name(side, home_team, away_team)
    signed_line = format(line, "+g")
    label = f"{team} {signed_line} {quantity['plural']}"
    if period != _FULL_GAME:
        label = f"{label} · {period[1]}"
    return {
        "kind": "signed_handicap",
        "proposition_key": f"handicap|{quantity['key']}|{side}|{period[0]}|{signed_line}",
        "label": label,
        "quantity": quantity,
        "period": period,
        "subject": {"side": side, "label": team},
        "predicate": {"relation": "handicap", "bound": None, "line": line},
        "option_side": side,
    }


def _type_rank(entry: dict, facts: Optional[dict]) -> Optional[dict]:
    """§4.1 rank: ``_TOP_N_RE`` with an integer N on the market's own name AND
    the classifier's ``independent_participation`` stamp. A name the regex
    reads with no N (make cut / qualify / advance) is refused; a name it does
    not read at all is an ordinary named question."""
    name = (facts or {}).get("name") or entry.get("market_name") or ""
    match = _TOP_N_RE.search(name)
    if match is None:
        return None
    shape = _meta(facts).get("shape")
    relation = shape.get("outcome_relation") if isinstance(shape, dict) else None
    if match.group(1) is None or relation != "independent_participation":
        return {"reason": "untyped_predicate"}
    bound = int(match.group(1))
    market_id = entry["market_ids"][0]
    return {
        "kind": "rank_predicate",
        "proposition_key": f"rank|finishing_position|m:{market_id}|le:{bound}",
        "label": f"Top {bound}",
        "quantity": None,
        "period": None,
        "subject": None,
        "predicate": {"relation": "le", "bound": bound, "line": None},
        "option_side": "category",
    }


def _game_result(entry: dict, lifecycle_state: str, shared: dict) -> dict:
    """§6 game path. A bare ``is_winner: false`` is Lost only when the route's
    own `_verdict_is_provable` says the market was decided, never voided."""
    row = entry["row"]
    is_winner = row.get("is_winner")
    if is_winner is True:
        return {"state": "won", "evidence_kind": "settled_grade_fields"}
    if is_winner is False:
        market_id = entry["market_ids"][0] if entry["market_ids"] else None
        if shared["verdict_is_provable"](row, market_id in shared["markets_with_a_winner"]):
            return {"state": "lost", "evidence_kind": "verdict_is_provable"}
        return {"state": "unknown", "evidence_kind": "none"}
    if lifecycle_state == "open":
        return {"state": "open", "evidence_kind": "none"}
    return {"state": "unknown", "evidence_kind": "none"}


def _game_option(entry: dict, side: str, lifecycle_state: str, shared: dict) -> dict:
    """One served row → one option (§4)."""
    legs_by_id = shared["legs_by_id"]
    contributors = entry["contributor_ids"]
    result = _game_result(entry, lifecycle_state, shared)
    raws = [_raw(legs_by_id.get(cid)) for cid in contributors]
    served_value = _finite_probability(entry["row"].get(entry["value_key"]))
    basis_quoted = "published_source_display" if len(contributors) == 1 else "unknown"

    refused = False
    if result["state"] in ("won", "lost"):
        published = (None, "result", "result")
    elif served_value is not None:
        published = (served_value, "quoted", basis_quoted)
    elif (
        raws and all(r == 0.0 for r in raws) and result["state"] == "open"
        and not _published_on_a_sibling_axis(entry, legs_by_id)
    ):
        # F1: the route serves a stored 0.0 as null (`if prob else None`);
        # finite 0 is a real quote and the annotation says so — but only on
        # the leg's OWN axis: an under leg's 0.0 on the over axis is 1.0, and
        # nothing is computed here, so that case stays refused.
        published = (0.0, "quoted", basis_quoted)
    elif all(r is None for r in raws):
        published = (None, "unpriced", "unknown")
    else:
        # A served null over a priced leg is the route declining to publish;
        # nothing is invented for it and no raw value leaks beside it.
        refused = True
        published = (None, "refused", "unknown")
    value, value_state, basis = published

    evidence = [] if refused else _game_evidence(entry, side, shared)
    leg = legs_by_id.get(contributors[0]) if len(contributors) == 1 else None
    comparison = _game_comparison(entry, value_state, leg, shared)
    return {
        "option_key": "o:" + "+".join(str(c) for c in sorted(contributors)),
        "label": _axis_label(entry),
        "side": side,
        "market_ids": list(entry["market_ids"]),
        "contributor_outcome_ids": list(contributors),
        "published": {
            "value": value,
            "value_state": value_state,
            "basis": basis,
            "source": entry["source"] if len(contributors) == 1 else None,
            "observed_at": entry["observed_at"],
        },
        "source_evidence": evidence,
        "result": result,
        "comparison": comparison,
    }


def _published_on_a_sibling_axis(entry: dict, legs_by_id: dict) -> bool:
    """F2: is this totals row's value its under leg's sibling's (over) axis?"""
    if not entry["total_axis"]:
        return False
    return any(
        leg is not None and _leg_reads_under(leg.name)
        for leg in (legs_by_id.get(cid) for cid in entry["contributor_ids"])
    )


def _game_evidence(entry: dict, side: str, shared: dict) -> list:
    """§4.2 — one entry per contributor, from the LOADED leg only."""
    evidence = []
    for cid in entry["contributor_ids"]:
        leg = shared["legs_by_id"].get(cid)
        if leg is None:
            continue
        if entry["total_axis"]:
            leg_side = "under" if _leg_reads_under(leg.name) else "over"
        else:
            leg_side = side
        evidence.append({
            "source": entry["source"],
            "market_id": leg.market_id,
            "outcome_id": cid,
            "leg_side": leg_side,
            "raw_probability": _round4(_raw(leg)),
            "observed_at": shared["observed"](leg),
        })
    return evidence


def _game_comparison(entry: dict, value_state: str, leg: Any, shared: dict) -> dict:
    """§6 + R1/R2/R3/R4. One cell, one reason, in R1's order:
    ``not_quoted`` → ``leg_is_complement`` → pin reason →
    ``current_clock_unknown`` → ``baseline_not_earlier``."""
    if value_state != "quoted" or leg is None:
        # R4: a multi-contributor option has no blend comparison in v1.
        return _unavailable("not_quoted")
    raw = _raw(leg)
    if raw is None:
        return _unavailable("not_quoted")
    if entry["total_axis"] and _leg_reads_under(leg.name):
        return _unavailable(LEG_IS_COMPLEMENT)
    # R3: the pin is read from the market's own metadata in EVERY status.
    meta = _meta(shared["market_facts"].get(leg.market_id))
    pin = pin_evidence(meta.get("pregame_mark"), leg.id, shared["commence_time"], shared["is_pregame"])
    latest = {"probability": round(raw, 4), "observed_at": shared["observed"](leg)}
    decided = _comparison(
        {
            "current": {"state": "quoted", "probability": latest["probability"]},
            "contributors": [{"observed_at": latest["observed_at"]}],
        },
        [pin],
    )
    # R2: `latest` exists iff the pair is comparable, and it is the RAW value.
    return {
        "state": decided["state"],
        "reason": decided["reason"],
        "baseline": decided["baseline"],
        "latest": latest if decided["state"] == "comparable" else None,
        "delta_points": decided["delta_points"],
    }


def _question_markets(entries: list) -> list:
    return sorted({mid for entry in entries for mid in entry["market_ids"]})


def _question_lifecycle(entries: list, market_ids: list, shared: dict) -> dict:
    won_any = any(entry["row"].get("is_winner") is True for entry in entries)
    statuses = [_status(shared["market_facts"].get(mid)) for mid in market_ids]
    return _lifecycle(won_any, statuses)


def _option_counts(
    market_ids: list,
    returned: int,
    missing: list,
    shared: dict,
    three_way: bool,
) -> tuple[dict, Optional[bool]]:
    loaded = sum(len(shared["legs_by_market"].get(mid, [])) for mid in market_ids)
    declared = None
    meta: dict = {}
    if len(market_ids) == 1:
        facts = shared["market_facts"].get(market_ids[0]) or {}
        meta = _meta(facts)
        declared = venue_leg_count(meta, facts.get("name"), facts.get("mutually_exclusive") is True)
    counts = {
        "declared": declared,
        "loaded": loaded,
        "returned": returned,
        "missing_identified": len(missing),
    }
    complete = _completeness(
        returned=returned, loaded=loaded, declared=declared, meta=meta, three_way=three_way,
    )
    return counts, complete


def _typed_question(proposition_key: str, slot: dict, shared: dict) -> dict:
    """A count / handicap / rank question (§3)."""
    kind, info, entries = slot["kind"], slot["info"], slot["entries"]
    market_ids = _question_markets(entries)
    lifecycle = _question_lifecycle(entries, market_ids, shared)

    if kind == "rank_predicate":
        options = [_game_option(e, "category", lifecycle["state"], shared) for e in entries]
        legs = shared["legs_by_market"].get(market_ids[0], [])
        missing = _missing_options(legs, {}, shared) if len(legs) <= _LIST_CAP else []
    elif len(entries) == 1:
        options = [_game_option(entries[0], info["option_side"], lifecycle["state"], shared)]
        # A count/handicap rung's siblings are their OWN questions, so a
        # ladder's other legs are not missing options of this one.
        missing = []
    else:
        options = [_unblended_option(entries, info["option_side"], lifecycle["state"], shared)]
        missing = []

    counts, complete = _option_counts(market_ids, len(options), missing, shared, False)
    first = entries[0]
    return {
        "question_key": "q:" + proposition_key,
        "proposition_key": proposition_key,
        "display_scope": "game",
        "kind": kind,
        "label": info["label"],
        "market_name": first["market_name"],
        "source_array": first["array"],
        "quantity": info["quantity"],
        "period": _period_obj(info["period"]),
        "subject": info["subject"],
        "predicate": info["predicate"],
        "complement_question_key": None,
        "typing": {"state": "typed", "reason": None},
        "lifecycle": lifecycle,
        "options": options,
        "missing_options": missing,
        "option_counts": counts,
        "complete": complete,
        "source_totals": _source_totals(options),
        "_market_ids": market_ids,
    }


def _unblended_option(entries: list, side: str, lifecycle_state: str, shared: dict) -> dict:
    """U5 / §4.2 — ≥2 served rows typed to one proposition the route did NOT
    blend. One option, value null, basis unknown; every contributor's raw
    value stays in ``source_evidence``. Blending them is another reviewed ship."""
    contributors = sorted({cid for e in entries for cid in e["contributor_ids"]})
    results = [_game_result(e, lifecycle_state, shared) for e in entries]
    states = {r["state"] for r in results}
    result = results[0] if len(states) == 1 else {"state": "unknown", "evidence_kind": "none"}
    evidence = [ev for e in entries for ev in _game_evidence(e, side, shared)]
    return {
        "option_key": "o:" + "+".join(str(c) for c in contributors),
        "label": _axis_label(entries[0]),
        "side": side,
        "market_ids": _question_markets(entries),
        "contributor_outcome_ids": contributors,
        "published": {
            "value": None,
            "value_state": "unblended_equivalents",
            "basis": "unknown",
            "source": None,
            "observed_at": None,
        },
        "source_evidence": evidence,
        "result": result,
        "comparison": _unavailable("not_quoted"),
    }


def _named_groups(named_entries: list) -> list:
    """One named question per served market-id set (§4.1): a matchup entry, or
    rows grouped by the union of their market ids."""
    groups: list = []  # [(id set, [(entry, reason)])]
    matchup_groups: dict = {}
    for item in named_entries:
        entry = item[0]
        if entry["matchup"] is not None:
            matchup_groups.setdefault(entry["matchup"]["index"], []).append(item)
            continue
        ids = set(entry["market_ids"])
        joined = [g for g in groups if g[0] & ids]
        merged_ids = set(ids)
        merged_items: list = []
        for g in joined:
            merged_ids |= g[0]
            merged_items.extend(g[1])
            groups.remove(g)
        merged_items.append(item)
        groups.append((merged_ids, merged_items))
    return [items for _, items in groups] + list(matchup_groups.values())


def _missing_options(legs: list, sides: dict, shared: dict) -> list:
    """§7 — loaded legs no question in this object returned. Identity from the
    loaded leg; never a price (a refused leg stays refused)."""
    missing = []
    for leg in legs:
        if leg.id in shared["served_ids"]:
            continue
        side = sides.get(leg.id)
        missing.append({
            "option_key": f"o:{leg.id}",
            "outcome_id": leg.id,
            "label": leg.name,
            "side": side if side not in (None, "category", "contender") else None,
            "value_state": "unpriced" if _raw(leg) is None else "unavailable",
        })
    return missing


def _named_question(group: list, shared: dict) -> dict:
    entries = [entry for entry, _ in group]
    reasons = {reason for _, reason in group if reason is not None}
    market_ids = _question_markets(entries)
    first = entries[0]
    matchup_type = first["matchup"]["type"] if first["matchup"] else None

    legs = [leg for mid in market_ids for leg in shared["legs_by_market"].get(mid, [])]
    facts = shared["market_facts"].get(market_ids[0]) if len(market_ids) == 1 else None
    sides = (
        _named_sides(legs, (facts or {}).get("mutually_exclusive"), matchup_type,
                     shared["home_team"], shared["away_team"])
        if len(market_ids) == 1 else {}
    )
    three_way = _three_way_proven(sides)
    lifecycle = _question_lifecycle(entries, market_ids, shared)

    options = []
    for entry in entries:
        cids = entry["contributor_ids"]
        side = sides.get(cids[0], "category") if len(cids) == 1 else "category"
        options.append(_game_option(entry, side, lifecycle["state"], shared))

    missing = _missing_options(legs, sides, shared) if len(legs) <= _LIST_CAP else []
    counts, complete = _option_counts(market_ids, len(options), missing, shared, three_way)
    period = (
        _period(first["market_type"], first["row"].get("period"), facts,
                shared["sport_prefix"], shared["period_from_ticker"], shared["period_from_name"])
        if facts is not None else None
    )
    reason = next((r for r in UNTYPED_REASONS if r in reasons), None)
    return {
        "question_key": "m:" + "+".join(str(m) for m in market_ids),
        "proposition_key": None,
        "display_scope": "game",
        "kind": "named_options",
        "label": first["market_name"],
        "market_name": first["market_name"],
        "source_array": first["array"],
        "quantity": None,
        "period": _period_obj(period),
        "subject": None,
        "predicate": None,
        "complement_question_key": None,
        "typing": (
            {"state": "untyped", "reason": reason} if reason else {"state": "typed", "reason": None}
        ),
        "lifecycle": lifecycle,
        "options": options,
        "missing_options": missing,
        "option_counts": counts,
        "complete": complete,
        "source_totals": _source_totals(options),
        "_market_ids": market_ids,
    }


def _link_complements(questions: list) -> None:
    """§4.1 — a handicap's complement is the SAME market's other served leg,
    typed to the opposite side with the negated line. Never computed by the
    client; never set on a count (totals are already over-axis, F2)."""
    handicaps = [q for q in questions if q["kind"] == "signed_handicap"]
    for q in handicaps:
        for other in handicaps:
            if other is q or not set(q["_market_ids"]) & set(other["_market_ids"]):
                continue
            if (
                other["subject"]["side"] != q["subject"]["side"]
                and other["predicate"]["line"] == -q["predicate"]["line"]
                and other["period"] == q["period"]
                and other["quantity"] == q["quantity"]
            ):
                q["complement_question_key"] = other["question_key"]
                break


# ── the Series matrix ────────────────────────────────────────────────────────


def build_series_question_matrix(
    *,
    formatted_series: list,
    series_by_market: dict,
    series_withheld: set,
    settled_before_the_game: Callable[[Any], bool],
    home_team: Optional[str],
    away_team: Optional[str],
) -> Optional[dict]:
    """``series_question_matrix`` for one ``/related-futures`` build, or ``None``.

    ``formatted_series`` is the served card after ``relabel_series_card``;
    ``series_by_market`` is every leg the route loaded per Series market;
    ``series_withheld`` its refusal set. The Series question's lifecycle is the
    Series market's own (R6, §6): a final Game never closes an open Series.
    """
    coverage = _empty_coverage()
    questions: list = []
    for market_row in formatted_series:
        try:
            questions.append(_series_question(market_row, series_by_market, series_withheld,
                                              home_team, away_team))
        except Exception:
            coverage["build_errors"] += len(market_row.get("outcomes") or [])
    eligible = 0
    for legs in series_by_market.values():
        market = legs[0].market if legs else None
        if market is not None and not settled_before_the_game(market):
            eligible += 1
    return _finish(
        "series", questions, coverage,
        {"eligible": eligible, "returned": len(formatted_series)},
    )


def _series_question(market_row: dict, series_by_market: dict, series_withheld: set,
                     home_team: Optional[str], away_team: Optional[str]) -> dict:
    market_id = market_row["market_id"]
    legs = list(series_by_market.get(market_id) or [])
    legs_by_id = {leg.id: leg for leg in legs}
    market = legs[0].market if legs else None
    meta = market.__dict__.get("market_metadata") if market is not None else None
    meta = meta if isinstance(meta, dict) else {}
    mutually_exclusive = getattr(market, "mutually_exclusive", None)
    sides = _named_sides(legs, mutually_exclusive, None, home_team, away_team)

    rows = market_row.get("outcomes") or []
    won_any = any(r.get("settled") is True and r.get("is_winner") is True for r in rows)
    status = market_row.get("status")
    lifecycle = _lifecycle(won_any, [status if isinstance(status, str) else None])

    options = [
        _series_option(row, market_row, legs_by_id.get(row.get("outcome_id")), sides,
                       series_withheld, lifecycle["state"])
        for row in rows
    ]
    served_ids = {row.get("outcome_id") for row in rows}
    missing = []
    if len(legs) <= _LIST_CAP:
        missing = _missing_options(legs, sides, {"served_ids": served_ids})
    declared = venue_leg_count(meta, getattr(market, "name", None), mutually_exclusive is True)
    loaded = len(legs)
    counts = {
        "declared": declared,
        "loaded": loaded,
        "returned": len(options),
        "missing_identified": len(missing),
    }
    complete = _completeness(
        returned=len(options), loaded=loaded, declared=declared, meta=meta,
        three_way=_three_way_proven(sides),
    )
    return {
        "question_key": f"m:{market_id}",
        "proposition_key": None,
        "display_scope": "series",
        "kind": "named_options",
        "label": market_row.get("market_name"),
        "market_name": market_row.get("market_name"),
        "source_array": "series_markets",
        "quantity": None,
        "period": None,
        "subject": None,
        "predicate": None,
        "complement_question_key": None,
        "typing": {"state": "typed", "reason": None},
        "lifecycle": lifecycle,
        "options": options,
        "missing_options": missing,
        "option_counts": counts,
        "complete": complete,
        "source_totals": _source_totals(options),
        "_market_ids": [market_id],
    }


def _series_option(row: dict, market_row: dict, leg: Any, sides: dict,
                   series_withheld: set, lifecycle_state: str) -> dict:
    """One served Series leg → one option. Series clocks are null (U2)."""
    outcome_id = row.get("outcome_id")
    side = sides.get(outcome_id, "category")
    refused = outcome_id in series_withheld
    settled = row.get("settled") is True
    if settled:
        result = {
            "state": "won" if row.get("is_winner") is True else "lost",
            "evidence_kind": "outcome_is_settled",
        }
    elif lifecycle_state == "open":
        result = {"state": "open", "evidence_kind": "none"}
    else:
        result = {"state": "unknown", "evidence_kind": "none"}

    raw = _raw(leg)
    served_value = _finite_probability(row.get("probability"))
    if result["state"] in ("won", "lost"):
        value, value_state, basis = None, "result", "result"
    elif refused:
        value, value_state, basis = None, "refused", "unknown"
    elif served_value is not None:
        value, value_state, basis = served_value, "quoted", "published_source_display"
    elif raw == 0.0 and result["state"] == "open":
        # F1: `not so.current_probability` serves a stored 0.0 as null.
        value, value_state, basis = 0.0, "quoted", "published_source_display"
    elif raw is None:
        value, value_state, basis = None, "unpriced", "unknown"
    else:
        value, value_state, basis = None, "refused", "unknown"

    evidence = []
    if not refused and leg is not None:
        evidence.append({
            "source": market_row.get("source"),
            "market_id": market_row.get("market_id"),
            "outcome_id": outcome_id,
            "leg_side": side,
            "raw_probability": _round4(raw),
            "observed_at": None,
        })
    reason = "not_quoted" if value_state != "quoted" else SERIES_BASELINE_UNSUPPORTED
    return {
        "option_key": f"o:{outcome_id}",
        "label": row.get("name"),
        "side": side,
        "market_ids": [market_row.get("market_id")],
        "contributor_outcome_ids": [outcome_id],
        "published": {
            "value": value,
            "value_state": value_state,
            "basis": basis,
            "source": market_row.get("source"),
            "observed_at": None,
        },
        "source_evidence": evidence,
        "result": result,
        "comparison": _unavailable(reason),
    }
