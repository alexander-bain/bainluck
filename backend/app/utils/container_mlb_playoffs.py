"""Which games, and which questions, are one MLB postseason. #9650 (v3, canonical #9217).

**SHIP: a reader opening this year's MLB playoffs sees every playoff game we
hold and the questions on it — not last October's games, not a September
regular-season game, and not the same game twice.** (Pillar: MATCHING / TRUTH.)

This is the pure half of the MLB adapter for `container_assembly`, the sibling
of `container_nfl.py`. It decides membership and says why every non-member is
not one; the task half (`app/tasks/container_mlb_playoffs_assembly.py`) reads
ESPN's boards and our rows and hands the candidates to the shared
`assemble_container`. No database, no network, no clock here.

THE POSTSEASON IS ESPN'S, NEVER OURS. ESPN's MLB scoreboard stamps every game
with `season.type` (3 = postseason; `ESPNEvent.season_type`), the same reading
the ESPN game-day pass and `espn_certain_postseason` already trust to call a
game a playoff game. That is the only thing that makes a game a member. Not
`llm_importance` (a label we write, partly from a classifier), not a kickoff in
October, not a team pair — two clubs meet in September and again in the Wild
Card.

THE SEASON IS READ OFF THE GAME. An MLB season lives inside one calendar year
(the Tokyo opener in March through the World Series in early November), so a
postseason game's season is its own date's year. A board entry with no date has
no season and is refused, never assumed to be this year's.

A GAME IS ONE OF OURS BY ID. ESPN's game id joins our row through
`events.espn_id`, the id `espn_certain_postseason` and the ESPN game-day pass
stamp. Names and kickoff times never admit a member here. A second row for the
same game that holds no ESPN id (a StatPal or Odds API twin; `event_twin_fold`
folds those at serve time by name and minute) cannot get in — it is reported,
and if it holds questions the collection is short them and says so.

A MARKET IS A MEMBER BECAUSE ITS EVENT IS (`futures_markets.event_id`, gotcha
#15). Kalshi's and Polymarket's markets on one game are two questions, and both
stay.

NOT EVERY LISTED GAME IS A GAME. ESPN lists "Game 3 If Necessary" before the
series decides whether it happens. `postseason_series.certain_to_be_played` is
the existing rule: a certain, live or finished game with no row of ours is a
gap; an uncertain one with no row is not yet owed, and is reported as such.

EVERY NON-MEMBER IS ACCOUNTED FOR, and "the playoffs are empty" is never the
same shape as "we could not tell" (gotcha #53). A board day ESPN did not answer
is a day we cannot vouch for, not an empty day.

WHAT IS DELIBERATELY NOT HERE. No bracket, no series table, no seed list, no
member list. A postseason is declared by one value (`MlbPostseason`) and the
board days the caller reads; everything in it is discovered from ESPN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional

from app.utils.container_class import MemberEvidence
from app.utils.postseason_series import certain_to_be_played

#: Our `sports.key` for MLB.
MLB_SPORT_KEY = "baseball_mlb"

#: ESPN `season.type`: 1 preseason, 2 regular season, 3 postseason.
ESPN_POSTSEASON = 3

#: ESPN statuses (`ESPNEvent.status`) that mean the game is being or was played,
#: so it is owed a row whatever the series arithmetic says.
_PLAYED_STATUSES = frozenset({"in", "post", "final"})

#: Edge sources — the same two the NFL adapter uses. A game is a member because
#: the authority placed it in the postseason; a market because the matcher put
#: it on that game.
EVENT_EDGE_SOURCE = "authority_tournament_id"
MARKET_EDGE_SOURCE = "matcher"

#: ESPN's names for a side it has not decided yet.
_PLACEHOLDER_TEAM_NAMES = frozenset({"TBD", "TBA", "N/A", ""})

# --- exclusion and unavailability reasons (closed; tests read these names) ----

EXCLUDED_NO_ESPN_ID = "no_espn_id"
EXCLUDED_NOT_POSTSEASON = "not_postseason"
EXCLUDED_NO_SEASON_TYPE = "no_season_type"
EXCLUDED_NO_DATE = "no_season_evidence"
EXCLUDED_OTHER_SEASON = "other_season"
EXCLUDED_PLACEHOLDER = "placeholder_game"
EXCLUDED_CONFLICTING_IDENTITY = "conflicting_identity"
EXCLUDED_DUPLICATE_EVENT_ROWS = "duplicate_event_rows"
EXCLUDED_MARKET_ON_DUPLICATE = "market_on_duplicate_event"

UNAVAILABLE_NO_BOARD_DAYS = "no_board_days"
UNAVAILABLE_BOARDS_DARK = "espn_boards_dark"
UNAVAILABLE_NO_POSTSEASON_GAMES = "no_postseason_games_listed"
UNAVAILABLE_NO_EVENT_ROW = "no_event_row"

NOT_YET_CERTAIN = "not_yet_certain"

# --- why a postseason that found members is still not complete (closed) ------

INCOMPLETE_BOARD_DAY_DARK = "board_day_unread"
INCOMPLETE_NO_EVENT_ROW = "game_without_event_row"
INCOMPLETE_DUPLICATE_ROWS = "game_with_duplicate_event_rows"
INCOMPLETE_CONFLICTING_IDENTITY = "game_with_conflicting_identity"
INCOMPLETE_MARKETS_TRUNCATED = "market_read_truncated"
INCOMPLETE_STRANDED_QUESTIONS = "questions_on_rows_without_espn_id"


@dataclass(frozen=True)
class MlbPostseason:
    """One MLB postseason, named by its season."""

    season: int

    def __post_init__(self) -> None:
        if self.season < 1903:
            raise ValueError(f"season={self.season!r} is not an MLB postseason")

    @property
    def slug(self) -> str:
        return f"mlb-{self.season}-postseason"

    @property
    def display_name(self) -> str:
        return f"MLB {self.season} Postseason"


def mlb_season_for_date(when: datetime) -> int:
    """An MLB season is one calendar year, so a game's season is its year."""
    return when.year


def _team_name(team: Any) -> str:
    if team is None:
        return ""
    return (getattr(team, "display_name", None) or getattr(team, "name", None) or "").strip()


def is_placeholder_game(entry: Any) -> bool:
    """A bracket slot ESPN has not filled: either side unnamed."""
    return (
        _team_name(getattr(entry, "home_team", None)).upper() in _PLACEHOLDER_TEAM_NAMES
        or _team_name(getattr(entry, "away_team", None)).upper() in _PLACEHOLDER_TEAM_NAMES
    )


def _entry_receipt(entry: Any, **extra) -> dict:
    date = getattr(entry, "date", None)
    return {
        "espn_id": str(getattr(entry, "espn_id", None) or "") or None,
        "teams": [
            _team_name(getattr(entry, "away_team", None)) or None,
            _team_name(getattr(entry, "home_team", None)) or None,
        ],
        "date": date.isoformat() if isinstance(date, datetime) else None,
        "season_type": getattr(entry, "season_type", None),
        **extra,
    }


@dataclass(frozen=True)
class PostseasonGame:
    """One game ESPN files in the postseason. Status and series are carried as
    ESPN served them."""

    espn_id: str
    date: datetime
    status: Optional[str]
    teams: tuple
    game_number: Optional[int]
    certain: bool
    certainty_reason: str

    def receipt(self, **extra) -> dict:
        return {
            "espn_id": self.espn_id,
            "teams": list(self.teams),
            "date": self.date.isoformat(),
            "espn_status": self.status,
            "game_number": self.game_number,
            "certain": self.certain,
            "certainty": self.certainty_reason,
            **extra,
        }


@dataclass
class PostseasonSelection:
    """ESPN's postseason games for one season, and every entry it set aside."""

    target: MlbPostseason
    games: list = field(default_factory=list)
    excluded: dict = field(default_factory=dict)
    unavailable: Optional[str] = None
    days_read: list = field(default_factory=list)
    days_dark: list = field(default_factory=list)
    #: Every ESPN id the boards named, whatever its season type. A row holding
    #: one of these is accounted for — a member, or an entry refused above —
    #: and is never reported as unidentified.
    listed_ids: set = field(default_factory=set)
    #: Postseason ids of THIS season refused for a contradiction. The
    #: postseason is short a game it may own.
    withheld: list = field(default_factory=list)

    def exclude(self, reason: str, receipt: dict) -> None:
        self.excluded.setdefault(reason, []).append(receipt)


def _certainty(entry: Any) -> tuple[bool, str]:
    if getattr(entry, "status", None) in _PLAYED_STATUSES:
        return True, "played"
    return certain_to_be_played(getattr(entry, "playoff_series", None))


def _identity(entry: Any) -> tuple:
    date = getattr(entry, "date", None)
    season = mlb_season_for_date(date) if isinstance(date, datetime) else None
    return (getattr(entry, "season_type", None), season)


def select_postseason_games(
    boards: Iterable[tuple[str, Optional[list]]], target: MlbPostseason
) -> PostseasonSelection:
    """ESPN's postseason games for ``target`` across the boards read.

    ``boards`` is ``[(YYYYMMDD, entries-or-None)]``: None is a day ESPN did not
    answer (`get_scoreboard`'s dark signal), ``[]`` a day with no games. A game
    id ESPN lists twice with a different season or season type has no single
    identity and is refused rather than placed by whichever came first.
    """
    selection = PostseasonSelection(target=target)
    entries: list = []
    for day, board in boards:
        if board is None:
            selection.days_dark.append(day)
            continue
        selection.days_read.append(day)
        entries.extend(board)

    if not selection.days_read:
        selection.unavailable = (
            UNAVAILABLE_BOARDS_DARK if selection.days_dark else UNAVAILABLE_NO_BOARD_DAYS
        )
        return selection

    identities: dict[str, set] = {}
    first: dict[str, Any] = {}
    for entry in entries:
        espn_id = str(getattr(entry, "espn_id", None) or "").strip()
        if not espn_id or espn_id == "None":
            selection.exclude(EXCLUDED_NO_ESPN_ID, _entry_receipt(entry))
            continue
        selection.listed_ids.add(espn_id)
        identities.setdefault(espn_id, set()).add(_identity(entry))
        first.setdefault(espn_id, entry)

    for espn_id, entry in first.items():
        seen = identities[espn_id]
        if len(seen) > 1:
            if (ESPN_POSTSEASON, target.season) in seen:
                selection.withheld.append(espn_id)
            selection.exclude(
                EXCLUDED_CONFLICTING_IDENTITY,
                _entry_receipt(entry, identities=sorted(str(s) for s in seen)),
            )
            continue
        season_type, season = next(iter(seen))
        if season_type is None:
            selection.exclude(EXCLUDED_NO_SEASON_TYPE, _entry_receipt(entry))
            continue
        if season_type != ESPN_POSTSEASON:
            selection.exclude(EXCLUDED_NOT_POSTSEASON, _entry_receipt(entry))
            continue
        if season is None:
            selection.exclude(EXCLUDED_NO_DATE, _entry_receipt(entry))
            continue
        if season != target.season:
            selection.exclude(EXCLUDED_OTHER_SEASON, _entry_receipt(entry))
            continue
        if is_placeholder_game(entry):
            selection.exclude(EXCLUDED_PLACEHOLDER, _entry_receipt(entry))
            continue
        certain, reason = _certainty(entry)
        series = getattr(entry, "playoff_series", None)
        selection.games.append(
            PostseasonGame(
                espn_id=espn_id,
                date=entry.date,
                status=getattr(entry, "status", None),
                teams=(
                    _team_name(getattr(entry, "away_team", None)),
                    _team_name(getattr(entry, "home_team", None)),
                ),
                game_number=getattr(series, "game_number", None),
                certain=certain,
                certainty_reason=reason,
            )
        )

    if not selection.games and not selection.withheld:
        selection.unavailable = UNAVAILABLE_NO_POSTSEASON_GAMES
    return selection


@dataclass(frozen=True)
class EventRow:
    """The columns of one of our MLB events that membership reads."""

    id: int
    espn_id: Optional[str]
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
class PostseasonMembers:
    """What the postseason holds, as candidates for `assemble_container`, plus
    the per-game lifecycle a reader of the report needs and every refusal."""

    candidates: list = field(default_factory=list)
    games: list = field(default_factory=list)
    excluded: dict = field(default_factory=dict)
    unavailable: list = field(default_factory=list)
    not_yet_certain: list = field(default_factory=list)

    def exclude(self, reason: str, receipt: dict) -> None:
        self.excluded.setdefault(reason, []).append(receipt)


def resolve_postseason_members(
    selection: PostseasonSelection,
    event_rows: Iterable[EventRow],
    market_rows: Iterable[MarketRow],
) -> PostseasonMembers:
    """Join ESPN's postseason games to our rows by ESPN id, then take their markets.

    Exactly one of our rows per game, or none is a member: two rows holding one
    ESPN id are two rows for one game, and picking one would hide the finding
    while admitting half of it. Their markets are held back with them.
    """
    from app.tasks.container_assembly import Candidate

    members = PostseasonMembers()
    if selection.unavailable:
        return members

    by_id: dict[str, list[EventRow]] = {}
    for row in event_rows:
        key = (row.espn_id or "").strip()
        if key:
            by_id.setdefault(key, []).append(row)

    member_events: set[int] = set()
    duplicate_events: set[int] = set()
    for game in sorted(selection.games, key=lambda g: (g.date, g.espn_id)):
        rows = sorted(by_id.get(game.espn_id, ()), key=lambda r: r.id)
        if not rows:
            if game.certain:
                members.unavailable.append(game.receipt(reason=UNAVAILABLE_NO_EVENT_ROW))
            else:
                members.not_yet_certain.append(game.receipt(reason=NOT_YET_CERTAIN))
            continue
        if len(rows) > 1:
            duplicate_events.update(r.id for r in rows)
            members.exclude(
                EXCLUDED_DUPLICATE_EVENT_ROWS, game.receipt(event_ids=[r.id for r in rows])
            )
            continue
        row = rows[0]
        member_events.add(row.id)
        members.games.append(
            game.receipt(
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
                external_id=game.espn_id,
            )
        )

    seen_markets: set[int] = set()
    for market in sorted(market_rows, key=lambda m: m.id):
        if market.id in seen_markets:
            continue
        seen_markets.add(market.id)
        if market.event_id in member_events:
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


def postseason_incompleteness(
    selection: PostseasonSelection,
    members: PostseasonMembers,
    *,
    markets_truncated: bool,
    stranded_questions: int = 0,
) -> list[str]:
    """Every reason this pass cannot say it holds the whole postseason read.

    [] means whole *over the board days read*. Members admitted around a gap
    are still right, so a caller may keep them — but an unread day, a game owed
    a row that has none, a game held as two rows, a contradicted game, a capped
    question read, or questions sitting on a row with no ESPN id make the pass
    `partial`, never `complete` (gotcha #53). Uncertain games with no row are
    not owed yet and do not count. Fixed order: the first is the headline.
    """
    reasons: list[str] = []
    if selection.days_dark:
        reasons.append(INCOMPLETE_BOARD_DAY_DARK)
    if members.unavailable:
        reasons.append(INCOMPLETE_NO_EVENT_ROW)
    if members.excluded.get(EXCLUDED_DUPLICATE_EVENT_ROWS):
        reasons.append(INCOMPLETE_DUPLICATE_ROWS)
    if selection.withheld:
        reasons.append(INCOMPLETE_CONFLICTING_IDENTITY)
    if markets_truncated:
        reasons.append(INCOMPLETE_MARKETS_TRUNCATED)
    if stranded_questions:
        reasons.append(INCOMPLETE_STRANDED_QUESTIONS)
    return reasons
