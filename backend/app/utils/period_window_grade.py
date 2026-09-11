"""Grade a window-bounded baseball prop off the line score (#1735).

``prop_window`` (#1588) answers *can we prove this prop's window is over?* and
the read path uses it to SUPPRESS: against a false number an absent card is
strictly better. That shipped, and it is half of the ship. #1588's own
acceptance criterion is "a finished event page shows a graded result **or** is
suppressed", so suppression bought the honesty and left the result owed.

This module pays the other half for the one family where the resolution input is
already sitting on the event row: **baseball innings**. ``Event.box_score_data``
carries ``home_period_scores`` / ``away_period_scores`` — a per-inning line score
— on 94 of the 96 finished MLB events of the trailing week (measured
2026-09-10). No venue round-trip, no new ingestion, no price consulted.

WHAT A GRADE IS WORTH HERE, MEASURED
------------------------------------
The specimen Alex saw (event 15308050, Braves 2 – Rays 7, line score
``home [0,0,0,1,0,...]`` / ``away [0,3,0,3,0,...]``) carried 19 ungraded
window-bounded outcomes, every one of them suppressed and therefore invisible.
Graded off the line score, **every one of the 19 agrees with the price the
market was quoting**: "Tampa Bay wins first 5 innings" was 0.99 and Tampa Bay
led the first five 6–1; "Tie 1st inning" was 0.99 and the first inning was 0–0.
Those 0.99s were never wrong numbers. They were unlabelled results — which is
exactly what "settled means settled" says not to serve.

FAIL-SAFE, IN THE SAME DIRECTION AS ``prop_window``
---------------------------------------------------
Every branch defaults to ``None`` — **no grade**, which leaves the row
suppressed and the page exactly as it is today. A grade is published only when
the window, the line score, the outcome's shape AND (where a side is named) the
side are all positively identified. Wrongly withholding a verdict costs the
reader a row they cannot see today anyway; wrongly publishing one prints a false
result next to a game they just watched, which is the bug this whole arc exists
to remove. The asymmetry is the guardrail (gotcha #43).

Four refusals are deliberate and are the ones worth knowing about:

* **Anything but innings.** ``prop_window`` also classifies ``half`` and
  ``quarter`` windows, and the period array is indexed in the SPORT's own unit —
  an NFL line score is quarters, so a "1st half" market spans ``[0:2]`` and not
  ``[0:1]``. Comparing two scales is precisely the mistake ``parse_period_scale``
  exists to prevent, so a non-inning unit is refused rather than guessed. The
  soccer half is the obvious follow-up and needs a per-sport unit map.
* **A short window on a short line score.** A game called after four innings has
  no first-five result. The window must be fully covered by BOTH arrays.
* **A push.** ``_build_props_script`` speaks two words, hit and miss, and a push
  rendered as "miss" is a false verdict. An exact-integer total or an exactly
  covered spread is refused, not rounded. (PropsSection itself already renders a
  ``push``; teaching the builder that third word is a follow-up, not a thing to
  smuggle in here.)
* **An ambiguous side.** "New York" against a Yankees/Mets line matches both, so
  it matches neither. See :func:`_resolve_side`.
"""

from __future__ import annotations

import re

__all__ = ["grade_period_window"]


# A run-scored yes/no question: "First Inning Run", NRFI/YRFI, and Kalshi's
# `KXMLBRFI` series, whose title says nothing (gotcha #16 — prefer the ticker).
_RUN_QUESTION_RE = re.compile(r"\brun\b|\bruns\b|\bnrfi\b|\byrfi\b", re.IGNORECASE)
_RUN_TICKER_RE = re.compile(r"^kxmlbrfi", re.IGNORECASE)

_YES_NAMES = frozenset({"yes"})
_NO_NAMES = frozenset({"no"})

# "Over 3.5 runs in the first 5 innings" / "Under 8.5".
_OVER_UNDER_RE = re.compile(r"^\s*(over|under)\s+(\d+(?:\.\d+)?)\b", re.IGNORECASE)

# "Tampa Bay wins first 5 innings" / "Atlanta wins 1st inning".
_WINS_RE = re.compile(r"^\s*(?P<team>.+?)\s+wins\b", re.IGNORECASE)

# "Tie", "Tie 1st inning", "Draw".
_TIE_RE = re.compile(r"^\s*(?:tie|draw)\b", re.IGNORECASE)

# "Tampa Bay -1.5 first 5 innings" / "Atlanta +2.5".
_SPREAD_RE = re.compile(r"^\s*(?P<team>.+?)\s+(?P<sign>[+-])\s*(?P<line>\d+(?:\.\d+)?)\b")


def _norm(text) -> str:
    """Lowercased, single-spaced, punctuation-light — for team-name comparison only."""
    if not text:
        return ""
    cleaned = re.sub(r"[.'’]", "", str(text)).lower()
    return " ".join(cleaned.split())


def _resolve_side(team_text, home_team_name, away_team_name):
    """``"home"``, ``"away"``, or ``None`` when the name does not name exactly one.

    The outcome wears a SHORT name and the row wears the full one — "Tampa Bay"
    against "Tampa Bay Rays", "Los Angeles A" against "Los Angeles Angels". So
    the test is prefix containment in either direction, and the fail-safe is
    **exactly one** side matching:

    * "New York" on a Yankees/Mets matchup matches both, so it resolves to
      neither. Picking one would print a verdict under the wrong club's name.
    * "Chicago WS" matches neither "Chicago White Sox" nor "Pittsburgh Pirates",
      because "ws" is an abbreviation and not a prefix. That row keeps today's
      behaviour — suppressed — rather than being graded off a guess.

    A permissive matcher is the right tool for LINKING two rows that are probably
    the same fixture and the wrong tool for DISPLAYING a result, so this is
    deliberately its own strict test rather than a reuse of the matcher helpers.
    """
    needle = _norm(team_text)
    if not needle:
        return None

    matches = []
    for side, full_name in (("home", home_team_name), ("away", away_team_name)):
        candidate = _norm(full_name)
        if not candidate:
            continue
        if candidate == needle or candidate.startswith(needle) or needle.startswith(candidate):
            matches.append(side)

    return matches[0] if len(matches) == 1 else None


def _window_totals(first_period, last_period, home_period_scores, away_period_scores):
    """``(home_runs, away_runs)`` over innings ``first_period..last_period``, or ``None``.

    Both bounds are inclusive and 1-based, exactly as
    :func:`app.utils.prop_window.prop_window_span` reports them, so a
    single-inning question sums one inning and "first five" sums five. Reading
    only the END and summing from the top is the bug this signature exists to
    make impossible: on production a "9th Inning Winner" is 51 of the 62
    window-bounded rows a finished MLB page suppresses, and grading it over
    innings 1–9 would publish the GAME's result under the ninth inning's name.

    Refuses unless BOTH arrays cover the whole window with real integers. A
    rain-shortened game has no first-five result, and a ``None`` entry is a hole
    in the line score rather than a zero — summing it as one would publish a
    verdict off a number nobody reported.
    """
    if not isinstance(first_period, int) or not isinstance(last_period, int):
        return None
    if first_period < 1 or last_period < first_period:
        return None
    if not isinstance(home_period_scores, list) or not isinstance(away_period_scores, list):
        return None
    if len(home_period_scores) < last_period or len(away_period_scores) < last_period:
        return None

    totals = []
    for periods in (home_period_scores, away_period_scores):
        window = periods[first_period - 1:last_period]
        # `bool` is an `int` subclass and would sum as 0/1; a line score never
        # holds one, and letting it through would be a silent coercion.
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in window):
            return None
        totals.append(sum(window))
    return (totals[0], totals[1])


def _plural_runs(n: int) -> str:
    return f"{n} run" if n == 1 else f"{n} runs"


def _scoreline(away_runs: int, home_runs: int) -> str:
    """#5086 — the ONE place a period scoreline is composed, always AWAY–HOME.

    This used to be three f-strings following two different rules: a row that
    named a team printed that team's runs first, and the tie row printed HOME
    first. Each is defensible read alone, and together they made one inning
    state itself two ways four lines apart — Alex, on the served specimen:

        Tampa Bay wins first 5 innings   6–1 — hit
        Tie                              1–6 — miss
        Atlanta wins first 5 innings     1–6 — miss

    with nothing on screen saying which side either number belonged to, and the
    FIRST 5 SPREAD block underneath flipping the same five innings the same way.
    His ruling is the contract this helper exists to keep: "whatever order is
    chosen, it has to be chosen once for the whole period block, not per row."

    Away–home is that order because it is already the site's everywhere else —
    the web summary and every native card (`Utilities/EventState.swift`). The
    subject-first rule it replaces was documented as needing "no legend", which
    was true of a row and false of a group; the group is what a reader sees.

    The winner and spread arms still resolve ``mine``/``theirs`` to decide the
    VERDICT. Only the displayed pair is fixed to away–home: this changes what a
    row says, never whether it hit.
    """
    return f"{away_runs}–{home_runs}"


def grade_period_window(
    unit,
    first_period,
    last_period,
    market_name,
    ticker,
    outcome_name,
    home_period_scores,
    away_period_scores,
    home_team_name,
    away_team_name,
):
    """``{"actual": str, "hit": bool}`` for one window-bounded outcome, or ``None``.

    ``unit`` / ``first_period`` / ``last_period`` come straight from
    :func:`app.utils.prop_window.prop_window_span` so the window this grades is,
    by construction, the same window that suppression proved was over — one
    classifier, not two that drift.

    ``actual`` is prose about the number, never a verdict word: the caller
    composes ``f"{actual} — {hit|miss}"`` through ``_build_props_script``, which
    is the site's one settled vocabulary for this slot (#1650 exists because a
    single backend state was wearing three phrasings).

    Every scoreline this function emits is AWAY–HOME, through
    :func:`_scoreline`, whatever the row names — see that helper for why the
    older subject-first rule was withdrawn (#5086).
    """
    if unit != "inning":
        return None

    totals = _window_totals(
        first_period, last_period, home_period_scores, away_period_scores
    )
    if totals is None:
        return None
    home_runs, away_runs = totals
    combined = home_runs + away_runs

    name = str(market_name or "")
    outcome = str(outcome_name or "").strip()
    if not outcome:
        return None
    outcome_key = _norm(outcome)

    # ── Shape A: "was there a run?" ──────────────────────────────────────────
    # Only a yes/no row on a question that is actually about a run being scored.
    # The ticker is authoritative and the title is the fallback (gotcha #16):
    # `KXMLBRFI-26SEP091915TBATL` carries "First Inning Run" nowhere else.
    if outcome_key in _YES_NAMES or outcome_key in _NO_NAMES:
        tick = str(ticker or "")
        if not (_RUN_TICKER_RE.match(tick) or _RUN_QUESTION_RE.search(name)):
            # A bare Yes/No on some other window question — "1st Inning Total"
            # stores a lone `Yes` with no line anywhere on the row, so there is
            # nothing to compare the runs against. Refuse.
            return None
        scored = combined >= 1
        hit = scored if outcome_key in _YES_NAMES else not scored
        return {"actual": _plural_runs(combined), "hit": hit}

    # ── Shape B: over/under on the window's combined runs ────────────────────
    over_under = _OVER_UNDER_RE.match(outcome)
    if over_under:
        line = float(over_under.group(2))
        if combined == line:
            return None  # a push; see the module docstring
        is_over = over_under.group(1).lower() == "over"
        hit = (combined > line) if is_over else (combined < line)
        return {"actual": _plural_runs(combined), "hit": hit}

    # ── Shape C: the window's winner, including the tie leg ──────────────────
    if _TIE_RE.match(outcome):
        return {
            "actual": _scoreline(away_runs, home_runs),
            "hit": home_runs == away_runs,
        }

    wins = _WINS_RE.match(outcome)
    if wins:
        side = _resolve_side(wins.group("team"), home_team_name, away_team_name)
        if side is None:
            return None
        mine, theirs = (home_runs, away_runs) if side == "home" else (away_runs, home_runs)
        return {"actual": _scoreline(away_runs, home_runs), "hit": mine > theirs}

    # ── Shape D: the window's spread ─────────────────────────────────────────
    # Matched last: "Tampa Bay -1.5 first 5 innings" and "Tampa Bay wins first 5
    # innings" both start with a team name, and only the spread carries a signed
    # line, so the winner arm above must have first refusal.
    spread = _SPREAD_RE.match(outcome)
    if spread:
        side = _resolve_side(spread.group("team"), home_team_name, away_team_name)
        if side is None:
            return None
        line = float(spread.group("line"))
        if spread.group("sign") == "-":
            line = -line
        mine, theirs = (home_runs, away_runs) if side == "home" else (away_runs, home_runs)
        margin = (mine - theirs) + line
        if margin == 0:
            return None  # a push; see the module docstring
        return {"actual": _scoreline(away_runs, home_runs), "hit": margin > 0}

    return None
