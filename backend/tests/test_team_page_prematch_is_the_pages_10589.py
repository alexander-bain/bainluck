"""#10589 — a team page's "we had them at N%" is the game page's "Pre-match N%".

PILLAR: TRUTH / FORMATTING · SHIP: a team page's pre-game number is the number
the game's own page prints as its pre-match chance.

Seen 2026-10-06 04:32Z on the iPhone: Brewers → Recent → "vs San Diego Padres ·
FINAL · we had them at 55% · 4–3"; one tap later the game page (15323985) read
"Brewers Win · Pre-match 44% – 56%". The team brief served
`opening_home_probability` (the sportsbook median, 0.549) while the page serves
the #8315 ladder (kalshi 0.555). Both clients print the brief's
`pregame_win_probability` as round(p × 100), so the server is the one fix.

Pinned on the brief the team route builds (`_folded_briefs`, the real seam):

* the specimen prints the page's percent from BOTH teams' pages — the home side
  56 and the away side 44, the derived half of the page's paired rounding, which
  a raw underdog reading re-rounded alone would print as 45;
* it is computed from the SAME object `events._settled_prematch_odds` serves;
* an unsettled row never reads and keeps its opening line;
* both rails share ONE read, and a failed read costs only the venue rungs.
"""

from __future__ import annotations

import math
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.models import Team
from app.routes import teams as teams_route
from app.routes.events import _settled_prematch_odds
from app.utils.prematch_reading import PREMATCH_PRIOR_SQL

from tests.test_container_hydrated_reader_9636 import KICKOFF, _Result, _event, _sport

SPECIMEN = 15323985
MLB = "baseball_mlb"
_PREMATCH = " ".join(PREMATCH_PRIOR_SQL.split())


class _Savepoint:
    def __init__(self, log):
        self.log = log

    async def commit(self):
        self.log.append("commit")

    async def rollback(self):
        self.log.append("rollback")


class _PrematchSession:
    """Answers the pre-match statement and nothing else (the fold is stubbed)."""

    def __init__(self, rows=(), *, fail=False):
        self.rows = list(rows)
        self.fail = fail
        self.prematch_binds: list[dict] = []
        self.savepoint_log: list[str] = []

    async def begin_nested(self):
        self.savepoint_log.append("begin")
        return _Savepoint(self.savepoint_log)

    async def execute(self, sql, params=None):
        assert " ".join(str(sql).split()) == _PREMATCH, str(sql)[:120]
        self.prematch_binds.append(params)
        if self.fail:
            raise RuntimeError("canceling statement due to statement timeout")
        wanted = set(params["ids"])
        return _Result([r for r in self.rows if r.event_id in wanted])


@pytest.fixture(autouse=True)
def _no_fold(monkeypatch):
    async def _empty(db, rows):
        return {}

    monkeypatch.setattr(teams_route, "folded_probability_sources_batch", _empty)


def _row(event_id, source, home, away, draw=None):
    return SimpleNamespace(
        event_id=event_id,
        source=source,
        home_win_probability=home,
        away_win_probability=away,
        draw_probability=draw,
    )


def _team(team_id, name):
    team = Team(id=team_id, name=name)
    return team


BREWERS = _team(1, "Milwaukee Brewers")
PADRES = _team(2, "San Diego Padres")


def _final(event_id, *, open_home, open_away, hours=-30):
    return _event(
        event_id, "Milwaukee Brewers", "San Diego Padres", hours=hours,
        status="completed", home_score=4, away_score=3,
        home_team_id=BREWERS.id, away_team_id=PADRES.id,
        completed_at=KICKOFF + timedelta(hours=hours + 3),
        opening_home_probability=open_home, opening_away_probability=open_away,
        sport=_sport(MLB, "MLB"),
    )


def _prints(p) -> int:
    """What both clients print: web `Math.round(pre * 100)`, Swift `round(p * 100)`."""
    return math.floor(p * 100 + 0.5)


async def _brief(session, team, *rails):
    out = await teams_route._folded_briefs(session, team, *rails)
    return {b["id"]: b for rail in out for b in rail}


async def test_the_specimen_prints_the_pages_pre_match_percent_from_both_team_pages():
    game = _final(SPECIMEN, open_home=0.549, open_away=0.451)
    rows = [_row(SPECIMEN, "kalshi", 0.555, 0.445)]

    page = await _settled_prematch_odds(_PrematchSession(rows), game, MLB)
    assert page["source"] == "kalshi"
    assert (page["away_rendered_percent"], page["home_rendered_percent"]) == (44, 56)

    brewers = (await _brief(_PrematchSession(rows), BREWERS, [game]))[SPECIMEN]
    padres = (await _brief(_PrematchSession(rows), PADRES, [game]))[SPECIMEN]

    # The reader's line, before: "we had them at 55%" off the opening 0.549.
    assert _prints(0.549) == 55
    assert brewers["is_home"] is True and padres["is_home"] is False
    assert _prints(brewers["pregame_win_probability"]) == page["home_rendered_percent"] == 56
    # The derived half: the raw away reading 0.445 alone would print 45.
    assert _prints(0.445) == 45
    assert _prints(padres["pregame_win_probability"]) == page["away_rendered_percent"] == 44


@pytest.mark.parametrize(
    "rows, open_home, open_away",
    [
        # The second specimen (15319529, the Cardinals game): kalshi 0.655 vs 0.648.
        ([_row(SPECIMEN, "kalshi", 0.655, 0.345)], 0.648, 0.352),
        # Polymarket alone.
        ([_row(SPECIMEN, "polymarket", 0.47, 0.53)], 0.52, 0.48),
        # Both venues: the ladder picks, not the team page.
        ([_row(SPECIMEN, "polymarket", 0.47, 0.53), _row(SPECIMEN, "kalshi", 0.405, 0.595)],
         0.44, 0.56),
        # No venue reading: the books rung, still the page's rounding.
        ([], 0.555, 0.445),
    ],
)
async def test_every_rung_prints_what_the_page_prints(rows, open_home, open_away):
    game = _final(SPECIMEN, open_home=open_home, open_away=open_away)
    page = await _settled_prematch_odds(_PrematchSession(rows), game, MLB)
    assert page is not None

    home = (await _brief(_PrematchSession(rows), BREWERS, [game]))[SPECIMEN]
    away = (await _brief(_PrematchSession(rows), PADRES, [game]))[SPECIMEN]

    assert _prints(home["pregame_win_probability"]) == page["home_rendered_percent"]
    assert _prints(away["pregame_win_probability"]) == page["away_rendered_percent"]


async def test_an_unsettled_row_never_reads_and_keeps_its_opening_line():
    upcoming = _event(
        15323999, "Milwaukee Brewers", "San Diego Padres", hours=20,
        home_team_id=BREWERS.id, away_team_id=PADRES.id,
        opening_home_probability=0.61, opening_away_probability=0.39,
        sport=_sport(MLB, "MLB"),
    )
    session = _PrematchSession([_row(15323999, "kalshi", 0.9, 0.1)])

    brief = (await _brief(session, BREWERS, [upcoming]))[15323999]

    assert brief["pregame_win_probability"] == 0.61
    assert session.prematch_binds == []
    assert session.savepoint_log == []


async def test_both_rails_share_one_read_cut_at_each_rows_own_kickoff():
    recent = [
        _final(SPECIMEN, open_home=0.549, open_away=0.451),
        _final(15322620, open_home=0.62, open_away=0.38, hours=-54),
    ]
    upcoming = [
        _event(15323999, "Milwaukee Brewers", "San Diego Padres", hours=20,
               home_team_id=BREWERS.id, away_team_id=PADRES.id, sport=_sport(MLB, "MLB")),
    ]
    rows = [_row(SPECIMEN, "kalshi", 0.555, 0.445), _row(15322620, "kalshi", 0.645, 0.355)]
    session = _PrematchSession(rows)

    briefs = await _brief(session, BREWERS, upcoming, recent)

    assert len(session.prematch_binds) == 1
    binds = session.prematch_binds[0]
    assert binds["ids"] == [SPECIMEN, 15322620]
    assert binds["cutoffs"] == [recent[0].commence_time, recent[1].commence_time]
    assert _prints(briefs[SPECIMEN]["pregame_win_probability"]) == 56
    assert _prints(briefs[15322620]["pregame_win_probability"]) == 65


async def test_a_failed_venue_read_costs_the_team_page_only_the_venue_rungs():
    game = _final(SPECIMEN, open_home=0.549, open_away=0.451)
    session = _PrematchSession([_row(SPECIMEN, "kalshi", 0.555, 0.445)], fail=True)

    brief = (await _brief(session, BREWERS, [game]))[SPECIMEN]
    page = await _settled_prematch_odds(_PrematchSession(fail=True), game, MLB)

    assert session.savepoint_log == ["begin", "rollback"]
    assert page["source"] != "kalshi"
    assert _prints(brief["pregame_win_probability"]) == page["home_rendered_percent"] == 55
