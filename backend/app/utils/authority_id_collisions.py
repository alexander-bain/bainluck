"""One game, one authority id — who really is ESPN event ``N``, decided by ESPN.

═══ WHY THIS MODULE EXISTS ═══

``events.espn_id`` is the authority channel: ``espn_sync`` corrects status,
``commence_time``, ``completed_at`` and the win probability of a row *through*
that column, and lane1/057 (#2693 step 0) made tennis carry one for the first
time.  A column that steers writes has to name one row, and today it does not:
measured on production 2026-09-02, **196 ids are worn by 430 rows**.

The tempting reading — "430 duplicate rows, merge the twins" — is wrong, and
measuring it is what this module is for.  Sampled against ESPN, most collisions
are not twins at all:

    401847094  ESPN: Alabama Crimson Tide v Ole Miss Rebels
               ours: 14683176 Alabama Crimson Tide v Ole Miss Rebels   <- is it
               ours: 14707075 North Alabama       v Ole Miss           <- is NOT

The second row is a *different game* wearing the id, put there by a matcher
that let a shared surname through.  Fusing those two would destroy a real
fixture and its result.

═══ WHAT THIS REPAIR DOES, AND THE LARGER THING IT DOES NOT ═══

**It hands the id back. It never merges a row and never deletes one.**  Every
non-keeper in a group gets ``espn_id = NULL`` and nothing else: no FK is
re-pointed, no row is retired.  That is the entire write, and it is what the
invariant needs — ``UNIQUE (espn_id) WHERE espn_id IS NOT NULL`` requires one
wearer per id and cares nothing about how many event rows exist.

The reason for drawing the line there is that the two problems are different
sizes.  Un-wearing an id touches one nullable column and every prior value is
in the receipt, so the whole repair reverses with an UPDATE.  Fusing two event
rows re-points eleven foreign keys and ends in a DELETE, and a DELETE that
picked the wrong keeper cannot be undone by anything.  A queue called *one
game, one authority id* buys the first; the second is the duplicate-EVENT
program and needs its own ship.

So a collision still resolves into two shapes, because the shapes have
different follow-ups even though today they get the same write:

    TWIN            both rows really are ESPN event N (name variants:
                    "St.Louis Cardinals" / "St. Louis Cardinals").  The loser
                    hands the id back and is filed as a merge candidate.
    WRONG FIXTURE   a different game wearing the id.  It hands the id back and
                    is a matching bug (#2693), not a merge candidate.

═══ THE TEST IS EXACT, AGAINST ESPN'S OWN VOCABULARY ═══

A row is ESPN event N when both of its stored team names appear EXACTLY —
after ``normalize_team_name_for_matching`` — in the list of names ESPN itself
publishes for that competitor: ``displayName``, ``shortDisplayName``,
``location``, ``name``, ``abbreviation``, ``nickname``.  No prefix rule, no
token subset, no edit distance.

That is not fastidiousness, it is the defect.  A prefix rule makes ``Kansas`` a
wildcard for ``Kansas State`` and ``Alabama`` one for ``North Alabama``, which
is how half of these collisions were created; a matcher is not repaired by a
looser copy of itself.  ESPN's own vocabulary is the one list that holds
``Ole Miss`` for the Rebels and ``UCF`` for the Knights without also holding
``Kansas`` for the Wildcats.

**And not by team id, though there is one.**  ``events.home_team_id ->
teams.espn_id`` is ESPN's own team id and looks like the stronger channel; the
first draft of this module used it and had to be withdrawn.  Measured
2026-09-02, **1,204 of the 1,469 team rows carrying an espn_id sit in a
colliding (sport, espn_id)** — ``North Alabama`` wears Alabama's 148,
``Ball State`` and ``Indiana State`` both wear Florida State's 72.  Deciding on
that channel merged three different fixtures into Florida State v Miami.  An id
is only stronger than a name when the id is sound, and this one was written by
the same matcher that caused the collisions.  The team ids are carried into
every receipt as an observation, because a row whose names agree while its team
FK points elsewhere is a team-identity finding (#1204) worth having.

Both orientations are accepted (``home`` against away, ``away`` against home):
some feeds invert the pair, and the inversion is a fact about the row worth
recording, not a reason to refuse an identity that is otherwise exact.

═══ TIME IS A TIE-BREAK, NEVER A GATE ═══

A row whose ``commence_time`` disagrees with ESPN is not evidence the row is
the wrong game — it is the exact defect ``espn_sync`` exists to fix, and lane
1/057 shipped because a tennis match served ``closed 0-1`` while ESPN scored
its second set.  Gating on time would unstamp the rows that need the authority
most.

So time enters only when the *teams* have already failed to separate two rows:
a Cardinals doubleheader has two fixtures with identical names and one shared
id, and ``MAX_TWIN_DELTA`` is the only thing that says which one ESPN meant.

═══ WHAT IT REFUSES ═══

``NO_ROW_AGREES`` and ``AMBIGUOUS`` write nothing.  A group where the authority
recognises none of our rows is a finding about this module's name handling as
much as about the data, and unstamping every row on the strength of a
normalizer that just failed twice would be believing the failure.  Refusing
leaves a visible, countable group; guessing leaves a silent, plausible one
(gotcha #53).

Nothing here touches a database or a network.  Given what ESPN said and what
the rows hold, it returns a decision — so the decision is testable without
either, and the job, the audit script and the tests all read one copy of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional, Sequence

from app.utils.authority_name_forms import (
    canonical_forms,
    composed_forms,
    synonym_forms,
)
from app.utils.name_normalization import normalize_team_name_for_matching

__all__ = [
    "MAX_TWIN_DELTA",
    "ROW_VERDICTS",
    "GROUP_OUTCOMES",
    "AuthorityRecord",
    "CandidateRow",
    "RowVerdict",
    "GroupDecision",
    "authority_names",
    "decide_group",
    "summarize",
]

#: How far apart two rows that BOTH match the authority's teams may sit before
#: they stop being one game recorded twice and start being two games (a
#: doubleheader) sharing one id.  Three hours: longer than any single fixture's
#: start-time disagreement between the Odds API and ESPN that has been observed
#: (minutes), and shorter than the gap between the two halves of a
#: doubleheader (measured 5-18h on the 2026-05-23 Giants/White Sox group).
MAX_TWIN_DELTA = timedelta(hours=3)

#: Per-row verdicts.  Closed set — a free-text reason would make the group
#: counts unaggregatable, which is the mistake INVARIANTS query (c) records.
ROW_VERDICTS = (
    #: Both competitors match a name ESPN publishes, and this row keeps the id.
    "AGREES",
    #: Also this fixture, at the same hour — a twin. Hands the id back and is
    #: filed as a merge candidate for the duplicate-EVENT program.
    "AGREES_TWIN",
    #: At least one competitor is not any name ESPN publishes for this event.
    "TEAMS_DISAGREE",
    #: Teams agree, but this row's start belongs to a different cluster from
    #: the one the authority points at — a doubleheader's other half, or the
    #: next day's game in the series.
    "TIME_DISAGREES",
)

#: Group outcomes.  Only the first two ever write.
GROUP_OUTCOMES = (
    #: Exactly one row is this event.  It keeps the id; every other row hands
    #: it back.
    "RESOLVED_ONE",
    #: Two or more rows are the same game recorded twice.  One keeps the id;
    #: the twins hand it back and are filed as merge candidates.
    "RESOLVED_MERGE",
    #: ESPN has nothing for this id (404, or a league path we cannot derive).
    #: Writes nothing — an absent authority is not a verdict.
    "AUTHORITY_UNAVAILABLE",
    #: The authority recognises none of our rows.  Writes nothing.
    "NO_ROW_AGREES",
    #: Two or more rows agree on teams and none is inside ``MAX_TWIN_DELTA`` of
    #: the authority's start, so nothing separates them.  Writes nothing.
    "AMBIGUOUS",
)


def _normalized(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return normalize_team_name_for_matching(value)


def _forms_of_all(names) -> frozenset[str]:
    """The union of every reduction of every name the authority published."""
    forms: set[str] = set()
    for name in names:
        forms |= canonical_forms(name)
    return frozenset(forms)


def authority_names(competitor: dict[str, Any]) -> frozenset[str]:
    """Every name ESPN publishes for one competitor, normalized.

    The competitor dict is ESPN's, straight off ``summary`` or ``scoreboard``:
    the team block sits under ``team`` on a scoreboard competition and is
    sometimes the competitor itself on other shapes, so both are read.  Empty
    strings are dropped rather than kept as a name that matches every blank.

    This is the list the exact-match rule tests against, and its breadth is
    what lets the rule stay exact — ``Ole Miss`` is in ESPN's vocabulary for
    the Rebels, so no fuzzy rule is needed to accept it.

    #2792: the breadth was not sufficient after all, in a way that is ESPN's
    formatting rather than our matching. It publishes ``location`` and ``name``
    separately and only *usually* prints their concatenation as ``displayName``
    — for the AFL, Hawthorn's ``displayName`` is bare ``Hawthorn``, so our
    ordinary "Hawthorn Hawks" matched none of the five strings read here. The
    compositions ESPN's own fields imply are therefore added
    (:func:`~app.utils.authority_name_forms.composed_forms`); the rule stays
    exact and only the vocabulary grows.
    """
    block = (
        competitor.get("team")
        if isinstance(competitor.get("team"), dict)
        else competitor
    )
    names = set()
    for key in (
        "displayName",
        "shortDisplayName",
        "location",
        "name",
        "nickname",
        "abbreviation",
    ):
        normalized = _normalized(block.get(key))
        if normalized:
            names.add(normalized)
    names |= composed_forms(block)
    return frozenset(names)


@dataclass(frozen=True)
class AuthorityRecord:
    """What ESPN says event ``authority_id`` is."""

    authority_id: str
    home_names: frozenset[str]
    away_names: frozenset[str]
    #: ESPN's own team ids for the two competitors. NOT a decider — see
    #: ``_teams_agree`` for the measurement that disqualified them. Carried so
    #: a receipt can record that our team FK disagreed with the authority.
    home_team_id: Optional[str] = None
    away_team_id: Optional[str] = None
    #: ESPN's scheduled start, when it publishes one.  ``None`` disables the
    #: doubleheader tie-break rather than failing the group: with no anchor,
    #: two rows carrying identical teams are twins by every test we have.
    starts_at: Optional[datetime] = None
    #: Carried through to the receipt so a verdict can be re-read later
    #: without a second call to ESPN.
    label: str = ""

    @property
    def usable(self) -> bool:
        """Both sides named. A record with a blank side can decide nothing."""
        return bool(self.home_names) and bool(self.away_names)


@dataclass(frozen=True)
class CandidateRow:
    """One ``events`` row wearing the contested id."""

    event_id: int
    sport_key: str
    home_team_name: str
    away_team_name: str
    commence_time: Optional[datetime] = None
    #: ``teams.espn_id`` for each side, dereferenced through the event's team
    #: FKs. Observed, never consulted — ``_teams_agree`` explains why.
    home_team_authority_id: Optional[str] = None
    away_team_authority_id: Optional[str] = None
    #: Higher wins the KEEP slot in a merge. The job fills this with the row's
    #: dependent count (markets, snapshots); the pure layer only orders on it.
    weight: int = 0
    #: Second tie-break: a row the Odds API created carries one.
    has_external_id: bool = False


@dataclass(frozen=True)
class RowVerdict:
    event_id: int
    verdict: str
    #: True when the row's home matched ESPN's away and vice versa.
    inverted: bool = False
    #: Seconds between this row's ``commence_time`` and the authority's start,
    #: absolute. ``None`` when either side has no time.
    delta_seconds: Optional[int] = None
    #: ``team_id`` | ``team_name`` | ``none`` — which channel reached the
    #: verdict. A repair whose verdicts are all ``team_name`` is a different
    #: claim from one whose verdicts are all ``team_id``, and the bus is
    #: entitled to see which it is being asked to grade.
    channel: str = "none"


@dataclass(frozen=True)
class GroupDecision:
    authority_id: str
    outcome: str
    rows: tuple[RowVerdict, ...] = ()
    #: The row that keeps the id. ``None`` for every non-writing outcome.
    keep_event_id: Optional[int] = None
    #: EVERY row that must hand the id back — twins and wrong fixtures alike.
    #: This is the write list, and it is one list precisely because the write
    #: is the same for both.
    unstamp_event_ids: tuple[int, ...] = ()
    #: The subset of ``unstamp_event_ids`` that is the same game as the keeper.
    #: Reported, never acted on here — see the module docstring.
    twin_event_ids: tuple[int, ...] = ()
    note: str = ""

    @property
    def writes(self) -> bool:
        return self.outcome in ("RESOLVED_ONE", "RESOLVED_MERGE")


def _teams_agree(row: CandidateRow, record: AuthorityRecord) -> tuple[bool, bool, str]:
    """``(agrees, inverted, channel)`` — the row's OWN names against ESPN's.

    ═══ WHY NOT THE TEAM IDS ═══

    ``events.home_team_id -> teams.espn_id`` looks like the id channel this
    repair should obviously prefer, and the first draft of this module used it.
    It is poisoned, and by the same defect:

        teams 14622  "North Alabama"   espn_id 148   <- Alabama Crimson Tide's
        teams 14628  "Ball State"      espn_id  72   <- Florida State's
        teams 14630  "Indiana State"   espn_id  72   <- Florida State's

    Measured 2026-09-02: **1,204 of the 1,469 team rows carrying an espn_id sit
    in a colliding (sport, espn_id)**. Deciding on that channel made "North
    Alabama v Ole Miss" AGREE with Alabama v Ole Miss and merged three
    different fixtures into Florida State v Miami — the exact fusion this
    repair exists to prevent, arrived at by trusting an id.

    An id channel is only stronger than a name channel when the id is sound.
    This one is a *derived* link our own matcher wrote; the row's stored team
    names are what the SOURCE said the fixture was. So the names decide, and
    the team ids are carried into the receipt as an observation — a row whose
    names agree while its team ids point elsewhere is a team-identity finding
    (#1204), not a reason to change this verdict.

    ═══ WHY THE COMPARISON IS BETWEEN SETS OF FORMS (#2792) ═══

    Both sides are reduced through
    :func:`~app.utils.authority_name_forms.canonical_forms` and agree when their
    form sets intersect. The reductions are punctuation, a leading article, a
    club initialism and a founding year — each one a rewriting of the WHOLE
    name, so no name reduces to a fragment of itself and no short token becomes
    a wildcard. That property is what keeps ``Ohio State Buckeyes`` and ``Texas
    State Bobcats`` apart, which is the case #2792 is named for and the one this
    rule exists to fail.

    Because every form set contains the plain normalized name, this is a strict
    widening: nothing the exact rule used to agree on can stop agreeing.

    ═══ AND THE ASYMMETRIC HALF (#2823) ═══

    Our side — and ONLY our side — is additionally widened by
    :func:`~app.utils.authority_name_forms.synonym_forms`, an exact
    ``(sport, name)`` lookup for the dozen clubs ESPN simply calls something
    else: ``Athletic Bilbao``/``Athletic Club``, ``Sporting Lisbon``/``Sporting
    CP``, ``Sam Houston State``/``Sam Houston``. Those are not reachable by any
    structural rule, and every rule that would reach them fuses ``Ohio State``
    with ``Texas State``. A table of named clubs cannot generalise, so it cannot
    generalise wrongly; see that constant for why it is keyed on sport.
    """
    ours_home = canonical_forms(row.home_team_name) | synonym_forms(
        row.home_team_name, row.sport_key
    )
    ours_away = canonical_forms(row.away_team_name) | synonym_forms(
        row.away_team_name, row.sport_key
    )
    if not ours_home or not ours_away or not record.home_names or not record.away_names:
        return False, False, "none"
    theirs_home = _forms_of_all(record.home_names)
    theirs_away = _forms_of_all(record.away_names)
    if (ours_home & theirs_home) and (ours_away & theirs_away):
        return True, False, "team_name"
    if (ours_home & theirs_away) and (ours_away & theirs_home):
        return True, True, "team_name"
    return False, False, "team_name"


def _delta_seconds(row: CandidateRow, record: AuthorityRecord) -> Optional[int]:
    if row.commence_time is None or record.starts_at is None:
        return None
    return int(abs((row.commence_time - record.starts_at).total_seconds()))


def _cluster_by_time(rows: Sequence[CandidateRow]) -> list[list[CandidateRow]]:
    """Rows that agree on teams, grouped into "one game" by their own clocks.

    Single linkage on the sorted start times with a ``MAX_TWIN_DELTA`` gap: two
    rows are the same fixture when nothing bigger than that separates them.

    A row with no ``commence_time`` is handled by which of two situations it is
    in, and the distinction matters:

    * **Some rows are timed and some are not.** The timeless one becomes its own
      cluster, so the group refuses instead of absorbing it into whichever timed
      cluster happened to come first. An absent clock is not evidence of
      belonging anywhere.
    * **NO row is timed.** Then the clock separates nothing, and one cluster per
      row would be a false ambiguity manufactured out of a field none of them
      has. Rows the teams already matched and time cannot distinguish are twins
      by every test available — the same reading the record's own missing
      ``starts_at`` gets.
    """
    timed = sorted(
        (r for r in rows if r.commence_time is not None), key=lambda r: r.commence_time
    )
    untimed = [r for r in rows if r.commence_time is None]
    if not timed:
        return [list(rows)] if rows else []

    clusters: list[list[CandidateRow]] = []
    for row in timed:
        if clusters and (
            row.commence_time - clusters[-1][-1].commence_time <= MAX_TWIN_DELTA
        ):
            clusters[-1].append(row)
        else:
            clusters.append([row])
    clusters.extend([row] for row in untimed)
    return clusters


def _select_cluster(
    clusters: list[list[CandidateRow]], record: AuthorityRecord
) -> tuple[Optional[list[CandidateRow]], str]:
    """Which cluster is the authority's fixture — or ``(None, why not)``.

    Two rungs, tried in order, and neither is a similarity score:

    1. **A row inside ``MAX_TWIN_DELTA`` of ESPN's start.** Ordinary agreement.
    2. **A row on ESPN's own UTC calendar date.** This is the rung that
       resolves the four Orioles/Guardians/Rays/Brewers groups of 2026-08-18,
       where the row holding thirty markets and 3,682 snapshots turned out to
       be the NEXT DAY'S game wearing this id, and the correct keeper was the
       empty row four hours off the authority's clock. Weight would have picked
       the wrong one; the date picks the right one.

    Two clusters passing the same rung is not a tie to break, it is a genuine
    doubleheader we cannot resolve — ``None``, and the group stays visible.
    """
    if len(clusters) == 1:
        return clusters[0], ""
    if record.starts_at is None:
        return None, "the authority publishes no start time"

    window = MAX_TWIN_DELTA.total_seconds()
    near = [
        c
        for c in clusters
        if any(
            r.commence_time is not None
            and abs((r.commence_time - record.starts_at).total_seconds()) <= window
            for r in c
        )
    ]
    if len(near) == 1:
        return near[0], ""
    if len(near) > 1:
        return None, "more than one sits inside the authority's window"

    authority_date = record.starts_at.date()
    same_day = [
        c
        for c in clusters
        if any(
            r.commence_time is not None and r.commence_time.date() == authority_date
            for r in c
        )
    ]
    if len(same_day) == 1:
        return same_day[0], ""
    if len(same_day) > 1:
        return None, "more than one falls on the authority's date"
    return None, "none is within the authority's window or on its date"


def _rank(row: CandidateRow) -> tuple:
    """Sort key for the KEEP slot: most dependents, then sourced, then oldest.

    ``event_id`` last and ascending is deliberate. The older row is the one
    other tables have had longer to point at, and it is stable — re-running the
    repair after a partial apply must pick the same winner or the second pass
    undoes the first.
    """
    return (-row.weight, 0 if row.has_external_id else 1, row.event_id)


def decide_group(
    record: Optional[AuthorityRecord],
    rows: Sequence[CandidateRow],
    authority_id: str = "",
) -> GroupDecision:
    """One contested id -> what to do about it. Pure.

    ``record is None`` (or a record ESPN only half-populated) is
    ``AUTHORITY_UNAVAILABLE``: the absence of an answer is not an answer, and a
    group we could not ask about must stay visible rather than resolve itself
    into a write.
    """
    key = authority_id or (record.authority_id if record else "")

    if record is None or not record.usable:
        return GroupDecision(
            authority_id=key,
            outcome="AUTHORITY_UNAVAILABLE",
            rows=tuple(RowVerdict(r.event_id, "TEAMS_DISAGREE") for r in rows),
            note="ESPN published no usable record for this id",
        )

    agreeing: list[tuple[CandidateRow, bool, Optional[int], str]] = []
    verdicts: dict[int, RowVerdict] = {}
    for row in rows:
        agrees, inverted, channel = _teams_agree(row, record)
        delta = _delta_seconds(row, record)
        if agrees:
            agreeing.append((row, inverted, delta, channel))
        else:
            verdicts[row.event_id] = RowVerdict(
                row.event_id, "TEAMS_DISAGREE", inverted, delta, channel
            )

    if not agreeing:
        return GroupDecision(
            authority_id=key,
            outcome="NO_ROW_AGREES",
            rows=tuple(verdicts[r.event_id] for r in rows),
            note=f"{record.label or key}: no row carries both competitors",
        )

    # TIME ONLY SEPARATES ROWS THE TEAMS COULD NOT, and it separates them from
    # EACH OTHER before it compares any of them to the authority. Two rows
    # holding the same fixture at the same hour are one game recorded twice
    # even when both disagree with ESPN's clock by nineteen hours (measured:
    # Cal Poly v Long Beach State, 401856210) — and the clock is exactly what
    # the authority exists to correct, so making it the entry test would
    # unstamp the rows that need correcting most.
    clusters = _cluster_by_time([c[0] for c in agreeing])
    chosen, reason = _select_cluster(clusters, record)
    if chosen is None:
        for row, inverted, delta, channel in agreeing:
            verdicts[row.event_id] = RowVerdict(
                row.event_id, "AGREES", inverted, delta, channel
            )
        return GroupDecision(
            authority_id=key,
            outcome="AMBIGUOUS",
            rows=tuple(verdicts[r.event_id] for r in rows),
            note=f"{len(clusters)} distinct start times carry the authority's competitors; {reason}",
        )

    kept_ids = {row.event_id for row in chosen}
    for row, inverted, delta, channel in agreeing:
        verdicts[row.event_id] = RowVerdict(
            row.event_id,
            "AGREES" if row.event_id in kept_ids else "TIME_DISAGREES",
            inverted,
            delta,
            channel,
        )

    ordered = sorted(chosen, key=_rank)
    keep = ordered[0]
    twins = tuple(r.event_id for r in ordered[1:])
    for event_id in twins:
        held = verdicts[event_id]
        verdicts[event_id] = RowVerdict(
            event_id, "AGREES_TWIN", held.inverted, held.delta_seconds, held.channel
        )
    unstamp = tuple(r.event_id for r in rows if r.event_id != keep.event_id)

    return GroupDecision(
        authority_id=key,
        outcome="RESOLVED_MERGE" if twins else "RESOLVED_ONE",
        rows=tuple(verdicts[r.event_id] for r in rows),
        keep_event_id=keep.event_id,
        unstamp_event_ids=unstamp,
        twin_event_ids=twins,
        note=record.label or "",
    )


def summarize(decisions: Iterable[GroupDecision]) -> dict[str, Any]:
    """Counts the bus can re-derive: outcomes, and the two write totals."""
    outcomes: dict[str, int] = {name: 0 for name in GROUP_OUTCOMES}
    verdict_counts: dict[str, int] = {name: 0 for name in ROW_VERDICTS}
    channels: dict[str, int] = {}
    groups = 0
    unstamp = 0
    merge = 0
    inverted = 0
    for decision in decisions:
        groups += 1
        outcomes[decision.outcome] = outcomes.get(decision.outcome, 0) + 1
        for row in decision.rows:
            verdict_counts[row.verdict] = verdict_counts.get(row.verdict, 0) + 1
            channels[row.channel] = channels.get(row.channel, 0) + 1
            if row.inverted:
                inverted += 1
        if decision.writes:
            unstamp += len(decision.unstamp_event_ids)
            merge += len(decision.twin_event_ids)
    return {
        "groups": groups,
        "outcomes": outcomes,
        "row_verdicts": verdict_counts,
        # Groups still wearing one id on two rows after this repair runs. The
        # unique index cannot be created while this is above zero, so it is the
        # number the migration note has to quote.
        "groups_unresolved": groups
        - outcomes["RESOLVED_ONE"]
        - outcomes["RESOLVED_MERGE"],
        # Which channel every verdict came through. A repair graded on the id
        # channel and quietly delivered on the name channel is a different
        # repair; this is the line that makes the swap visible.
        "channels": dict(sorted(channels.items())),
        "rows_to_unstamp": unstamp,
        "rows_that_are_twins": merge,
        "rows_inverted": inverted,
    }
