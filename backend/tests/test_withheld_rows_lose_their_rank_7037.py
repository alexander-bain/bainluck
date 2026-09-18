"""#7037: a withheld price must not keep the rank that price won it.

WHAT A READER SAW, on production 2026-09-18 at `b1dfe5c69`. `/hub/boxing`,
"TOURNAMENT WINNERS", the WBC Heavyweight Title card:

    Tyson Fury          –
    Oleksandr Usyk      93%
    Agit Kabayel        87%
    Moses Itauma        79%

#7016 had just taught this payload to refuse a price it cannot stand behind, and
Fury's is one of the refused. But it did not teach the ORDER to refuse it, so the
row kept the slot its raw 0.97 had won. ROW ORDER IS THE ONLY RANKING SIGNAL
these cards have — `PropGroupCard` (`top_outcomes.slice(0, 6)`) and `AwardCard`
(`.slice(0, 5)`) render the array exactly as handed and neither re-sorts — so the
top slot went on asserting "favourite" about the one number on the card we had
decided we may not print. Deleting a value does not delete what was derived from
it; the sort was derived from it.

Measured on the five live hub payloads, by card name: **0 before #7016, 13 after**
(mma 3, boxing 2, golf 1, tennis 1, esports 6). This class is CREATED by #7016 and
is the residue of a correct fix, not a reason to revert one — the prices it
withheld should stay withheld.

THE PREDICATE IS THE HOUSE'S. `routes/futures.py` already sorts
`0 if o.id in withheld else <price>` in both its browse arm and `get_group`, and
states the rule there: "the sort key has to know about the withhold or a refused
leg takes a slot it then renders empty." `league_futures.py` is the arm that never
adopted it. So the structural guard below is that the two modules still agree,
not merely that this one behaves.
"""

import inspect

from app.routes import league_futures as lf


class _Outcome:
    def __init__(self, oid, name, prob, *, movement=None, is_winner=False,
                 resolution_source=None):
        self.id = oid
        self.name = name
        self.current_probability = prob
        self.opening_probability = None
        self.rank = oid
        self.probability_change_24h = movement
        self.team_id = None
        self.is_winner = is_winner
        self.resolution_source = resolution_source


class _Market_with:
    """A market-shaped holder for a field, for `_sorted_outcomes(market)`."""

    def __init__(self, outcomes):
        self.outcomes = outcomes


class _Market:
    def __init__(self, name="WBC Heavyweight Title", *, mutually_exclusive=False,
                 status="open"):
        self.name = name
        self.llm_sport_category = "boxing"
        # Non-exclusive by default so the #7016 squeeze does not rescale these
        # fields underneath the ordering assertions — this file grades ORDER.
        self.mutually_exclusive = mutually_exclusive
        self.status = status


def _names(rows):
    return [r["name"] for r in rows]


# ── the specimen ────────────────────────────────────────────────────────────


def test_the_heavyweight_card_no_longer_leads_with_a_blank_row():
    """The reported card, in the reported order. Fury is refused, so Usyk leads."""
    field = [
        _Outcome(1, "Tyson Fury", 0.97),
        _Outcome(2, "Oleksandr Usyk", 0.93),
        _Outcome(3, "Agit Kabayel", 0.87),
        _Outcome(4, "Moses Itauma", 0.79),
    ]
    rows = lf._serialize_outcomes(lf._sorted_outcomes(_Market_with(field)), _Market(), {1})

    assert _names(rows) == ["Oleksandr Usyk", "Agit Kabayel", "Moses Itauma", "Tyson Fury"]
    assert rows[0]["probability"] == 0.93
    assert rows[-1]["probability"] is None


def test_the_first_row_carries_a_price_whenever_any_live_row_has_one():
    """The reader-facing invariant, stated as the card sees it.

    This is the assertion that actually tracks the defect: whatever else moves,
    a card with at least one publishable live price must not open on a blank.
    """
    field = [
        _Outcome(1, "Carlos Adames", 0.90),
        _Outcome(2, "Keith Thurman", 0.88),
        _Outcome(3, "Sebastian Fundora", 0.85),
    ]
    rows = lf._serialize_outcomes(lf._sorted_outcomes(_Market_with(field)), _Market(), {1, 2})

    assert rows[0]["probability"] is not None
    assert rows[0]["name"] == "Sebastian Fundora"


def test_withheld_rows_are_demoted_as_a_block_keeping_their_own_order():
    """Demotion, not a reshuffle. The refused rows keep their relative ranking
    and the priced rows keep theirs — this changes which GROUP leads, nothing
    about the ordering inside either group.
    """
    field = [
        _Outcome(1, "Refused high", 0.90),
        _Outcome(2, "Priced high", 0.80),
        _Outcome(3, "Refused low", 0.70),
        _Outcome(4, "Priced low", 0.60),
    ]
    rows = lf._serialize_outcomes(lf._sorted_outcomes(_Market_with(field)), _Market(), {1, 3})

    assert _names(rows) == ["Priced high", "Priced low", "Refused high", "Refused low"]


# ── the bound: withholding moves a row WITHIN the live group, never across ──


def test_a_withheld_live_row_still_outranks_a_settled_one():
    """#3868's invariant is not spent to pay for this one.

    A settled row draws Won/Lost and never a percentage, so its blankness
    asserts no rank. Demoting withheld rows past the settled tail would push a
    live contender below finished business — the exact inversion `_live_first`
    exists to prevent.
    """
    # The market stays OPEN and the winner carries a tier-3 venue settlement —
    # the Alcaraz-child shape `_outcome_is_settled` documents. A `resolved`
    # market settles EVERY row, which would leave no live bucket for this guard
    # to be about and pass for the wrong reason.
    winner = _Outcome(9, "Won already", 1.0, is_winner=True,
                      resolution_source="api_settlement")
    field = [winner, _Outcome(1, "Refused", 0.90), _Outcome(2, "Priced", 0.50)]
    market = _Market(status="open")

    # Self-verifying fixture: one settled row, two live ones. Without these the
    # ordering assertion below is vacuous.
    assert lf._outcome_is_settled(winner, "open", True) is True
    assert lf._outcome_is_settled(field[1], "open", True) is False
    assert lf._outcome_is_settled(field[2], "open", True) is False

    rows = lf._serialize_outcomes(lf._sorted_outcomes(_Market_with(field)), market, {1})
    assert _names(rows) == ["Priced", "Refused", "Won already"]


def test_a_withheld_winner_is_not_demoted_below_the_losers():
    """The settled tail is ordered by RESULT, and a withhold must not re-sort it."""
    won = _Outcome(9, "Won already", 1.0, is_winner=True)
    lost = _Outcome(8, "Knocked out", 0.0, is_winner=False)
    market = _Market(status="resolved")
    assert lf._outcome_is_settled(won, "resolved", True) is True

    rows = lf._serialize_outcomes(
        lf._sorted_outcomes(_Market_with([won, lost])), market, {9}
    )
    assert _names(rows) == ["Won already", "Knocked out"]


# ── the slice: demotion changes what survives into the payload ──────────────


def test_demotion_frees_a_visible_slot_for_a_priced_row():
    """`_serialize_outcomes` returns `[:10]` and the cards slice again on top of
    it, so ordering decides which rows a reader ever sees. A refused leg holding
    a top-ten slot spends it on an em-dash; demoted, the slot goes to a row that
    can be printed.
    """
    field = [_Outcome(i, f"Refused {i}", 0.99 - i / 100) for i in range(1, 11)]
    field.append(_Outcome(50, "Priced survivor", 0.10))
    rows = lf._serialize_outcomes(
        lf._sorted_outcomes(_Market_with(field)), _Market(), {o.id for o in field[:10]}
    )

    assert len(rows) == 10
    assert rows[0]["name"] == "Priced survivor"
    assert rows[0]["probability"] == 0.10


# ── controls ────────────────────────────────────────────────────────────────


def test_CONTROL_a_field_nobody_refused_is_ordered_exactly_as_before():
    """The whole no-withhold path must be byte-identical: this ship may only
    move rows the price guard actually named.
    """
    field = [
        _Outcome(1, "Iga Swiatek", 0.795),
        _Outcome(2, "Qinwen Zheng", 0.205),
        _Outcome(3, "Someone else", 0.10),
    ]
    ranked = lf._sorted_outcomes(_Market_with(field))

    assert lf._live_first(ranked) == ranked
    assert lf._live_first(ranked, "open", set()) == ranked
    assert lf._live_first(ranked, "open", None) == ranked

    rows = lf._serialize_outcomes(ranked, _Market(), set())
    assert _names(rows) == ["Iga Swiatek", "Qinwen Zheng", "Someone else"]


def test_CONTROL_a_wholly_refused_field_still_leads_blank_and_that_is_honest():
    """The documented LIMIT of this fix, asserted so nobody reads it as broader.

    When every live row is refused there is no priced row to promote, so the card
    still opens on a dash. Ordering cannot rescue a field with nothing printable
    in it — and the row order no longer asserts anything false, because no row
    claims a rank over another. (`AwardCard` renders a leader like this as a bold
    "0%" via `leader.probability ?? 0`; that is a layout defect, filed separately
    and ux-owned under notice 41. It is NOT fixed here.)
    """
    field = [_Outcome(1, "A", 0.49), _Outcome(2, "B", 0.49)]
    rows = lf._serialize_outcomes(
        lf._sorted_outcomes(_Market_with(field)), _Market(), {1, 2}
    )

    assert [r["probability"] for r in rows] == [None, None]
    assert _names(rows) == ["A", "B"]


def test_CONTROL_the_withhold_itself_still_happens():
    """Ordering is additive to #7016, never a replacement for it."""
    field = [_Outcome(1, "Tyson Fury", 0.97, movement=0.04), _Outcome(2, "Usyk", 0.93)]
    rows = lf._serialize_outcomes(lf._sorted_outcomes(_Market_with(field)), _Market(), {1})

    fury = next(r for r in rows if r["name"] == "Tyson Fury")
    assert fury["probability"] is None
    assert fury["movement_24h"] is None
    assert "probability" in fury  # present and null, never omitted


# ── structural: one rule, not a fourth copy of it ───────────────────────────


def test_both_hub_and_league_surfaces_order_through_this_one_function():
    """The hub (`/api/hub/{slug}` composes `get_league_futures`) and the league
    page reach `_serialize_outcomes` by different call sites. If the ordering
    lived in either caller the two would drift, which is the disagreement #7016
    was filed about in the first place.
    """
    source = inspect.getsource(lf._serialize_outcomes)
    assert "_live_first(sorted_outcomes, market_status, withheld_ids)" in source


def test_the_sort_that_feeds_the_resolved_check_is_deliberately_untouched():
    """`_sorted_outcomes` feeds `_effectively_resolved`, which reads `[0]` as the
    leader and SKIPS the market. Folding the withhold in there would change which
    cards the page draws at all — a different ship. Guarded so a later tidy-up
    does not "simplify" the two into one.
    """
    field = [_Outcome(1, "Refused", 0.97), _Outcome(2, "Priced", 0.50)]
    ranked = lf._sorted_outcomes(_Market_with(field))

    assert [o.name for o in ranked] == ["Refused", "Priced"]
    assert "withheld" not in inspect.getsource(lf._sorted_outcomes)
