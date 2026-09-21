"""#7505 — a sole-moneyline Polymarket event writes BOTH sides, not one.

THE DEFECT (measured on production 2026-09-21, reader-visible).

`/hub/tennis` at 390px served a card reading

    Davis Cup: Liam Draxl vs. Quentin Halys
    Liam Draxl  ▓▓▓▓░░░░  50%

— two players named in the title, one priced, and a half-filled comparative
bar. A reader cannot tell whether Halys is the other 50% or simply unpriced.
Two cards up, the same shape for Fery/Andrade (94%) and Zverev/Prizmic (94%).

THE VENUE PUBLISHES BOTH SIDES; WE WROTE ONE. Read at Gamma per standing
notice 26/27 rather than inferred from our tables — `GET /events/1045485`,
slug `daviscup-draxl-halys-2026-09-19`::

    markets: 1
    Davis Cup: Liam Draxl vs. Quentin Halys
        outcomes      ["Liam Draxl", "Quentin Halys"]
        outcomePrices ["0.5", "0.5"]

So "Polymarket does not price the second side" is false, and the repair is an
ingest one rather than the render rule the issue offered as its alternative.

THIS IS #6739's UNFINISHED HALF. #6739 established that a single-market event
is often a game whose venue listing holds just the moneyline, and taught leg 0
to wear the side's name instead of "Yes". It stopped at the label. The second
leg was one index away the whole time — `outcomes[1]`, the array #6739's own
docstring calls "definitionally the side this number belongs to".

WHY ONLY THESE EVENTS ARE AFFECTED. An event with more than one market also
gets a DECOMPOSED `{condition}_yes`/`_no` row carrying both sides, which is why
an NHL game reads correctly: market 61814742 (the parent) holds one leg
"Hurricanes", and 61814743 (the decomposition) holds "Hurricanes 0.495" /
"Flames 0.505". The decomposition branch is gated on `len(event.markets) > 1`,
so a sole-moneyline event never reaches it and the one-leg parent is the only
row a reader can be served.

POPULATION, measured on production 2026-09-21 (polymarket, name matching
'% vs%', exactly one leg):

    ==========================================  =====
    status='open'                                 977
      ... of which a decomposed sibling exists     509
      ... of which NO sibling exists (this fix)    468
    status='resolved'                          16,879
    ==========================================  =====

Open rows by sport: soccer 387 · tennis 198 · hockey 176 · esports 47 ·
baseball 39 · basketball 30 · football 23 · rugby 15 · table_tennis 13. All 27
Davis Cup rows are sibling-less, which is why that tie is what ux photographed.

🔴 THE KEY IS `_side1` AND NOT `{condition}_no`, AND THAT IS THE WHOLE TRAP.
`duplicate_condition_outcomes.drop_duplicate_legs` drops a leg whose id ends
`_yes`/`_no` when the BARE condition id is also present on the same market —
which is exactly the pair this branch would produce — and it runs at SERVE time
in `routes/feed.py`, `routes/events.py` and six places in `routes/futures.py`.
Keyed `_no`, this leg would be written on every poll and filtered out of every
reader surface: inert on precisely its own population. `test_the_complement_
survives_the_serve_time_dedup` runs the real production helper over the real
emitted ids so the trap cannot be re-entered by a later "make it consistent"
edit.

🔴 THE CONTROLS MATTER MORE THAN THE SHIP ASSERTION, exactly as on #6739 and
#6050. "Always emit outcomes[1]" passes the ship test and doubles every genuine
Yes/No question — the 17 #6739 measured, and the whole politics/econ/crypto
single-market population behind them. So the second leg is asserted to be
CONDITIONAL from both directions, and every degenerate payload is pinned to one
leg.

RED-FIRST, on master `b725775dd` before the fix: every test in
`TestBothSidesAreWritten` fails with `len(rows) == 1`; every test in
`TestOneLeggedShapesStayOneLegged` already passes and must keep passing.

NOTE ON A NEIGHBOUR'S TEST. `test_poly_single_market_names_its_side_6739.py`
asserted `len(rows) == 1` on a two-sided payload. That assertion was incidental
to its ship (which is the LABEL) and is the exact behaviour this issue changes,
so it is updated there rather than worked around here, and says why in place.
"""

from __future__ import annotations

import pytest

from app.services.polymarket_api import PolymarketEvent, PolymarketMarket
from app.tasks.polymarket import _parent_outcome_data, complementary_book
from app.utils.duplicate_condition_outcomes import drop_duplicate_legs
from app.utils.generic_market_history import wanted_gamma_outcome_name

COND = "0x7e6cf23d5a4d9419368610b2489da98ce641a668f3218c7f006843721bdd91d0"


def _single_market_event(
    *,
    title: str,
    question: str,
    outcomes: list[str],
    prices: list[float],
    best_bid: float | None = 0.60,
    best_ask: float | None = 0.64,
    last_trade_price: float | None = 0.62,
) -> PolymarketEvent:
    """One event, one market — the shape that reaches the last branch.

    Built from the real pydantic models, like #6739's fixture, so a field this
    branch reads cannot drift out from under the test.
    """
    return PolymarketEvent(
        id="1045485",
        title=title,
        markets=[
            PolymarketMarket(
                condition_id=COND,
                question=question,
                outcomes=outcomes,
                outcome_prices=prices,
                best_bid=best_bid,
                best_ask=best_ask,
                last_trade_price=last_trade_price,
            )
        ],
    )


def _draxl_halys(**kw) -> PolymarketEvent:
    """The photographed specimen, with the venue's own payload (read 2026-09-21)."""
    return _single_market_event(
        title="Davis Cup: Liam Draxl vs. Quentin Halys",
        question="Davis Cup: Liam Draxl vs. Quentin Halys",
        outcomes=["Liam Draxl", "Quentin Halys"],
        prices=[0.5, 0.5],
        **kw,
    )


class TestBothSidesAreWritten:
    """The ship. Each of these fails on master with one leg."""

    def test_the_photographed_card_gets_its_second_player(self):
        """The literal defect: "Draxl 50%" with Halys named and never priced."""
        rows = _parent_outcome_data(_draxl_halys())

        assert [r["name"] for r in rows] == ["Liam Draxl", "Quentin Halys"]

    def test_the_two_legs_sum_to_one_so_the_bar_is_readable(self):
        """A two-way card whose sides do not sum to 1 is a new defect, not a fix.

        The price is the complement of the number we actually STORE, not the
        raw `outcomePrices[1]`: leg 0 is priced through the gated resolver
        (0.495 where the venue posts 0.49), so the raw complement would serve a
        pair summing to 1.005. The complement of the stored number is also what
        the decomposed sibling holds for the same game (market 61814743:
        Hurricanes 0.495 / Flames 0.505), so the two rows agree.
        """
        rows = _parent_outcome_data(
            _single_market_event(
                title="Alvark Tokyo vs. Ryukyu Golden Kings",
                question="Alvark Tokyo vs. Ryukyu Golden Kings",
                outcomes=["Ryukyu Golden Kings", "Alvark Tokyo"],
                prices=[0.62, 0.38],
            )
        )

        assert len(rows) == 2
        assert rows[0]["prob"] + rows[1]["prob"] == pytest.approx(1.0)
        assert rows[1]["prob"] == pytest.approx(1 - rows[0]["prob"])

    def test_the_complement_is_the_side_its_price_belongs_to_not_the_title_order(self):
        """The warrant is index-parallelism, not word order — #6739's rule, on
        the leg #6739 did not write. `outcomes[0]` is the AWAY side here, so a
        positional rule would hand each price to the wrong player."""
        rows = _parent_outcome_data(
            _single_market_event(
                title="Alvark Tokyo vs. Ryukyu Golden Kings",
                question="Alvark Tokyo vs. Ryukyu Golden Kings",
                outcomes=["Ryukyu Golden Kings", "Alvark Tokyo"],
                prices=[0.62, 0.38],
            )
        )

        assert rows[0]["name"] == "Ryukyu Golden Kings"
        assert rows[1]["name"] == "Alvark Tokyo"

    def test_the_complement_survives_the_serve_time_dedup(self):
        """🔴 THE TRAP, pinned with the real production helper.

        `drop_duplicate_legs` removes a `_yes`/`_no` leg whose bare condition id
        is also on the same market. Keyed `{condition}_no`, this leg is exactly
        that shape and would be filtered out of feed, events and six futures
        call sites — written every poll, never served. Running the real helper
        over the real emitted ids is what makes that unrepeatable.
        """
        rows = _parent_outcome_data(_draxl_halys())

        survivors = drop_duplicate_legs(rows, lambda r: r["external_id"])

        assert len(survivors) == 2, (
            "the complement was dropped by the serve-time dedup — it is keyed "
            "in the _yes/_no namespace, which is reserved for the decomposition "
            "branch and garbage-collected against a bare twin"
        )
        assert [r["name"] for r in survivors] == ["Liam Draxl", "Quentin Halys"]

    def test_the_complement_key_is_outside_the_binary_leg_namespace(self):
        """States the rule directly, so the reason survives a refactor that
        keeps the dedup test passing by accident."""
        rows = _parent_outcome_data(_draxl_halys())

        assert rows[0]["external_id"] == COND
        assert rows[1]["external_id"] == f"{COND}_side1"
        assert not rows[1]["external_id"].endswith(("_yes", "_no"))

    def test_the_complement_asks_gamma_for_its_own_token_by_name(self):
        """Not merely dodging the filter — landing on the right history series.

        `wanted_gamma_outcome_name` reads a `_yes`/`_no` id positionally and
        anything else BY NAME ("BY NAME, NEVER BY POSITION", Q489). The
        complement's name is the venue's own `outcomes[1]` token, so its chart
        asks for the Halys token by the label Gamma published. A `_no` key
        would have asked for the "No" token, which this market does not have —
        and per that helper's own docstring a mis-attributed token does not
        make a line stale, it makes it INVERTED.
        """
        rows = _parent_outcome_data(_draxl_halys())

        complement = _Row(rows[1])
        assert wanted_gamma_outcome_name(complement) == "Quentin Halys"

    def test_the_complement_book_is_the_partner_token_not_a_copy(self):
        """A binary CLOB's two tokens share one book, so the complement's bid is
        the other side of the same orders. Reuses the shipped identity rather
        than restating it, which is also what keeps this leg consistent with the
        decomposed writer's Under/No leg.
        """
        rows = _parent_outcome_data(_draxl_halys(best_bid=0.60, best_ask=0.64,
                                                 last_trade_price=0.62))

        expected_bid, expected_ask, expected_last = complementary_book(0.60, 0.64, 0.62)
        assert rows[1]["yes_bid"] == expected_bid
        assert rows[1]["yes_ask"] == expected_ask
        assert rows[1]["last_price"] == expected_last
        assert rows[1]["yes_bid"] != rows[0]["yes_bid"], (
            "the complement copied the Yes token's book instead of reading the "
            "partner side of it"
        )

    def test_the_complement_carries_the_same_provenance_and_no_new_keys(self):
        """CERT-3202's `market` reference is provenance, so the partner leg owes
        it too — the parent-field writers ask THIS child whether it settled. The
        key set is asserted so a new priced key cannot enter through the new
        leg, which is the half a reviewer cannot see from the ship assertion.
        """
        event = _draxl_halys()
        rows = _parent_outcome_data(event)

        assert rows[1]["market"] is event.markets[0]
        assert set(rows[1]) == set(rows[0]) == {
            "external_id",
            "name",
            "prob",
            "yes_bid",
            "yes_ask",
            "last_price",
            "market",
        }

    def test_leg_zero_is_byte_identical_to_what_6739_shipped(self):
        """The claim is "a leg was ADDED", not "a leg moved". #6739's row must
        come through untouched, or this is a pricing change wearing a
        completeness fix's clothes."""
        rows = _parent_outcome_data(
            _single_market_event(
                title="Jukurit Mikkeli vs. Vaasan Sport",
                question="Jukurit Mikkeli vs. Vaasan Sport",
                outcomes=["Jukurit Mikkeli", "Vaasan Sport"],
                prices=[0.62, 0.38],
            )
        )

        assert {k: v for k, v in rows[0].items() if k != "market"} == {
            "external_id": COND,
            "name": "Jukurit Mikkeli",
            "prob": 0.62,
            "yes_bid": 0.60,
            "yes_ask": 0.64,
            "last_price": 0.62,
        }


class TestOneLeggedShapesStayOneLegged:
    """The controls. Every one of these already passes on master and must keep
    passing: this is the direction in which the fix is allowed to fail but
    never to guess."""

    def test_a_genuine_yes_no_question_gets_no_second_leg(self):
        """17 of #6739's 240 measured rows, and the entire non-sports
        single-market population behind them. "No 29%" as a separate rung under
        a question card is noise, not completeness."""
        rows = _parent_outcome_data(
            _single_market_event(
                title="Will the Fed cut rates in October?",
                question="Will the Fed cut rates in October?",
                outcomes=["Yes", "No"],
                prices=[0.71, 0.29],
            )
        )

        assert len(rows) == 1
        assert rows[0]["name"] == "Yes"

    @pytest.mark.parametrize(
        "outcomes",
        [
            pytest.param([], id="outcomes-absent"),
            pytest.param(["Liam Draxl"], id="only-one-token"),
            pytest.param(["Liam Draxl", ""], id="second-token-blank"),
            pytest.param(["Liam Draxl", "   "], id="second-token-whitespace"),
            pytest.param(["Liam Draxl", "No"], id="second-token-bare-no"),
            pytest.param(["Liam Draxl", "NO"], id="second-token-uppercase-no"),
            pytest.param(["", "Quentin Halys"], id="first-token-blank"),
            pytest.param(["Yes", "Quentin Halys"], id="first-token-bare-yes"),
        ],
    )
    def test_a_degenerate_payload_never_invents_a_partner(self, outcomes):
        """A malformed venue payload must not be able to mint a second rung.
        Both directions are covered: a missing SECOND side leaves #6739's single
        named leg alone, and a missing FIRST side keeps the whole rescue off.
        """
        rows = _parent_outcome_data(
            _single_market_event(
                title="Davis Cup: Liam Draxl vs. Quentin Halys",
                question="Davis Cup: Liam Draxl vs. Quentin Halys",
                outcomes=outcomes,
                prices=[0.5, 0.5],
            )
        )

        assert len(rows) == 1

    def test_a_token_echoing_the_question_gets_no_partner(self):
        """Relabelling a leg with its own market's name reproduces the collapse
        Q492 undoes, so #6739 refuses it — and a refused side cannot then be
        used to justify a partner for it."""
        rows = _parent_outcome_data(
            _single_market_event(
                title="Jukurit Mikkeli vs. Vaasan Sport",
                question="Jukurit Mikkeli vs. Vaasan Sport",
                outcomes=["Jukurit Mikkeli vs. Vaasan Sport", "Vaasan Sport"],
                prices=[0.5, 0.5],
            )
        )

        assert len(rows) == 1
        assert rows[0]["name"] == "Yes"

    def test_a_single_market_over_under_keeps_its_one_leg(self):
        """An o/u question's fallback is "Under", which is not a Yes/No token,
        so `_sub_market_side_label` short-circuits and returns it unchanged —
        the partner is refused for the same reason #6739 never second-guesses an
        already-named side. Pinned because "o/u" is the one fallback in this
        branch that is not "No", and a later edit could easily start emitting
        an "Under" rung here that no reader asked for.
        """
        rows = _parent_outcome_data(
            _single_market_event(
                title="Cavalry FC vs. Forge FC - Total Corners",
                question="Cavalry FC vs. Forge FC - Total Corners O/U 9.5",
                outcomes=["Over", "Under"],
                prices=[0.55, 0.45],
            )
        )

        assert len(rows) == 1

    def test_an_unpriced_market_writes_nothing_at_all(self):
        """The `prob is None or prob <= 0` refusal is upstream of the partner,
        so a market we decline to price cannot acquire a complement of a price
        that does not exist."""
        rows = _parent_outcome_data(
            _single_market_event(
                title="Davis Cup: Liam Draxl vs. Quentin Halys",
                question="Davis Cup: Liam Draxl vs. Quentin Halys",
                outcomes=["Liam Draxl", "Quentin Halys"],
                prices=[0.0, 1.0],
                best_bid=None,
                best_ask=None,
                last_trade_price=None,
            )
        )

        assert rows == []


class TestTheOtherTwoShapesAreUntouched:
    """`_parent_outcome_data` serves three branches and this issue is about one.
    Folding them together would be a pricing change wearing a refactor's
    clothes, which the function's own docstring warns about."""

    def test_a_negrisk_field_gets_one_leg_per_sub_market_as_before(self):
        event = PolymarketEvent(
            id="31552",
            title="Presidential Election Winner 2028",
            neg_risk=True,
            markets=[
                PolymarketMarket(
                    condition_id="0xaaa",
                    question="Will A win?",
                    outcomes=["Yes", "No"],
                    outcome_prices=[0.6, 0.4],
                    group_item_title="Candidate A",
                    best_bid=0.59,
                    best_ask=0.61,
                ),
                PolymarketMarket(
                    condition_id="0xbbb",
                    question="Will B win?",
                    outcomes=["Yes", "No"],
                    outcome_prices=[0.4, 0.6],
                    group_item_title="Candidate B",
                    best_bid=0.39,
                    best_ask=0.41,
                ),
            ],
        )

        rows = _parent_outcome_data(event)

        assert [r["external_id"] for r in rows] == ["0xaaa", "0xbbb"]

    def test_a_game_with_sub_markets_still_gets_one_leg_per_sub_market(self):
        """The multi-market parent is the moneyline matching anchor and its
        second side comes from the DECOMPOSED row, which already writes the
        pair. Adding a complement here would double every sub-market."""
        event = PolymarketEvent(
            id="1059215",
            title="Hurricanes vs. Flames",
            neg_risk=False,
            markets=[
                PolymarketMarket(
                    condition_id="0xccc",
                    question="Hurricanes vs. Flames",
                    outcomes=["Hurricanes", "Flames"],
                    outcome_prices=[0.49, 0.51],
                    best_bid=0.48,
                    best_ask=0.50,
                ),
                PolymarketMarket(
                    condition_id="0xddd",
                    question="Hurricanes vs. Flames: O/U 5.5",
                    outcomes=["Over", "Under"],
                    outcome_prices=[0.595, 0.405],
                    best_bid=0.59,
                    best_ask=0.60,
                ),
            ],
        )

        rows = _parent_outcome_data(event)

        assert [r["external_id"] for r in rows] == ["0xccc", "0xddd"]


class _Row:
    """A minimal stand-in for the ORM outcome `wanted_gamma_outcome_name` reads.

    That helper takes `.external_id` and `.name` off a row object; the branch
    under test emits dicts, so this adapts one without importing the model or
    re-implementing the helper's rule.
    """

    def __init__(self, row: dict):
        self.external_id = row["external_id"]
        self.name = row["name"]
