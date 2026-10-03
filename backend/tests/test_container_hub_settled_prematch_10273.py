"""#10273 — a finished game shows one pre-match number on the NFL week hub and on its page.

PILLAR: TRUTH · SHIP: the hub card of a settled game prints the pre-match
reading its own page prints.

Seen 2026-10-03 03:05Z, Steelers @ Browns (14780550, final 24–27): the NFL
Week 4 hub card read Steelers 59% (`opening_odds`, the sportsbook median); one
tap later the page read "Pre-match 60%" (`prematch_odds`, kalshi). The hub
hydrates its game cards through the `/api/events` list serializer, which never
carried `prematch_odds`; the event route (#8315) and `/api/feed` both do.

Pinned here, on the served hub payload:

* the specimen's card carries `prematch_odds` and it is the page's number;
* it is the SAME object `events._settled_prematch_odds` serves for the same
  rows — one ladder, not three;
* only settled cards read or carry it, and the read is ONE statement for the
  whole hub, however many settled games it holds;
* a failed venue read costs the hub nothing but the venue rungs.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.routes.events import _settled_prematch_odds
from app.utils.prematch_reading import PREMATCH_PRIOR_SQL

from tests.test_container_hydrated_reader_9636 import (
    KICKOFF,
    _Hub,
    _Result,
    _Session,
    _event,
    _get,
)

SPECIMEN = 14780550
_PREMATCH = " ".join(PREMATCH_PRIOR_SQL.split())


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")


def _is_prematch(sql) -> bool:
    return " ".join(str(sql).split()) == _PREMATCH


class _Savepoint:
    def __init__(self, log):
        self.log = log

    async def commit(self):
        self.log.append("commit")

    async def rollback(self):
        self.log.append("rollback")


class _PrematchHubSession(_Session):
    """The #9636 hub double, plus the pre-match statement and a savepoint."""

    def __init__(self, hub, *, rows=(), fail=False, **kwargs):
        super().__init__(hub, **kwargs)
        self.rows = list(rows)
        self.fail = fail
        self.prematch_binds: list[dict] = []
        self.savepoint_log: list[str] = []

    async def begin_nested(self):
        self.savepoint_log.append("begin")
        return _Savepoint(self.savepoint_log)

    async def execute(self, sql, params=None):
        if _is_prematch(sql):
            self.statements.append(str(sql))
            self.prematch_binds.append(params)
            if self.fail:
                raise RuntimeError("canceling statement due to statement timeout")
            wanted = set(params["ids"])
            return _Result([r for r in self.rows if r.event_id in wanted])
        return await super().execute(sql, params)


def _row(event_id, source, home, away, draw=None):
    return SimpleNamespace(
        event_id=event_id,
        source=source,
        home_win_probability=home,
        away_win_probability=away,
        draw_probability=draw,
    )


def _final(event_id, home, away, *, open_home, open_away, hours=-72, **extra):
    return _event(
        event_id, home, away, hours=hours, status="completed",
        home_score=extra.pop("home_score", 27), away_score=extra.pop("away_score", 24),
        completed_at=KICKOFF + timedelta(hours=hours + 3),
        opening_home_probability=open_home, opening_away_probability=open_away,
        **extra,
    )


def _week4(*events):
    edges = [("match_winner", "event", e.id, 74, "statpal", 1.0) for e in events]
    return _Hub("nfl-2026-week-4", container_id=74, edges=edges, name="NFL 2026 · Week 4")


def _cards(payload):
    return {m["id"]: m["card"] for s in payload["sections"] for m in s["members"]}


async def test_the_specimen_hub_card_prints_the_pages_pre_match_number():
    game = _final(SPECIMEN, "Cleveland Browns", "Pittsburgh Steelers",
                  open_home=0.4072, open_away=0.5928)
    rows = [_row(SPECIMEN, "kalshi", 0.405, 0.595)]
    session = _PrematchHubSession(_week4(game), events=[game], rows=rows)

    card = _cards(await _get(session, "nfl-2026-week-4"))[SPECIMEN]

    # The card the reader saw: opening 59 — still served, for released readers.
    assert round(card["opening_odds"]["away_probability"] * 100) == 59
    # The number the page prints, now on the hub card too.
    assert card["prematch_odds"]["away_rendered_percent"] == 60
    assert card["prematch_odds"]["home_rendered_percent"] == 40
    assert card["prematch_odds"]["source"] == "kalshi"


@pytest.mark.parametrize(
    "rows, open_home, open_away, sport",
    [
        # The specimen: a venue rung outranks the books.
        ([_row(SPECIMEN, "kalshi", 0.405, 0.595)], 0.4072, 0.5928, "americanfootball_nfl"),
        # Polymarket alone.
        ([_row(SPECIMEN, "polymarket", 0.47, 0.53)], 0.4072, 0.5928, "americanfootball_nfl"),
        # Both venues: the ladder picks, not the hub.
        ([_row(SPECIMEN, "polymarket", 0.47, 0.53), _row(SPECIMEN, "kalshi", 0.405, 0.595)],
         0.4072, 0.5928, "americanfootball_nfl"),
        # No venue reading: the books rung.
        ([], 0.4072, 0.5928, "americanfootball_nfl"),
        # A three-way sport with a priced draw (#7514): the away slot is not 1 − home.
        ([_row(SPECIMEN, "polymarket", 0.45, 0.30, 0.25)], 0.46, 0.28, "soccer_epl"),
    ],
)
async def test_the_hub_card_serves_the_same_object_as_the_event_page(rows, open_home, open_away, sport):
    from tests.test_container_hydrated_reader_9636 import _sport

    game = _final(SPECIMEN, "Cleveland Browns", "Pittsburgh Steelers",
                  open_home=open_home, open_away=open_away, sport=_sport(sport, sport))
    hub_session = _PrematchHubSession(_week4(game), events=[game], rows=rows)
    card = _cards(await _get(hub_session, "nfl-2026-week-4"))[SPECIMEN]

    page_session = _PrematchHubSession(None, rows=rows)
    page = await _settled_prematch_odds(page_session, game, sport)

    assert page is not None
    assert card["prematch_odds"] == page


async def test_only_settled_cards_read_or_carry_it_and_the_cutoff_is_their_own_kickoff():
    final = _final(SPECIMEN, "Cleveland Browns", "Pittsburgh Steelers",
                   open_home=0.4072, open_away=0.5928)
    live = _event(14780551, "Philadelphia Eagles", "Dallas Cowboys", hours=-1, status="live",
                  home_score=7, away_score=3, opening_home_probability=0.6,
                  opening_away_probability=0.4)
    later = _event(14780552, "Buffalo Bills", "Kansas City Chiefs", hours=53,
                   opening_home_probability=0.55, opening_away_probability=0.45)
    rows = [
        _row(SPECIMEN, "kalshi", 0.405, 0.595),
        # A live game's venue reading must never become a "pre-match" number.
        _row(14780551, "kalshi", 0.9, 0.1),
    ]
    session = _PrematchHubSession(_week4(final, live, later), events=[final, live, later], rows=rows)

    cards = _cards(await _get(session, "nfl-2026-week-4"))

    assert "prematch_odds" in cards[SPECIMEN]
    assert "prematch_odds" not in cards[14780551]
    assert "prematch_odds" not in cards[14780552]
    assert len(session.prematch_binds) == 1
    binds = session.prematch_binds[0]
    assert binds["ids"] == [SPECIMEN]
    assert binds["cutoffs"] == [final.commence_time]


async def test_an_all_unsettled_hub_never_issues_the_read():
    later = _event(14780552, "Buffalo Bills", "Kansas City Chiefs", hours=53)
    session = _PrematchHubSession(_week4(later), events=[later])
    cards = _cards(await _get(session, "nfl-2026-week-4"))
    assert "prematch_odds" not in cards[14780552]
    assert session.prematch_binds == []
    assert session.savepoint_log == []


async def test_the_read_is_one_statement_for_one_settled_game_and_forty():
    counts = {}
    for games in (1, 40):
        events = [
            _final(14790000 + i, f"Home {i}", f"Away {i}", open_home=0.55, open_away=0.45)
            for i in range(games)
        ]
        rows = [_row(e.id, "kalshi", 0.52, 0.48) for e in events]
        session = _PrematchHubSession(_week4(*events), events=events, rows=rows)
        cards = _cards(await _get(session, "nfl-2026-week-4"))
        assert all(c["prematch_odds"]["source"] == "kalshi" for c in cards.values())
        assert len(session.prematch_binds) == 1
        counts[games] = len(session.statements)
    assert counts[1] == counts[40], counts


async def test_a_failed_venue_read_costs_the_hub_only_the_venue_rungs():
    game = _final(SPECIMEN, "Cleveland Browns", "Pittsburgh Steelers",
                  open_home=0.4072, open_away=0.5928)
    session = _PrematchHubSession(
        _week4(game), events=[game], rows=[_row(SPECIMEN, "kalshi", 0.405, 0.595)], fail=True,
    )

    payload = await _get(session, "nfl-2026-week-4")
    card = _cards(payload)[SPECIMEN]

    assert payload["state"] == "published"
    assert session.savepoint_log == ["begin", "rollback"]
    # The books rung, exactly as the card would answer with no venue snapshots.
    assert card["prematch_odds"]["source"] != "kalshi"
    assert card["prematch_odds"]["away_rendered_percent"] == 59
