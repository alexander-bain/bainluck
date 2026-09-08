"""#3980 — a futures card whose every outcome is priceless is not a card.

WHAT A READER SAW. `https://bainluck.com/sport/boxing/boxing` at 390px on
2026-09-08 (banked: `artifacts-live-107/boxing-BEFORE-390-s2350.png`), the
Tournament Winners rail, between a fully priced card and a partly priced one:

    WBC FLYWEIGHT TITLE ON JANUARY 1, 2027
      #1  Galal Yafai              —
      #2  Rene Calixto Bibiano     —
      #3  Ndabezinhle Phiri        —
      #4  Francisco Rodriguez Jr.  —
      #5  Tobias Reyes             —
      #6  Yankiel Rivera           —
                            +13 more

Six names, six em-dashes, and a `+13 more` promising thirteen more of them, on a
product whose whole promise is the number. The `—` itself is right — #3617(b)
forbids inventing `Lost` for a leg nobody priced. The defect is one level up:
**the card should never have been admitted**, exactly as #3964 ruled that a
section heading must not outlive its cards. Here the card outlives its numbers.

MEASURED, production `/api/leagues/boxing_boxing`, 2026-09-08 19:17Z, the eight
rows of `futures`:

    2951398  WBC Flyweight      0 of 10 returned priced (outcome_count 19)  <- this
    2951400  WBC Cruiserweight  1 of 10                                     <- stays
    2951397  WBC Welterweight   1 of 10                                     <- stays
    3126724  WBC Bantamweight   6 of 10
    2951421  WBC Middleweight  10 of 10
    2951423  WBC Heavyweight   10 of 10
    2951399  WBC Featherweight 10 of 10
    2951422  WBC Lightweight   10 of 10

Flyweight's legs are `probability: null` AND `opening_probability: null`, so it
is not a stale-price or a settlement artifact: that card has never carried a
price. Across ten leagues the same shape was published in twelve sections, and
the envelope was already confessing to it — `shown + dropped` exceeded `total`
by exactly the number of unpriced rows the payload nonetheless served (verified
three for three by live/105: nfl `more_markets` 5/5, boxing `futures` 1/1, nhl
`more_markets` 2/2).

THIS IS A WIRING FIX, NOT A NEW RULE. `is_unpriced_card` has been the shared
predicate since the hub needed it, and its docstring states the intent outright:
*a surface that RENDERS the sections must be able to drop exactly the rows this
module COUNTS as dropped.* `/api/hub/tennis` obeys it. The league route counted
its unpriced rows and served them anyway.

THE TWO DIRECTIONS, and the second is the one that costs something:

  * DROP — a card with zero priced outcomes.
  * KEEP — a card with at least ONE priced outcome (Cruiserweight: Opetaia 60%
    over five em-dashes), and a SETTLED card, which legitimately has no live
    price and whose receipts the standing "settled means settled" ruling
    requires us to show.

Backend, so it reaches every client: the iOS app decodes the same `sections`.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.routes.league_futures import _drawable_sections

NOW = datetime(2026, 9, 8, 19, 0, tzinfo=timezone.utc)


def _card(id_, *probabilities, **extra):
    """A section row shaped the way `build_league` serializes one."""
    row = {
        "id": id_,
        "name": f"market-{id_}",
        "top_outcomes": [{"probability": p} for p in probabilities],
    }
    row.update(extra)
    return row


# The production specimen, reduced to the shape that decides it. Ten returned
# legs, every one priceless — `outcome_count` 19 is irrelevant to the predicate
# and is left off deliberately, so the test cannot pass for the wrong reason.
FLYWEIGHT = _card(2951398, *([None] * 10))
CRUISERWEIGHT = _card(2951400, 0.60, *([None] * 9))
WELTERWEIGHT = _card(2951397, 0.93, *([None] * 9))
HEAVYWEIGHT = _card(2951423, *([0.5] * 10))


class TestTheCardComesOff:
    def test_the_flyweight_card_is_not_served(self):
        served, _, unpriced = _drawable_sections({"futures": [FLYWEIGHT]}, now=NOW)
        assert "futures" not in served, (
            "a card with no priced leg draws six names and no numbers; it is the "
            "same absence #3964 removed, wearing furniture"
        )
        assert unpriced == {"futures": 1}, "and the drop is DECLARED, never silent"

    def test_the_real_boxing_futures_section_loses_exactly_one_row(self):
        # The whole section as production served it, in order.
        served, no_outcomes, unpriced = _drawable_sections(
            {"futures": [HEAVYWEIGHT, FLYWEIGHT, CRUISERWEIGHT, WELTERWEIGHT]},
            now=NOW,
        )
        assert [m["id"] for m in served["futures"]] == [2951423, 2951400, 2951397]
        assert unpriced == {"futures": 1}
        assert no_outcomes == {}, "none of these rows is EMPTY — they are priceless"

    def test_order_is_preserved_for_the_survivors(self):
        # A filter that reorders a ranked rail is a different bug arriving with
        # the fix; the rail's sort was decided long before this clause.
        served, _, _ = _drawable_sections(
            {"futures": [HEAVYWEIGHT, FLYWEIGHT, CRUISERWEIGHT]}, now=NOW
        )
        assert [m["id"] for m in served["futures"]] == [2951423, 2951400]


class TestTheDirectionThatCostsSomething:
    """Retention. A remedy that also deletes the priced cards is not a remedy."""

    @pytest.mark.parametrize(
        "card,label",
        [
            (CRUISERWEIGHT, "one price and nine em-dashes — Opetaia 60%"),
            (WELTERWEIGHT, "one price and nine em-dashes — Benn 93%"),
            (HEAVYWEIGHT, "fully priced"),
        ],
    )
    def test_one_priced_leg_is_enough(self, card, label):
        served, _, unpriced = _drawable_sections({"futures": [card]}, now=NOW)
        assert [m["id"] for m in served["futures"]] == [card["id"]], label
        assert unpriced == {}

    def test_a_zero_probability_is_a_price_not_an_absence(self):
        # `0.0` is falsy and a leg the book prices at zero is still an answer.
        # This is the classic way a "has a number?" test deletes real content.
        served, _, unpriced = _drawable_sections(
            {"futures": [_card(1, 0.0, None, None)]}, now=NOW
        )
        assert [m["id"] for m in served["futures"]] == [1]
        assert unpriced == {}

    def test_a_settled_card_keeps_its_receipts(self):
        # "Settled means settled" — heroes show winners, cards show results. A
        # finished market has no live price BY DEFINITION, and dropping it here
        # would delete the record the standing ruling requires us to show.
        # Both settled signals `is_unpriced_card` reads, tested apart.
        by_status = _card(1, None, None, status="resolved")
        by_date = _card(
            2, None, None, resolution_date=(NOW - timedelta(days=3)).isoformat()
        )
        served, _, unpriced = _drawable_sections(
            {"futures": [by_status, by_date]}, now=NOW
        )
        assert [m["id"] for m in served["futures"]] == [1, 2]
        assert unpriced == {}

    def test_a_future_resolution_date_does_not_make_a_priceless_card_settled(self):
        # The Flyweight card resolves 2027-01-01. If the settled test read the
        # date without comparing it, this ship would be a no-op on its own
        # specimen — and the test above would still pass.
        not_yet = _card(
            3, None, None, resolution_date=(NOW + timedelta(days=115)).isoformat()
        )
        served, _, unpriced = _drawable_sections({"futures": [not_yet]}, now=NOW)
        assert "futures" not in served
        assert unpriced == {"futures": 1}

    def test_a_healthy_sibling_section_survives_an_all_unpriced_one(self):
        # gotcha #42 — one item's fate must never decide another's.
        served, _, unpriced = _drawable_sections(
            {"futures": [FLYWEIGHT], "props": [HEAVYWEIGHT]}, now=NOW
        )
        assert list(served) == ["props"]
        assert unpriced == {"futures": 1}


class TestTheEnvelopeAddsUp:
    """`shown + dropped == total` — live/105's free counter, made a guard.

    It was false in twelve sections on 2026-09-08 and the excess was exactly
    this defect's population, which is what makes it the right acceptance test:
    it needs no new instrumentation and it cannot drift, because both sides are
    published.
    """

    @staticmethod
    def _counts(rows, *, census_unpriced, skipped=0, now=NOW):
        """Reproduce the route's arithmetic over one section.

        `census_unpriced` is what `resolve_entity_tier` counts — the census sees
        the UNFILTERED rows, so it is stated here rather than derived, which is
        the whole point: the two sides must agree without being the same code.
        """
        served, no_outcomes, unpriced = _drawable_sections({"s": rows}, now=now)
        total_census = len(rows)
        return {
            "total": total_census + skipped,
            "shown": total_census - no_outcomes.get("s", 0) - unpriced.get("s", 0),
            "dropped": census_unpriced + skipped,
            "served_rows": len(served.get("s", [])),
        }

    def test_the_boxing_futures_section_balances(self):
        c = self._counts(
            [HEAVYWEIGHT, FLYWEIGHT, CRUISERWEIGHT, WELTERWEIGHT],
            census_unpriced=1,
        )
        assert c == {"total": 4, "shown": 3, "dropped": 1, "served_rows": 3}
        assert c["shown"] + c["dropped"] == c["total"]

    def test_it_balances_with_empty_rows_and_a_price_skip_in_the_same_section(self):
        # All three exclusion reasons at once, which is the shape that broke it:
        # `matches` on boxing had empties, `more_markets` on the NFL had both.
        rows = [HEAVYWEIGHT, FLYWEIGHT, _card(9)]
        c = self._counts(rows, census_unpriced=2, skipped=4)
        assert c == {"total": 7, "shown": 1, "dropped": 6, "served_rows": 1}
        assert c["shown"] + c["dropped"] == c["total"]

    def test_a_section_that_lost_nothing_balances(self):
        c = self._counts([HEAVYWEIGHT, CRUISERWEIGHT], census_unpriced=0)
        assert c["shown"] + c["dropped"] == c["total"] == 2

    def test_the_one_shape_that_still_under_claims_and_which_way_it_leans(self):
        # HONEST LIMIT, stated rather than hidden. A row that is BOTH settled and
        # empty is dropped here (it draws nothing) but the census does not count
        # it as `unpriced` (settled is tested first, and settled is never
        # unpriced). So the identity is off by one for that row — and the lean is
        # SHOWN LOW, i.e. we under-claim. That is the safe direction and it is
        # not the defect #3980 filed, which was claiming rows we did not serve.
        # Nothing on production had this shape on 2026-09-08; the guard above
        # would go red if that changed, and this test says which way to read it.
        c = self._counts([HEAVYWEIGHT, _card(9, status="resolved")], census_unpriced=0)
        assert c["served_rows"] == 1
        assert c["shown"] + c["dropped"] < c["total"], "under-claims, never over"
