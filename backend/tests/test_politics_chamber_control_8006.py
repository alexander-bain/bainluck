"""#8006 — the SENATE CONTROL card must quote a chamber-control market.

On 2026-09-22 `/politics` printed `SENATE CONTROL 10% R vs 90% D`. The number
came from Polymarket `59395529`, *"Republicans favored to win the Senate on Nate
Silver's Bulletin by...?"* — five legs (`Yes`, `No`, and three dates),
`mutually_exclusive = false` — a question about when a newsletter would rate
Republicans as favored. Kalshi `CONTROLS-2026` sat in the same congressional
pool saying 60.5% D.

Two independent faults, so two sets of assertions:

* the SELECTOR matched on bare containment (`republican.*senate`), which admits
  any sentence naming a party and the chamber and matched **neither** genuine
  control market, both phrased "which party will win …";
* the EXTRACTOR mined a `Yes`/`No` pair out of a five-leg non-exclusive ladder.

🔴 THE CONTROL IS THE DESIGN. Every specimen below is a real open row measured
from production, and the refusals are the point — in particular the five
`Which party will win the <State> State Senate in 2026?` markets, which are
mutually exclusive, two-outcome AND party-named, so they clear every structural
gate and are caught only by the name rule. A version of this fix without
`_names_a_state` passes if you only assert the positives.
"""

from types import SimpleNamespace

import pytest

from app.routes.politics import (
    _HOUSE_CONTROL_RE,
    _SENATE_CONTROL_RE,
    _extract_control_probs,
    _find_chamber_control,
)


def _mk(market_id, name, outcomes, *, source="kalshi", mutually_exclusive=True):
    """A market shaped the way the selector reads one."""
    return SimpleNamespace(
        id=market_id,
        name=name,
        source=source,
        mutually_exclusive=mutually_exclusive,
        outcomes=[
            SimpleNamespace(name=n, current_probability=p) for n, p in outcomes
        ],
    )


# --- the real rows, as production held them 2026-09-22 ---------------------

def _senate_control_kalshi():
    return _mk(108620, "Which party will win the U.S. Senate?",
               [("Democratic Party", 0.605), ("Republican Party", 0.395)])


def _senate_control_poly():
    # Polymarket pads a field market with `Party A`..`Party F` placeholders that
    # carry no price; `clean_outcomes` strips those, `Other` survives it.
    return _mk(112902, "Which party will win the Senate in 2026?",
               [("Democratic Party", 0.645), ("Republican Party", 0.355),
                ("Other", None), ("Party A", None), ("Party B", None),
                ("Party C", None), ("Party D", None), ("Party E", None),
                ("Party F", None)],
               source="polymarket")


def _house_control_kalshi():
    return _mk(108621, "Which party will win the U.S. House?",
               [("Democratic Party", 0.9075), ("Republican Party", 0.0945)])


def _nate_silver():
    """The row that was served as SENATE CONTROL. The whole reason for this file."""
    return _mk(59395529,
               "Republicans favored to win the Senate on Nate Silver's Bulletin by...?",
               [("No", 0.895), ("September 30", 0.280), ("October 31", 0.180),
                ("Yes", 0.105), ("September 15", 0.011)],
               source="polymarket", mutually_exclusive=False)


def _core_four():
    """#6778's payload named this one — also not a control market."""
    return _mk(114419, 'Will Democrats win all "core four" senate races?',
               [("Yes", 0.415)], source="polymarket", mutually_exclusive=False)


_STATE_SENATES = [
    _mk(60709604, "Which party will win the Arizona State Senate in 2026?",
        [("Republican Party", 0.83), ("Democratic Party", 0.17)], source="polymarket"),
    _mk(60709605, "Which party will win the Texas State Senate in 2026?",
        [("Republican Party", 0.9405), ("Democratic Party", 0.033)], source="polymarket"),
    _mk(60709606, "Which party will win the Wisconsin State Senate in 2026?",
        [("Republican Party", 0.60), ("Democratic Party", 0.40)], source="polymarket"),
    _mk(60709607, "Which party will win the Minnesota State Senate in 2026?",
        [("Democratic Party", 0.55), ("Republican Party", 0.45)], source="polymarket"),
    _mk(60709608, "Which party will win the Maine State Senate in 2026?",
        [("Democratic Party", 0.70), ("Republican Party", 0.30)], source="polymarket"),
]

def _favorite_on_a_date():
    """The row that makes `mutually_exclusive` load-bearing.

    "House control favorite on November 2?" is the Nate Silver error in
    miniature: not *who holds the chamber* but *who is the favourite on a given
    date*. It is party-named, two-legged and sums to exactly 100, so it clears
    the duel gate — and being an exact complement it would out-rank the real
    market (`108621` sums to 100.2) and print 97% D. `mutually_exclusive = false`
    is the only signal that separates them.
    """
    return _mk(61876973, "House control favorite on November 2?",
               [("Democratic Party", 0.9685), ("Republican Party", 0.0315)],
               source="polymarket", mutually_exclusive=False)


_OTHER_REFUSALS = [
    _favorite_on_a_date(),
    # Matched `republican.*senate` / `democrat.*senate` under the old rule.
    _mk(109795, "North Carolina Republican Senate nominee?",
        [("Michael Whatley", 0.86), ("Don Brown", 0.05), ("Other", 0.09)]),
    _mk(109796, "North Carolina Democratic Senate nominee?",
        [("Roy Cooper", 0.95), ("Other", 0.05)]),
    _mk(113851, "Republican Senate seats after the 2026 midterm elections?",
        [("50", 0.2), ("51", 0.3), ("52", 0.5)], source="polymarket"),
    _mk(114102, "Republicans win Trifecta with Senate Supermajority in midterms?",
        [("Yes", 0.02)], source="polymarket", mutually_exclusive=False),
    # Matches `senate majority` but is a person market, not a party duel.
    _mk(6804934, "Next Senate Majority Leader?",
        [("John Thune", 0.55), ("Chuck Schumer", 0.2), ("Other", 0.25)],
        source="polymarket"),
    _mk(59165086, "120th Congress: Who will be Senate Majority Leader?",
        [("John Thune", 0.5), ("Chuck Schumer", 0.3), ("Other", 0.2)]),
    # `mutually_exclusive = false` date/besides questions.
    _mk(59693655, "When will AP call the 2026 U.S. Senate majority?",
        [("Nov 4", 0.4), ("Nov 5", 0.3), ("Nov 6", 0.3)], mutually_exclusive=False),
    _mk(108677, "Will Republicans lose the House majority before the midterms?",
        [("Yes", 0.05)], mutually_exclusive=False),
]


class TestTheServedSpecimenIsRefused:
    """The exact row that printed `10% R vs 90% D`."""

    def test_nate_silver_market_yields_no_control_probabilities(self):
        assert _extract_control_probs(_nate_silver()) is None

    def test_nate_silver_market_cannot_become_the_senate_card(self):
        # It still READS like a senate sentence to a human, and that is fine —
        # what must not happen is it reaching the card.
        control = _find_chamber_control([_nate_silver()])
        assert control["senate"] is None

    def test_the_old_containment_arm_is_gone(self):
        # The regression this file exists to stop: a bare party+chamber mention.
        assert not _SENATE_CONTROL_RE.search(
            "Republicans favored to win the Senate on Nate Silver's Bulletin by...?"
        )

    def test_6778s_payload_market_is_also_refused(self):
        assert _extract_control_probs(_core_four()) is None


class TestTheRealControlMarketsAreSelected:
    """The half the old regex could never match."""

    def test_kalshi_senate_control_matches_and_extracts(self):
        probs = _extract_control_probs(_senate_control_kalshi())
        assert probs == {"gop": 39.5, "dem": 60.5,
                         "market_id": 108620, "source": "kalshi"}

    def test_polymarket_senate_control_survives_its_placeholder_legs(self):
        probs = _extract_control_probs(_senate_control_poly())
        assert probs is not None
        assert (probs["gop"], probs["dem"]) == (35.5, 64.5)

    def test_house_control_is_found_too(self):
        assert _HOUSE_CONTROL_RE.search("Which party will win the U.S. House?")
        probs = _extract_control_probs(_house_control_kalshi())
        assert probs is not None
        assert probs["dem"] == 90.8


class TestSelectionOverTheRealPool:
    """End to end, over the population the route actually iterates."""

    def test_the_card_quotes_the_control_market_not_the_newsletter(self):
        pool = [_nate_silver(), _core_four(), _senate_control_poly(),
                _senate_control_kalshi(), *_STATE_SENATES, *_OTHER_REFUSALS]
        senate = _find_chamber_control(pool)["senate"]
        assert senate is not None
        assert senate["market_id"] == 108620
        # The defect, stated as a number: the page said 90% D against ~60%.
        assert senate["dem"] == 60.5
        assert senate["gop"] == 39.5

    def test_selection_does_not_depend_on_pool_order(self):
        """The old loop took the first regex hit, so ordering WAS the answer."""
        pool = [_nate_silver(), _senate_control_poly(), _senate_control_kalshi(),
                *_STATE_SENATES]
        picks = {
            _find_chamber_control(list(reversed(pool)))["senate"]["market_id"],
            _find_chamber_control(pool)["senate"]["market_id"],
            _find_chamber_control(pool[2:] + pool[:2])["senate"]["market_id"],
        }
        assert picks == {108620}

    @pytest.mark.parametrize(
        "market", _STATE_SENATES, ids=lambda m: str(m.id))
    def test_a_state_senate_race_never_answers_who_holds_the_us_senate(self, market):
        """These clear EVERY structural gate. Only the name rule stops them."""
        assert _extract_control_probs(market) is not None, (
            "precondition: this row is structurally a valid party duel, which is "
            "why the name rule has to be the thing that refuses it"
        )
        assert _find_chamber_control([market])["senate"] is None

    @pytest.mark.parametrize(
        "market", _OTHER_REFUSALS, ids=lambda m: str(m.id))
    def test_rows_the_old_rule_admitted_are_refused(self, market):
        control = _find_chamber_control([market])
        assert control["senate"] is None
        assert control["house"] is None

    def test_a_favourite_on_a_date_never_outranks_the_real_house_market(self):
        """Exclusivity is load-bearing, and this is the row that proves it.

        Both are party duels; the impostor is the EXACT complement, so ranking
        alone prefers it. Without the `mutually_exclusive` gate the House card
        reads 97% D off a "who is favourite on November 2" question instead of
        91% D off "which party will win the U.S. House".
        """
        pool = [_favorite_on_a_date(), _house_control_kalshi()]
        house = _find_chamber_control(pool)["house"]
        assert house is not None
        assert house["market_id"] == 108621
        assert house["dem"] == 90.8

    def test_an_empty_pool_yields_no_card_rather_than_a_guess(self):
        assert _find_chamber_control([]) == {"senate": None, "house": None}
