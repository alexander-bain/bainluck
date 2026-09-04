"""live/059 addendum (D59 = A′) — THE SCORE LINE IS ATOMIC.

Alex's framing, and it is the whole specification:

    When a tennis match carries a StatPal anchor, the whole line — sets, games,
    points, server — comes from StatPal's livescores; otherwise sets + games
    from ESPN. **Never one field from each.** State (live/over/winner) stays
    ESPN's; if they disagree, ESPN's state + the linked source's last score with
    its own "as of" stamp.

═══ WHY ATOMICITY IS THE RULE AND NOT AN OPTIMISATION ═══

The tempting build is a field-wise merge: take sets from whoever has them, take
points from StatPal because ESPN has none, take the server from StatPal for the
same reason. It reads as strictly more information. It is not — it is a score
line that never existed.

Two feeds observe the same match at different instants. StatPal's livescores
board and ESPN's scoreboard are seconds to a minute apart, and a tennis game
turns over in well under a minute. A merged line therefore prints, routinely:

    sets from ESPN          6-4, 3-3        (as of 21:44:02)
    points from StatPal     40-30, Zverev   (as of 21:44:51, at 6-4, 4-3)

— a game score belonging to a game that is not the one the sets describe. Nobody
can tell, because both halves are true and the composite is false. There is no
"as of" a reader could apply to it, because it has two.

So the selector picks a SOURCE, once, per match, and takes the whole line from
it. The line then has one clock, and that clock is stamped on it.

═══ WHAT ESPN KEEPS, AND WHY IT IS NOT AN EXCEPTION ═══

STATE — live / over / who won — stays ESPN's under D27, and that does not
violate atomicity because state is not the score. The score line answers "what
is the score"; the state answers "is this match still being played". They are
two questions, they come off two authorities on purpose, and the payload names
both (`source` and `state_source`) so no renderer has to assume.

When the two disagree — ESPN says the match is over, StatPal's board still shows
it in play — the rule is ESPN's state with the linked source's LAST score and
its own stamp. Not StatPal's state, and not ESPN's score. A finished match whose
final line reads one game short with an honest `score_as_of` is a small,
self-describing wrongness that corrects on the next poll; a line assembled from
both is a large, invisible one that never corrects.

═══ HOW "A MIXED LINE IS IMPOSSIBLE" IS ENFORCED, NOT ASSERTED ═══

Three mechanisms, and the test file names each one:

  1. :func:`select_line` takes two WHOLE payloads and returns one of them. There
     is no code path that reads a score field out of the payload it did not
     choose — not "there is no such path today", but no such parameter.
  2. :data:`SCORE_FIELDS` and :data:`STATE_FIELDS` partition the payload. The
     composition copies each set from exactly one side, and
     :func:`assert_atomic` re-derives the check at runtime.
  3. `assert_atomic` is called on the way OUT of `select_line`, so a future edit
     that hand-copies one field across raises where it is written rather than
     rendering in New York.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.utils.espn_tennis_anchor import (
    SCORE_NOT_PLAYED,
    SCORE_ORIENTATION_UNRESOLVED,
    orient_sides,
)
from app.utils.tennis_linescore import (
    LINESCORE_NO_LINE,
    LINESCORE_UNIT,
    format_line,
)

#: The two sources a tennis line may come from. There is no third and no "mixed"
#: — a value this enum cannot express is a line this system cannot produce.
SOURCE_ESPN = "espn"
SOURCE_STATPAL = "statpal"

#: THE SCORE. Every one of these comes from the chosen source, together, always.
#: `points` and `serving` are in the set even though ESPN never publishes them:
#: an ESPN line carries them as ``None``, which is the honest answer ("this
#: source does not say"), where omitting the keys would let a renderer fall back
#: to some other object and rebuild the merge this module exists to prevent.
SCORE_FIELDS = frozenset({
    "unit", "sets", "current_set", "sets_won", "games",
    "points", "serving", "line", "observed_at",
})

#: THE STATE. ESPN's, under D27, whichever source the score came from.
STATE_FIELDS = frozenset({
    "state", "completion", "status_detail", "was_suspended",
})

#: StatPal's own words for a match in play, lowercased. Its tennis board reports
#: the SET rather than a state word — "Set 2", "Set 3" — so the live test is a
#: prefix, not a membership check. Measured on the live board 2026-09-04:
#: ``{"Finished": 4, "Set 2": 2, "Not Started": 47}``.
STATPAL_LIVE_PREFIXES = ("set ", "in play", "live")
STATPAL_FINISHED = ("finished", "final", "ended", "retired", "walkover")
STATPAL_SCHEDULED = ("not started", "scheduled")

#: 🔴 **ESPN'S WORDS, NOT OURS (CERT-881).** `espn_tennis.scoreboard_competitions`
#: publishes exactly three states — ``upcoming``, ``in_progress``, ``decided`` —
#: and `_states_disagree` compares StatPal's mapped word against that string. A
#: translation that lands on any OTHER word makes two feeds that agree the match
#: is over report a disagreement, and the page prints "score as of …" over a
#: final score forever. There is no third vocabulary in this file; if ESPN's
#: words change, these are the constants that change with them.
STATE_UPCOMING = "upcoming"
STATE_IN_PROGRESS = "in_progress"
STATE_DECIDED = "decided"


class MixedLineError(AssertionError):
    """A score line was assembled from more than one source. Never raise-and-catch.

    This is not an input-validation error — a caller cannot cause it with bad
    data. It can only be caused by an EDIT to the composition, which is why it
    is an AssertionError subclass and why it is raised rather than logged.
    """


# ---------------------------------------------------------------------------
# The StatPal reader — the finer grain, in our orientation
# ---------------------------------------------------------------------------


def _statpal_int(value: Any) -> Optional[int]:
    """StatPal publishes every number as a string, and "" for "not yet".

    ``""`` must read as None and never as 0 — an unplayed set scored 0-0 is a
    set that is being played badly, not a set that has not started (gotcha #53).
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _statpal_bool(value: Any) -> bool:
    """StatPal's booleans are the strings ``"True"`` / ``"False"``."""
    return str(value).strip().lower() == "true"


def statpal_state(raw_status: Any) -> Optional[str]:
    """StatPal's status word translated into ESPN'S state vocabulary, or None.

    Returned for comparison only. It never reaches the payload — the payload's
    state is ESPN's — but the disagreement has to be nameable before it can be
    reported, and a rule that cannot describe the disagreement it handles is a
    rule nobody can check.

    🔴 **THE TARGET VOCABULARY IS ESPN'S, AND THAT IS THE ENTIRE POINT.** This
    used to answer ``"final"`` for ``Finished`` and ``"scheduled"`` for ``Not
    Started`` — our words, for a value whose only consumer compares it to
    ESPN's ``decided`` / ``upcoming``. Two feeds that agreed a match was over
    therefore always disagreed, and every finished match on the board carried
    the stale-score caveat. A translation that keeps its own dialect is not a
    translation.
    """
    text = str(raw_status or "").strip().lower()
    if not text:
        return None
    if any(text.startswith(p) for p in STATPAL_LIVE_PREFIXES):
        return STATE_IN_PROGRESS
    if any(word in text for word in STATPAL_FINISHED):
        return STATE_DECIDED
    if any(word in text for word in STATPAL_SCHEDULED):
        return STATE_UPCOMING
    return None


def statpal_linescore(
    ours: list[str],
    match: dict[str, Any],
    *,
    observed_at: datetime,
) -> dict[str, Any]:
    """The StatPal line for one match, in OUR home/away order.

    ``match`` is one entry from a ``/v1/tennis/livescores`` tournament's
    ``match`` list — the raw shape, not :class:`StatPalFixture`, because the
    fixture dataclass drops ``game_score`` and ``serve`` and those two fields are
    the entire reason this source is preferred.

    Returns ``{"linescore": dict | None, "reason": str | None}`` — the SAME
    contract as :func:`tennis_linescore.authority_linescore`, deliberately, so
    :func:`select_line` never has to know which reader produced its inputs.

    Orientation is :func:`espn_tennis_anchor.orient_sides`, imported and not
    reimplemented, for the reason that function's own docstring gives: a second
    copy of the rule is a second chance to reverse a scoreline, and a reversed
    line is worse than a blank because a blank is visibly missing.
    """
    players = match.get("player")
    if not isinstance(players, list) or len(players) != 2:
        return {"linescore": None, "reason": SCORE_NOT_PLAYED}

    oriented = orient_sides(ours, players)
    if oriented is None:
        return {"linescore": None, "reason": SCORE_ORIENTATION_UNRESOLVED}
    home, away = oriented

    rows: list[dict[str, Any]] = []
    for key in ("s1", "s2", "s3", "s4", "s5"):
        home_games = _statpal_int(home.get(key))
        away_games = _statpal_int(away.get(key))
        rows.append({
            "home": home_games,
            "away": away_games,
            # StatPal's tennis board publishes no per-set tiebreak points (only
            # the match-level `tb` flag), so the bracket is genuinely absent
            # rather than dropped. `format_set` prints no bracket for None,
            # which is the right answer: guessing the loser's points is how a
            # 7-5 tiebreak comes to read as the opposite result.
            "home_tiebreak": None,
            "away_tiebreak": None,
            # NO PER-SET WINNER FLAG EITHER, so the set winner is derived from
            # the games — and it is only sound because the derivation is fenced:
            # a set is awarded only when it is COMPLETE by the rules of tennis
            # (see `_set_won_by`). An abandoned set stays unawarded, which is
            # the property ESPN's flag was protecting.
            "won_by": _set_won_by(home_games, away_games),
        })
    while rows and rows[-1]["home"] is None and rows[-1]["away"] is None:
        rows.pop()
    if not rows:
        return {"linescore": None, "reason": LINESCORE_NO_LINE}

    state = statpal_state(match.get("status"))
    current_set: Optional[int] = None
    if state == "in_progress":
        for index in range(len(rows) - 1, -1, -1):
            if rows[index]["won_by"] is None:
                current_set = index + 1
                break

    home_points = str(home.get("game_score") or "").strip() or None
    away_points = str(away.get("game_score") or "").strip() or None
    serving: Optional[str] = None
    if _statpal_bool(home.get("serve")):
        serving = "home"
    elif _statpal_bool(away.get("serve")):
        serving = "away"

    return {
        "linescore": {
            "source": SOURCE_STATPAL,
            "statpal_fixture_id": str(match.get("id") or "") or None,
            "unit": LINESCORE_UNIT,
            "sets": rows,
            "current_set": current_set,
            "sets_won": {
                "home": _statpal_int(home.get("totalscore")) or 0,
                "away": _statpal_int(away.get("totalscore")) or 0,
            },
            "games": {
                "home": sum(r["home"] for r in rows if r["home"] is not None),
                "away": sum(r["away"] for r in rows if r["away"] is not None),
            },
            # THE TWO FIELDS THAT JUSTIFY THIS SOURCE. Only published while a
            # match is in play; "" off the board reads as None, not as "0-0".
            "points": (
                {"home": home_points, "away": away_points}
                if (home_points or away_points) else None
            ),
            "serving": serving,
            "line": format_line(rows),
            # OUR read, not StatPal's write — StatPal publishes no per-match
            # write timestamp, so a consumer measuring freshness is measuring
            # our read and the field name says so.
            "observed_at": observed_at.isoformat(),
            # For the disagreement report only; never rendered as the state.
            "reported_state": state,
        },
        "reason": None,
    }


def _set_won_by(home: Optional[int], away: Optional[int]) -> Optional[str]:
    """Who won this set, or None — and None for everything that is not certain.

    ESPN publishes a per-set winner flag and :func:`tennis_linescore._set_rows`
    reads it. StatPal publishes only the games, so the flag has to be derived,
    and a naive "whoever has more" hands an ABANDONED set to whoever was ahead
    in it — the exact inversion `authority_score` refuses 5 of 6 retirements
    over.

    So the derivation is fenced by the rules of tennis: a set is won at 6 with a
    two-game margin, at 7 over 5 or 6 (the 7-6 tiebreak included), and never
    otherwise. ``3-1`` when a player retires is left unawarded, which is what it
    is — an unfinished set, not a 1-0 win.
    """
    if home is None or away is None:
        return None
    high, low = max(home, away), min(home, away)
    won = (high == 6 and low <= 4) or (high == 7 and low in (5, 6))
    if not won:
        return None
    return "home" if home > away else "away"


# ---------------------------------------------------------------------------
# The selector — one source per match, whole
# ---------------------------------------------------------------------------


def select_line(
    *,
    espn: Optional[dict[str, Any]],
    statpal: Optional[dict[str, Any]],
    has_statpal_anchor: bool,
) -> Optional[dict[str, Any]]:
    """THE SWITCH. One source for the whole score line, ESPN for the state.

    ``espn`` and ``statpal`` are complete linescore payloads (the ``linescore``
    value from :func:`tennis_linescore.authority_linescore` and
    :func:`statpal_linescore`) or ``None`` when that source refused. Returns one
    composed payload, or ``None`` when neither source has a line.

    THE RULE, in the order it is applied:

      1. **A StatPal anchor makes StatPal the score.** Not "StatPal if it looks
         better" and not "StatPal for the fields ESPN lacks" — the anchor is the
         join that says this row IS that match, and once it exists StatPal's
         board is the finer view of the same thing. `has_statpal_anchor` is
         passed rather than inferred from `statpal is not None`, because an
         unanchored name-match is exactly the wrong reason to switch sources.
      2. **No anchor, or an anchored source that refused, falls back to ESPN
         WHOLE.** A StatPal payload that came back `None` is a source that said
         nothing; the answer is ESPN's entire line, never ESPN's line with
         StatPal's points bolted on — that is the mixed line.
      3. **ESPN always owns the state**, including when only StatPal has a
         score. When they disagree the payload says so in `state_disagrees` and
         carries `score_as_of` — the chosen source's own stamp — so the reader
         is told the score is a moment old rather than shown a line that
         pretends otherwise.

    Raises :class:`MixedLineError` if the composition it just built is not
    atomic. That cannot happen from data; it can only happen from an edit.
    """
    chosen_name = SOURCE_ESPN
    chosen = espn
    if has_statpal_anchor and statpal is not None:
        chosen_name = SOURCE_STATPAL
        chosen = statpal
    if chosen is None:
        # The anchored source refused and ESPN also has nothing — or the other
        # way round. Fall back to whichever single source DID answer, whole.
        chosen = statpal if espn is None else espn
        chosen_name = SOURCE_STATPAL if espn is None else SOURCE_ESPN
    if chosen is None:
        return None

    out: dict[str, Any] = {}
    # THE SCORE — every field, from ONE payload, by iteration over the field set
    # rather than by naming them one at a time. A field written by hand is a
    # field that can be written from the other side.
    for field in SCORE_FIELDS:
        out[field] = chosen.get(field)

    # THE STATE — ESPN's, always, under D27. When ESPN refused entirely there is
    # no state to take and the payload says `None` rather than borrowing
    # StatPal's: a state word from the source that is not the state authority is
    # precisely the mix this module forbids, in the field where it would be
    # least visible.
    state_holder = espn or {}
    for field in STATE_FIELDS:
        out[field] = state_holder.get(field)

    out["source"] = chosen_name
    out["state_source"] = SOURCE_ESPN if espn is not None else None
    # The chosen source's OWN clock, named so a renderer can print "as of".
    out["score_as_of"] = chosen.get("observed_at")
    out["state_disagrees"] = _states_disagree(espn, statpal)
    for key in ("espn_competition_id", "statpal_fixture_id"):
        if chosen.get(key) is not None:
            out[key] = chosen[key]

    assert_atomic(out, espn=espn, statpal=statpal)
    return out


def _states_disagree(
    espn: Optional[dict[str, Any]], statpal: Optional[dict[str, Any]]
) -> bool:
    """Whether the two feeds currently describe different match states.

    False when either side is silent — an absence is not a disagreement, and
    reporting one would put an "as of" caveat on every match ESPN alone covers.
    """
    if not espn or not statpal:
        return False
    theirs = statpal.get("reported_state")
    if theirs is None:
        return False
    return theirs != espn.get("state")


def assert_atomic(
    line: dict[str, Any],
    *,
    espn: Optional[dict[str, Any]],
    statpal: Optional[dict[str, Any]],
) -> None:
    """Every score field came from the source the payload NAMES. Or raise.

    Re-derives the invariant from the output rather than trusting the code that
    built it: for each field in :data:`SCORE_FIELDS`, the value must equal the
    named source's value for that field. A hand-copied field from the other side
    fails here — unless the two sources happen to agree on it, in which case
    there is nothing to detect and nothing to be wrong about.

    This is the runtime half of "a mixed line is impossible". The compile-time
    half is that :func:`select_line` never receives a field, only two payloads.
    """
    named = line.get("source")
    source = {SOURCE_ESPN: espn, SOURCE_STATPAL: statpal}.get(named)
    if source is None:
        raise MixedLineError(
            f"line names source {named!r} but that source produced no payload"
        )
    for field in SCORE_FIELDS:
        if line.get(field) != source.get(field):
            raise MixedLineError(
                f"score field {field!r} does not match the named source "
                f"{named!r} — the line is mixed"
            )
