"""#5637 — an unmapped Kalshi ticker is sorted by the venue's series tag, not by
guessing at the market's name.

THE DEFECT. Step 1 of `_categorize_kalshi_market` is the ticker map and its own
comment calls it authoritative. An UNMAPPED prefix resolved to nothing and fell
through to the name rules, which read club names that happen to be sport words.
Measured on production 2026-09-12, every one of these was live:

    AFC Wimbledon (EFL League One)      -> tennis
    Racing Club / Avellaneda / Louisville -> motorsports
    CFL "total points"                  -> basketball
    "Fantasy Points" (#5621)            -> basketball

Each wrong guess bought a wrong-sport duplicate event, which a reader hits by
searching their own club: `q=Redblacks` returned the real CFL game AND a
`basketball_other` ghost with the teams reversed and no price.

WHY THE TAG AND NOT A TOKEN LIST. #5628 proposed a hand-written token allowlist;
the census found four live families it would have missed. Deriving the token
from a sibling key already in the maps is worse than the gap: two of the five
families have no sibling at all, and `kxargpremdivgame` (Argentina Primera
División, soccer) would derive from `kxarglnbgame` (Argentina LNB, BASKETBALL).
The venue already publishes the answer, and the translation of its vocabulary
into ours is derivable from `SPORT_PREFIX_TO_LLM_CATEGORY` with no literals.
"""

import pytest
from unittest.mock import MagicMock

from app.tasks.kalshi import (
    _SERIES_TAG_CACHE,
    _categorize_kalshi_market,
    _resolve_series_tag,
    series_tag_to_category,
)
from app.utils.prediction_market_matching import (
    auto_create_sport_key_from_category,
)
from app.utils.sport_keys import SPORT_PREFIX_TO_LLM_CATEGORY


#: The five families measured live on production 2026-09-12, with the tag the
#: venue itself returned from `/series/{ticker}` that morning.
LIVE_FAMILIES = [
    # (series ticker, venue tag, the category we must reach, what we used to say)
    ("KXCFLTOTAL", "Football", "football", "basketball"),
    ("KXEFLL1GAME", "Soccer", "soccer", "tennis"),
    ("KXURYPDGAME", "Soccer", "soccer", "motorsports"),
    ("KXARGPREMDIVGAME", "Soccer", "soccer", "motorsports"),
    ("KXNWSLGAME", "Soccer", "soccer", "motorsports"),
]


@pytest.fixture(autouse=True)
def _clear_cache():
    _SERIES_TAG_CACHE.clear()
    yield
    _SERIES_TAG_CACHE.clear()


class _FakeService:
    """Counts calls, so "no network for a mapped ticker" is provable."""

    def __init__(self, tags_by_series=None):
        self.tags_by_series = tags_by_series or {}
        self.calls = []

    async def get_series_metadata(self, series_ticker):
        self.calls.append(series_ticker)
        if series_ticker not in self.tags_by_series:
            return None
        return {"ticker": series_ticker, "tags": self.tags_by_series[series_ticker]}


# ── the derivation ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "tag,expected",
    [
        ("Soccer", "soccer"),
        ("Football", "football"),
        ("Basketball", "basketball"),
        ("Baseball", "baseball"),
        ("Tennis", "tennis"),
        ("Golf", "golf"),
        ("Cricket", "cricket"),
        ("Boxing", "boxing"),
        ("Chess", "chess"),
        ("Esports", "esports"),
        ("Rugby", "rugby"),
        ("Lacrosse", "lacrosse"),
        ("Darts", "darts"),
        ("Squash", "squash"),
        # the two whose tag is a PREFIX of ours, not a category of ours
        ("Hockey", "hockey"),
        ("Motorsport", "motorsports"),
        # and the one with a space in it
        ("Aussie Rules", "aussierules"),
        ("MMA", "mma"),
    ],
)
def test_every_sport_tag_the_venue_publishes_resolves(tag, expected):
    assert series_tag_to_category(tag) == expected


@pytest.mark.parametrize(
    "tag",
    [
        # real tags from the same census that are NOT a sport we model. Each
        # must fall through to today's behaviour rather than guess.
        "Olympics",
        "Television",
        "Movies",
        "Music",
        "Music charts",
        "Trump",
        "Fed",
        "US Elections",
        "Other",
        "Table Tennis",
        "Cycling",
        "Volleyball",
        "Rowing",
        "AI",
        None,
        "",
        "   ",
    ],
)
def test_a_tag_we_do_not_model_falls_through_rather_than_guessing(tag):
    assert series_tag_to_category(tag) is None


def test_the_translation_is_derived_from_the_prefix_map_not_a_literal_list():
    """Anti-vacuity: the point of #5637 is that nobody edits a list per series.

    If someone replaces the derivation with a hand-written dict, this fails —
    every category we model has to resolve from its own name, and every prefix
    from its own name, because that is what "derived" means here.
    """
    for prefix, category in SPORT_PREFIX_TO_LLM_CATEGORY.items():
        assert series_tag_to_category(category) == category, (
            f"category {category!r} must resolve to itself"
        )
        assert series_tag_to_category(prefix) == category, (
            f"prefix {prefix!r} must resolve to {category!r}"
        )


def test_the_derivation_tracks_a_newly_modelled_sport(monkeypatch):
    """A sport added to the prefix map is understood with no edit here."""
    extended = dict(SPORT_PREFIX_TO_LLM_CATEGORY)
    extended["kabaddi"] = "kabaddi"
    monkeypatch.setattr(
        "app.utils.sport_keys.SPORT_PREFIX_TO_LLM_CATEGORY", extended
    )
    assert series_tag_to_category("Kabaddi") == "kabaddi"


# ── the cascade ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("series,tag,expected,used_to_say", LIVE_FAMILIES)
def test_the_five_live_families_are_sorted_by_the_venue(
    series, tag, expected, used_to_say
):
    """The ship, stated on the specimens that were wrong on production."""
    name = {
        "KXCFLTOTAL": "Will the Ottawa Redblacks vs Toronto Argonauts total be over 45.5?",
        "KXEFLL1GAME": "Will AFC Wimbledon beat Doncaster?",
        "KXURYPDGAME": "Will Racing Club beat Boston River?",
        "KXARGPREMDIVGAME": "Will Huracan beat Racing Avellaneda?",
        "KXNWSLGAME": "Will Racing Louisville beat Gotham?",
    }[series]
    ticker = f"{series.lower()}-25sep12abc"

    assert (
        _categorize_kalshi_market(name, "Sports", ticker, series_tag=tag) == expected
    )
    # and it is the TAG that moved it, not the name: `used_to_say` is what the
    # name rules produce unaided, so reaching `expected` without the tag would
    # mean this specimen never needed the ship.
    assert expected != used_to_say


def test_the_name_rules_really_were_wrong_without_the_tag():
    """The red half: without a tag these still read as the wrong sport.

    Without this the test above could pass on a name rule that was already
    right, and the ship would be unproven.
    """
    assert (
        _categorize_kalshi_market(
            "Will AFC Wimbledon beat Doncaster?", "Sports", "kxefll1game-25sep12abc"
        )
        == "tennis"
    )
    assert (
        _categorize_kalshi_market(
            "Will Racing Club beat Boston River?", "Sports", "kxurypdgame-25sep12abc"
        )
        == "motorsports"
    )


def test_a_mapped_ticker_still_wins_over_the_tag():
    """Step 1 stays authoritative — the tag names only the sport, the ticker
    map names the league, so a tag may never demote a mapping."""
    # kxeflcupgame -> soccer_england_efl_cup in the ticker map
    assert (
        _categorize_kalshi_market(
            "Will Arsenal beat Chelsea?",
            "Sports",
            "kxeflcupgame-25sep12abc",
            series_tag="Basketball",
        )
        == "soccer"
    )


def test_the_ipo_rule_still_outranks_the_tag():
    """Step 0 stays on top: "Kraken IPO" is economics even in a Hockey series."""
    assert (
        _categorize_kalshi_market(
            "Will Kraken IPO before 2027?",
            "Sports",
            "kxsomethingunmapped-25sep12abc",
            series_tag="Hockey",
        )
        == "economics"
    )


def test_no_tag_leaves_the_old_cascade_exactly_as_it_was():
    """The fallback must not change any classification it has nothing to say
    about — `series_tag=None` is the pre-#5637 function."""
    for name, category, ticker in [
        ("Will the Chiefs beat the Raiders?", "Sports", "kxnflgame-25sep12kcvlv"),
        ("Will Bitcoin close above $100k?", "Crypto", "kxbtc-25sep12"),
        ("Who will win the 2028 election?", "Politics", "kxpresparty-28"),
    ]:
        assert _categorize_kalshi_market(
            name, category, ticker
        ) == _categorize_kalshi_market(name, category, ticker, series_tag=None)


# ── what the ship actually buys: the football families stop minting a row ────


def test_the_football_families_now_reach_the_refusal_and_mint_nothing():
    """#5621/#5637's real payoff, and the reason this is NOT a map addition.

    `football` is in LLM_CATEGORIES_THAT_MAY_NOT_CREATE_EVENTS, so once the CFL
    series classifies as football the auto-create refuses and no ghost row
    exists. A ticker MAPPING would instead make the sport key come from the
    ticker, bypassing this refusal and minting a correctly-sported ghost.
    """
    category = _categorize_kalshi_market(
        "Will the Ottawa Redblacks vs Toronto Argonauts total be over 45.5?",
        "Sports",
        "kxcfltotal-25sep12ottvstor",
        series_tag="Football",
    )
    assert category == "football"
    assert auto_create_sport_key_from_category(category) is None


def test_the_soccer_families_are_correctly_sported_but_still_create():
    """Stated so the ship is not read as delivering more than it does.

    `soccer` is NOT in the refusal set, so these four families get the right
    sport and STILL mint a row. The remaining duplicate is the id-less-claim
    behaviour of ruling 048 — the matching layer, filed under #2693 (D35).
    """
    category = _categorize_kalshi_market(
        "Will AFC Wimbledon beat Doncaster?",
        "Sports",
        "kxefll1game-25sep12afcvdon",
        series_tag="Soccer",
    )
    assert category == "soccer"
    assert auto_create_sport_key_from_category(category) == "soccer_other"


# ── the resolver ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_mapped_ticker_costs_no_network_call():
    """The fetch is scoped to the population this ship is about."""
    service = _FakeService({"KXNFLGAME": ["Football"]})
    assert await _resolve_series_tag(service, "KXNFLGAME-25SEP12KCVLV") is None
    assert service.calls == []


@pytest.mark.asyncio
async def test_an_unmapped_ticker_is_fetched_once_and_cached():
    service = _FakeService({"KXEFLL1GAME": ["Soccer"]})
    for _ in range(4):
        tag = await _resolve_series_tag(service, "KXEFLL1GAME-25SEP12AFCVDON")
        assert tag == "Soccer"
    assert service.calls == ["KXEFLL1GAME"], "one call per series, not per event"


@pytest.mark.asyncio
async def test_an_untagged_series_is_remembered_too():
    """Negative caching: without it every event in an untagged series refetches."""
    service = _FakeService({"KXSPELLINGBEE": []})
    for _ in range(3):
        assert await _resolve_series_tag(service, "KXSPELLINGBEE-26") is None
    assert service.calls == ["KXSPELLINGBEE"]


@pytest.mark.asyncio
async def test_a_missing_series_does_not_raise_and_does_not_guess():
    service = _FakeService({})
    assert await _resolve_series_tag(service, "KXNOSUCHSERIES-26") is None
    assert service.calls == ["KXNOSUCHSERIES"]


@pytest.mark.asyncio
async def test_a_raising_series_lookup_degrades_instead_of_killing_the_beat():
    """Ingestion must survive a sick enrichment.

    The first CI run of this ship failed with "Kalshi poll processed 0/1
    events — ingestion may be broken", because one raise inside the resolve
    aborted the whole poll at the top level. A tag we cannot read is a reason
    to classify the old way, never a reason to stop ingesting Kalshi.
    """

    class _Raising:
        async def get_series_metadata(self, series_ticker):
            raise RuntimeError("kalshi /series is having a day")

    assert await _resolve_series_tag(_Raising(), "KXEFLL1GAME-25SEP12AFCVDON") is None


@pytest.mark.asyncio
async def test_a_non_awaitable_service_attribute_degrades_too():
    """The exact shape that broke CI: a fake whose method is not awaitable."""
    service = MagicMock()
    assert await _resolve_series_tag(service, "KXEFLL1GAME-25SEP12AFCVDON") is None


@pytest.mark.asyncio
async def test_a_sick_series_is_only_looked_up_once_per_beat():
    """The degraded result is cached too, so a bad series costs one line, not
    one per event in it."""

    class _CountingRaiser:
        def __init__(self):
            self.calls = 0

        async def get_series_metadata(self, series_ticker):
            self.calls += 1
            raise RuntimeError("boom")

    service = _CountingRaiser()
    for _ in range(3):
        assert await _resolve_series_tag(service, "KXEFLL1GAME-25SEP12X") is None
    assert service.calls == 1


@pytest.mark.asyncio
async def test_an_absent_ticker_is_handled():
    service = _FakeService({})
    assert await _resolve_series_tag(service, None) is None
    assert await _resolve_series_tag(service, "") is None
    assert service.calls == []
