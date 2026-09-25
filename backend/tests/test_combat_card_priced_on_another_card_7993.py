"""#7993 — the MMA hub stops offering a phantom "Sun, Sep 27" card.

═══ THE DEFECT ═══

Production 2026-09-24 17:30Z, `/api/hub/mma` upcoming:

    event:ufc:26sep26  Fight Night: Rosas Jr vs Barcelos          12 fights
    event:ufc:26sep27  UFC Fight Night: Rosas Jr. vs. Barcelos     3 fights  <- phantom

The three Sep 27 "bouts" are rows 15315974/5/6 — `Osmanli vs Uulu`, `Harrell vs
Brener`, `Dumont Viana vs Perez`, `commence_time_source='kalshi'`, no provider
id. The matcher could not join those Kalshi fights to the schedule rows of the
same bouts (spelled "Ilimbek Akylbek", "Elves Brenner", "Norma Dumont"), so under
ruling 048 it minted a row for each, stamped with Kalshi's CLOSE time (gotcha
#14) — 02:20Z, 05:00Z, 05:40Z the next UTC day. `_list_event_bouts` keys rows by
their UTC date, so they formed a card of their own. Each row's OWN open market
(`KXUFCFIGHT-26SEP26DUMPER/HARBRE/OSMUUL`) was on the real card all along.

═══ WHAT IS ASSERTED ═══

  1. the lister drops the phantom and keeps the real card, count unchanged
  2. the page behind the phantom answers `None` (the route's 404)
  3. lister and page agree, both directions (the #6733 property)
  4. controls: a bout of the token's own keeps the card on both layers; a real
     events-only card with no markets is untouched
  5. the predicate's own arms, including a ticker that names THIS card
"""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_combat import (
    card_bouts_are_priced_on_another_card,
    event_commence_token,
    list_card_concepts,
    ticker_card_tokens_by_event,
)
from app.utils.event_ufc import UFC_CONFIG, UFCEventAdapter

_IDS = itertools.count(7993000)

# ONE clock read for the whole module. The module-level card (_D, _NEXT) is
# built at collection time and the controls call _at() at run time; with a
# fresh now() each, a run that collects before 00:00 UTC and reaches the
# controls after it puts the "own bout" a day past _NEXT (CI 2026-09-25 00:14Z).
_NOW = datetime.now(timezone.utc)


def _at(days: int, hour: int, minute: int = 0) -> datetime:
    """A fixed instant. Offset FIRST, then truncate (gotcha #44)."""
    return (_NOW + timedelta(days=days)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )


def _bout(home, away, when):
    return SimpleNamespace(
        id=next(_IDS),
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        status="scheduled",
        win_probability_sources=None,
    )


def _market(ticker, name, close, event_id):
    return SimpleNamespace(
        id=next(_IDS),
        external_id=ticker,
        name=name,
        commence_time=close,
        event_id=event_id,
        market_metadata=None,
        outcomes=[SimpleNamespace(name="A"), SimpleNamespace(name="B")],
    )


class _FakeResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._items)


class _FakeDB:
    """Dispatch on the statement text (see #6733's suite for why)."""

    def __init__(self, events=(), markets=()):
        self._events = list(events)
        self._markets = list(markets)

    async def execute(self, statement, *_a, **_k):
        sql = str(statement)
        if "futures_outcomes" in sql:
            return _FakeResult([])
        if "futures_markets" in sql:
            return _FakeResult(self._markets)
        return _FakeResult(self._events)


# The real card: schedule rows on day D, each priced by a Kalshi ticker of D.
_D = _at(2, 19)
_DAY = event_commence_token(_D)
_NEXT = event_commence_token(_D + timedelta(days=1))
_T = _DAY.upper()

_REAL = [
    _bout("Raul Rosas Jr", "Raoni Barcelos", _D),
    _bout("Montel Jackson", "Ricky Simon", _D),
    _bout("Melissa Amaya", "Valesca Machado", _D.replace(hour=22)),
]
_REAL_MARKETS = [
    _market(f"KXUFCFIGHT-{_T}ROSBAR", "Fight Night: Rosas Jr vs Barcelos",
            _at(3, 6, 40), _REAL[0].id),
    _market(f"KXUFCFIGHT-{_T}JACSIM", "Fight Night: Jackson vs Simon",
            _at(3, 3, 0), _REAL[1].id),
    _market(f"KXUFCFIGHT-{_T}AMAMAC", "Fight Night: Amaya vs Machado",
            _at(3, 5, 20), _REAL[2].id),
]

# The Kalshi-minted twins: stamped with Kalshi's close time on day D+1, each
# linked to ITS OWN ticker of day D. 02:20Z is 4h20m after the real card's last
# scheduled bout — outside the rollover fold, exactly as on production.
_TWINS = [
    _bout("Dumont Viana", "Perez", _at(3, 2, 20)),
    _bout("Harrell", "Brener", _at(3, 5, 0)),
    _bout("Osmanli", "Uulu", _at(3, 5, 40)),
]
_TWIN_MARKETS = [
    _market(f"KXUFCFIGHT-{_T}DUMPER", "Fight Night: Dumont Viana vs Perez",
            _TWINS[0].commence_time, _TWINS[0].id),
    _market(f"KXUFCFIGHT-{_T}HARBRE", "Fight Night: Harrell vs Brener",
            _TWINS[1].commence_time, _TWINS[1].id),
    _market(f"KXUFCFIGHT-{_T}OSMUUL", "Fight Night: Osmanli vs Uulu",
            _TWINS[2].commence_time, _TWINS[2].id),
]
_MARKETS = _REAL_MARKETS + _TWIN_MARKETS


def _rows(markets):
    """The lister's open-market projection: (id, ext_id, name, commence, meta)."""
    return [(m.id, m.external_id, m.name, m.commence_time, None) for m in markets]


async def _listed(events, markets):
    got = await list_card_concepts(
        UFC_CONFIG, _FakeDB(events=events, markets=markets), rows=_rows(markets)
    )
    return {c["key"].rsplit(":", 1)[-1]: c for c in got}


async def _page(token, events, markets):
    return await UFCEventAdapter().build_event(
        token, _FakeDB(events=events, markets=markets)
    )


def test_the_twins_fall_outside_the_rollover_fold_like_production():
    """Guards the fixture: if the twins rolled into day D the arms below would
    pass without the fix."""
    assert _DAY != _NEXT
    assert event_commence_token(_TWINS[0].commence_time) == _NEXT


@pytest.mark.asyncio
class TestThePhantomCardIsGone:
    async def test_the_lister_drops_it_and_keeps_the_real_card(self):
        listed = await _listed(_REAL + _TWINS, _MARKETS)
        assert _NEXT not in listed, f"phantom {_NEXT} still listed: {listed[_NEXT]}"
        assert _DAY in listed
        # The real card's fight count is the venue's — six bouts, not three.
        assert listed[_DAY]["fight_count"] == 6, listed[_DAY]
        # And its date is still the schedule's, not Kalshi's close stamp.
        assert listed[_DAY]["start_date"] == _D.replace(hour=22).isoformat()

    async def test_the_page_behind_it_answers_none(self):
        assert await _page(_NEXT, _REAL + _TWINS, _MARKETS) is None

    async def test_the_list_and_the_page_agree(self):
        events = _REAL + _TWINS
        listed = await _listed(events, _MARKETS)
        on_page = (await _page(_NEXT, events, _MARKETS)) is not None
        assert on_page == (_NEXT in listed) is False


@pytest.mark.asyncio
class TestControls:
    async def test_one_bout_of_its_own_keeps_the_card_on_both_layers(self):
        """A card that holds even one bout no other card prices is a card."""
        own = _bout("Kevin Holland", "Michel Pereira", _at(3, 4, 0))
        events = _REAL + _TWINS + [own]
        listed = await _listed(events, _MARKETS)
        page = await _page(_NEXT, events, _MARKETS)
        assert _NEXT in listed
        assert page is not None
        assert len(page["children"]) == 4

    async def test_a_real_events_only_card_is_untouched(self):
        """No markets at all — the branch #6733 protects — still builds."""
        when = _at(9, 18)
        real = [
            _bout("Darren Till", "Yoel Romero", when),
            _bout("Natalia Silva", "Wang Cong", when + timedelta(hours=1)),
        ]
        token = event_commence_token(when)
        listed = await _listed(real, [])
        assert token in listed
        assert await _page(token, real, []) is not None

    async def test_without_the_market_links_the_phantom_would_be_served(self):
        """The mutant arm: the same rows with the twins' markets UNLINKED are
        served as a card — so the refusal above comes from the link, not from
        anything else about the rows."""
        unlinked = [
            _market(m.external_id, m.name, m.commence_time, None)
            for m in _TWIN_MARKETS
        ]
        listed = await _listed(_REAL + _TWINS, _REAL_MARKETS + unlinked)
        assert _NEXT in listed


class TestThePredicate:
    def test_arms(self):
        a, b = _TWINS[0], _TWINS[1]
        elsewhere = {a.id: {"26sep26"}, b.id: {"26sep26"}}
        assert card_bouts_are_priced_on_another_card([a, b], elsewhere, {"26sep27"})
        assert not card_bouts_are_priced_on_another_card([], elsewhere, {"26sep27"})
        # one bout with no market of its own
        assert not card_bouts_are_priced_on_another_card(
            [a, b], {a.id: {"26sep26"}}, {"26sep27"}
        )
        # a ticker naming THIS card is this card's bout
        assert not card_bouts_are_priced_on_another_card(
            [a], {a.id: {"26sep26", "26sep27"}}, {"26sep27"}
        )

    def test_ticker_tokens_skip_rows_with_no_card_ticker(self):
        got = ticker_card_tokens_by_event(
            UFC_CONFIG,
            [
                _market("KXUFCFIGHT-26SEP26DUMPER", "x", None, 1),
                _market("0xabc", "venue row", None, 2),
                _market("KXUFCFIGHT-26SEP26HARBRE", "y", None, None),
            ],
        )
        assert got == {1: {"26sep26"}}
