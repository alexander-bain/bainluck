"""#8263 — a boxing fight stops appearing on two fight nights.

═══ THE DEFECT ═══

Production 2026-09-27 17:40Z, 390px:

    /event/boxing/26oct10  Floyd Schofield vs Lucas Bahdi   main event 85% / 14%
    /event/boxing/26oct11  Takuma Inoue vs Nasukawa T.      Matchups: "Floyd
                           Scholfield vs Lucas Bahdi" 84% / 16%

Kalshi lists the fight once, as ``KXBOXING-26OCT10SCHOFIBAHDI``. The Odds API
row 15301121 ("Floyd Scholfield", its spelling) sits at 03:00Z Oct 11 — 11pm ET
Oct 10 — and `_list_event_bouts` keys it by that UTC date, so it joined the
Japanese card on Oct 11 (08:00-11:00Z), five hours later, beyond the rollover
fold. The Kalshi market is linked to a different, id-less row (ruling 048), so
#7993's priced-on-another-card test cannot see this bout either.

═══ WHAT IS ASSERTED ═══

  1. the Oct 11 page lists the Japanese card's four bouts, not the US fight
  2. the lister agrees — the Oct 11 card counts four, the Oct 10 card survives
  3. the Oct 10 page gains no second copy of the fight
  4. the helper's refusals: own token, not adjacent, both neighbours, one
     shared fighter, scoped token
  5. the mutant arm — with no ticker for the fight, the bout stays on Oct 11
"""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.event_boxing import BOXING_CONFIG, BoxingEventAdapter
from app.utils.event_combat import (
    event_commence_token,
    list_card_concepts,
    rekey_bouts_onto_ticker_cards,
)

_IDS = itertools.count(8263000)

# ONE clock read for the module (see #7993's suite for the midnight race).
_NOW = datetime.now(timezone.utc)


def _at(days: int, hour: int, minute: int = 0) -> datetime:
    """A fixed instant. Offset FIRST, then truncate (gotcha #44)."""
    return (_NOW + timedelta(days=days)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )


def _bout(home, away, when, source="odds_api"):
    return SimpleNamespace(
        id=next(_IDS),
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        commence_time_source=source,
        status="scheduled",
        win_probability_sources=None,
    )


def _outcome(name, p):
    return SimpleNamespace(
        name=name,
        current_probability=p,
        current_yes_bid=None,
        current_yes_ask=None,
        price_observed_at=None,
        updated_at=None,
    )


def _market(ticker, name, close, event_id, probs=(0.85, 0.14)):
    a, b = [s.strip() for s in name.split(" vs ")]
    return SimpleNamespace(
        id=next(_IDS),
        external_id=ticker,
        name=name,
        source="kalshi",
        commence_time=close,
        event_id=event_id,
        market_metadata=None,
        outcomes=[_outcome(a, probs[0]), _outcome(b, probs[1])],
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


# The US night, day X: Kalshi's ticker date. The schedule has Sandoval at 02:00Z
# on X and the Odds API's Scholfield row at 03:00Z on X+1, as on production.
_X = _at(13, 2)
_DAY = event_commence_token(_X)
_NEXT = event_commence_token(_X + timedelta(days=1))
_T = _DAY.upper()

_SANDOVAL = _bout("Ricardo Rafael Sandoval", "Oscar Collazo", _X)
_SCHOLFIELD = _bout("Floyd Scholfield", "Lucas Bahdi", _at(14, 3))
# Takuma Inoue's card in Japan, day X+1, 08:00-11:00Z — five hours after
# Scholfield, so the rollover fold never joins the two groups.
_JAPAN = [
    _bout("Matsumoto R.", "Acosta Silveira R.", _at(14, 8)),
    _bout("Nishida R.", "Goodman S.", _at(14, 9)),
    _bout("Tsuboi T.", "Malajika R.", _at(14, 10)),
    _bout("Takuma Inoue", "Nasukawa T.", _at(14, 11)),
]
_EVENTS = [_SANDOVAL, _SCHOLFIELD, *_JAPAN]

# Kalshi's fight is linked to its OWN id-less row (15312788 on production), which
# is outside the schedule window — so no market reaches the Scholfield row.
_SCHOFIELD_MKT = _market(
    f"KXBOXING-{_T}SCHOFIBAHDI",
    "Floyd Schofield vs Lucas Bahdi",
    _at(14, 5),
    99_999_999,
)
_SANDOVAL_MKT = _market(
    f"KXBOXING-{_T}SANDCOLL",
    "Ricardo Rafael Sandoval vs Oscar Collazo",
    _at(14, 5),
    _SANDOVAL.id,
    probs=(0.54, 0.44),
)
_MARKETS = [_SCHOFIELD_MKT, _SANDOVAL_MKT]


def _rows(markets):
    return [(m.id, m.external_id, m.name, m.commence_time, None) for m in markets]


async def _listed(events, markets):
    got = await list_card_concepts(
        BOXING_CONFIG, _FakeDB(events=events, markets=markets), rows=_rows(markets)
    )
    return {c["key"].rsplit(":", 1)[-1]: c for c in got}


async def _page(token, events, markets):
    return await BoxingEventAdapter().build_event(
        token, _FakeDB(events=events, markets=markets)
    )


def _names(page):
    return [c["market_name"] for c in page["children"]]


def test_the_fixture_is_the_production_shape():
    """If Scholfield keyed onto day X already, the arms below would be vacuous."""
    assert event_commence_token(_SCHOLFIELD.commence_time) == _NEXT != _DAY


@pytest.mark.asyncio
class TestTheFightIsOnOneNight:
    async def test_the_next_day_page_lists_only_its_own_card(self):
        page = await _page(_NEXT, _EVENTS, _MARKETS)
        assert page is not None
        assert not any("Bahdi" in n for n in _names(page)), _names(page)
        assert len(page["children"]) == 4
        assert page["event"]["name"] == "Takuma Inoue vs Nasukawa T."

    async def test_the_lister_agrees(self):
        listed = await _listed(_EVENTS, _MARKETS)
        assert _NEXT in listed and _DAY in listed
        assert listed[_NEXT]["fight_count"] == 4, listed[_NEXT]
        # The Japanese card still opens at its own first bout, not at 03:00Z.
        assert listed[_NEXT]["start_date"] == _JAPAN[0].commence_time.isoformat()

    async def test_the_ticker_night_gains_no_second_copy(self):
        page = await _page(_DAY, _EVENTS, _MARKETS)
        assert page is not None
        bahdi = [n for n in _names(page) if "Bahdi" in n]
        assert bahdi == ["Floyd Schofield vs Lucas Bahdi"], _names(page)
        assert len(page["children"]) == 2

    async def test_without_the_ticker_the_bout_stays_where_it_was(self):
        """The mutant arm: no Kalshi fight names Scholfield, so nothing moves —
        the move comes from the ticker's roster and nothing else."""
        page = await _page(_NEXT, _EVENTS, [_SANDOVAL_MKT])
        assert any("Bahdi" in n for n in _names(page)), _names(page)
        assert len(page["children"]) == 5


def _grouped(*bouts):
    out: dict[str, list] = {}
    for b in bouts:
        out.setdefault(event_commence_token(b.commence_time), []).append(b)
    return out


class TestTheHelpersRefusals:
    def test_moves_onto_the_adjacent_ticker_card(self):
        got = rekey_bouts_onto_ticker_cards(
            _grouped(_SCHOLFIELD, *_JAPAN),
            {_DAY: ["Floyd Schofield vs Lucas Bahdi"]},
        )
        assert got[_DAY] == [_SCHOLFIELD]
        assert got[_NEXT] == _JAPAN

    def test_own_token_lists_it_so_it_stays(self):
        roster = {
            _DAY: ["Floyd Schofield vs Lucas Bahdi"],
            _NEXT: ["Floyd Schofield vs Lucas Bahdi", "Inoue vs Nasukawa"],
        }
        bouts = _grouped(_SCHOLFIELD)
        got = rekey_bouts_onto_ticker_cards(bouts, roster)
        assert got is bouts

    def test_a_rematch_weeks_away_is_not_this_fight(self):
        far = event_commence_token(_X - timedelta(days=30))
        bouts = _grouped(_SCHOLFIELD)
        got = rekey_bouts_onto_ticker_cards(
            bouts, {far: ["Floyd Schofield vs Lucas Bahdi"]}
        )
        assert got is bouts

    def test_both_neighbours_list_it_so_no_evidence_picks_one(self):
        after = event_commence_token(_SCHOLFIELD.commence_time + timedelta(days=1))
        bouts = _grouped(_SCHOLFIELD)
        got = rekey_bouts_onto_ticker_cards(
            bouts,
            {
                _DAY: ["Floyd Schofield vs Lucas Bahdi"],
                after: ["Lucas Bahdi vs Floyd Schofield"],
            },
        )
        assert got is bouts

    def test_one_shared_fighter_is_not_a_shared_bout(self):
        bouts = _grouped(_SCHOLFIELD)
        got = rekey_bouts_onto_ticker_cards(
            bouts, {_DAY: ["Floyd Schofield vs Brandon Adams"]}
        )
        assert got is bouts

    def test_a_scoped_token_is_not_a_ticker_card(self):
        bouts = _grouped(_SCHOLFIELD)
        got = rekey_bouts_onto_ticker_cards(
            bouts, {f"{_DAY}zuffaboxing": ["Floyd Schofield vs Lucas Bahdi"]}
        )
        assert got is bouts

    def test_a_row_on_kalshis_clock_keeps_its_card(self):
        """#7993's rows carry Kalshi's CLOSE stamp; that fix refuses to let the
        stamp date the real card, and so does this one."""
        minted = _bout("Floyd Schofield", "Lucas Bahdi", _at(14, 3), source="kalshi")
        unknown = _bout("Floyd Schofield", "Lucas Bahdi", _at(14, 3), source=None)
        for row in (minted, unknown):
            bouts = _grouped(row)
            got = rekey_bouts_onto_ticker_cards(
                bouts, {_DAY: ["Floyd Schofield vs Lucas Bahdi"]}
            )
            assert got is bouts


# Production: Kalshi lists the four Japanese fights under tickers dated two WEEKS
# before the card (`KXBOXING-26SEP27INOUET` for an Oct 11 bout), each linked to
# its schedule row. #7993 read that as "every bout is priced on another card".
_EARLY = event_commence_token(_X - timedelta(days=13)).upper()
_JAPAN_MARKETS = [
    _market(
        f"KXBOXING-{_EARLY}{tag}",
        f"{b.home_team_name} vs {b.away_team_name}",
        b.commence_time,
        b.id,
    )
    for tag, b in zip(("RR2", "RS", "TR", "INOUET"), _JAPAN)
]


@pytest.mark.asyncio
class TestTheRealCardSurvivesWithoutTheStrayBout:
    async def test_the_lister_keeps_the_japanese_card(self):
        listed = await _listed(_EVENTS, _MARKETS + _JAPAN_MARKETS)
        assert _NEXT in listed, sorted(listed)
        assert listed[_NEXT]["fight_count"] == 4, listed[_NEXT]

    async def test_the_page_keeps_it_too(self):
        page = await _page(_NEXT, _EVENTS, _MARKETS + _JAPAN_MARKETS)
        assert page is not None
        assert len(page["children"]) == 4
        assert not any("Bahdi" in n for n in _names(page)), _names(page)

    def test_a_ticker_weeks_away_is_not_7993s_shape(self):
        from app.utils.event_combat import card_bouts_are_priced_on_another_card

        far = {b.id: {_EARLY.lower()} for b in _JAPAN}
        near = {b.id: {_DAY} for b in _JAPAN}
        assert not card_bouts_are_priced_on_another_card(_JAPAN, far, {_NEXT})
        assert card_bouts_are_priced_on_another_card(_JAPAN, near, {_NEXT})


@pytest.mark.asyncio
class TestAFoldedCardIsNeverSplit:
    """The re-key runs AFTER the folds. Run before them, it moved the bouts of a
    midnight-crossing card that Kalshi names and stranded the one it does not —
    on production that minted a phantom `26oct04` "Shevchenko vs Silva · 2
    fights" beside UFC 332."""

    async def test_a_midnight_crosser_stays_one_card(self):
        d = _at(20, 22)
        day = event_commence_token(d)
        nxt = event_commence_token(d + timedelta(days=1))
        t = day.upper()
        bouts = [
            _bout("Alpha One", "Bravo Two", d),
            _bout("Echo Five", "Foxtrot Six", d + timedelta(hours=2)),
            _bout("Charlie Three", "Delta Four", d + timedelta(hours=3)),
        ]
        # Kalshi names Alpha and the LATER post-midnight bout, not the earlier
        # one — production's shape: moved first, the stranded bout would open
        # before the moved one ended and the fold's overlap guard refuses.
        markets = [
            _market(f"KXBOXING-{t}ALPBRA", "Alpha One vs Bravo Two", d, bouts[0].id),
            _market(
                f"KXBOXING-{t}CHADEL",
                "Charlie Three vs Delta Four",
                d + timedelta(hours=3),
                None,
            ),
        ]
        assert event_commence_token(bouts[1].commence_time) == nxt != day
        listed = await _listed(bouts, markets)
        assert nxt not in listed, listed.get(nxt)
        page = await _page(nxt, bouts, markets)
        # The spillover link resolves onto the whole card, as #1712 built it.
        assert page is not None
        assert sorted(_names(page)) == [
            "Alpha One vs Bravo Two",
            "Charlie Three vs Delta Four",
        ]
