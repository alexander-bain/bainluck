"""Which games, and which questions, are one NFL week. #9649 (v3, canonical #9217).

**SHIP: a reader opening one NFL week sees exactly that week's games and the
questions we hold on them — not the week before, not last season's rematch, and
not the same game twice.** (Pillar: MATCHING / DISCOVER.)

This is the pure half of the NFL adapter for `container_assembly`. It decides
membership and says why every non-member is not one; the task half
(`app/tasks/container_nfl_assembly.py`) reads rows and hands the candidates to
the shared `assemble_container`. No database, no network, no clock here, so the
whole rule is gradeable from the banked StatPal capture.

THE WEEK IS THE AUTHORITY'S, NEVER OURS. StatPal's NFL `season-schedule` files
every contest under `stage → week` (`Regular Season / Week 1`), and the parser
carries that onto `StatPalFixture.round_info`. That is the only place a week
number comes from. It is never inferred from a kickoff date — a Thursday game
sits three days from the previous Monday game and a flexed or postponed game
moves dates without changing weeks — and never from a team pair, because two
teams meet twice a season.

A GAME IS ONE OF OURS BY ID. A contest joins our event through the StatPal
contest id the NFL stamper writes (`events.statpal_fixture_id`, the column the
anchor channel treats as the truth; `stamp_nfl_statpal_fixtures`). Names and
kickoff times never admit a member here. The Rams–Cardinals phantom that sits
at the Chargers–Cardinals kickoff holds no contest id, so it cannot get in —
it is reported instead.

A MARKET IS A MEMBER BECAUSE ITS EVENT IS. `futures_markets.event_id` pointing
at a member event is the test (gotcha #15: an already-linked market is never
re-windowed), with one exception: the game's own winner market. Kalshi's and
Polymarket's "who wins" markets are the game card's blended number, so they are
reported under `EXCLUDED_GAME_WINNER_MARKET`, never edged
(`container_game_winner`, #9650). Every other question on the game stays.

EVERY NON-MEMBER IS ACCOUNTED FOR, and "the week is empty" is never the same
shape as "we could not tell" (gotcha #53):

* ``unavailable`` — the authority could not name the week at all (season
  unknown, the schedule is another season, the week is not in it), or a real
  contest has no row of ours. Upstream gaps stay gaps; nothing is fabricated.
* ``excluded`` — a candidate we refused, keyed by the rule that refused it:
  another week, a bracket placeholder, a contest filed under two weeks, two of
  our rows claiming one contest.

WHAT IS DELIBERATELY NOT HERE. No member list, no week calendar, no edition
table. A week is declared by three values (`NflWeek`), and everything in it is
discovered from the authority's schedule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional

from app.utils.container_class import MemberEvidence
from app.utils.container_game_winner import (
    EXCLUDED_GAME_WINNER_MARKET,
    is_the_games_own_winner_market,
)

#: Our `sports.key` for the NFL. StatPal's `nfl` id space is 1:1 with it
#: (`provider_anchor_keys.statpal_id_space`).
NFL_SPORT_KEY = "americanfootball_nfl"

STAGE_PRESEASON = "Pre Season"
STAGE_REGULAR = "Regular Season"
STAGE_POSTSEASON = "Post Season"

#: StatPal's three stage names, exactly as served, to the slug fragment each
#: puts in a container slug. The regular season is the default and carries none.
_STAGE_SLUGS = {
    STAGE_PRESEASON: "preseason-",
    STAGE_REGULAR: "",
    STAGE_POSTSEASON: "postseason-",
}

#: `round_info` is `"<stage> / <week>"` (`StatPalAPIService._parse_nfl_season_schedule`).
_ROUND_SEPARATOR = " / "

#: Only numbered weeks have a week identity. `Hall of Fame Weekend` and the
#: postseason rounds (`Wild Card`, …) are real stage names without a number, and
#: they fall out as `no_week_identity` rather than being guessed a number.
_WEEK_RE = re.compile(r"^Week (\d{1,2})$")

#: The edge source for a game the authority placed in the week. Its confidence
#: is `container_assembly.SOURCE_CONFIDENCE`'s, not this file's.
EVENT_EDGE_SOURCE = "authority_tournament_id"

#: The edge source for a market. It is a member through its `event_id`, which
#: the matcher wrote, so that is the honest provenance — and its confidence is
#: the matcher's default rather than the authority's 1.0.
MARKET_EDGE_SOURCE = "matcher"

# --- exclusion and unavailability reasons (closed; tests read these names) ----

EXCLUDED_NO_CONTEST_ID = "no_contest_id"
EXCLUDED_PLACEHOLDER = "placeholder_contest"
EXCLUDED_NO_WEEK_IDENTITY = "no_week_identity"
EXCLUDED_CONFLICTING_IDENTITY = "conflicting_week_identity"
EXCLUDED_OTHER_WEEK = "other_week"
EXCLUDED_WRONG_SEASON = "wrong_season"
EXCLUDED_DUPLICATE_EVENT_ROWS = "duplicate_event_rows"
EXCLUDED_MARKET_ON_DUPLICATE = "market_on_duplicate_event"

UNAVAILABLE_SEASON_UNKNOWN = "schedule_season_unknown"
UNAVAILABLE_SEASON_MISMATCH = "schedule_is_another_season"
UNAVAILABLE_WEEK_NOT_SCHEDULED = "week_not_in_schedule"
UNAVAILABLE_NO_EVENT_ROW = "no_event_row"

# --- why a week that found members is still not complete (closed) -------------
#: A pass that admitted some games is `complete` only when every game the
#: authority files under the week is a member. Each reason below is a game (or a
#: slice of the week's questions) the pass could not vouch for.

INCOMPLETE_NO_EVENT_ROW = "contest_without_event_row"
INCOMPLETE_DUPLICATE_ROWS = "contest_with_duplicate_event_rows"
INCOMPLETE_CONFLICTING_IDENTITY = "week_contest_with_conflicting_identity"
INCOMPLETE_MARKETS_TRUNCATED = "market_read_truncated"

#: Names StatPal uses for a participant it does not know yet — the same test
#: `stamp_nfl_statpal_fixtures.is_placeholder_fixture` applies (D106 R3),
#: repeated here only because importing a task module into a pure util would
#: drag the anchor channel and the StatPal client in with it.
_PLACEHOLDER_TEAM_NAMES = frozenset({"TBD", "TBA", "N/A", ""})


@dataclass(frozen=True)
class NflWeek:
    """One NFL week, named by the three values the authority files it under."""

    season: int
    week: int
    stage: str = STAGE_REGULAR

    def __post_init__(self) -> None:
        if self.stage not in _STAGE_SLUGS:
            raise ValueError(f"stage={self.stage!r} is not one of {sorted(_STAGE_SLUGS)}")
        if self.week < 1:
            raise ValueError(f"week={self.week!r} must be 1 or more")

    @property
    def slug(self) -> str:
        return f"nfl-{self.season}-{_STAGE_SLUGS[self.stage]}week-{self.week}"

    @property
    def display_name(self) -> str:
        prefix = "" if self.stage == STAGE_REGULAR else f"{self.stage} "
        return f"NFL {self.season} · {prefix}Week {self.week}"


def parse_round_identity(round_info: Optional[str]) -> Optional[tuple[str, int]]:
    """``"Regular Season / Week 1"`` → ``("Regular Season", 1)``; else None.

    Exact, not fuzzy: an unknown stage or an unnumbered week is no identity, and
    no identity is an exclusion the report names — never a nearest guess.
    """
    if not isinstance(round_info, str):
        return None
    parts = round_info.split(_ROUND_SEPARATOR)
    if len(parts) != 2:
        return None
    stage, week = (p.strip() for p in parts)
    if stage not in _STAGE_SLUGS:
        return None
    match = _WEEK_RE.match(week)
    if match is None:
        return None
    return stage, int(match.group(1))


def nfl_season_for_kickoff(kickoff: datetime) -> int:
    """The NFL season a kickoff belongs to: the league names a season for the
    year it starts, so January and February playoff games belong to the year
    before."""
    return kickoff.year if kickoff.month >= 3 else kickoff.year - 1


def _start_known(fixture) -> bool:
    return fixture.start_time is not None and not getattr(
        fixture, "start_is_placeholder", False
    )


def is_placeholder_contest(fixture) -> bool:
    """A bracket slot, not a game: both sides the same club id, or both unnamed."""
    home_id = (getattr(fixture, "home_team_id", None) or "").strip()
    away_id = (getattr(fixture, "away_team_id", None) or "").strip()
    if home_id and home_id == away_id:
        return True
    home = (fixture.home_team or "").strip().upper()
    away = (fixture.away_team or "").strip().upper()
    return home in _PLACEHOLDER_TEAM_NAMES and away in _PLACEHOLDER_TEAM_NAMES


def schedule_season(fixtures: Iterable) -> Optional[int]:
    """Which season this schedule read is, from its own regular-season kickoffs.

    StatPal's NFL `season-schedule` is one season per call and carries no season
    field, so the season is read off the contests it holds: every known,
    non-placeholder regular-season kickoff must agree. None when there is no
    such kickoff or they disagree — an unknown season is not assumed to be the
    one the caller asked for.
    """
    seasons = {
        nfl_season_for_kickoff(f.start_time)
        for f in fixtures
        if _start_known(f)
        and not is_placeholder_contest(f)
        and (parse_round_identity(f.round_info) or ("", 0))[0] == STAGE_REGULAR
    }
    return seasons.pop() if len(seasons) == 1 else None


@dataclass(frozen=True)
class WeekContest:
    """One authority contest the week holds. Status and kickoff are carried as
    the authority served them — unknown stays unknown."""

    contest_id: str
    round_info: str
    status: Optional[str]
    kickoff: Optional[datetime]
    start_known: bool
    teams: tuple

    def receipt(self, **extra) -> dict:
        return {
            "statpal_id": self.contest_id,
            "round": self.round_info,
            "teams": list(self.teams),
            "kickoff": self.kickoff.isoformat() if self.start_known else None,
            "authority_status": self.status,
            **extra,
        }


def _fixture_receipt(fixture, **extra) -> dict:
    return {
        "statpal_id": fixture.fixture_id or None,
        "round": fixture.round_info,
        "teams": [fixture.away_team, fixture.home_team],
        **extra,
    }


@dataclass
class WeekSelection:
    """The authority's contests for one week, and every contest it set aside."""

    target: NflWeek
    season: Optional[int] = None
    contests: list = field(default_factory=list)
    excluded: dict = field(default_factory=dict)
    unavailable: Optional[str] = None
    #: Contest ids the authority files under THIS week that were refused anyway
    #: (also filed under another week). The week is short a game it may own.
    withheld: list = field(default_factory=list)

    def exclude(self, reason: str, receipt: dict) -> None:
        self.excluded.setdefault(reason, []).append(receipt)


def select_week_contests(fixtures: Iterable, target: NflWeek) -> WeekSelection:
    """The contests the authority files under ``target``, deduped by contest id.

    A contest id StatPal lists under two different weeks has no single week and
    is excluded rather than placed in whichever came first.
    """
    fixtures = list(fixtures)
    selection = WeekSelection(target=target, season=schedule_season(fixtures))
    if selection.season is None:
        selection.unavailable = UNAVAILABLE_SEASON_UNKNOWN
        return selection
    if selection.season != target.season:
        selection.unavailable = UNAVAILABLE_SEASON_MISMATCH
        return selection

    identities: dict[str, set] = {}
    first: dict[str, object] = {}
    for fixture in fixtures:
        contest_id = (fixture.fixture_id or "").strip()
        if not contest_id:
            selection.exclude(EXCLUDED_NO_CONTEST_ID, _fixture_receipt(fixture))
            continue
        identities.setdefault(contest_id, set()).add(parse_round_identity(fixture.round_info))
        first.setdefault(contest_id, fixture)

    for contest_id, fixture in first.items():
        if is_placeholder_contest(fixture):
            selection.exclude(EXCLUDED_PLACEHOLDER, _fixture_receipt(fixture))
            continue
        seen = identities[contest_id]
        if len(seen) > 1:
            if (target.stage, target.week) in seen:
                selection.withheld.append(contest_id)
            selection.exclude(
                EXCLUDED_CONFLICTING_IDENTITY,
                _fixture_receipt(fixture, rounds=sorted(str(s) for s in seen)),
            )
            continue
        identity = next(iter(seen))
        if identity is None:
            selection.exclude(EXCLUDED_NO_WEEK_IDENTITY, _fixture_receipt(fixture))
            continue
        if identity != (target.stage, target.week):
            selection.exclude(EXCLUDED_OTHER_WEEK, _fixture_receipt(fixture))
            continue
        known = _start_known(fixture)
        if known and nfl_season_for_kickoff(fixture.start_time) != selection.season:
            selection.exclude(EXCLUDED_WRONG_SEASON, _fixture_receipt(fixture))
            continue
        selection.contests.append(
            WeekContest(
                contest_id=contest_id,
                round_info=fixture.round_info,
                status=fixture.status,
                kickoff=fixture.start_time,
                start_known=known,
                teams=(fixture.away_team, fixture.home_team),
            )
        )

    if not selection.contests:
        selection.unavailable = UNAVAILABLE_WEEK_NOT_SCHEDULED
    return selection


@dataclass(frozen=True)
class EventRow:
    """The columns of one of our NFL events that membership reads."""

    id: int
    statpal_fixture_id: Optional[str]
    status: Optional[str]
    commence_time: Optional[datetime]
    home: Optional[str]
    away: Optional[str]


@dataclass(frozen=True)
class MarketRow:
    """The columns of one of our markets that membership and assembly read."""

    id: int
    event_id: Optional[int]
    name: Optional[str]
    external_id: Optional[str]
    source: Optional[str]
    market_type: Optional[str]
    status: Optional[str]


@dataclass
class WeekMembers:
    """What the week holds, as candidates for `assemble_container`, plus the
    per-game lifecycle a reader of the report needs and every refusal."""

    candidates: list = field(default_factory=list)
    games: list = field(default_factory=list)
    excluded: dict = field(default_factory=dict)
    unavailable: list = field(default_factory=list)

    def exclude(self, reason: str, receipt: dict) -> None:
        self.excluded.setdefault(reason, []).append(receipt)


def resolve_week_members(
    selection: WeekSelection,
    event_rows: Iterable[EventRow],
    market_rows: Iterable[MarketRow],
) -> WeekMembers:
    """Join the week's contests to our rows by contest id, then take their markets.

    Exactly one of our rows per contest, or none is a member: two rows claiming
    one contest are two rows for one game, and picking one would hide the
    finding while admitting half of it. Their markets are held back with them.
    """
    from app.tasks.container_assembly import Candidate

    members = WeekMembers()
    if selection.unavailable:
        return members

    by_contest: dict[str, list[EventRow]] = {}
    for row in event_rows:
        key = (row.statpal_fixture_id or "").strip()
        if key:
            by_contest.setdefault(key, []).append(row)

    member_events: dict[int, WeekContest] = {}
    duplicate_events: set[int] = set()
    for contest in selection.contests:
        rows = sorted(by_contest.get(contest.contest_id, ()), key=lambda r: r.id)
        if not rows:
            members.unavailable.append(contest.receipt(reason=UNAVAILABLE_NO_EVENT_ROW))
            continue
        if len(rows) > 1:
            duplicate_events.update(r.id for r in rows)
            members.exclude(
                EXCLUDED_DUPLICATE_EVENT_ROWS,
                contest.receipt(event_ids=[r.id for r in rows]),
            )
            continue
        row = rows[0]
        member_events[row.id] = contest
        members.games.append(
            contest.receipt(
                event_id=row.id,
                event_status=row.status,
                commence_time=row.commence_time.isoformat() if row.commence_time else None,
            )
        )
        members.candidates.append(
            Candidate(
                child_type="event",
                child_id=row.id,
                source=EVENT_EDGE_SOURCE,
                evidence=MemberEvidence(
                    node_type="event",
                    name=f"{row.away} at {row.home}" if row.away and row.home else None,
                    max_side_size=1,
                ),
                external_id=contest.contest_id,
            )
        )

    seen_markets: set[int] = set()
    for market in sorted(market_rows, key=lambda m: m.id):
        if market.id in seen_markets:
            continue
        seen_markets.add(market.id)
        if market.event_id in member_events and is_the_games_own_winner_market(
            market.market_type, market.name, market.external_id
        ):
            members.exclude(
                EXCLUDED_GAME_WINNER_MARKET,
                {"market_id": market.id, "event_id": market.event_id, "source": market.source},
            )
        elif market.event_id in member_events:
            members.candidates.append(
                Candidate(
                    child_type="market",
                    child_id=market.id,
                    source=MARKET_EDGE_SOURCE,
                    evidence=MemberEvidence(
                        node_type="market",
                        name=market.name,
                        market_shape=market.market_type,
                        external_id=market.external_id,
                    ),
                    external_id=market.external_id,
                    market_source=market.source,
                )
            )
        elif market.event_id in duplicate_events:
            members.exclude(
                EXCLUDED_MARKET_ON_DUPLICATE,
                {"market_id": market.id, "event_id": market.event_id, "source": market.source},
            )

    return members


def week_incompleteness(
    selection: WeekSelection, members: WeekMembers, *, markets_truncated: bool
) -> list[str]:
    """Every reason this pass cannot say it holds the whole week; [] = whole.

    Members admitted around a gap are still right, so a caller may keep them —
    but a week missing a game, holding a game we could not tell apart from its
    twin row, or whose question read hit the cap is `partial`, never `complete`
    (gotcha #53). The order is fixed so the first reason is a stable headline.
    """
    reasons: list[str] = []
    if members.unavailable:
        reasons.append(INCOMPLETE_NO_EVENT_ROW)
    if members.excluded.get(EXCLUDED_DUPLICATE_EVENT_ROWS):
        reasons.append(INCOMPLETE_DUPLICATE_ROWS)
    if selection.withheld:
        reasons.append(INCOMPLETE_CONFLICTING_IDENTITY)
    if markets_truncated:
        reasons.append(INCOMPLETE_MARKETS_TRUNCATED)
    return reasons


# ---------------------------------------------------------------------------
# #5344: the authority moved a game to another week — where it now belongs
# ---------------------------------------------------------------------------
#
# SHIP: when the authoritative schedule moves a game to another week, the next
# complete automatic pass moves it and its questions to the correct hub; old
# links stay truthful and a person's withdrawal is never undone. (Pillars:
# MATCHING / DISCOVER / TRUTH.) Contract:
# `artifacts/containers-1.0.4-20261011/AUTHORITY-5344-CONTRACT-RETURN.md`,
# policy A (`5344-CORRECTION-POLICY-DECISION.md`).
#
# The pure half. `placement_snapshot` reads one whole season schedule and says,
# for every contest it can place, the ONE week the authority files it under —
# or why it cannot. `admission_verdict` decides, from the decisions a container
# already holds, whether a pass that started reading at ``barrier`` may change
# that container at all. The task half (`container_nfl_assembly`) does the
# reads, the locks and the move.
#
# A MOVE NEEDS A POSITIVE PLACEMENT, NEVER AN ABSENCE. A contest the schedule
# does not list at all has no placement, so it is never moved out of anything:
# StatPal publishes no cancelled-contest signal, and a missing row is an outage
# until proved otherwise (gotcha #53).

#: The feed and id space a placement comes from (contract C1).
RELOCATION_SOURCE_KEY = "statpal:nfl:season-schedule"

#: `container_member_decisions.rule_version` (VARCHAR(32)) for every decision
#: this rule writes. The barrier gate reads only rows carrying it.
RELOCATION_RULE_VERSION = "nfl-authority-relocation-v1"

#: The edge sources this adapter owns on an NFL week (contract C7). An edge with
#: any other source is another writer's, and a move never deletes it.
OWNED_EDGE_SOURCES = frozenset({EVENT_EDGE_SOURCE, MARKET_EDGE_SOURCE})

# --- decision reasons (`container_member_decisions.reason`, ≤ 40 chars) -------

#: Positively placed in another week by a complete read: left this container,
#: or (on the destination's row) arrived from another.
DECISION_RELOCATED = "authority_relocated"
#: Placed here, but a person withdrew it from here: it never arrives, and the
#: week it left still loses it — the authority says it is not that week's.
DECISION_RELOCATED_WITHDRAWN = "relocated_destination_withdrawn"

# --- why a read cannot move anything (closed) ---------------------------------

REFUSE_PARSE_INCOMPLETE = "schedule_parse_incomplete"
REFUSE_DUPLICATE_CONTEST_ROWS = "duplicate_contest_rows"

# --- the barrier gate's verdicts (closed) -------------------------------------

ADMIT = "admit"
#: An earlier-started read than one already applied here. Changes nothing.
STALE_SNAPSHOT = "stale_snapshot"
#: Two reads with the SAME barrier disagree about where a member belongs. Equal
#: barriers do not say which is newer, so neither may change anything.
CONFLICTING_EQUAL_BARRIER = "conflicting_equal_barrier"


@dataclass(frozen=True)
class PlacementSnapshot:
    """One whole-season read, as the contract's C1–C6 (no database, no clock).

    ``complete`` is the read half of C5: the parse dropped nothing and the read
    is the declared season. Per-member checks (one row of ours, markets read in
    full) are the task half's. ``barrier`` is the database instant taken BEFORE
    the fetch began; it orders our reads, never the provider's data (RA).
    """

    edition: int
    season: Optional[int]
    barrier: Optional[datetime]
    refusals: tuple
    #: contest id → the one week it is filed under, for every placeable contest.
    placements: dict
    #: contest id → why it has no single week in this read.
    refused: dict
    #: Every week slug this read names for the edition (the reverse lookup's
    #: bound: a move only ever touches containers this read itself names).
    week_slugs: frozenset

    @property
    def complete(self) -> bool:
        return not self.refusals

    def destination(self, contest_id: Optional[str]) -> Optional[str]:
        week = self.placements.get((contest_id or "").strip())
        return week.slug if week is not None else None


def placement_snapshot(
    fixtures: Iterable,
    *,
    edition: int,
    barrier: Optional[datetime],
    parse_complete: bool,
    duplicate_contest_ids: Iterable[str] = (),
) -> PlacementSnapshot:
    """Where the authority files every contest of one season read.

    The rules are `select_week_contests`'s, applied to the whole season at once:
    a contest under two week identities, a bracket placeholder, a round with no
    numbered week and a kickoff in another season have no placement. A contest
    the read counts as a duplicate row (`StatPalNflScheduleRead.duplicates`) is
    refused too, even when every copy names the same week: C5 moves a member
    only on one row.
    """
    fixtures = list(fixtures)
    season = schedule_season(fixtures)
    refusals: list[str] = []
    if not parse_complete:
        refusals.append(REFUSE_PARSE_INCOMPLETE)
    if season is None:
        refusals.append(UNAVAILABLE_SEASON_UNKNOWN)
    elif season != edition:
        refusals.append(UNAVAILABLE_SEASON_MISMATCH)

    duplicates = {(c or "").strip() for c in duplicate_contest_ids}
    identities: dict[str, set] = {}
    first: dict[str, object] = {}
    for fixture in fixtures:
        contest_id = (fixture.fixture_id or "").strip()
        if not contest_id:
            continue
        identities.setdefault(contest_id, set()).add(parse_round_identity(fixture.round_info))
        first.setdefault(contest_id, fixture)

    placements: dict[str, NflWeek] = {}
    refused: dict[str, str] = {}
    slugs: set[str] = set()
    for contest_id, fixture in first.items():
        seen = identities[contest_id]
        for identity in seen:
            if identity is not None:
                slugs.add(NflWeek(season=edition, week=identity[1], stage=identity[0]).slug)
        if is_placeholder_contest(fixture):
            refused[contest_id] = EXCLUDED_PLACEHOLDER
        elif contest_id in duplicates:
            refused[contest_id] = REFUSE_DUPLICATE_CONTEST_ROWS
        elif len(seen) > 1:
            refused[contest_id] = EXCLUDED_CONFLICTING_IDENTITY
        elif next(iter(seen)) is None:
            refused[contest_id] = EXCLUDED_NO_WEEK_IDENTITY
        elif _start_known(fixture) and nfl_season_for_kickoff(fixture.start_time) != edition:
            refused[contest_id] = EXCLUDED_WRONG_SEASON
        else:
            stage, week = next(iter(seen))
            placements[contest_id] = NflWeek(season=edition, week=week, stage=stage)

    return PlacementSnapshot(
        edition=edition,
        season=season,
        barrier=barrier,
        refusals=tuple(refusals),
        placements=placements if not refusals else {},
        refused=refused,
        week_slugs=frozenset(slugs) if not refusals else frozenset(),
    )


@dataclass(frozen=True)
class PriorDecision:
    """One `container_member_decisions` row this rule wrote, as the gate reads it."""

    child_type: str
    child_id: int
    outcome: str
    reason: str
    evidence: dict

    @property
    def barrier(self) -> Optional[datetime]:
        return parse_barrier((self.evidence or {}).get("barrier"))

    @property
    def to_slug(self) -> Optional[str]:
        return (self.evidence or {}).get("to_slug")

    @property
    def contest_id(self) -> Optional[str]:
        return (self.evidence or {}).get("contest_id")


def parse_barrier(value) -> Optional[datetime]:
    """An evidence barrier back to an instant; None for anything not tz-aware."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else None
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def admission_verdict(
    priors: Iterable[PriorDecision], snapshot: PlacementSnapshot
) -> tuple[str, Optional[dict]]:
    """May a pass that began reading at ``snapshot.barrier`` change this container?

    * A row of this rule with a LATER barrier ⇒ ``stale_snapshot``: a read that
      started after ours already decided here, so ours is older evidence.
    * A row with the SAME barrier is the same instant's evidence. It agrees when
      this read places that row's contest in the same week; then the pass may go
      on (an identical repeat is a no-op by construction). It disagrees — or
      this read cannot place it at all — ⇒ ``conflicting_equal_barrier``, and
      nothing in the container may change.
    * No barrier on the pass ⇒ ``admit`` only when the container holds no row of
      this rule; a barrier-less pass can never be ordered against one that has.

    Returns ``(verdict, detail)``; ``detail`` names the row that decided it.
    """
    barrier = snapshot.barrier
    priors = [p for p in priors if p.barrier is not None]
    if barrier is None:
        if priors:
            return STALE_SNAPSHOT, {"reason": "pass_has_no_barrier"}
        return ADMIT, None
    later = [p for p in priors if p.barrier > barrier]
    if later:
        newest = max(later, key=lambda p: p.barrier)
        return STALE_SNAPSHOT, {
            "applied_barrier": newest.barrier.isoformat(),
            "child": f"{newest.child_type}:{newest.child_id}",
        }
    for prior in priors:
        if prior.barrier != barrier:
            continue
        here = snapshot.destination(prior.contest_id) if snapshot.complete else None
        if here is None or here != prior.to_slug:
            return CONFLICTING_EQUAL_BARRIER, {
                "child": f"{prior.child_type}:{prior.child_id}",
                "contest_id": prior.contest_id,
                "recorded_to_slug": prior.to_slug,
                "this_read_to_slug": here,
            }
    return ADMIT, None
