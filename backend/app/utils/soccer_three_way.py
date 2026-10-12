"""#1011 — the soccer three-way calibration contract, in one place.

Soccer's game winner is a three-way question: home, draw, away. Until
2026-09-16 every sportsbook reading of it was stored as a two-way pair
renormalized to sum to 1.0, so the draw's ~25% of the mass was folded into the
two named sides. Those rows were excluded from the accuracy curve in July
(Queue #158) because the draw was never stored and cannot be put back.

**WHAT CHANGED, AND WHEN — the cutoff below is a release time, not a guess.**
``_parse_snapshot_values`` (``tasks/odds_polling.py``) was rewritten to de-vig
over every outcome the book quotes (``utils/odds_math.h2h_pair_on_the_full_board``,
PR #6581, merged as 52c36019a) and went live in release **v4636 at
2026-09-16T17:43:41Z**. Live's after-check on #1011 read the first re-polled
rows at 17:45:40Z and 17:47:43Z, with `betting` moving onto the three-way scale
on every specimen (Besiktas v Marseille 0.6897 → 0.5278 against Kalshi 0.535).

**WHAT THE STORED NUMBERS MEAN NOW — derived from the writers, not assumed.**

* ``odds_snapshots.home_win_probability`` / ``away_win_probability`` are one
  book's two named legs de-vigged over the WHOLE board. On a board that quotes a
  draw they sum to about 0.74 and the draw is the remainder,
  ``1 - home - away``. The writer never names the draw and never consults the
  sport; on a genuinely two-way board the pair still sums to 1.0.
* ``events.opening_home_probability`` / ``opening_away_probability`` are the
  per-leg MEDIANS of those snapshots, written together by
  ``_maybe_set_opening_odds`` on every poll until kickoff — so the last write
  is the last pre-kickoff consensus, and the pair keeps the draw's remainder.
* ``events.closing_away_probability`` is written as ``1 - closing_home`` by
  ``_backfill_closing_lines``. The closing PAIR therefore always sums to 1.0
  and cannot carry the draw; it is not read by the three-way arm.

**WHY A ROW IS ALSO PROVEN, NOT ONLY DATED.** A row from before the cutoff is a
renormalized pair: its two legs, each rounded to four places, sum to 1.0 within
0.0001. A three-way row leaves the draw's remainder. Requiring that remainder
to be at least :data:`SOCCER_DRAW_RESIDUAL_MIN` (100x the rounding error, and
below any draw price a book offers on a 90-minute market) means a row is
graded three-way only when its own numbers say the draw is in them. A
two-way-shaped soccer row after the cutoff — a board the writer read as
two outcomes — is not graded three-way and stays excluded, rather than being
graded as two losses on a drawn match.

**THE GRADE.** Three outcomes per reading: home wins, away wins, and the draw
(equal scores). Drawn matches are IN the population; a two-way arm drops them,
which is only honest for a pair that was renormalized conditional on no draw.

**THE SCORE MUST BE THE 90-MINUTE SCORE (CERT-4066).** A soccer game winner
settles on regulation time. A knockout tie that is level after 90 minutes and
won in extra time or on penalties is a DRAW for this market, but its stored
final score names a winner. We store no regulation score, and guessing one
from the final is not allowed, so a match is admitted only when its own row
says it ENDED at full time:

* ``events.period == "FT"`` — the sync writes ESPN's ``status.type.detail``
  into ``period`` (``espn_helpers._sanitize_period``); #2908 records it writing
  ``FT`` on a match ESPN finished at full time. Extra-time and shootout
  finishes are separate ESPN statuses (``STATUS_FINAL_AET``,
  ``STATUS_FINAL_PEN``; census in ``services/espn_api.espn_terminal_state``:
  5,572 full time, 7 after extra time, 57 on penalties), and exact equality
  refuses whatever detail they carry; or
* ``box_score_data.provider_box_evidence.provider_status.name ==
  "STATUS_FULL_TIME"`` — ESPN's own status name, stored with a fresh box.

Anything else — an extra-time or penalty finish, a row no provider finished
with a status, a period left at a live token — is regulation UNPROVEN and stays
excluded, counted with the rest. Exact equality is the fail-closed form: a new
or unexpected spelling refuses rather than admits.

Pure module: no app imports, no I/O. The SQL that applies this contract binds
:data:`SOCCER_THREE_WAY_PARAMS`, and the Python twin below is what the unit
tests pin it against.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

#: Release v4636 (52c36019a, PR #6581) — the minute the full-board de-vig went
#: live. A soccer reading captured, or a match kicked off, before this has no
#: draw in it and is never graded three-way.
SOCCER_THREE_WAY_SINCE = datetime(2026, 9, 16, 17, 43, 41, tzinfo=timezone.utc)

#: The smallest draw remainder that proves a stored pair kept the draw. A
#: renormalized pair leaves at most 0.0001 (four-place rounding of two legs).
SOCCER_DRAW_RESIDUAL_MIN = 0.01

#: ESPN's ``status.type.detail`` for a match that ended at full time, as the
#: sync stores it in ``events.period``. Matched exactly, so any other detail —
#: an extra-time or shootout finish, a live token — refuses.
SOCCER_REGULATION_FINISH_PERIOD = "FT"

#: ESPN's ``status.type.name`` for the same, as a fresh box stores it in
#: ``box_score_data.provider_box_evidence.provider_status.name``.
SOCCER_REGULATION_FINISH_STATUS = "STATUS_FULL_TIME"

#: Bind parameters for every SQL statement that applies the contract. Bound,
#: never interpolated, so the statement text names the contract and the values
#: live in exactly one place.
SOCCER_THREE_WAY_PARAMS = {
    "soccer_three_way_since": SOCCER_THREE_WAY_SINCE,
    "soccer_draw_residual_min": SOCCER_DRAW_RESIDUAL_MIN,
    "soccer_regulation_period": SOCCER_REGULATION_FINISH_PERIOD,
    "soccer_regulation_status": SOCCER_REGULATION_FINISH_STATUS,
}

#: Stamped on every per-sportsbook bucket built under this contract. The curve
#: reader publishes a soccer bucket ONLY when it carries this stamp, so a bucket
#: written by an older writer (two-way, draws dropped) can never be read as a
#: three-way one — whether it arrives from Redis or from the durable survivor.
SOCCER_THREE_WAY_CONTRACT = "soccer_three_way/v1"

#: The bucket key that carries :data:`SOCCER_THREE_WAY_CONTRACT`.
SOCCER_THREE_WAY_CONTRACT_KEY = "three_way_contract"


def is_soccer_key(sport_key: Optional[str]) -> bool:
    """A league-scoped soccer sport key (``soccer_epl``), the curve's category."""
    return bool(sport_key) and sport_key.startswith("soccer_")


def draw_residual(home: Optional[float], away: Optional[float]) -> Optional[float]:
    """``1 - home - away`` for a pair of positive legs, else None."""
    if home is None or away is None:
        return None
    home, away = float(home), float(away)
    if home <= 0 or away <= 0:
        return None
    return 1.0 - home - away


def pair_keeps_the_draw(home: Optional[float], away: Optional[float]) -> bool:
    """True when the stored pair leaves the draw's remainder (see module doc)."""
    residual = draw_residual(home, away)
    return residual is not None and residual >= SOCCER_DRAW_RESIDUAL_MIN


def regulation_finish_proven(
    period: Optional[str], provider_status_name: Optional[str] = None
) -> bool:
    """True when the row itself says the match ended at full time (module doc)."""
    return (
        period == SOCCER_REGULATION_FINISH_PERIOD
        or provider_status_name == SOCCER_REGULATION_FINISH_STATUS
    )


def three_way_outcomes(
    home: Optional[float],
    away: Optional[float],
    home_score: Optional[float],
    away_score: Optional[float],
    observed_at: Optional[datetime] = None,
    *,
    regulation_proven: bool,
) -> Optional[list[tuple[float, bool]]]:
    """The three graded outcomes of one soccer reading, or None if it is not one.

    ``observed_at`` is when the reading was taken (a snapshot's capture time,
    or the match's kickoff for the last pre-kickoff consensus).
    ``regulation_proven`` is :func:`regulation_finish_proven` for the match —
    keyword-only and required, so no caller can grade a final score it has not
    shown to be the 90-minute one. Returns ``[(p_home, home_won), (p_away,
    away_won), (p_draw, drawn)]``, or None when the reading predates the cutoff,
    does not keep the draw, the match has no score, or its score is not proven
    to be the regulation score.
    """
    if observed_at is not None and observed_at < SOCCER_THREE_WAY_SINCE:
        return None
    if home_score is None or away_score is None:
        return None
    if not regulation_proven:
        return None
    if not pair_keeps_the_draw(home, away):
        return None
    home, away = float(home), float(away)
    return [
        (home, home_score > away_score),
        (away, away_score > home_score),
        (1.0 - home - away, home_score == away_score),
    ]
