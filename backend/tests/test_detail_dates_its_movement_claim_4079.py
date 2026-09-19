"""#4079 — the detail payload can finally say WHEN a price moved.

Alex's original report named the green arrow and the "24h" numbers under the
graph. The copy half was repaired by #7176's dated-basis bank; this is the
DETAIL RESPONSE PATH, which the bank never reached — `dated_movement_basis` is
read at exactly one call site, in `routes/feed.py`.

What the detail route served instead was `probability_change_24h`, which
CAL-P159 proved is a per-write delta that freezes, beside `last_updated`, which
#2024 settled is *"that a poll RAN"* and explicitly **not** *"that the price
MOVED"*. The column that answers the second question — `price_changed_at`,
advanced by `price_changed_at_value` only when the written price `IS DISTINCT
FROM` the stored one — has existed since #2024 and reached no reader on any
route. So every surface that wanted to date a move had to date it by the poll.

MEASURED ON PRODUCTION 2026-09-19, over a 300-market slice of the markets that
actually make a movement claim (the population carrying a `dated_movement_basis`
key):

  * 3,467 ladder rows; **1,054 (30.4%)** carry a `price_changed_at` on a
    different DAY from their `last_updated`.
  * Of the 300 LEADER rows — the row the web hero pill dates by, via
    `movementWindowLabel(leader?.last_updated)` — **52 name the wrong day** and
    **26 have no stamp at all**: 78 of 300 hero pills make a last-move day claim
    the payload cannot support.
  * `last_updated` coverage is 100%; `price_changed_at` is 79.35%. The bank, for
    contrast, covers **14.22%** of ladder rows (2,286 of 16,074 across the 1,416
    banked markets) — which is why the bank is not the instrument for a surface
    that renders the WHOLE field, and why this ship shares the existing column
    rather than inventing a second temporal policy.

THE FIXTURE IS MARKET 58321581 — *Game of the Year*, one of #4079's three named
specimens — copied from `futures_outcomes` on 2026-09-19 rather than invented,
so a later reader can re-fetch the id and check it. It is the shape the whole
finding rests on: one sweep stamped all 24 rows `last_updated` 10:38:51, while
thirteen of them last actually moved on 09-18 04:31:29, thirty hours earlier.

These tests pin the PRODUCER half of a two-lane ship (notice 46). The consumers
are ux's `movementWindowLabel`, which reads the wrong column today, and native's
`FuturesDetailView`, whose sort control is still literally captioned
`"24h Change"` (`FuturesDetailView.swift:13`) over the frozen per-write delta.
Nothing here changes a rendered pixel on its own, and nothing here changes
`probability_change_24h`, its writers, or any ranking that reads it.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes.futures import _format_market_detail
from app.utils.futures_unsupported_price import WITHHELD_PRICE_FIELDS

MARKET_ID = 58321581

#: The single sweep stamp every row on 58321581 carries. One write, 24 rows.
SWEEP = datetime(2026, 9, 19, 10, 38, 51, 278292, tzinfo=timezone.utc)

#: `price_changed_at` as production holds it for six of that market's rows.
#: Only the first two moved on the sweep; the rest are hours-to-days older.
MOVED_ON_THE_SWEEP = SWEEP
MOVED_YESTERDAY_AFTERNOON = datetime(
    2026, 9, 18, 13, 50, 38, 865287, tzinfo=timezone.utc
)
MOVED_OVERNIGHT = datetime(2026, 9, 19, 0, 42, 9, 854699, tzinfo=timezone.utc)
MOVED_YESTERDAY_EVENING = datetime(2026, 9, 18, 20, 52, 15, 913408, tzinfo=timezone.utc)
MOVED_THIRTY_HOURS_AGO = datetime(2026, 9, 18, 4, 31, 29, 111326, tzinfo=timezone.utc)

# (outcome_id, name, current_probability, probability_change_24h, price_changed_at)
GOTY_ROWS = [
    (216388319, "Grand Theft Auto VI", 0.660, -0.025, MOVED_ON_THE_SWEEP),
    (216388320, "Resident Evil Requiem", 0.110, 0.0, MOVED_YESTERDAY_AFTERNOON),
    (216388327, "Phantom Blade Zero", 0.0505, 0.0, MOVED_OVERNIGHT),
    (216388325, "Control Resonant", 0.0305, 0.0, MOVED_YESTERDAY_EVENING),
    (216388318, "007 First Light", 0.020, 0.0, MOVED_THIRTY_HOURS_AGO),
    (216388321, "Half-Life 3", 0.0045, 0.0, MOVED_THIRTY_HOURS_AGO),
]


def _outcome(outcome_id, name, prob, change, price_changed_at, **overrides):
    """One `futures_outcomes` row as the detail serializer meets it.

    `SimpleNamespace` for the reason every other serializer test in this suite
    uses it: the function takes whatever carrier the route hands it and reads
    attributes off it. See `test_a_carrier_without_the_column_degrades_to_a_refusal`
    for the one case where the attribute is deliberately absent.
    """
    row = SimpleNamespace(
        id=outcome_id,
        name=name,
        external_id=f"0x{outcome_id:064x}",
        current_probability=prob,
        current_american_odds=None,
        rank=None,
        rank_change_24h=None,
        probability_change_24h=change,
        opening_probability=None,
        opening_american_odds=None,
        is_winner=None,
        resolution_source=None,
        last_updated=SWEEP,
        price_changed_at=price_changed_at,
        team_id=None,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def _goty_market(outcomes=None):
    """Market 58321581 as production holds it."""
    return SimpleNamespace(
        id=MARKET_ID,
        name="Game of the Year 2026",
        description=None,
        category="award",
        source="polymarket",
        external_id="58321581",
        status="open",
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=1,
        llm_sport_category="entertainment",
        # The six rows sum to 0.8755, comfortably under the squeeze band, so
        # `normalize_display_probs` is a no-op and every price below is the
        # stored one. That is deliberate: this ship is about an instant, and a
        # squeezed price would put a second variable in every assertion.
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=(
            outcomes if outcomes is not None else [_outcome(*r) for r in GOTY_ROWS]
        ),
    )


def _detail(market, withheld=None):
    return _format_market_detail(market, None, withheld or set())


def _by_name(payload, name):
    return next(o for o in payload["outcomes"] if o["name"] == name)


class TestTheStampReachesTheReader:
    """The producer half: the instant is on the wire, in a shape a client can use."""

    def test_the_key_is_served_on_every_row(self):
        payload = _detail(_goty_market())
        assert len(payload["outcomes"]) == 6
        for outcome in payload["outcomes"]:
            assert "price_changed_at" in outcome, (
                f"{outcome['name']} reached the reader with no price_changed_at key — "
                "a client cannot date a move it is never sent"
            )

    def test_it_is_an_iso_instant_not_a_datetime_object(self):
        """JSON-serialisable, and the same spelling `last_updated` uses."""
        payload = _detail(_goty_market())
        gta = _by_name(payload, "Grand Theft Auto VI")
        assert gta["price_changed_at"] == MOVED_ON_THE_SWEEP.isoformat()
        assert isinstance(gta["price_changed_at"], str)

    def test_the_row_that_moved_and_the_row_that_did_not_are_now_distinguishable(self):
        """THE WHOLE SHIP, in one assertion.

        Both rows carry the identical `last_updated`, because one sweep wrote
        them both. Before this field a reader had no way to tell them apart and
        `movementWindowLabel` dated both to Sep 19. Only one of them moved then.
        """
        payload = _detail(_goty_market())
        gta = _by_name(payload, "Grand Theft Auto VI")
        half_life = _by_name(payload, "Half-Life 3")

        assert (
            gta["last_updated"] == half_life["last_updated"]
        ), "fixture drift: the premise is that ONE sweep stamped both rows"
        assert gta["price_changed_at"] != half_life["price_changed_at"]
        assert half_life["price_changed_at"] == MOVED_THIRTY_HOURS_AGO.isoformat()

    def test_the_poll_stamp_overstates_the_move_on_four_of_six_rows(self):
        """The measured production shape, reproduced on the named specimen.

        Four of these six rows last moved on a DIFFERENT DAY from the poll that
        stamped them. That ratio is what the 1,054-of-3,467 production count is
        made of, and it is the reason a reader dating a move by `last_updated`
        is told the wrong day.
        """
        payload = _detail(_goty_market())
        wrong_day = [
            o
            for o in payload["outcomes"]
            if o["price_changed_at"][:10] != o["last_updated"][:10]
        ]
        assert sorted(o["name"] for o in wrong_day) == [
            "007 First Light",
            "Control Resonant",
            "Half-Life 3",
            "Resident Evil Requiem",
        ]


class TestTheRefusalIsHonest:
    """NULL is "we never saw it move" — a refusal, never a zero and never absent."""

    def test_a_row_that_never_moved_serves_the_key_present_and_null(self):
        """`undefined !== null` is true in both clients, so the key must be THERE.

        The same contract #5539 and #5611 state for the withheld price: a client
        testing `!== null` reads an omitted key as a value.
        """
        # The same row, with the stamp production would hold for an outcome
        # nothing has rewritten since the column shipped: NULL.
        rows = [_outcome(*GOTY_ROWS[0]), _outcome(*GOTY_ROWS[1][:4], None)]
        payload = _detail(_goty_market(rows))
        never_moved = _by_name(payload, "Resident Evil Requiem")
        assert "price_changed_at" in never_moved
        assert never_moved["price_changed_at"] is None

    def test_a_carrier_without_the_column_degrades_to_a_refusal_not_an_exception(self):
        """A projection that stopped loading the column must not empty the ladder.

        `dated_movement_basis` argues this at length for its own column and it
        applies identically here: raising inside the per-item serializer would
        cost the reader all six rows rather than one dated claim (gotcha #42).
        """
        thin = _outcome(*GOTY_ROWS[0])
        del thin.price_changed_at
        payload = _detail(_goty_market([thin, _outcome(*GOTY_ROWS[1])]))

        assert len(payload["outcomes"]) == 2, "one unreadable row emptied the ladder"
        assert _by_name(payload, "Grand Theft Auto VI")["price_changed_at"] is None
        # The healthy sibling is untouched — the fail-closed half that matters.
        assert (
            _by_name(payload, "Resident Evil Requiem")["price_changed_at"]
            == MOVED_YESTERDAY_AFTERNOON.isoformat()
        )


class TestTheWithholdRailIsUnchanged:
    """An instant reconstructs no price, so the price refusal does not touch it."""

    def test_a_withheld_row_keeps_its_instant_while_losing_its_price(self):
        payload = _detail(_goty_market(), withheld={216388319})
        gta = _by_name(payload, "Grand Theft Auto VI")

        assert gta["probability"] is None
        assert gta["probability_change_24h"] is None
        assert payload["prices_withheld"] == 1
        assert gta["price_changed_at"] == MOVED_ON_THE_SWEEP.isoformat(), (
            "the withhold rail nulled an instant — it exists to stop a reader "
            "reconstructing a refused PRICE, and a timestamp is not one"
        )

    def test_the_stamp_is_deliberately_not_a_withheld_price_field(self):
        """Stated here so a later edit to that tuple has to argue with a test."""
        assert "price_changed_at" not in WITHHELD_PRICE_FIELDS
        assert set(WITHHELD_PRICE_FIELDS) == {
            "probability",
            "american_odds",
            "probability_change_24h",
            "movement",
        }


class TestNothingElseMoved:
    """Codex's constraint: preserve the stored deltas and the ranking inputs."""

    def test_the_per_write_delta_is_served_exactly_as_before(self):
        """This ship adds an instant. It does not reinterpret the number.

        `probability_change_24h` keeps its meaning and all of its readers —
        `/api/futures/movers`, `update_max_movement`, `max_movement_24h` and
        `compute_futures_highlight`'s CHOICE of subject.
        """
        payload = _detail(_goty_market())
        assert (
            _by_name(payload, "Grand Theft Auto VI")["probability_change_24h"] == -0.025
        )
        # 0.0 is falsy and has always served as None on this route; pinned so the
        # new key cannot be read as licence to change the old one.
        assert _by_name(payload, "Half-Life 3")["probability_change_24h"] is None

    def test_the_prices_and_the_order_are_untouched(self):
        payload = _detail(_goty_market())
        assert [o["name"] for o in payload["outcomes"]] == [
            "Grand Theft Auto VI",
            "Resident Evil Requiem",
            "Phantom Blade Zero",
            "Control Resonant",
            "007 First Light",
            "Half-Life 3",
        ]
        assert _by_name(payload, "Grand Theft Auto VI")["probability"] == 0.660

    @pytest.mark.parametrize("key", ["last_updated", "probability", "id", "name"])
    def test_the_existing_keys_still_arrive(self, key):
        payload = _detail(_goty_market())
        assert all(key in o for o in payload["outcomes"])
