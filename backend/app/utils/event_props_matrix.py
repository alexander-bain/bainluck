"""The DURING player-props matrix (#10236): one typed question, one number.

PILLARS: FORMATTING / TRUTH. During a supported game a reader compares
players' quoted chances for one count stat in a grid, opens one cell's question
and its sources, and Close/Back returns to the same stat, row and threshold.
This module builds the additive ``during_player_props`` key on
``GET /api/events/{id}/game-markets``. Every existing key on that response —
``player_props``, ``props_script``, settlement, the stream envelope — is
untouched by it.

Contract: ``10236-DURING-INPUT-CONTRACT-v1.md`` (Live) as amended once by
``10236-DURING-INPUT-CONTRACT-v1.1-AUTHORITY.md`` (Authority's typed decisions),
plus Live's accepted addendum (raw under pins, exact-union baselines and
clocks, ``actual_only`` grades carried verbatim). Section marks below (§4.4,
A2 …) point into those files.

Pure: no I/O, no provider query, no ORM. The route hands in its own rows and
its own decision functions, so every decision the old card makes is asked
through the SAME function here — window, grade, monotonicity, redundant parent,
pregame-pin gate — never re-spelled (CERT-2486 is what a second spelling
costs). What this module owns is only what the old card never decided: the
typed question key, the own-side quote, the union fold, the pin comparison and
the closed refusal coverage.

🔴 WHY THE MATRIX DOES NOT READ ``player_props``. Step 9's 0.05–0.95 band
deletes every ungraded extreme price, and 9b mutates its representative in
place and drops each contributor's own value. A grid built from that list
would lose real quotes (a finite 0.0 is a quote) and could not show which
source said what. The route therefore snapshots the candidate rows BEFORE
step 9 and hands the copy here. Nothing built here flows back into the old
lists.

🔴 WHY THE 9b KEY IS NOT THE EQUIVALENCE (v1.1 A0). 9b keys on the RAW
threshold, and the two venues write one question two ways — Kalshi
``Aaron Judge: 2+`` (2.0) and Polymarket ``Aaron Judge: Hits O/U 1.5`` /
``Over`` (1.5) are both "hits ≥ 2". The matrix folds on the typed
``question_key``, so its contributor set is equal to, or a strict superset of,
any 9b row's. The VALUE rule is 9b's own (:func:`blend_mean`, which 9b now
calls too).
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional

from app.utils.latest_observation import blended_observed_at

CONTRACT = "10236.v1"
COVERAGE_SCOPE = "linked_markets_loaded_for_event"
PERIOD_KEY = "full_game"
PERIOD_LABEL = "Game"

# The closed refusal set, in the order a row is tested (v1.1 "Final coverage
# spelling"): a row is counted once, under the FIRST reason it hits.
REFUSAL_REASONS = (
    "ambiguous_subject",
    "team_subject",
    "untyped_stat",
    "untyped_predicate",
    "window_closed",
    "monotonic_conflict",
    "redundant_parent",
)

# The closed comparison reasons (v1 §4.4). `contributor_set_mismatch` is part
# of the published set but this producer never emits it: the baseline is only
# ever taken over the exact contributor set the current value is taken over,
# so a member without a pin makes the cell unavailable with THAT member's
# reason instead (Live addendum, term 2).
COMPARISON_REASONS = (
    "baseline_basis_opening_line",
    "no_pregame_pin",
    "baseline_clock_unknown",
    "current_clock_unknown",
    "baseline_not_earlier",
    "contributor_set_mismatch",
    "not_quoted",
)

# A3 — THE CLOSED STAT TABLE. A row types only when its normalised stat text is
# EXACTLY one of a stat's spellings, so a period-qualified stat ("1st 5 innings
# strikeouts") can never match and `period_key` is always `full_game` in v1.
#
# Each spelling is proved against a real market name retained in the repo's
# fixtures (`tests/test_event_props_matrix_10236.py::TestEveryAdmittedSpelling`
# names the file it came from). v1.1 listed four more spellings — `goals`,
# `home run`, `rbi`, `runs scored` — and none has a real market name in the
# repo (`goals`' only hit is the placeholder "Player: 3+ Goals"), so per v1.1
# they are DELETED rather than shipped on a guess. A stat added later is one
# row here plus one fixture there.
#
#   stat_key, label, unit singular, unit plural, accepted spellings
STAT_TABLE: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    ("hits", "Hits", "hit", "hits", ("hits",)),
    ("home_runs", "Home Runs", "home run", "home runs", ("home runs",)),
    ("total_bases", "Total Bases", "base", "bases", ("total bases",)),
    ("rbis", "RBIs", "RBI", "RBIs", ("rbis",)),
    ("runs", "Runs", "run", "runs", ("runs",)),
    ("strikeouts", "Strikeouts", "strikeout", "strikeouts", ("strikeouts",)),
    ("walks", "Walks", "walk", "walks", ("walks",)),
    ("stolen_bases", "Stolen Bases", "stolen base", "stolen bases", ("stolen bases",)),
    ("receptions", "Receptions", "reception", "receptions", ("receptions",)),
    ("passing_completions", "Completions", "completion", "completions", ("passing completions",)),
    ("passing_attempts", "Pass Attempts", "attempt", "attempts", ("passing attempts",)),
    ("points", "Points", "point", "points", ("points",)),
    ("rebounds", "Rebounds", "rebound", "rebounds", ("rebounds",)),
    ("assists", "Assists", "assist", "assists", ("assists",)),
    ("shots_on_goal", "Shots on Goal", "shot", "shots", ("shots on goal",)),
    ("saves", "Saves", "save", "saves", ("saves",)),
)

_STAT_BY_SPELLING = {
    spelling: row[0] for row in STAT_TABLE for spelling in row[4]
}

# A4 — the three typed shapes. Numbers are captured with their decimals so a
# non-integer count is REFUSED as `untyped_predicate` rather than silently
# failing to match (and being miscounted as some other reason).
_COUNT_PLUS_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\+\s*$")
_COUNT_PLUS_STAT_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\+\s+(?P<stat>.+?)\s*$")
_OU_LINE_RE = re.compile(r"\bO/U\s*(\d+(?:\.\d+)?)\s*$", re.IGNORECASE)
_INTEGER_RE = re.compile(r"^\d+$")
_HALF_LINE_RE = re.compile(r"^(\d+)\.5$")

_SOURCE_RANK = {"kalshi": 0, "polymarket": 1}

_GRADE_KEYS = ("actual", "hit", "is_winner", "resolution_source")


def blend_mean(values: Iterable[float]) -> float:
    """THE value rule for one number drawn from several sources' prices.

    The unweighted mean, rounded to 4 — lifted verbatim out of step 9b so the
    old card and the matrix cannot drift apart (v1.1 A1). 9b calls this for
    its fold; the matrix calls it for its own (wider) union fold and for the
    union of pregame pins. Changing it changes a published blend, which is a
    reviewed class with its own ship.
    """
    vals = list(values)
    return round(sum(vals) / len(vals), 4)


def normalize_subject(text: Optional[str]) -> str:
    """A2 — the event-local subject key: NFKD with accents stripped, `.`
    removed, whitespace collapsed, lowercase. Nothing else — no initial
    expansion, no surname matching, no roster lookup."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.replace(".", "").split()).lower()


def _normalize_stat(text: Optional[str]) -> str:
    return " ".join((text or "").split()).lower()


def _team_forms(*team_names: Optional[str]) -> set[str]:
    """A2 — every spelling under which a subject is the TEAM, not a player:
    the full name, the name minus its last word (the locality), and the last
    word (the nickname). `Detroit: 250+` and `New Orleans: 250+` (#6769)."""
    forms: set[str] = set()
    for name in team_names:
        norm = normalize_subject(name)
        if not norm:
            continue
        words = norm.split()
        forms.add(norm)
        forms.add(words[-1])
        if len(words) > 1:
            forms.add(" ".join(words[:-1]))
    return forms


def _parse_stamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _finite_probability(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f) or f < 0.0 or f > 1.0:
        return None
    return f


def type_prop_row(
    market_name: Optional[str],
    outcome_name: Optional[str],
    player_and_stat: Callable[[Optional[str], Optional[str]], tuple[str, str]],
    team_forms: set[str],
) -> dict:
    """Type one prop leg into a question, or say why it cannot be typed.

    Returns ``{"refused": reason}`` or the typed parts. Tested in the order
    the coverage counts in: subject → stat → predicate.

    The SUBJECT is `_prop_player_and_stat`'s, passed in as ``player_and_stat``
    — the same function 9b and 9c group by. A2 admits only its three named
    branches; its fallback branch returns the outcome's own lowercased text,
    and that signature is how a fallback identity is told apart and refused
    `ambiguous_subject` instead of being grouped. The original-case label is
    read from the same span the branch read.
    """
    oname = (outcome_name or "").strip()
    mname = (market_name or "").strip()
    who, stat_text = player_and_stat(market_name, outcome_name)
    olower = oname.lower()

    colon = oname.find(":")
    if colon > 0:
        # Kalshi: "Aaron Judge: 2+" — the outcome names the player, the market
        # names the stat.
        branch = "kalshi_colon"
        subject_raw = oname[:colon].strip()
        remainder = oname[colon + 1:]
    elif olower in ("over", "under") and who != olower:
        # Polymarket O/U: "Trea Turner: Hits O/U 2.5" / "Over".
        branch = "polymarket_ou"
        subject_raw = mname.split(":", 1)[0].strip()
        remainder = ""
    elif olower in ("yes", "no") and who != olower:
        # Polymarket Yes/No (#9608): "Pierce Charles: 1+ saves" / "Yes".
        branch = "polymarket_yes_no"
        subject_raw = mname.rsplit(":", 1)[0].strip()
        remainder = stat_text
    else:
        return {"refused": "ambiguous_subject"}

    subject_key = normalize_subject(who)
    if not subject_key or normalize_subject(subject_raw) != subject_key:
        return {"refused": "ambiguous_subject"}
    if subject_key in team_forms:
        return {"refused": "team_subject"}

    # ── stat ──
    count_text: Optional[str] = None
    if branch == "polymarket_yes_no":
        m = _COUNT_PLUS_STAT_RE.match(remainder or "")
        if m is None:
            return {"refused": "untyped_stat"}
        count_text = m.group(1)
        stat_norm = _normalize_stat(m.group("stat"))
    else:
        stat_norm = _normalize_stat(stat_text)
    stat_key = _STAT_BY_SPELLING.get(stat_norm)
    if stat_key is None:
        return {"refused": "untyped_stat"}

    # ── predicate ──
    if branch == "kalshi_colon":
        m = _COUNT_PLUS_RE.match(remainder)
        if m is None or not _INTEGER_RE.match(m.group(1)) or int(m.group(1)) < 1:
            return {"refused": "untyped_predicate"}
        kind, count, side = "count_at_least", int(m.group(1)), "over"
    elif branch == "polymarket_ou":
        m = _OU_LINE_RE.search(mname)
        half = _HALF_LINE_RE.match(m.group(1)) if m else None
        if half is None:
            # An integer or non-.5 line can push — not a count question.
            return {"refused": "untyped_predicate"}
        k = int(half.group(1))
        if olower == "over":
            kind, count, side = "count_at_least", k + 1, "over"
        else:
            kind, count, side = "count_at_most", k, "under"
    else:
        if not _INTEGER_RE.match(count_text or "") or int(count_text) < 1:
            return {"refused": "untyped_predicate"}
        n = int(count_text)
        if olower == "yes":
            kind, count, side = "count_at_least", n, "over"
        else:
            kind, count, side = "count_at_most", n - 1, "under"

    return {
        "subject_key": subject_key,
        "subject_label": subject_raw,
        "stat_key": stat_key,
        "kind": kind,
        "count": count,
        "side": side,
        "question_key": question_key(subject_key, stat_key, kind, count),
    }


def question_key(subject_key: str, stat_key: str, kind: str, count: int) -> str:
    """A4 — deterministic from the typed parts; never a price, clock or index."""
    if kind == "count_at_least":
        return f"s:{subject_key}|{stat_key}|{PERIOD_KEY}|ge:{count}|over"
    return f"s:{subject_key}|{stat_key}|{PERIOD_KEY}|le:{count}|under"


def _predicate_label(kind: str, count: int) -> str:
    return f"{count}+" if kind == "count_at_least" else f"{count} or fewer"


def pin_evidence(
    pregame_mark: Any,
    outcome_id: Any,
    commence_time: Any,
    is_pregame: Callable[[Any, Any], bool],
) -> dict:
    """One leg's pregame baseline as the RAW pin, or the reason there is none.

    Reads ``market_metadata["pregame_mark"]["outcomes"][str(outcome_id)]``
    through the route's own ``_pregame_mark_is_pregame`` (passed as
    ``is_pregame``) and uses the value AS STORED — the price of this
    outcome's own predicate. `_resolve_pregame_mark` is deliberately NOT
    used: it flips an under leg to ``1 − raw`` (the over axis) and falls back
    to the opening line without saying so, and either would put a different
    question's number, or a non-pregame number, under this row (Live
    addendum, term 1). That function keeps its signature and behaviour.
    """
    if not isinstance(pregame_mark, dict):
        return {"reason": "no_pregame_pin"}
    raw = (pregame_mark.get("outcomes") or {}).get(str(outcome_id))
    if raw is None:
        return {"reason": "no_pregame_pin"}
    if not is_pregame(pregame_mark, commence_time):
        # The old card would print the opening line here; that is not a pin.
        return {"reason": "baseline_basis_opening_line"}
    value = _finite_probability(raw)
    if value is None:
        return {"reason": "no_pregame_pin"}
    observed = pregame_mark.get("observed_at")
    if not isinstance(observed, str) or _parse_stamp(observed) is None:
        return {"reason": "baseline_clock_unknown"}
    return {"probability": value, "observed_at": observed}


def _comparison(question: dict, pins: list[dict]) -> dict:
    """v1 §4.4 with the addendum: comparable only when EVERY contributor has a
    pregame pin whose own clock is known and earlier than that contributor's
    own current clock; the baseline is the same unweighted mean over the
    exact same set. The first failing member's reason names the cell."""
    unavailable = {"state": "unavailable", "baseline": None, "delta_points": None}
    current = question["current"]
    if current["state"] != "quoted":
        return {**unavailable, "reason": "not_quoted"}
    for contributor, pin in zip(question["contributors"], pins):
        if "reason" in pin:
            return {**unavailable, "reason": pin["reason"]}
        current_seen = _parse_stamp(contributor["observed_at"])
        if current_seen is None:
            return {**unavailable, "reason": "current_clock_unknown"}
        if not _parse_stamp(pin["observed_at"]) < current_seen:
            return {**unavailable, "reason": "baseline_not_earlier"}
    baseline = blend_mean(p["probability"] for p in pins)
    return {
        "state": "comparable",
        "reason": None,
        "baseline": {
            "probability": baseline,
            "observed_at": blended_observed_at(p["observed_at"] for p in pins),
            "basis": "pregame_pin",
        },
        "delta_points": round((current["probability"] - baseline) * 100, 1),
    }


def build_during_player_props(
    rows: list[dict],
    *,
    player_and_stat: Callable[[Optional[str], Optional[str]], tuple[str, str]],
    window_is_closed: Callable[[dict], bool],
    grade_is_in_hand: Callable[[dict], bool],
    enforce_monotonicity: Callable[[list[dict]], list[dict]],
    redundant_parent_ids: Callable[[list[dict]], set],
    pregame_mark_by_market_id: dict,
    is_pregame: Callable[[Any, Any], bool],
    commence_time: Any,
    home_team: Optional[str],
    away_team: Optional[str],
) -> Optional[dict]:
    """The ``during_player_props`` object, or ``None`` when no row types.

    ``rows`` is the route's deep copy of the prop candidates taken BEFORE
    step 9 — one row per outcome leg, construction refusals already applied,
    no interest band. The caller gates on the served status being live; this
    function does not look at the clock.

    Refusals are counted in LEGS (source rows), under the first reason each
    hits; a question refused by the monotonic or redundant-parent decision
    counts every leg it folded.
    """
    refused = {reason: 0 for reason in REFUSAL_REASONS}
    team_forms = _team_forms(home_team, away_team)

    # ── 1. type each leg; the shared window/grade decisions (§4.2) ──
    legs_by_question: dict[str, list[dict]] = {}
    typed_by_question: dict[str, dict] = {}
    for row in rows:
        typed = type_prop_row(
            row.get("market_name"), row.get("outcome_name"), player_and_stat, team_forms
        )
        if "refused" in typed:
            refused[typed["refused"]] += 1
            continue
        graded = grade_is_in_hand(row)
        # `_window_open`'s rule, asked through the same two functions: a graded
        # row is a result and stays; an ungraded row whose window is provably
        # over leaves.
        if not graded and window_is_closed(row):
            refused["window_closed"] += 1
            continue
        over = row.get("over_probability")
        if over is None:
            own = None
        else:
            # A5 / addendum term 3: the chance of THIS leg's own predicate.
            # Rows are stored over-oriented and an inverted (Under/No) leg
            # carries the complement, so its own price is 1 − over.
            own = round(1.0 - float(over), 4) if row.get("_inverted") else over
        outcome_ids = list(row.get("contributor_outcome_ids") or [])
        legs_by_question.setdefault(typed["question_key"], []).append({
            "row": row,
            "typed": typed,
            "graded": graded,
            "own": _finite_probability(own),
            "source": row.get("source"),
            "market_id": row.get("_market_id"),
            "outcome_id": outcome_ids[0] if len(outcome_ids) == 1 else None,
        })
        typed_by_question.setdefault(typed["question_key"], typed)

    # ── 2. fold on the typed question key (A1) ──
    questions: dict[str, dict] = {}
    for qkey, legs in legs_by_question.items():
        legs.sort(key=lambda l: (
            _SOURCE_RANK.get(l["source"], len(_SOURCE_RANK)),
            l["outcome_id"] if isinstance(l["outcome_id"], int) else float("inf"),
        ))
        typed = typed_by_question[qkey]
        contributors = [
            {
                "source": l["source"],
                "market_id": l["market_id"],
                "outcome_id": l["outcome_id"],
                "outcome_name": l["row"].get("outcome_name"),
                "side": typed["side"],
                "period_key": PERIOD_KEY,
                "probability": None if l["graded"] else l["own"],
                "observed_at": l["row"].get("observed_at"),
            }
            for l in legs
        ]
        graded_legs = [l for l in legs if l["graded"]]
        if graded_legs:
            # A graded row never gets a live chance (§4.2); its existing
            # `_grade_settled_prop` fields ride verbatim (addendum term 4).
            source_row = graded_legs[0]["row"]
            current = {"state": "actual_only", "probability": None, "basis": None, "observed_at": None}
            result = {k: source_row[k] for k in _GRADE_KEYS if k in source_row}
        elif any(l["own"] is None for l in legs):
            current = {"state": "unavailable", "probability": None, "basis": None, "observed_at": None}
            result = None
        else:
            current = {
                "state": "quoted",
                "probability": blend_mean(l["own"] for l in legs),
                "basis": "single_source" if len(legs) == 1 else "blend_mean",
                # The blend's clock is its oldest contributor's, and one
                # unknown clock makes it unknown (#4970). `last_updated` is
                # never read.
                "observed_at": blended_observed_at(c["observed_at"] for c in contributors),
            }
            result = None
        market_ids = sorted({
            i for l in legs for i in ([l["market_id"]] if l["market_id"] is not None else [])
        })
        questions[qkey] = {
            "question_key": qkey,
            "subject": {
                "key": typed["subject_key"],
                # A2: original case from the first contributor (Kalshi, then
                # Polymarket, then ascending outcome id).
                "label": legs[0]["typed"]["subject_label"],
                "kind": "player",
            },
            "stat_key": typed["stat_key"],
            "period_key": PERIOD_KEY,
            "predicate": {
                "kind": typed["kind"],
                "count": typed["count"],
                "side": typed["side"],
                "label": _predicate_label(typed["kind"], typed["count"]),
            },
            "complement_question_key": (
                question_key(typed["subject_key"], typed["stat_key"], "count_at_least", typed["count"] + 1)
                if typed["side"] == "under" else None
            ),
            "current": current,
            "contributors": contributors,
            "result": result,
            "_market_id": legs[0]["market_id"],
            "_market_ids": market_ids,
            "contributor_outcome_ids": sorted({
                oid for l in legs for oid in (l["row"].get("contributor_outcome_ids") or [])
            }),
            "_legs": legs,
        }

    # ── 3. the shared monotonic decision (9c's function, A5) ──
    #
    # On OVER-ORIENTED copies, grouped by (subject, stat, period, side) and
    # sorted by count, exactly as 9c groups. Only quoted questions priced above
    # zero take part: the function's own `> 0` filter is the old card's "a 0%
    # rung is a dead quote" editorial rule — the same class as the interest
    # band §4.1 refuses — and would delete a finite 0.0, which is a real quote.
    # The function CAPS a violating rung to its neighbour's price rather than
    # dropping it; a capped number is no contributor's quote, so a question it
    # caps or drops is refused `monotonic_conflict` instead of re-labelled.
    groups: dict[tuple, list[dict]] = {}
    for q in questions.values():
        cur = q["current"]
        if cur["state"] != "quoted":
            continue
        oriented = cur["probability"] if q["predicate"]["side"] == "over" else round(1.0 - cur["probability"], 4)
        if oriented <= 0:
            continue
        groups.setdefault(
            (q["subject"]["key"], q["stat_key"], q["period_key"], q["predicate"]["side"]), []
        ).append({
            "_question_key": q["question_key"],
            "over_probability": oriented,
            "threshold": q["predicate"]["count"],
            "_market_id": q["_market_id"],
            "observed_at": cur["observed_at"],
        })
    for group in groups.values():
        group.sort(key=lambda x: x["threshold"])
        kept = {
            item["_question_key"]: item["over_probability"]
            for item in enforce_monotonicity([dict(item) for item in group])
        }
        for item in group:
            qkey = item["_question_key"]
            if kept.get(qkey) != item["over_probability"]:
                refused["monotonic_conflict"] += len(questions[qkey]["_legs"])
                del questions[qkey]

    # ── 4. the shared redundant-parent decision (#4189) on this population ──
    redundant = redundant_parent_ids(list(questions.values()))
    if redundant:
        for qkey in list(questions):
            ids = set(questions[qkey]["_market_ids"])
            if ids and ids <= redundant:
                refused["redundant_parent"] += len(questions[qkey]["_legs"])
                del questions[qkey]

    if not questions:
        return None

    # ── 5. comparison (§4.4) and the served shape ──
    out_rows = []
    for q in questions.values():
        pins = [
            pin_evidence(
                pregame_mark_by_market_id.get(l["market_id"]),
                l["outcome_id"],
                commence_time,
                is_pregame,
            )
            for l in q.pop("_legs")
        ]
        q["comparison"] = _comparison(q, pins)
        out_rows.append(q)
    out_rows.sort(key=lambda q: (
        q["stat_key"], q["period_key"], q["subject"]["label"],
        q["predicate"]["count"], q["predicate"]["side"],
    ))

    present = {q["stat_key"] for q in out_rows}
    stats = [
        {
            "stat_key": stat_key,
            "label": label,
            "unit": plural,
            "unit_singular": singular,
            "period_key": PERIOD_KEY,
            "period_label": PERIOD_LABEL,
            "predicate": "count_at_least",
        }
        for stat_key, label, singular, plural, _spellings in STAT_TABLE
        if stat_key in present
    ]
    states = [q["current"]["state"] for q in out_rows]
    return {
        "contract": CONTRACT,
        "stats": stats,
        "rows": out_rows,
        "coverage": {
            "scope": COVERAGE_SCOPE,
            "subjects": len({q["subject"]["key"] for q in out_rows}),
            "questions": len(out_rows),
            "quoted": states.count("quoted"),
            "actual_only": states.count("actual_only"),
            "unavailable": states.count("unavailable"),
            "refused": refused,
        },
    }
