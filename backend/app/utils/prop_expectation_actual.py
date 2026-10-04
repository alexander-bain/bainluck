"""The AFTER player-props comparison (#10237): saved chance vs final statistic.

PILLARS: FORMATTING / TRUTH. After a supported game a reader sees how likely a
player milestone was before play and whether ESPN's final statistic reached
it, with the final count stated once per player. This module builds the
additive ``after_player_props`` key on ``GET /api/events/{id}/game-markets``.
Every existing key on that response is untouched by it.

Contract: ``10237-AFTER-AUTHORITY-ACK-v1.md`` (Authority, with its 0215Z
addendum), over Live's writer marker ``10237-LIVE-WRITER-ACK-v1.md`` v1.1
(``app/utils/provider_box_evidence.py``). Section marks below (F-1, I-2, E-3,
§5 …) point into the Authority file. Question typing is #10236's
(:func:`app.utils.event_props_matrix.type_prop_row`), called, never re-spelled.

Pure: no I/O, no ORM, no ``routes`` import. The route hands in its own rows,
the event's box dict and its own #5509 pregame gate.

🔴 THE ACTUAL NEVER READS ``hit``. ``_grade_settled_prop`` can fill ``hit``
from ``_venue_typed_hit`` when the box has no answer, so a bare ``hit`` does not
mean "the official statistic reached the threshold" (ruling 003: clients
format, never adjudicate). The actual here is an independent typed channel
read only from a box whose own provider evidence proves it final. A venue's
settlement rides beside it as ``venue_grade`` and never drives ``comparison``.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from app.utils.box_score_capture import BOX_SCORE_SOURCES, box_is_live_capture
from app.utils.event_props_matrix import (
    COVERAGE_SCOPE,
    PERIOD_KEY,
    PERIOD_LABEL,
    STAT_TABLE,
    _team_forms,
    blend_mean,
    normalize_subject,
    type_prop_row,
)

CONTRACT = "10237.v1"
SOURCE_LABEL = "ESPN final statistic"
FINALITY_BASIS = "espn_fresh_box_status_final"
ADMISSION = "pregame_pin_5509"

# §1 — the sports whose ESPN box is this product's official final statistic.
AFTER_SPORTS = frozenset({"baseball_mlb"})

# F-7 — an ALLOWLIST. A status name the reader does not know fails closed, so a
# new ESPN status needs no writer change. The name is pinned against a real
# stored MLB summary in the test file's fixture gate.
FINAL_STATUS_NAMES: dict[str, frozenset[str]] = {
    "baseball_mlb": frozenset({"STATUS_FINAL"}),
}

# §3 — the v1 stat set: stat_key → the batting box key (`_GROUP_STAT_MAP`).
# Batting lines are group-keyed (#1990), so neither can be read as a pitcher's
# hits/home runs allowed. One row here plus one fixture adds a stat.
AFTER_STAT_BOX_KEYS: dict[str, str] = {
    "home_runs": "home runs",
    "hits": "hits",
}

# §6 coverage — legs (source rows) refused, each under the FIRST reason it hits.
REFUSAL_REASONS = (
    "untyped_stat",
    "untyped_predicate",
    "ambiguous_subject",
    "team_subject",
    "under_side",
    "stat_not_in_after_set",
)

# A player's "N+" can never be likelier than their "M+" for M < N. When two
# admitted rungs of one player × stat × period say otherwise, at least one pin
# is wrong and the ladder cannot say which (SD@MIL 15322620: Machado HR 1+
# pinned 0.075, 2+ pinned 0.485 off an empty Polymarket book, #9083). Both
# rungs are withheld. Float slack only — not a policy margin.
LADDER_INVERTED = "ladder_inverted"
_LADDER_SLACK = 1e-9


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


def box_finality(box: Any, espn_id: Any, sport_key: Optional[str]) -> dict:
    """F-1..F-7: is this box ESPN's final statistic for this event?

    Returns ``{"state", "reason", "evidence"}``; ``state`` is ``final``,
    ``pending`` or ``unknown`` and ``reason`` is the FIRST failing test.
    ``evidence`` is the accepted marker once F-1..F-5b pass (pending or final),
    else ``None``.

    Never finality: an absent or False ``live``, ``completed_at``, the served
    status, ``is_winner``, ``hit``, ``resolution_source``, a price or the GET
    time. A retained box keeps its own marker (or none), so a retained live box
    is never final.
    """

    def _no(state: str, reason: str) -> dict:
        return {"state": state, "reason": reason, "evidence": None}

    if sport_key not in AFTER_SPORTS:
        return _no("unknown", "sport_not_supported")
    evidence = box.get("provider_box_evidence") if isinstance(box, dict) else None
    if not isinstance(evidence, dict):
        return _no("unknown", "no_provider_evidence")
    if evidence.get("evidence_kind") != "fresh_provider_box" or evidence.get("provider") != "espn":
        return _no("unknown", "evidence_kind_not_accepted")
    # Re-checked at READ time: a later re-key of `espn_id` cannot carry an old box.
    expected = str(espn_id).strip() if espn_id is not None else ""
    returned = evidence.get("provider_event_id")
    if not expected or not isinstance(returned, str) or returned != expected:
        return _no("unknown", "provider_event_mismatch")
    captured = evidence.get("captured_at")
    if not isinstance(captured, str) or not captured or captured != box.get("fetched_at"):
        return _no("unknown", "evidence_clock_mismatch")
    players = box.get("players")
    if not isinstance(players, dict) or not players:
        return _no("unknown", "evidence_box_empty")
    if box_is_live_capture(box):
        return {"state": "pending", "reason": "live_capture", "evidence": evidence}
    status = evidence.get("provider_status")
    status = status if isinstance(status, dict) else {}
    if not (
        evidence.get("provider_final") is True
        and status.get("completed") is True
        and status.get("name") in FINAL_STATUS_NAMES.get(sport_key, frozenset())
    ):
        return {"state": "pending", "reason": "provider_not_final", "evidence": evidence}
    return {"state": "final", "reason": None, "evidence": evidence}


def _box_identity(box: dict, subject_key: str) -> dict:
    """I-1/I-2: the ONE `(athlete_id, team_id)` whose name normalises to the key.

    `_parse_boxscore` keys the numeric box by display name and MERGES two
    athletes who share one, so uniqueness is decided here, on the identity
    list, before any stat is read. An entry under this name without both ids
    is counted as a second identity: a dropped twin must not make a shared
    name look unique.
    """
    pairs: set[tuple[str, str]] = set()
    names: set[str] = set()
    malformed = False
    for entry in box.get("player_identities") or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or normalize_subject(name) != subject_key:
            continue
        athlete_id = str(entry.get("athlete_id") or "").strip()
        team_id = str(entry.get("team_id") or "").strip()
        if athlete_id and team_id:
            pairs.add((athlete_id, team_id))
        else:
            malformed = True
        names.add(name)
    if not names:
        return {"reason": "player_not_in_box"}
    if malformed or len(pairs) != 1 or len(names) != 1:
        return {"reason": "ambiguous_player"}
    (athlete_id, team_id), = pairs
    return {"athlete_id": athlete_id, "team_id": team_id, "name": names.pop()}


def _count_value(value: Any) -> Optional[int]:
    """I-4: a finite non-negative integer count; `2.0` is 2, `2.5` is refused."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0 or value != int(value):
        return None
    return int(value)


def record_version(
    provider: str, provider_event_id: str, athlete_id: str, team_id: str,
    stat_key: str, period_key: str, value: int,
) -> str:
    """§5: what changes when the STATISTIC changes, and only then.

    ``captured_at`` is excluded on purpose: a re-fetch of an unchanged box is a
    heartbeat, not a correction. A 2→1 correction changes the version.
    """
    canonical = json.dumps(
        [provider, provider_event_id, athlete_id, team_id, stat_key, period_key, value],
        separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_actual(
    box: Any, finality: dict, subject_key: str, subject_label: str, stat_key: str,
) -> dict:
    """One player × stat actual: F-1..F-7, then I-1..I-4.

    A missing player is ``unknown`` / ``player_not_in_box``, never DNP and never
    zero; v1 emits no ``not_applicable`` (an ESPN MLB box carries no positive
    participation record). A verified final ``0`` is a real zero.
    """
    actual = {
        "actual_key": f"s:{subject_key}|{stat_key}|{PERIOD_KEY}",
        "subject": {"key": subject_key, "label": subject_label, "kind": "player"},
        "stat_key": stat_key,
        "period_key": PERIOD_KEY,
        "state": finality["state"],
        "reason": finality["reason"],
        "value": None,
        "source_label": None,
        "provider": None,
        "provider_event_id": None,
        "athlete_id": None,
        "team_id": None,
        # Retrieval evidence, not play or correction time. Present once the
        # marker is accepted (pending or final).
        "captured_at": None,
        "finality_basis": None,
        "record_version": None,
    }
    evidence = finality["evidence"]
    if evidence is not None:
        actual["provider"] = evidence["provider"]
        actual["provider_event_id"] = evidence["provider_event_id"]
        actual["captured_at"] = evidence["captured_at"]
    if finality["state"] != "final":
        return actual

    def _unknown(reason: str) -> dict:
        return {**actual, "state": "unknown", "reason": reason}

    identity = _box_identity(box, subject_key)
    if "reason" in identity:
        return _unknown(identity["reason"])
    line = box["players"].get(identity["name"])
    box_key = AFTER_STAT_BOX_KEYS[stat_key]
    if not isinstance(line, dict) or box_key not in line:
        return _unknown("stat_missing")
    value = _count_value(line[box_key])
    if value is None:
        return _unknown("stat_not_integer_count")
    actual.update({
        "value": value,
        "source_label": SOURCE_LABEL,
        "athlete_id": identity["athlete_id"],
        "team_id": identity["team_id"],
        "finality_basis": FINALITY_BASIS,
        "record_version": record_version(
            evidence["provider"], evidence["provider_event_id"],
            identity["athlete_id"], identity["team_id"], stat_key, PERIOD_KEY, value,
        ),
    })
    return actual


def admit_pin(
    pregame_mark: Any,
    outcome_id: Any,
    commence_time: Any,
    is_pregame: Callable[[Any, Any], bool],
) -> dict:
    """E-1..E-3: one contributor's saved pregame chance, or why there is none.

    The value is the pin AS STORED for this over outcome. The #5509 gate is the
    route's ``_pregame_mark_is_pregame``, passed in and called. E-3 is one
    stricter precondition: that gate treats an unjudgeable pin as pregame, and
    an unjudged pin is no proof for a number labelled "saved pregame chance".
    The opening line, the representative ``pregame_mark`` on a ``player_props``
    row, a terminal price and ingestion time are never admitted.
    """
    raw = None
    if isinstance(pregame_mark, dict):
        raw = (pregame_mark.get("outcomes") or {}).get(str(outcome_id))
    value = _finite_probability(raw)
    if value is None:
        return {"reason": "no_pregame_pin"}
    if not is_pregame(pregame_mark, commence_time):
        return {"reason": "pin_after_start"}
    clock = None
    for key in ("observed_at", "captured_at"):
        if _parse_stamp(pregame_mark.get(key)) is not None:
            clock = pregame_mark[key]
            break
    commence = _parse_stamp(commence_time) or _parse_stamp(pregame_mark.get("commence_time"))
    if clock is None or commence is None:
        return {"reason": "pin_unjudgeable"}
    return {"probability": value, "observed_at": clock}


def _expectation(legs: list[dict], pins: list[dict]) -> dict:
    """§4 value rule: 0 admitted → unavailable; 1 → single_source; ≥2 → the
    shared 9b mean over the admitted pins (equivalence is the question key)."""
    contributors, excluded = [], []
    for leg, pin in zip(legs, pins):
        if "reason" in pin:
            excluded.append({
                "source": leg["source"], "outcome_id": leg["outcome_id"], "reason": pin["reason"],
            })
            continue
        contributors.append({
            "source": leg["source"],
            "market_id": leg["market_id"],
            "outcome_id": leg["outcome_id"],
            "outcome_name": leg["outcome_name"],
            "probability": pin["probability"],
            "observed_at": pin["observed_at"],
            "admission": ADMISSION,
        })
    if not contributors:
        return {
            "state": "unavailable", "reason": "no_admitted_pin", "probability": None,
            "basis": None, "observed_at": None, "contributors": [], "excluded": excluded,
        }
    return {
        "state": "available",
        "reason": None,
        "probability": blend_mean(c["probability"] for c in contributors),
        "basis": "single_source" if len(contributors) == 1 else "blend_mean",
        # The latest admitted pin's own clock — never a quote clock.
        "observed_at": max(
            (c["observed_at"] for c in contributors), key=lambda s: _parse_stamp(s)
        ),
        "contributors": contributors,
        "excluded": excluded,
    }


def _withhold_inverted_ladders(questions: list[dict]) -> None:
    """Withhold BOTH rungs of every inverted pair within one ladder (see
    ``LADDER_INVERTED``). Each withheld contributor moves to ``excluded``
    under that reason, so the evidence stays on the payload."""
    ladders: dict[str, list[dict]] = {}
    for q in questions:
        if q["expectation"]["state"] == "available":
            ladders.setdefault(q["actual_key"], []).append(q)
    for rungs in ladders.values():
        rungs.sort(key=lambda q: q["predicate"]["count"])
        inverted: set[int] = set()
        for i, lower in enumerate(rungs):
            for j in range(i + 1, len(rungs)):
                upper = rungs[j]
                if (
                    upper["predicate"]["count"] > lower["predicate"]["count"]
                    and upper["expectation"]["probability"]
                    - lower["expectation"]["probability"] > _LADDER_SLACK
                ):
                    inverted.update((i, j))
        for k in inverted:
            exp = rungs[k]["expectation"]
            rungs[k]["expectation"] = {
                "state": "unavailable", "reason": LADDER_INVERTED, "probability": None,
                "basis": None, "observed_at": None, "contributors": [],
                "excluded": exp["excluded"] + [
                    {"source": c["source"], "outcome_id": c["outcome_id"], "reason": LADDER_INVERTED}
                    for c in exp["contributors"]
                ],
            }


def _venue_grade(legs: list[dict]) -> Optional[dict]:
    """§5: a venue's own settlement, verbatim, kept apart from the comparison.

    Only a ``resolution_source`` outside ``BOX_SCORE_SOURCES`` (a box-computed
    verdict is not the venue's word). Never ``hit``, never ``_venue_typed_hit``.
    The first contributor in source order that carries one.
    """
    for leg in legs:
        source = leg["row"].get("resolution_source")
        if source is not None and source not in BOX_SCORE_SOURCES:
            return {"is_winner": leg["row"].get("is_winner"), "resolution_source": source}
    return None


def build_after_player_props(
    rows: list[dict],
    *,
    box_score_data: Any,
    espn_id: Any,
    sport_key: Optional[str],
    player_and_stat: Callable[[Optional[str], Optional[str]], tuple[str, str]],
    pregame_mark_by_market_id: dict,
    is_pregame: Callable[[Any, Any], bool],
    commence_time: Any,
    home_team: Optional[str],
    away_team: Optional[str],
) -> Optional[dict]:
    """The ``after_player_props`` object, or ``None`` when no question types.

    ``rows`` is the route's deep copy of the prop candidates taken BEFORE step
    9 (the #10236 population). The CALLER gates on the event being finished;
    this function never looks at a clock or a served status.
    """
    refused = {reason: 0 for reason in REFUSAL_REASONS}
    team_forms = _team_forms(home_team, away_team)
    source_rank = {"kalshi": 0, "polymarket": 1}

    legs_by_question: dict[str, list[dict]] = {}
    typed_by_question: dict[str, dict] = {}
    for row in rows:
        typed = type_prop_row(
            row.get("market_name"), row.get("outcome_name"), player_and_stat, team_forms
        )
        if "refused" in typed:
            refused[typed["refused"]] += 1
            continue
        if typed["side"] != "over":
            refused["under_side"] += 1
            continue
        if typed["stat_key"] not in AFTER_STAT_BOX_KEYS:
            refused["stat_not_in_after_set"] += 1
            continue
        outcome_ids = list(row.get("contributor_outcome_ids") or [])
        legs_by_question.setdefault(typed["question_key"], []).append({
            "row": row,
            "typed": typed,
            "source": row.get("source"),
            "market_id": row.get("_market_id"),
            "outcome_id": outcome_ids[0] if len(outcome_ids) == 1 else None,
            "outcome_name": row.get("outcome_name"),
        })
        typed_by_question.setdefault(typed["question_key"], typed)

    if not legs_by_question:
        return None

    finality = box_finality(box_score_data, espn_id, sport_key)
    questions: list[dict] = []
    for qkey, legs in legs_by_question.items():
        legs.sort(key=lambda l: (
            source_rank.get(l["source"], len(source_rank)),
            l["outcome_id"] if isinstance(l["outcome_id"], int) else float("inf"),
        ))
        typed = typed_by_question[qkey]
        pins = [
            admit_pin(
                pregame_mark_by_market_id.get(l["market_id"]), l["outcome_id"],
                commence_time, is_pregame,
            )
            for l in legs
        ]
        questions.append({
            "question_key": qkey,
            "actual_key": f"s:{typed['subject_key']}|{typed['stat_key']}|{PERIOD_KEY}",
            # A2: original case from the first contributor, as #10236 labels it.
            "subject": {"key": typed["subject_key"], "label": legs[0]["typed"]["subject_label"], "kind": "player"},
            "stat_key": typed["stat_key"],
            "period_key": PERIOD_KEY,
            "predicate": {
                "kind": typed["kind"],
                "count": typed["count"],
                "side": typed["side"],
                "label": f"{typed['count']}+",
            },
            "expectation": _expectation(legs, pins),
            "comparison": None,
            "venue_grade": _venue_grade(legs),
            "_market_ids": sorted({l["market_id"] for l in legs if l["market_id"] is not None}),
            "contributor_outcome_ids": sorted({
                oid for l in legs for oid in (l["row"].get("contributor_outcome_ids") or [])
            }),
        })
    _withhold_inverted_ladders(questions)
    # Server-written order; clients key on it and never index.
    questions.sort(key=lambda q: (q["stat_key"], q["subject"]["label"], q["predicate"]["count"]))

    # The actual is built ONCE per player × stat (the first question in served
    # order names it), so "the final count once per player" is structural.
    actuals: dict[str, dict] = {}
    for q in questions:
        actual = actuals.get(q["actual_key"])
        if actual is None:
            actual = actuals[q["actual_key"]] = build_actual(
                box_score_data, finality, q["subject"]["key"], q["subject"]["label"], q["stat_key"],
            )
        if actual["state"] == "final":
            reached = actual["value"] >= q["predicate"]["count"]
            q["comparison"] = {"state": "reached" if reached else "below", "reason": None}
        else:
            q["comparison"] = {"state": "unknown", "reason": actual["reason"]}

    actual_rows = sorted(actuals.values(), key=lambda a: (a["stat_key"], a["subject"]["label"]))
    present = {q["stat_key"] for q in questions}
    stats = [
        {
            "stat_key": stat_key,
            "label": label,
            "unit_singular": singular,
            "unit_plural": plural,
            "period_key": PERIOD_KEY,
            "period_label": PERIOD_LABEL,
            "predicate": "count_at_least",
        }
        for stat_key, label, singular, plural, _spellings in STAT_TABLE
        if stat_key in present
    ]
    states = [a["state"] for a in actual_rows]
    return {
        "contract": CONTRACT,
        "stats": stats,
        "actuals": actual_rows,
        "questions": questions,
        "coverage": {
            "scope": COVERAGE_SCOPE,
            "questions": len(questions),
            "actuals": len(actual_rows),
            "final": states.count("final"),
            "pending": states.count("pending"),
            "unknown": states.count("unknown"),
            "expectation_available": sum(
                1 for q in questions if q["expectation"]["state"] == "available"
            ),
            "refused": refused,
        },
    }
