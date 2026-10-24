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

A PROVEN DUPLICATE'S QUESTIONS COME IN THROUGH ITS MEMBER (#9886). A row that
carries `provenance:duplicate-of:<member>` was proven, at the write side and on
an id-anchored correspondence (ruling 048), to be the same game as a member.
`proven_duplicates.folded_event_ids` already serves its markets on the member's
page; `admit_proven_duplicates` lets the postseason count them the same way.
The row itself never becomes a member and no market moves: each question keeps
its own `event_id`, and the report names the row it sits on and the member it
came in through. The label is trusted exactly as far as that reader trusts it —
ONE HOP. A label naming a row that is not this postseason's member, naming
itself, naming a row that is itself labelled, or sitting beside a second label
admits nothing, and neither does a row on another sport, another season, or
holding an ESPN id of its own. Each refusal is named, and a refused row in the
postseason's span stays unidentified, so its questions still make the pass
`partial`.

A MARKET IS A MEMBER BECAUSE ITS EVENT IS (`futures_markets.event_id`, gotcha
#15) — except the game's own winner market. Kalshi's and Polymarket's "who wins
Game 1" markets are the game card's blended number, not two more questions, so
they are reported under `EXCLUDED_GAME_WINNER_MARKET`, never edged
(`container_game_winner`). Every other question on the game stays.

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

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional

from app.services.anchor_channel import DUPLICATE_TAG_PREFIX
from app.utils.container_class import MemberEvidence
from app.utils.container_game_winner import (
    EXCLUDED_GAME_WINNER_MARKET,
    is_the_games_own_winner_market,
)
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
EXCLUDED_DUPLICATE_LABEL_REFUSED = "duplicate_label_refused"

# --- why a `duplicate-of` label admits nothing (closed; tests read these names)

REFUSED_OTHER_SPORT = "other_sport"
REFUSED_CONFLICTING_LABELS = "conflicting_labels"
REFUSED_MALFORMED_LABEL = "malformed_label"
REFUSED_SELF_LABEL = "self_label"
REFUSED_TARGET_NOT_A_MEMBER = "target_not_a_member"
REFUSED_ROW_HOLDS_ESPN_ID = "row_holds_espn_id"
REFUSED_TARGET_IS_LABELLED = "target_is_labelled"
REFUSED_OTHER_SEASON = "other_season"

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
INCOMPLETE_DUPLICATES_UNREAD = "proven_duplicates_unread"


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
    #: The tail of every `provenance:duplicate-of:` label the row carries
    #: (`duplicate_labels`). Read on a member so a label naming it can tell
    #: whether it is itself a duplicate.
    duplicate_labels: tuple = ()


def duplicate_labels(event_tags: Any) -> tuple:
    """The tail of every ``provenance:duplicate-of:`` element, verbatim, in order.

    Verbatim so a malformed or second label is SEEN and refused rather than
    skipped: `proven_duplicates.canonical_id_from_tags` returns the first
    numeric tail, which is right for a page printing one row and wrong for a
    membership rule that must refuse a row naming two games. JSONB arrives as a
    list from asyncpg and as serialised text from a test double; text is
    decoded, never iterated (iterating it yields characters and finds nothing).
    """
    if isinstance(event_tags, str):
        try:
            event_tags = json.loads(event_tags)
        except ValueError:
            return ()
    if not isinstance(event_tags, (list, tuple)):
        return ()
    return tuple(
        tag[len(DUPLICATE_TAG_PREFIX):]
        for tag in event_tags
        if isinstance(tag, str) and tag.startswith(DUPLICATE_TAG_PREFIX)
    )


@dataclass(frozen=True)
class DuplicateRow:
    """One of our rows carrying a `duplicate-of` label that names a member."""

    id: int
    espn_id: Optional[str]
    status: Optional[str]
    commence_time: Optional[datetime]
    home: Optional[str]
    away: Optional[str]
    sport_key: Optional[str]
    duplicate_labels: tuple
    markets: int = 0

    def receipt(self, **extra) -> dict:
        return {
            "event_id": self.id,
            "teams": [self.away, self.home],
            "commence_time": self.commence_time.isoformat() if self.commence_time else None,
            "status": self.status,
            "espn_id": self.espn_id,
            "sport": self.sport_key,
            "labels": list(self.duplicate_labels),
            "markets": self.markets,
            **extra,
        }


@dataclass
class ProvenDuplicates:
    """Which labelled rows bring their questions in, through which member."""

    #: duplicate row id -> the member it was proven to duplicate.
    admitted: dict = field(default_factory=dict)
    receipts: list = field(default_factory=list)
    refused: list = field(default_factory=list)


def admit_proven_duplicates(
    target: MlbPostseason,
    members: dict,
    rows: Iterable[DuplicateRow],
) -> ProvenDuplicates:
    """Admit the rows whose ONE label names one of ``members`` directly.

    ``members`` is ``{event id: EventRow}`` for this postseason's members — the
    rows `resolve_postseason_members` admits by ESPN id, and nothing else. The
    label is the write side's proof and is trusted, never re-litigated by name
    or kickoff; everything here is the read side declining what that proof does
    not cover. First matching refusal wins, in a fixed order.
    """
    out = ProvenDuplicates()
    for row in sorted(rows, key=lambda r: r.id):
        labels = set(row.duplicate_labels)
        tail = next(iter(labels)) if len(labels) == 1 else None
        canonical = int(tail) if tail is not None and tail.isdigit() else None
        if row.sport_key != MLB_SPORT_KEY:
            refusal = REFUSED_OTHER_SPORT
        elif len(labels) != 1:
            refusal = REFUSED_CONFLICTING_LABELS
        elif canonical is None:
            refusal = REFUSED_MALFORMED_LABEL
        elif canonical == row.id:
            refusal = REFUSED_SELF_LABEL
        elif canonical not in members:
            refusal = REFUSED_TARGET_NOT_A_MEMBER
        elif (row.espn_id or "").strip():
            # ESPN's id is a game's identity; a row holding one is that game.
            refusal = REFUSED_ROW_HOLDS_ESPN_ID
        elif members[canonical].duplicate_labels:
            # One hop: a duplicate of a duplicate is a matching defect, and a
            # cycle ends here too — never walked.
            refusal = REFUSED_TARGET_IS_LABELLED
        elif row.commence_time is None or mlb_season_for_date(row.commence_time) != target.season:
            refusal = REFUSED_OTHER_SEASON
        else:
            out.admitted[row.id] = canonical
            out.receipts.append(row.receipt(duplicate_of=canonical))
            continue
        out.refused.append(row.receipt(refusal=refusal))
    return out


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
    #: Rows proven to duplicate a member, whose questions came in through it.
    proven_duplicates: list = field(default_factory=list)

    def exclude(self, reason: str, receipt: dict) -> None:
        self.excluded.setdefault(reason, []).append(receipt)


def postseason_member_rows(
    selection: PostseasonSelection, event_rows: Iterable[EventRow]
) -> dict:
    """``{event id: EventRow}`` for the rows that are members — the game half of
    `resolve_postseason_members`, which a `duplicate-of` label must name."""
    rows = list(event_rows)
    members, _, _ = _resolve_games(selection, rows)
    by_id = {row.id: row for row in rows}
    return {c.child_id: by_id[c.child_id] for c in members.candidates}


def resolve_postseason_members(
    selection: PostseasonSelection,
    event_rows: Iterable[EventRow],
    market_rows: Iterable[MarketRow],
    proven: Optional[ProvenDuplicates] = None,
) -> PostseasonMembers:
    """Join ESPN's postseason games to our rows by ESPN id, then take their markets.

    Exactly one of our rows per game, or none is a member: two rows holding one
    ESPN id are two rows for one game, and picking one would hide the finding
    while admitting half of it. Their markets are held back with them.

    ``proven`` (`admit_proven_duplicates`) names rows whose questions come in
    through a member. Only a member's own duplicates count — a label whose
    member did not survive this join admits nothing — and each question is
    counted once, receipted with the row it actually sits on.
    """
    from app.tasks.container_assembly import Candidate

    members, member_events, duplicate_events = _resolve_games(selection, list(event_rows))
    if selection.unavailable:
        return members

    via: dict[int, int] = {}
    if proven is not None:
        for receipt in proven.receipts:
            if receipt["duplicate_of"] in member_events:
                via[receipt["event_id"]] = receipt["duplicate_of"]
                members.proven_duplicates.append(receipt)
        for receipt in proven.refused:
            members.exclude(EXCLUDED_DUPLICATE_LABEL_REFUSED, receipt)

    seen_markets: set[int] = set()
    for market in sorted(market_rows, key=lambda m: m.id):
        if market.id in seen_markets:
            continue
        seen_markets.add(market.id)
        on_member = market.event_id in member_events or market.event_id in via
        receipt = {"market_id": market.id, "event_id": market.event_id, "source": market.source}
        if market.event_id in via:
            receipt["via_member"] = via[market.event_id]
        if on_member and is_the_games_own_winner_market(
            market.market_type, market.name, market.external_id
        ):
            members.exclude(EXCLUDED_GAME_WINNER_MARKET, receipt)
        elif on_member:
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
            members.exclude(EXCLUDED_MARKET_ON_DUPLICATE, receipt)

    return members


def _resolve_games(
    selection: PostseasonSelection, event_rows: list
) -> tuple[PostseasonMembers, set, set]:
    """The game half: members, their event ids, and rows refused as duplicates."""
    from app.tasks.container_assembly import Candidate

    members = PostseasonMembers()
    if selection.unavailable:
        return members, set(), set()

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
    return members, member_events, duplicate_events


def postseason_incompleteness(
    selection: PostseasonSelection,
    members: PostseasonMembers,
    *,
    markets_truncated: bool,
    stranded_questions: int = 0,
    duplicates_skipped: Optional[str] = None,
) -> list[str]:
    """Every reason this pass cannot say it holds the whole postseason read.

    [] means whole *over the board days read*. Members admitted around a gap
    are still right, so a caller may keep them — but an unread day, a game owed
    a row that has none, a game held as two rows, a contradicted game, a capped
    question read, questions sitting on a row with no ESPN id, or a skipped
    proven-duplicate read make the pass `partial`, never `complete` (gotcha
    #53). Uncertain games with no row are not owed yet and do not count. Fixed
    order: the first is the headline.

    ``duplicates_skipped`` is the reason the bounded duplicate read did not run
    (``too_many_members`` / ``duplicate_read_overflow``). A skip is a gap on its
    own: a proven duplicate OUTSIDE the span is never in the in-span report, so
    without this its questions would go unread under a `complete` verdict.
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
    if duplicates_skipped:
        reasons.append(INCOMPLETE_DUPLICATES_UNREAD)
    return reasons
