"""A soccer league page stops minting a scoreless twin — Q477 (P476-1/P476-2).

## The specimen

`/api/leagues/soccer_epl`, production 2026-08-31: **eight** recent-result cards
for **four** fixtures. Four carry a score; four sit at `00:00:00Z` with no score
at all.

    15290890  15:30Z  Manchester United v Ipswich Town   5-2
    15298940  00:00Z  Manchester United v Ipswich Town   -
    15290898  13:00Z  Sunderland v Fulham                1-0
    15298364  00:00Z  Sunderland v Fulham                -
    15299046  00:00Z  Sunderland AFC v Fulham FC         -     <- and a THIRD

Kalshi prices one match through a dozen of its own series and every ticker
carries the same fixture token:

    KXEPLSPREAD-26AUG30SUNFUL   -> linked to 15290898, the real row
    KXEPLBTTS-26AUG30SUNFUL     -> MINTED 15298364
    KXEPLFTTS-26AUG30SUNFUL     -> MINTED 15299046

Same provider, same token, three rows. The matcher's name comparison is what
differs between them ("Sunderland" vs "Sunderland AFC"), and an id-less claim
never absorbs — it creates (ruling 048, gotcha #32). The provider id that would
have settled it was sitting in the ticker the whole time.

## Why the anchor channel could not see it

`kalshi_anchor_key()` writes a `game` anchor only when
`is_kalshi_game_level_ticker()` says yes, and that consulted
`KALSHI_GAME_TICKER_PREFIXES`, which has **no EPL match series at all** —
`kxepl` appears only in the futures map. So every one of those tickers became
`id_kind='market'` keyed on its own unique string, and no two could ever
collide. Production held 1,531 Kalshi `market` anchors against 625 `game`.

Half two: even once they anchor, the SCHEDULE-DERIVED row has to be in the
channel for a twin to resolve onto it, and nothing ever put it there. Only
`find_or_create_event` wrote anchors, so the four real EPL rows carried **no
`event_provider_anchors` row at all** while each twin carried one. The side with
the score was the side missing from the channel.

## What is red before the fix

Measured against a clean `origin/master` worktree with only this file copied in:
**26 failed, 14 passed, EXIT 1 by assertion** — no collection error.

The three classes that carry the ship fail BEHAVIOURALLY, not on a missing name:

* `TestTheFixtureTokenAnchorsTheFixture` — `kalshi_anchor_key` returns
  `id_kind='market'` on a real match ticker.
* `TestTheMatcherActuallyCallsIt` — the real `_try_link_market` runs, links the
  market, and writes no anchor.
* `TestTheTwinResolvesOntoTheRealRow` — `find_or_create_event` mints a second
  Sunderland v Fulham row.

The 14 that pass are the refusals in `TestTheNearMissesAreStillRefused` — the
both-directions half, green on both trees, which is what makes the 26 mean
something. Everything this queue ADDS is imported inside the test that needs it
rather than at module scope, because a module-scope `ImportError` is a
collection failure and the first draft of this file had exactly that: all three
behavioural reds hidden behind one missing name, exit 2, proving nothing.

## What must stay green in BOTH directions (gotcha #43)

A guard that only proves the new promotions fire is half a guard, and on this
predicate the unsafe direction is a false POSITIVE — one fixture claiming
another's identity, which is an absorption. `TestTheNearMissesAreStillRefused`
pins every refusal the census found sitting next to a promotion, and
`TestTheBlastRadiusIsTheAnchorChannelOnly` pins that the matcher's ticker scan
and the link-rate denominator did not move.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.anchor_channel import COLLISION, CONFIRMED, NO_KEY, WROTE
from app.services.event_registry import (
    EventClaim,
    EventIdentity,
    _sport_id_cache,
    find_or_create_event,
)
from app.utils.provider_anchor_keys import (
    ANCHOR_KIND_GAME,
    ANCHOR_KIND_MARKET,
    kalshi_anchor_key,
)
from app.utils.sport_keys import (
    KALSHI_GAME_TICKER_PREFIXES,
    KALSHI_LINK_RATE_GAME_TICKER_PREFIXES,
    get_sport_key_from_ticker,
    is_kalshi_game_level_ticker,
    is_kalshi_shadowed_futures_ticker,
)
from tests.test_anchor_channel_consumer_2213 import _AnchorSession

# The symbols this queue ADDS are imported inside the tests that need them, not
# at module scope. At module scope a missing name is a collection ERROR, and a
# collection error takes the whole file down — including the behavioural tests
# that CAN run on the pre-fix bytes and must be seen to fail there by assertion.
# Red-first is a claim about behaviour; an ImportError is a claim about nothing.


def _match_series_map():
    from app.utils.sport_keys import KALSHI_MATCH_SERIES_TO_SPORT_KEY

    return KALSHI_MATCH_SERIES_TO_SPORT_KEY


def _is_match_series(ticker):
    from app.utils import sport_keys

    return sport_keys.is_kalshi_match_series_ticker(ticker)


def _record_link_anchor(*args, **kwargs):
    from app.services.anchor_channel import record_link_anchor

    return record_link_anchor(*args, **kwargs)

EPL_SPORT_ID = 1298
KICKOFF = datetime(2026, 8, 30, 13, 0, tzinfo=timezone.utc)

#: The three real tickers from the specimen above. Every one of them reduces to
#: this single anchor, which is the entire claim of this queue.
SUNFUL_TICKERS = (
    "KXEPLSPREAD-26AUG30SUNFUL",
    "KXEPLBTTS-26AUG30SUNFUL",
    "KXEPLFTTS-26AUG30SUNFUL",
)
SUNFUL_ANCHOR = "soccer_epl:26AUG30SUNFUL"


@pytest.fixture(autouse=True)
def _seed_sport_cache():
    _sport_id_cache["soccer_epl"] = EPL_SPORT_ID
    yield
    _sport_id_cache.pop("soccer_epl", None)


# ══════════════════════════════════════════════════════════════════════════
# RED before the fix — the token becomes the identity
# ══════════════════════════════════════════════════════════════════════════

class TestTheFixtureTokenAnchorsTheFixture:

    @pytest.mark.parametrize("ticker", SUNFUL_TICKERS)
    def test_every_series_for_one_match_yields_one_game_anchor(self, ticker):
        key = kalshi_anchor_key(ticker)
        assert key.id_kind == ANCHOR_KIND_GAME
        assert key.source_id == SUNFUL_ANCHOR

    def test_the_three_specimen_tickers_agree_with_each_other(self):
        """Stated as a set so the guard fails if any ONE of them drifts.

        The parametrised test above can pass three times with three different
        answers; this is the claim that actually matters.
        """
        assert {kalshi_anchor_key(t).source_id for t in SUNFUL_TICKERS} == {
            SUNFUL_ANCHOR
        }

    @pytest.mark.parametrize(
        "ticker,expected",
        [
            ("KXEPLGAME-26AUG30MUNIPS", "soccer_epl:26AUG30MUNIPS"),
            ("KXLALIGAGAME-26AUG29SEVATM", "soccer_spain_la_liga:26AUG29SEVATM"),
            (
                "KXBUNDESLIGABTTS-26AUG29RBLBMG",
                "soccer_germany_bundesliga:26AUG29RBLBMG",
            ),
            ("KXSERIEATOTAL-26AUG30NAPCOM", "soccer_italy_serie_a:26AUG30NAPCOM"),
            (
                "KXLIGUE1SPREAD-26AUG29AUXANG",
                "soccer_france_ligue_one:26AUG29AUXANG",
            ),
        ],
    )
    def test_each_declared_league_anchors_on_its_own_namespace(
        self, ticker, expected
    ):
        key = kalshi_anchor_key(ticker)
        assert key.id_kind == ANCHOR_KIND_GAME
        assert key.source_id == expected

    def test_the_second_half_is_a_market_on_the_same_fixture(self):
        """`KXLALIGA2H…` is the top flight's second HALF, not the Segunda.

        It must land on the SAME anchor as the full-match series, because it
        prices the same 90 minutes. This is the promotion that sits closest to a
        refusal and it is asserted against its neighbour, not alone.
        """
        assert (
            kalshi_anchor_key("KXLALIGA2HTOTAL-26AUG29SEVATM").source_id
            == kalshi_anchor_key("KXLALIGAGAME-26AUG29SEVATM").source_id
        )


class TestTheNearMissesAreStillRefused:
    """The unsafe direction: a false POSITIVE here is an absorption.

    Every `test_it_stays_a_market_anchor` case passes on BOTH trees — they are
    controls, and a refusal that only holds after the fix would prove nothing
    about what the fix did. `test_the_segunda_never_shares_a_fixture_with_the_top_flight`
    is the exception and is red before the fix, because half of what it asserts
    is a promotion; it is here rather than above because the claim it makes is
    about the two competitions staying apart.
    """

    @pytest.mark.parametrize(
        "ticker,why",
        [
            ("KXLALIGA2GAME-26AUG29ALBOVI", "La Liga 2 is a different league"),
            ("KXLALIGA2TOTAL-26AUG29ALBOVI", "La Liga 2 is a different league"),
            ("KXBUNDESLIGA2GAME-26AUG29COTSGF", "2. Bundesliga"),
            ("KXBUNDESLIGA2SPREAD-26AUG29COTSGF", "2. Bundesliga"),
            ("KXUCLADVANCE-26APR14ATMBAR", "a two-legged tie is not a match"),
            ("KXUCLGAME-26APR07RMABMU", "UCL is deliberately not declared"),
            ("KXUCLWGAME-26APR01BMUMNU", "Women's Champions League"),
            ("KXEPLTOP4-26", "a season future"),
            ("KXEPLLAST-27", "a season future"),
            ("KXEPLH2H-27ARSTOT", "a season matchup, not a fixture"),
            ("KXEPLRELEGATION-26", "a season future"),
            ("KXEPL-26", "the league winner"),
            ("KXEPLTEAMPOINTS-27", "a season future, and it neighbours TEAMTOTAL"),
        ],
    )
    def test_it_stays_a_market_anchor(self, ticker, why):
        assert kalshi_anchor_key(ticker).id_kind == ANCHOR_KIND_MARKET, why

    def test_the_segunda_never_shares_a_fixture_with_the_top_flight(self):
        """The sharpest collision the census found, asserted directly.

        `KXLALIGA2TOTAL` (Segunda) and `KXLALIGA2HTOTAL` (top flight, second
        half) differ by one character in the middle and name different
        competitions. Asserting only that the Segunda is `market` would still
        pass if a later edit made both `game` on one namespace.
        """
        segunda = kalshi_anchor_key("KXLALIGA2TOTAL-26AUG29ALBOVI")
        top_flight = kalshi_anchor_key("KXLALIGA2HTOTAL-26AUG29ALBOVI")
        assert segunda.source_id != top_flight.source_id
        assert segunda.id_kind == ANCHOR_KIND_MARKET
        assert top_flight.id_kind == ANCHOR_KIND_GAME


class TestTheTableIsWellFormed:

    def test_every_declared_prefix_resolves_to_the_sport_it_declares(self):
        """The silent-failure guard.

        `kalshi_anchor_key` needs BOTH a game verdict and a sport key; if
        `get_sport_key_from_ticker` answers `None` it falls back to a `market`
        anchor and the whole table quietly does nothing. That is an absence read
        as a fact (gotcha #53), so the agreement is asserted rather than assumed
        — and it is what disqualified `kxucl`, whose futures stem answers
        `soccer_uefa_champions_league`, a key no sport row carries.
        """
        for prefix, declared in _match_series_map().items():
            ticker = f"{prefix.upper()}-26AUG30HOMAWY"
            assert get_sport_key_from_ticker(ticker) == declared, (
                f"{prefix}: the anchor namespace would be "
                f"{get_sport_key_from_ticker(ticker)!r}, not {declared!r}"
            )

    def test_every_declared_prefix_actually_reads_as_a_match_series(self):
        for prefix in _match_series_map():
            assert _is_match_series(f"{prefix.upper()}-26AUG30HOMAWY")

    def test_no_declared_prefix_is_shadowed_by_a_futures_prefix(self):
        """Keeps the two predicates two halves of one question.

        `is_kalshi_shadowed_futures_ticker` reads only the game map, so a
        match-series prefix that a LONGER futures prefix shadowed would be
        game-level and not-shadowed at once — a contradiction that would go
        silent. Nothing today has that shape; this fires if a future stem does.
        """
        for prefix in _match_series_map():
            ticker = f"{prefix.upper()}-26AUG30HOMAWY"
            assert not is_kalshi_shadowed_futures_ticker(ticker)

    @pytest.mark.parametrize(
        "suffix,scope",
        [
            ("advance", "a two-legged tie"),
            ("series", "a best-of-N"),
            ("relegation", "a season"),
            ("top4", "a season"),
            ("h2h", "a season matchup"),
            ("winner", "a season"),
        ],
    )
    def test_no_suffix_names_a_scope_larger_than_one_fixture(self, suffix, scope):
        """The omissions are load-bearing, so they are asserted, not implied.

        Every refusal elsewhere in this file names a ticker Kalshi actually
        publishes. These do not: there is no `KXEPLADVANCE` today. The property
        still has to be pinned, because the failure mode of adding one of these
        suffixes is an ABSORPTION — a UCL tie carries a date token and two
        legitimate fixtures, so `advance` under a declared stem would give two
        different matches one identity. Asserted through a SYNTHETIC ticker
        rather than the tuple alone, so a later edit that reaches the same wrong
        answer by a different route is still caught.
        """
        ticker = f"KXEPL{suffix.upper()}-26AUG30SUNFUL"
        assert _is_match_series(ticker) is False, (
            f"{suffix} names {scope}, not one fixture"
        )
        assert kalshi_anchor_key(ticker).id_kind == ANCHOR_KIND_MARKET

    def test_a_tie_on_prefix_length_is_not_a_match_series(self, monkeypatch):
        """The longest-prefix rule, exercised the only way it can be today.

        No futures prefix currently ties or beats a match-series prefix on any
        real ticker — measured, zero pairs — so the comparison is a property
        with no live specimen, exactly like Q440's own tie test, and it is
        guarded the same way: a colliding entry is monkeypatched in. Without
        this the comparison is unreachable code that any mutant can delete.
        """
        import app.utils.sport_keys as sk

        monkeypatch.setitem(
            sk.KALSHI_FUTURES_TICKER_TO_SPORT_KEY, "kxeplgame", "soccer_epl"
        )
        assert sk.is_kalshi_match_series_ticker("KXEPLGAME-26AUG30SUNFUL") is False
        assert kalshi_anchor_key(
            "KXEPLGAME-26AUG30SUNFUL"
        ).id_kind == ANCHOR_KIND_MARKET

    def test_a_longer_futures_prefix_beats_a_match_series_one(self, monkeypatch):
        import app.utils.sport_keys as sk

        monkeypatch.setitem(
            sk.KALSHI_FUTURES_TICKER_TO_SPORT_KEY, "kxeplgame-26", "soccer_epl"
        )
        assert sk.is_kalshi_match_series_ticker("KXEPLGAME-26AUG30SUNFUL") is False

    def test_the_prefix_must_be_at_the_START_of_the_ticker(self):
        """`startswith`, not `in`. Synthetic, and it has to be.

        No production ticker carries a declared prefix mid-string — measured,
        zero — so a substring test would be indistinguishable from the real one
        on today's corpus while being wrong about any ticker Kalshi adds that
        embeds one.
        """
        assert _is_match_series("KXEPLGAME-26AUG30SUNFUL") is True
        assert _is_match_series("XKXEPLGAME-26AUG30SUNFUL") is False
        assert _is_match_series("KXOTHER-KXEPLGAME-26AUG30SUNFUL") is False

    def test_a_match_series_ticker_with_no_fixture_token_is_a_market(self):
        """Both conditions are required, and only one of them is about the map.

        A registered prefix says "this series prices single fixtures"; the
        fixture TOKEN says which one. Without the token there is nothing to
        anchor and the key must degrade — otherwise every tokenless ticker under
        one stem would share a single identity. No production ticker has this
        shape (measured, zero), so it is synthetic and stays pinned anyway.
        """
        from app.utils.prediction_market_matching import kalshi_game_id

        assert kalshi_game_id("KXEPLGAME-26") is None
        assert _is_match_series("KXEPLGAME-26") is True
        assert kalshi_anchor_key("KXEPLGAME-26").id_kind == ANCHOR_KIND_MARKET

    def test_the_stems_are_the_five_leagues_that_showed_twins(self):
        from app.utils.sport_keys import _KALSHI_MATCH_SERIES_LEAGUE_STEMS

        assert set(_KALSHI_MATCH_SERIES_LEAGUE_STEMS) == {
            "kxepl", "kxlaliga", "kxbundesliga", "kxseriea", "kxligue1",
        }


class TestTheBlastRadiusIsTheAnchorChannelOnly:
    """The matcher's ticker scan and the link-rate denominator do not move."""

    def test_no_declared_prefix_joins_the_game_ticker_tuple(self):
        assert (
            set(_match_series_map()) & set(KALSHI_GAME_TICKER_PREFIXES)
        ) == set()

    def test_no_declared_prefix_joins_the_link_rate_denominator(self):
        assert (
            set(_match_series_map())
            & set(KALSHI_LINK_RATE_GAME_TICKER_PREFIXES)
        ) == set()

    def test_the_shared_predicate_still_says_no(self):
        """`is_kalshi_game_level_ticker` has three consumers this fix must miss.

        `_KALSHI_TICKER_LIKE_PATTERNS` (the 15-minute matcher's scan) is built
        from `KALSHI_GAME_TICKER_PREFIXES`, and the predicate gates
        `is_game_level_market`, `extract_ticker_fragments` and the grammar
        adapter. Q477 needed none of them. Asserted through the predicates
        rather than the tuples, because the tuples are what a careless edit
        changes and the predicates are what production runs.
        """
        assert is_kalshi_game_level_ticker("KXEPLGAME-26AUG30SUNFUL") is False
        assert _is_match_series("KXEPLGAME-26AUG30SUNFUL") is True

    def test_the_matcher_still_gets_no_team_abbrevs_from_these_tickers(self):
        """The measured reason the shared predicate was left alone.

        `extract_ticker_fragments` is gated purely on
        `is_kalshi_game_level_ticker`, and it feeds ticker-derived abbreviations
        into the matcher's fuzzy team comparison. Widening the shared predicate
        would have changed its answer on **36 of the 88** promoted production
        series — a change to WHICH MARKETS LINK, in the same commit as a change
        to identity. It is parked, and this guard is what makes the parking
        real: if a later edit widens the shared predicate, this goes red rather
        than the matcher quietly moving.
        """
        from app.utils.prediction_market_matching import extract_ticker_fragments

        assert _is_match_series("KXBUNDESLIGAGAME-26APR04BMGFCH")
        assert extract_ticker_fragments("KXBUNDESLIGAGAME-26APR04BMGFCH") is None


# ══════════════════════════════════════════════════════════════════════════
# RED before the fix — the schedule-derived row joins the channel
# ══════════════════════════════════════════════════════════════════════════

def _event_row(event_id, **kw):
    return SimpleNamespace(
        id=event_id, sport_id=EPL_SPORT_ID, commence_time=KICKOFF,
        status=kw.get("status", "completed"),
        home_team_name=kw.get("home", "Sunderland"),
        away_team_name=kw.get("away", "Fulham"),
        espn_id=kw.get("espn_id"), external_id=None, statpal_fixture_id=None,
        # The registry updates fields by source priority once it resolves a row,
        # so a double that omits these raises AttributeError on the HIT path —
        # which reads as the fix failing rather than as the double being thin.
        commence_time_source=kw.get("commence_time_source", "espn"),
        home_score=kw.get("home_score", 1), away_score=kw.get("away_score", 0),
        completed_at=None, statpal_end_time=None, venue_id=None,
        broadcast_info=None, home_team_id=None, away_team_id=None,
    )


class TestTheLinkSideWritesTheAnchor:

    async def test_a_link_puts_the_real_row_into_the_channel(self):
        session = _AnchorSession(
            structured_candidates=[_event_row(15290898, espn_id="espn-1")],
            event_sports={15290898: EPL_SPORT_ID},
        )
        result = await _record_link_anchor(
            session, event_id=15290898, source="kalshi",
            provider_id="KXEPLSPREAD-26AUG30SUNFUL",
        )
        assert result.outcome == WROTE
        assert session.anchors[("kalshi", SUNFUL_ANCHOR, ANCHOR_KIND_GAME)] == 15290898

    async def test_a_market_kind_key_writes_nothing_at_all(self):
        """Tennis and Polymarket are recorded by the registry, not here.

        A `market` anchor is never consulted by `find_event_by_anchor`, so
        writing one on every newly-linked market would be a row per market
        bought for no resolution. The assertion is on the write LEDGER, not on
        the return value — a function can report NO_KEY and still have written.
        """
        session = _AnchorSession()
        result = await _record_link_anchor(
            session, event_id=99, source="kalshi",
            provider_id="KXATPMATCH-26AUG30BUBWOL",
        )
        assert result.outcome == NO_KEY
        assert session.anchor_writes == []

    async def test_a_polymarket_condition_id_writes_nothing_at_all(self):
        session = _AnchorSession()
        result = await _record_link_anchor(
            session, event_id=99, source="polymarket", provider_id="0xdeadbeef",
        )
        assert result.outcome == NO_KEY
        assert session.anchor_writes == []

    async def test_a_repeat_link_confirms_and_does_not_rewrite(self):
        session = _AnchorSession(
            anchors={("kalshi", SUNFUL_ANCHOR, ANCHOR_KIND_GAME): 15290898},
            structured_candidates=[_event_row(15290898, espn_id="espn-1")],
            event_sports={15290898: EPL_SPORT_ID},
        )
        result = await _record_link_anchor(
            session, event_id=15290898, source="kalshi",
            provider_id="KXEPLBTTS-26AUG30SUNFUL",
        )
        assert result.outcome == CONFIRMED
        assert session.anchors[("kalshi", SUNFUL_ANCHOR, ANCHOR_KIND_GAME)] == 15290898

    async def test_a_collision_never_repoints_and_never_tags(self):
        """The sharpest hazard in this queue, and it points the wrong way.

        `record_anchor` resolves a conflict first-writer-wins. At a LINK site the
        incumbent is typically the ticker-derived twin that got there first and
        the caller's event is the schedule-derived row carrying the score — so
        tagging on that outcome would brand the REAL row a duplicate of its own
        twin and hide it from the league rails. Both the repoint and the tag are
        asserted absent.
        """
        twin, real = 15298364, 15290898
        session = _AnchorSession(
            anchors={("kalshi", SUNFUL_ANCHOR, ANCHOR_KIND_GAME): twin},
            structured_candidates=[
                _event_row(twin), _event_row(real, espn_id="espn-1"),
            ],
            event_sports={twin: EPL_SPORT_ID, real: EPL_SPORT_ID},
        )
        result = await _record_link_anchor(
            session, event_id=real, source="kalshi",
            provider_id="KXEPLSPREAD-26AUG30SUNFUL",
        )
        assert result.outcome == COLLISION
        assert result.canonical_event_id == twin
        assert session.anchors[("kalshi", SUNFUL_ANCHOR, ANCHOR_KIND_GAME)] == twin
        assert session.tagged == [], (
            "the real row was tagged a duplicate of its own twin"
        )


class TestTheMatcherActuallyCallsIt:
    """A behavioural witness. A source-substring check would pass vacuously."""

    async def _link(self, session, ticker, event_id, monkeypatch):
        from app.tasks import prediction_market_matching as pmm

        async def _no_refusal(*a, **kw):
            return None

        async def _no_identities(*a, **kw):
            return None

        monkeypatch.setattr(
            pmm, "_check_duplicate_kalshi_linkage_reason", _no_refusal
        )
        monkeypatch.setattr(
            pmm, "_register_market_team_identities", _no_identities
        )
        monkeypatch.setattr(pmm, "_set_market_sport_fields", lambda *a, **kw: None)

        market = SimpleNamespace(
            id=1, source="kalshi", external_id=ticker, name="Sunderland vs Fulham",
            group_id=None, event_id=None,
        )
        stats = {"newly_linked": 0, "funnel": {"linked": 0}, "errors": []}
        await pmm._try_link_market(
            session, market, None,
            {"event_id": event_id, "home_team": "Sunderland",
             "away_team": "Fulham"},
            stats, None, KICKOFF, [],
        )
        return market, stats

    async def test_linking_a_market_writes_its_game_anchor(self, monkeypatch):
        session = _AnchorSession(
            structured_candidates=[_event_row(15290898, espn_id="espn-1")],
            event_sports={15290898: EPL_SPORT_ID},
        )
        market, stats = await self._link(
            session, "KXEPLSPREAD-26AUG30SUNFUL", 15290898, monkeypatch
        )
        # The link itself still happened — the anchor write is a rider, never a
        # gate on the user-visible half.
        assert market.event_id == 15290898
        assert stats["newly_linked"] == 1
        assert session.anchors[("kalshi", SUNFUL_ANCHOR, ANCHOR_KIND_GAME)] == 15290898
        assert stats["funnel"]["link_anchor_written"] == 1

    async def test_linking_a_tennis_market_writes_no_anchor(self, monkeypatch):
        session = _AnchorSession(
            structured_candidates=[_event_row(15290898, espn_id="espn-1")],
            event_sports={15290898: EPL_SPORT_ID},
        )
        market, stats = await self._link(
            session, "KXATPMATCH-26AUG30BUBWOL", 15290898, monkeypatch
        )
        assert market.event_id == 15290898
        assert session.anchor_writes == []
        assert "link_anchor_written" not in stats["funnel"]


# ══════════════════════════════════════════════════════════════════════════
# RED before the fix — the ship
# ══════════════════════════════════════════════════════════════════════════

class TestTheTwinResolvesOntoTheRealRow:

    async def test_the_second_series_finds_the_first_instead_of_creating(self):
        """The whole queue in one test.

        The real row is in the channel (half two put it there when the matcher
        linked `KXEPLSPREAD`). `KXEPLBTTS` for the same fixture now arrives as
        an auto-create claim. On the pre-fix bytes its anchor is a `market` key
        on its own ticker, Step 2 misses, and a second event row is born. On the
        repaired bytes Step 2 answers with the row that has the score on it.
        """
        real = _event_row(15290898, espn_id="espn-1")
        session = _AnchorSession(
            anchors={("kalshi", SUNFUL_ANCHOR, ANCHOR_KIND_GAME): 15290898},
            structured_candidates=[real],
            event_sports={15290898: EPL_SPORT_ID},
        )
        identity = EventIdentity(
            sport_key="soccer_epl",
            home_team_name="Sunderland AFC", away_team_name="Fulham FC",
            commence_time=datetime(2026, 8, 30, tzinfo=timezone.utc),
            commence_time_source="kalshi_ticker",
            claim=EventClaim(
                "kalshi", "pm_kalshi_KXEPLBTTS-26AUG30SUNFUL",
                provider_id="KXEPLBTTS-26AUG30SUNFUL",
            ),
            status="completed",
        )
        event, was_created = await find_or_create_event(session, identity)

        assert was_created is False, "a third Sunderland v Fulham row was minted"
        assert event.id == 15290898
        assert session.added == []
