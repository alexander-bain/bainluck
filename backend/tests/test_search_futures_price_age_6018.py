"""A FUTURES CARD STOPS STAMPING ITS PRICES WITH THE MOMENT WE TOUCHED THE ROW. #6018.

═══ WHAT WAS MEASURED ═══

One production screenshot, `GET https://bainluck.com/search?q=WNBA%20Champion` at
390px, 2026-09-13 22:47Z (`artifacts/lane1b-225/BEFORE-wnba-search-390.png`). Two
cards in the same result list, both headlining Minnesota at 48%:

    WNBA: 2026 Champion            Minnesota Lynx 48% …        pip: "Jul 21"
    Women's Pro Basketball Champion  Minnesota 48% …           pip: "21h ago"

Read against the rows the same minute (`futures_markets.updated_at` vs
`max/min(futures_outcomes.last_updated)`):

    id        name                  row touched          prices written
    9413479   WNBA: 2026 Champion   2026-07-21 17:16Z    top five all 2026-09-13 16:50Z
    55254662  WNBA Champion         2026-09-13 22:16Z    all twelve legs 2026-08-07 23:05Z

So the pip was wrong in BOTH directions on one screen. Market 9413479 claimed
eight weeks of decay over a six-hour-old ladder; market 55254662 claimed thirteen
minutes over legs frozen five weeks. The flattering label sat on the older
market — a reader comparing the two would trust exactly the wrong one.

═══ THE MECHANISM ═══

`components/FuturesCard` fed its footer pip `market.updated_at`, and
`_format_futures_for_search` is where that value reaches it. `updated_at` is the
MARKET ROW's write time; prices live one table down in
`futures_outcomes.last_updated`. Different passes write them — metadata, tier,
volume and image work bump the row without moving a price, and the pollers move
prices on rows whose metadata has not changed in months — so the two columns
drift apart in whichever direction the last writer happened to run. Neither
column is broken. The card was reading the wrong one.

═══ THE FIX, AND WHY IT IS THE OLDEST AND NOT THE NEWEST ═══

`_served_prices_as_of` adds `prices_updated_at` to the search card payload: the
OLDEST `last_updated` among the outcomes this card actually serves.

  * Oldest, because one pip over five rows is read as covering all five. The only
    claim that is honest for every row is a floor — nothing you can see here is
    older than this. Taking the newest would let one refreshed favourite vouch
    for four stale rungs, which is precisely the flattering half of the defect.
  * Served, not the whole ladder, because 9413479 carries an `Other` rung last
    written 2026-05-12 and a tail of 0.1% legs nobody refreshes. Ageing the card
    to those prints "May 12" over a ladder whose every VISIBLE answer is hours
    old — honest about rows the reader cannot see, misleading about the ones
    they can.
  * `None` when no served row carries a stamp, and the card then renders nothing.
    An empty corner claims nothing; the old pip claimed something false (Alex,
    standing notice 34).

`updated_at` itself is unmoved — it is the row's write time, other readers sort
on it, and this ship does not redefine it. The new key is purely additive.

═══ WHAT MUST NOT CHANGE ═══

Every other key of the search card payload, byte for byte, including
`updated_at`. The last class carries that as an explicit control, because the
cheapest wrong fix here is to overwrite `updated_at` in place and silently move
the search ORDER BY that reads it.
"""

from datetime import datetime, timezone

import pytest

from app.routes.events import _format_futures_for_search, _served_prices_as_of


UTC = timezone.utc


class _Outcome:
    """The three attributes the helper reads off an ORM outcome."""

    def __init__(self, oid: int, last_updated, name: str = "Leg", prob=0.5):
        self.id = oid
        self.last_updated = last_updated
        self.name = name
        self.current_probability = prob
        # #6676: the builder reads the stored book too. None on both sides is "no
        # book at all", which the empty-book predicate passes through — so this
        # file's default `prob=0.5` stays a real 50% and no stamp assertion moves.
        self.current_yes_bid = None
        self.current_yes_ask = None
        self.current_american_odds = None
        self.rank = None
        self.probability_change_24h = None
        self.external_id = f"ext-{oid}"
        self.is_winner = False


class _Market:
    def __init__(self, outcomes, updated_at=None, **kw):
        self.outcomes = outcomes
        self.updated_at = updated_at
        self.id = kw.get("id", 1)
        self.name = kw.get("name", "A market")
        self.sport = None
        self.category = "basketball"
        self.llm_sport_category = "basketball"
        self.market_tier = 1
        self.market_type = None
        self.status = "open"
        self.source = "polymarket"
        self.resolution_date = None
        self.mutually_exclusive = True


# ---------------------------------------------------------------------------
# The two production specimens, each in the direction it actually failed.
# ---------------------------------------------------------------------------


class TestTheTwoSpecimens:
    def test_a_fresh_ladder_on_a_stale_row_is_dated_by_its_prices(self):
        """Market 9413479: row touched Jul 21, top five written 16:50Z Sep 13.

        The pip printed "Jul 21". It must now speak for the prices.
        """
        priced_at = datetime(2026, 9, 13, 16, 50, 15, tzinfo=UTC)
        market = _Market(
            outcomes=[_Outcome(i, priced_at) for i in range(1, 6)],
            updated_at=datetime(2026, 7, 21, 17, 16, 38, tzinfo=UTC),
        )
        served = [{"id": i} for i in range(1, 6)]

        assert _served_prices_as_of(market, served) == priced_at.isoformat()
        # …and emphatically NOT the row's own stamp, which is what shipped.
        assert _served_prices_as_of(market, served) != market.updated_at.isoformat()

    def test_a_stale_ladder_on_a_fresh_row_is_dated_by_its_prices(self):
        """Market 55254662: row touched 22:16Z Sep 13, all twelve legs Aug 7.

        The pip printed "21h ago" over five-week-old prices — the flattering
        direction, and the one a reader has no way to catch.
        """
        priced_at = datetime(2026, 8, 7, 23, 5, 24, tzinfo=UTC)
        market = _Market(
            outcomes=[_Outcome(i, priced_at) for i in range(1, 13)],
            updated_at=datetime(2026, 9, 13, 22, 16, 3, tzinfo=UTC),
        )
        served = [{"id": i} for i in range(1, 13)]

        assert _served_prices_as_of(market, served) == priced_at.isoformat()
        assert _served_prices_as_of(market, served) != market.updated_at.isoformat()


# ---------------------------------------------------------------------------
# The floor, and its scope.
# ---------------------------------------------------------------------------


class TestItIsTheOldestOfTheDrawnRows:
    def test_one_stale_row_among_fresh_ones_ages_the_whole_card(self):
        """A pip over five rows covers five rows. The floor is the claim."""
        fresh = datetime(2026, 9, 13, 16, 50, tzinfo=UTC)
        stale = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
        market = _Market(
            outcomes=[
                _Outcome(1, fresh),
                _Outcome(2, fresh),
                _Outcome(3, stale),
                _Outcome(4, fresh),
            ],
            updated_at=fresh,
        )
        served = [{"id": i} for i in (1, 2, 3, 4)]

        assert _served_prices_as_of(market, served) == stale.isoformat()

    def test_a_dead_tail_the_card_does_not_draw_never_ages_it(self):
        """9413479's `Other` rung, written 2026-05-12, is not on the card.

        Scoping to the whole ladder would print "May 12" over five prices from
        this afternoon — the mirror-image lie, told about rows nobody can see.
        """
        fresh = datetime(2026, 9, 13, 16, 50, 15, tzinfo=UTC)
        may = datetime(2026, 5, 12, 16, 17, 37, tzinfo=UTC)
        market = _Market(
            outcomes=[
                _Outcome(1, fresh, name="Minnesota Lynx", prob=0.475),
                _Outcome(2, fresh, name="Las Vegas Aces", prob=0.135),
                _Outcome(99, may, name="Other", prob=None),
            ],
            updated_at=datetime(2026, 7, 21, tzinfo=UTC),
        )
        served = [{"id": 1}, {"id": 2}]  # `Other` is dropped before it is served

        assert _served_prices_as_of(market, served) == fresh.isoformat()


class TestItWithholdsRatherThanGuesses:
    def test_no_served_row_carries_a_stamp_returns_none(self):
        """The lean typeahead shape omits ids; nothing can be claimed from it."""
        market = _Market(
            outcomes=[_Outcome(1, datetime(2026, 9, 1, tzinfo=UTC))],
            updated_at=datetime(2026, 9, 13, tzinfo=UTC),
        )
        assert _served_prices_as_of(market, [{"name": "Yes"}]) is None

    def test_an_empty_card_returns_none(self):
        market = _Market(outcomes=[], updated_at=datetime(2026, 9, 13, tzinfo=UTC))
        assert _served_prices_as_of(market, []) is None

    def test_a_served_row_whose_stamp_is_null_is_skipped_not_zeroed(self):
        """A null `last_updated` is 'cannot say', never 'the epoch'."""
        fresh = datetime(2026, 9, 13, 16, 50, tzinfo=UTC)
        market = _Market(
            outcomes=[_Outcome(1, None), _Outcome(2, fresh)],
            updated_at=fresh,
        )
        assert _served_prices_as_of(market, [{"id": 1}, {"id": 2}]) == fresh.isoformat()

    def test_every_served_stamp_null_returns_none(self):
        market = _Market(
            outcomes=[_Outcome(1, None), _Outcome(2, None)],
            updated_at=datetime(2026, 9, 13, tzinfo=UTC),
        )
        assert _served_prices_as_of(market, [{"id": 1}, {"id": 2}]) is None

    def test_a_row_with_no_such_attribute_withholds_instead_of_raising(self):
        """Found by running the suite, not by reading it.

        `tests/integration/test_route_search_family_more_count_2646.py` builds
        its outcome doubles as `SimpleNamespace` with no `last_updated`, and a
        bare `o.last_updated` here turned all sixteen of its green tests into
        `AttributeError` 500s through the route. A serializer must not be the
        thing that empties a search page, and "this payload cannot say" is
        already a state this function has.
        """
        from types import SimpleNamespace

        market = _Market(
            outcomes=[SimpleNamespace(id=1, name="Yes")],
            updated_at=datetime(2026, 9, 13, tzinfo=UTC),
        )
        assert _served_prices_as_of(market, [{"id": 1}]) is None

    def test_one_attributeless_row_does_not_mute_its_stamped_sibling(self):
        fresh = datetime(2026, 9, 13, 16, 50, tzinfo=UTC)
        from types import SimpleNamespace

        market = _Market(
            outcomes=[SimpleNamespace(id=1, name="Yes"), _Outcome(2, fresh)],
            updated_at=fresh,
        )
        assert _served_prices_as_of(market, [{"id": 1}, {"id": 2}]) == fresh.isoformat()


# ---------------------------------------------------------------------------
# The payload.
# ---------------------------------------------------------------------------


class TestThePayloadAndWhatMustNotChange:
    def _specimen(self):
        priced_at = datetime(2026, 9, 13, 16, 50, 15, tzinfo=UTC)
        row_touched = datetime(2026, 7, 21, 17, 16, 38, tzinfo=UTC)
        market = _Market(
            outcomes=[
                _Outcome(1, priced_at, name="Minnesota Lynx", prob=0.475),
                _Outcome(2, priced_at, name="Las Vegas Aces", prob=0.135),
            ],
            updated_at=row_touched,
            name="WNBA: 2026 Champion",
            id=9413479,
        )
        return market, priced_at, row_touched

    def test_the_card_payload_carries_the_price_age(self):
        market, priced_at, _ = self._specimen()
        payload = _format_futures_for_search(market)

        assert payload["prices_updated_at"] == priced_at.isoformat()

    def test_updated_at_is_untouched(self):
        """The cheapest wrong fix overwrites `updated_at` in place.

        It is the row's write time, `/search` sorts on it (LAT-P037's tier-2
        tiebreak reads `updated_at` by name), and redefining it would move a
        page ordering to fix a label. This control fails if anyone tries.
        """
        market, priced_at, row_touched = self._specimen()
        payload = _format_futures_for_search(market)

        assert payload["updated_at"] == row_touched.isoformat()
        assert payload["updated_at"] != payload["prices_updated_at"]

    def test_the_rest_of_the_card_is_unchanged(self):
        """Additive: every pre-existing key still present, `prices_updated_at`
        the only new one."""
        market, _, _ = self._specimen()
        payload = _format_futures_for_search(market)

        expected = {
            "id",
            "name",
            "sport",
            "sport_name",
            "category",
            "llm_sport_category",
            "market_tier",
            "market_type_label",
            "status",
            "source",
            "resolution_date",
            "top_outcomes",
            "outcome_count",
            "updated_at",
            "prices_updated_at",
        }
        assert set(payload) == expected

    def test_a_market_with_no_price_history_serves_null_not_the_row_stamp(self):
        market = _Market(
            outcomes=[_Outcome(1, None, name="Yes", prob=0.5)],
            updated_at=datetime(2026, 9, 13, 22, 16, tzinfo=UTC),
        )
        payload = _format_futures_for_search(market)

        assert payload["prices_updated_at"] is None
        assert payload["updated_at"] is not None


@pytest.mark.parametrize(
    "served_ids,expected_index",
    [
        ([1], 0),
        ([2], 1),
        ([1, 2], 0),
    ],
)
def test_the_answer_tracks_which_rows_are_served(served_ids, expected_index):
    """Not a constant: change the served set, change the answer.

    A helper that returned `min(every stamp)` regardless of `served` would pass
    the specimens above; it fails here on `[2]`.
    """
    stamps = [
        datetime(2026, 8, 1, tzinfo=UTC),
        datetime(2026, 9, 13, tzinfo=UTC),
    ]
    market = _Market(
        outcomes=[_Outcome(1, stamps[0]), _Outcome(2, stamps[1])],
        updated_at=datetime(2026, 9, 13, 23, tzinfo=UTC),
    )
    served = [{"id": i} for i in served_ids]

    assert _served_prices_as_of(market, served) == stamps[expected_index].isoformat()
