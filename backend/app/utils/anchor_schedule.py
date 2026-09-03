"""An anchored row may not disagree with its own anchor about when the game starts.

#2693 / #2697, lane1/066.  ``events.espn_id`` is an identity claim: *this row
is that ESPN game*.  Everything downstream dereferences it — scores, status,
the clock, win probability.  This module answers the one question nobody was
asking of it: **does the row agree with the authority about the kickoff?**

═══ THE CASE THIS WAS BUILT ON, MEASURED BEFORE A LINE OF IT EXISTED ═══

NFL Week 1 opens Thursday 2026-09-10.  On 2026-09-03 all 34 upcoming NFL rows
carried an ESPN anchor (34/34, every one distinct — no twins, nothing
unanchored), and Week 1 still showed **18 games instead of 16**.  Two rows had
the right anchor, the right team names, and a kickoff belonging to a different
week::

    E14780595  SF 49ers @ LA Chargers   espn 401873124
        ours 2026-09-11 00:35Z   ESPN 2026-12-18 01:15Z   (Week 15, 98 days)
    E14781140  ARI Cardinals @ LA Rams  espn 401873004
        ours 2026-09-13 20:25Z   ESPN 2026-10-18 20:05Z   (Week 6, 35 days)

Each sat beside the genuine Week 1 fixture for the same away team (49ers @
**Rams**, Cardinals @ **Chargers**), both correct.  It looks like the SoFi
Stadium Rams/Chargers mixup and it is not: the team names match ESPN exactly.
It is a date bug wearing a valid anchor.  A 49ers fan a week before kickoff saw
their team playing twice.

═══ WHY NOTHING WAS EVER GOING TO CATCH IT ═══

``sync_scheduled_events`` already contains the right suspicion.  When our start
and ESPN's differ beyond the same-game window it REFUSES the correction and
logs *"the espn_id on this row points at a different game (#1947)"*.  That
refusal never fired here, and could not have:

**every ESPN pass is driven by today's scoreboard.**  ``espn_events`` is the
slate for the current date, and a row is only visited if its anchor is on that
slate (or its teams are).  An anchor pointing at December is on no slate we
will fetch until December.  So a row can carry a start that its own anchor
contradicts by three months and be invisible to every pass, in both directions,
indefinitely.

The fix is therefore not a better rule inside the scoreboard pass.  It is to
**dereference the anchor by id** — ask ESPN what game ``401873124`` actually is
— which is what ``app/tasks/reconcile_anchor_schedule`` does with the verdicts
below.

═══ WHY THE AUTHORITY MOVES US, RATHER THAN THE ANCHOR BEING REVOKED ═══

When our clock and the authority's disagree, exactly one of two things is
wrong, and the existing #1947 log asserts the second:

(a) our ``commence_time`` is wrong — the row is the game ESPN names, misdated;
(b) our ``espn_id`` is wrong — the row is some other fixture.

The teams decide between them, and only the teams.  If our stored names match
ESPN's competitors exactly then (a) holds: it is that game, misdated, and the
authority owns the date.  If they do not, this module writes nothing — that is
(b), it is ``authority-id-collisions``' question, and moving a start time to
"fix" a mis-anchor would drag a real fixture onto another game's clock.

Deciding on names rather than on ``teams.espn_id`` is not a preference; the id
channel is measurably poisoned (1,204 of 1,469 team rows sit in a colliding
``(sport, espn_id)``).  The argument in full, and the rule itself, are
``authority_id_collisions._teams_agree``, imported here rather than restated —
two copies of an identity rule is how the two rails come to disagree about who
a row is.

═══ EVERY REFUSAL IS A SENTENCE, AND SILENCE IS NEVER AGREEMENT ═══

A verdict of :data:`AGREES` means the authority answered and matched.  An
authority that did not answer yields :data:`NO_ANSWER`, never agreement
(gotcha #53): a dark ESPN and a row that is fine produce the same empty body,
and collapsing them would let an outage read as a clean bill of health.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from app.utils.authority_id_collisions import (
    AuthorityRecord,
    CandidateRow,
    _teams_agree,
)
from app.utils.espn_tennis_anchor import SETTLED_STATUSES

__all__ = [
    "AGREES",
    "AUTHORITY_MOVES_US",
    "NO_ANSWER",
    "REFUSED_COMPLETED",
    "REFUSED_SETTLED",
    "REFUSED_STATPAL",
    "SAME_START_TOLERANCE_S",
    "SCHEDULE_VERDICTS",
    "AnchoredRow",
    "ScheduleDecision",
    "schedule_decision",
    "summarize_decisions",
]

#: How far our start may sit from the authority's and still be the same clock.
#: Five minutes, the same tolerance every existing ESPN commence-time
#: correction uses (``espn_helpers`` in three places), so this rail cannot
#: disagree with the live pass about what "already agrees" means. It absorbs
#: ESPN restating a start to the minute; it does not absorb a week.
SAME_START_TOLERANCE_S = 300

AGREES = "agrees"
AUTHORITY_MOVES_US = "authority_moves_us"
NO_ANSWER = "no_answer"
#: The anchor names a different fixture. Writing nothing is the whole point:
#: this is ``authority-id-collisions``' question, not a schedule question.
TEAMS_DISAGREE = "teams_disagree"
REFUSED_COMPLETED = "refused_completed"
REFUSED_SETTLED = "refused_settled"
REFUSED_STATPAL = "refused_statpal"

SCHEDULE_VERDICTS = (
    AGREES,
    AUTHORITY_MOVES_US,
    TEAMS_DISAGREE,
    NO_ANSWER,
    REFUSED_COMPLETED,
    REFUSED_SETTLED,
    REFUSED_STATPAL,
)


@dataclass(frozen=True)
class AnchoredRow:
    """One ``events`` row that carries an authority id, as this rule needs it.

    Deliberately NOT :class:`CandidateRow`: that type is the collisions rail's
    view of a row (which team ids it carries, how it ranks against its twins),
    and this rule needs three fields it does not have — the status, the
    completion stamp and the provenance of the start time. It is converted to
    one only to call the shared team-agreement rule.
    """

    event_id: int
    sport_key: str
    home_team_name: str
    away_team_name: str
    espn_id: str
    commence_time: Optional[datetime] = None
    status: Optional[str] = None
    completed_at: Any = None
    commence_time_source: Optional[str] = None

    def as_candidate(self) -> CandidateRow:
        return CandidateRow(
            event_id=self.event_id,
            sport_key=self.sport_key,
            home_team_name=self.home_team_name,
            away_team_name=self.away_team_name,
            commence_time=self.commence_time,
        )


@dataclass(frozen=True)
class ScheduleDecision:
    """One row's verdict, and the write it authorises — which is usually none."""

    event_id: int
    espn_id: str
    verdict: str
    reason: str
    ours: Optional[datetime] = None
    theirs: Optional[datetime] = None
    delta_seconds: Optional[int] = None
    #: ESPN's label for the game, carried so a plan can be reviewed without a
    #: second call to the authority.
    authority_label: str = ""
    #: Observed, never a decider. ESPN listing the sides the other way round is
    #: still the same fixture, so it does not change the verdict — but a row
    #: whose orientation disagrees with the authority is worth seeing.
    orientation_inverted: bool = False
    #: The columns to move. Empty for every verdict except
    #: :data:`AUTHORITY_MOVES_US`.
    write: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.write is None:
            object.__setattr__(self, "write", {})


def _delta(ours: Optional[datetime], theirs: Optional[datetime]) -> Optional[int]:
    if ours is None or theirs is None:
        return None
    return int(abs((ours - theirs).total_seconds()))


def schedule_decision(
    row: AnchoredRow,
    record: Optional[AuthorityRecord],
    *,
    tolerance_s: int = SAME_START_TOLERANCE_S,
) -> ScheduleDecision:
    """What the authority's answer means for this row's start time. Pure.

    The refusals are ordered most-certain-first, and each one is a reason a
    person can act on rather than a silent ``continue``:

    1. **No usable answer** — no record, a record missing a side, or a record
       with no date. All three are absences, and an absence is not agreement
       (gotcha #53).
    2. **We have no start of our own** — nothing to compare, and inventing one
       from the authority is a different rail's job (this one corrects a
       disagreement; it does not fill a blank).
    3. **The row is finished** — ``completed_at`` set, or a settled status.
       Moving the start of a game that has already been played rewrites history
       for every chart that has drawn it, and risks the
       ``completed_at >= commence_time`` invariant (gotcha #46) whose violation
       is a P1 by standing rule. Strictly stronger than the existing
       ``commence_correction_inverts_completion`` guard, which only refuses the
       moves that would invert it.
    4. **StatPal set our start** — the existing precedence, stated in three
       places in ``espn_helpers``: StatPal outranks ESPN for kickoff times. A
       new rail that quietly reversed a precedence rule would be a regression
       wearing a fix's clothes.
    5. **The teams disagree** — the anchor names a different fixture, so the
       disagreement is about identity, not about the clock. Reported, never
       written. See the module docstring.

    Only then does the clock decide, and only two answers remain: inside the
    tolerance it :data:`AGREES`, outside it the authority moves us.
    """
    espn_id = row.espn_id
    if record is None or not record.usable:
        return ScheduleDecision(
            event_id=row.event_id,
            espn_id=espn_id,
            verdict=NO_ANSWER,
            reason="the authority did not answer for this id, or named only one side",
            ours=row.commence_time,
        )
    if record.starts_at is None:
        return ScheduleDecision(
            event_id=row.event_id,
            espn_id=espn_id,
            verdict=NO_ANSWER,
            reason="the authority answered but published no start time",
            ours=row.commence_time,
            authority_label=record.label,
        )
    if row.commence_time is None:
        return ScheduleDecision(
            event_id=row.event_id,
            espn_id=espn_id,
            verdict=NO_ANSWER,
            reason="the row has no start time to compare; filling a blank is not this rail",
            theirs=record.starts_at,
            authority_label=record.label,
        )

    common = {
        "event_id": row.event_id,
        "espn_id": espn_id,
        "ours": row.commence_time,
        "theirs": record.starts_at,
        "delta_seconds": _delta(row.commence_time, record.starts_at),
        "authority_label": record.label,
    }

    if row.completed_at is not None:
        return ScheduleDecision(
            **common,
            verdict=REFUSED_COMPLETED,
            reason="the row carries a completed_at; moving a played game's start rewrites history",
        )
    if row.status in SETTLED_STATUSES:
        return ScheduleDecision(
            **common,
            verdict=REFUSED_SETTLED,
            reason=f"the row is {row.status}; the authority does not re-date a settled game",
        )
    if row.commence_time_source == "statpal":
        return ScheduleDecision(
            **common,
            verdict=REFUSED_STATPAL,
            reason="StatPal set this start and outranks ESPN for kickoff times",
        )

    agrees, inverted, _channel = _teams_agree(row.as_candidate(), record)
    if not agrees:
        return ScheduleDecision(
            **common,
            verdict=TEAMS_DISAGREE,
            reason=(
                f"the anchor names {record.label or 'another fixture'}, not "
                f"{row.away_team_name} at {row.home_team_name} — an identity "
                "question for authority-id-collisions, not a clock one"
            ),
        )

    if common["delta_seconds"] is not None and common["delta_seconds"] <= tolerance_s:
        return ScheduleDecision(
            **common,
            verdict=AGREES,
            reason="within the same-start tolerance",
            orientation_inverted=inverted,
        )

    return ScheduleDecision(
        **common,
        verdict=AUTHORITY_MOVES_US,
        reason=(
            "same teams, different clock — the row is that game, misdated, and "
            "the authority owns the date"
        ),
        orientation_inverted=inverted,
        write={
            "commence_time": record.starts_at,
            # Stamped because it becomes true with this write, and because both
            # rows this rail was built on ALREADY claimed 'espn' while
            # disagreeing with ESPN by three months. The provenance column is
            # only worth anything if the thing that sets it also checked.
            "commence_time_source": "espn",
        },
    )


def summarize_decisions(decisions) -> dict[str, Any]:
    """Counts by verdict, plus the moves, for an operator line and a plan.

    Every verdict in :data:`SCHEDULE_VERDICTS` is present with a zero rather
    than omitted. A missing key and a measured zero read identically to a
    consumer, and this summary is what a reviewer decides to apply on.
    """
    decisions = list(decisions)
    by_verdict = {verdict: 0 for verdict in SCHEDULE_VERDICTS}
    for decision in decisions:
        by_verdict[decision.verdict] = by_verdict.get(decision.verdict, 0) + 1
    return {
        "examined": len(decisions),
        "by_verdict": by_verdict,
        "moves": [
            {
                "event_id": d.event_id,
                "espn_id": d.espn_id,
                "ours": d.ours.isoformat() if d.ours else None,
                "theirs": d.theirs.isoformat() if d.theirs else None,
                "delta_days": round((d.delta_seconds or 0) / 86400.0, 2),
                "authority": d.authority_label,
            }
            for d in decisions
            if d.verdict == AUTHORITY_MOVES_US
        ],
    }
