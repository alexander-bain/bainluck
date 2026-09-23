"""#8237, the residual — the page withholds on a SECOND term and the card had one.

#8237's first cut gave the card `normalize_display_probs`'s ``field_complete``
clause and repaired 10 of its 13 pre-registered boards. Five stayed split on the
served feed of 2026-09-23 17:00Z, and they are not an arithmetic error: they are a
term the card never asked.

`futures.py` composes the page's answer as a UNION of two sets::

    _withheld_ids = await _withheld_price_outcome_ids(db, market)   # the 5 arms
    if status == "open":
        _withheld_ids |= stale_observation_keys(...)                # #7537
    _field_complete = not _withheld_ids

The card's gate read the arms only.

🔴 WHY THE ARMS CANNOT ANSWER FOR THESE FIVE, measured on production 2026-09-23
17:20Z — the page's `prices_withheld` beside the STORED rows behind it:

    market    board                  legs  storedNULL  page_wh   oldest stamp
    128718    MLS Cup Winner 2026      31           1        1   2026-05-12
    7435308   MLB AL Comeback POY      11           1        1   2026-05-12
    9962834   NCAA FB 2027 Champion   109          93       67   2026-05-12
    12764689  DWTS S35 Winner          53          37       37   2026-05-12
    16634605  Next PM of Romania       49          13        1   2026-05-12
    ---- the two boards the first cut DID repair, as the contrast arm ----
    52755536  2031 Championship        26           0        7   2026-09-23
    2417016   Pro Baseball Matchup    225           0      100   2026-09-22

Every withheld leg on the five is stored-NULL; every one on the two repaired
boards carries a real price. That is the mechanism, not a coincidence:
`is_empty_book_midpoint` opens ``if probability is None: return False``, and a
price that does not exist cannot be refuted by a book either — so all five arms
are structurally SILENT on a leg that was never priced. The five boards carry a
four-month spread between oldest and newest stamp, so `stale_observation_keys`
names those legs and the page withholds on that term ALONE.

🪤 THE DIVISOR IDENTITY IS WHAT IDENTIFIED IT, BEFORE ANY CODE WAS READ. On all
five, ``implied_div == priced_sum`` to four decimals. A gate that fired and
computed a wrong divisor would not land on the priced sum exactly; one that was
never asked divides by precisely the legs that carry a number.

Rows below are market 128718 as `db-query` returned it at 2026-09-23 17:20Z, and
the split they produce is the one `/api/feed` served: Vancouver 0.1998 on the card
against 0.2115 on `/api/futures/128718`.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.feed import (
    _drop_stale_observation_legs,
    _feed_display_scale,
    _field_has_withheld_legs,
    _resolve_stale_ids,
)

FRESH = datetime(2026, 9, 23, 16, 29, 14, tzinfo=timezone.utc)
#: `Other`'s own stamp on production — four months behind its board.
FOSSIL = datetime(2026, 5, 12, 16, 16, 38, tzinfo=timezone.utc)

#: (id, name, stored probability, stamp). Every priced leg on this board shares
#: one stamp because a poll pass writes every row it touches with one `now`.
MLS_CUP: tuple[tuple[int, str, float | None, datetime], ...] = (
    (1707557, "Vancouver Whitecaps FC", 0.2115, FRESH),
    (1707565, "Nashville SC", 0.1810, FRESH),
    (1707556, "Inter Miami CF", 0.1700, FRESH),
    (1707558, "Los Angeles FC", 0.0750, FRESH),
    (1707577, "Chicago Fire FC", 0.0615, FRESH),
    (1707573, "St. Louis City SC", 0.0585, FRESH),
    (1707561, "Philadelphia Union", 0.0545, FRESH),
    (1707580, "Houston Dynamo FC", 0.0455, FRESH),
    (1707579, "FC Dallas", 0.0450, FRESH),
    (1707583, "Charlotte FC", 0.0315, FRESH),
    (1707581, "New England Revolution", 0.0285, FRESH),
    (1707571, "San Jose Earthquakes", 0.0195, FRESH),
    (1707570, "Orlando City SC", 0.0180, FRESH),
    (1707560, "New York City FC", 0.0115, FRESH),
    (1707563, "FC Cincinnati", 0.0075, FRESH),
    (1707566, "Seattle Sounders FC", 0.0060, FRESH),
    (1707578, "Colorado Rapids", 0.0060, FRESH),
    (1707569, "Minnesota United FC", 0.0055, FRESH),
    (1707562, "San Diego FC", 0.0040, FRESH),
    (1707585, "Portland Timbers", 0.0040, FRESH),
    (1707567, "New York Red Bulls", 0.0035, FRESH),
    (1707559, "LA Galaxy", 0.0030, FRESH),
    (1707582, "Real Salt Lake", 0.0025, FRESH),
    (1707568, "D.C. United", 0.0015, FRESH),
    (1707564, "Columbus Crew", 0.0010, FRESH),
    (1707572, "Sporting Kansas City", 0.0005, FRESH),
    (1707574, "Toronto FC", 0.0005, FRESH),
    (1707575, "Atlanta United FC", 0.0005, FRESH),
    (1707576, "Austin FC", 0.0005, FRESH),
    (1707584, "CF Montréal", 0.0005, FRESH),
    # The one the page refuses. Never priced, and four months behind the rest.
    (69775226, "Other", None, FOSSIL),
)

PRICED_SUM = 1.0585  # the thirty that carry a number
PAGE_VANCOUVER = 0.2115  # what `/api/futures/128718` prints for the leader
CARD_VANCOUVER = 0.1998  # what the card printed: 0.2115 / 1.0585
FOSSIL_ID = 69775226


def _legs(rows=MLS_CUP):
    return [
        SimpleNamespace(id=i, name=n, current_probability=p, last_updated=t)
        for i, n, p, t in rows
    ]


def _market(status="open", withheld=()):
    """The board as the feed carries it.

    ``withheld=()`` is PRODUCTION'S OWN VALUE for this market, not a convenience
    default: `withheld_price_outcome_ids_for_markets` stores an empty set for a
    board its arms refuse nothing on, and that is what this board carries.
    """
    m = SimpleNamespace(id=128718, name="MLS Cup Winner 2026")
    m.status = status
    if withheld is not None:
        m.__dict__["withheld_outcome_ids"] = list(withheld)
    return m


class TestTheFixtureCanActuallyFail:
    """Anti-vacuity. Each assertion below is a fact the guards depend on."""

    def test_the_priced_legs_land_inside_the_squeeze_band(self):
        """Outside the band the gate is unobservable and every test would pass."""
        assert sum(r[2] for r in MLS_CUP if r[2] is not None) == pytest.approx(
            PRICED_SUM, abs=1e-9
        )
        assert 1.05 < PRICED_SUM <= 1.60
        # Complete, this field IS divided — that is the behaviour under test.
        assert _feed_display_scale(
            _legs(), mutually_exclusive=True, field_complete=True
        ) == pytest.approx(PRICED_SUM, abs=1e-4)

    def test_and_that_divisor_is_the_split_a_reader_saw(self):
        scale = _feed_display_scale(
            _legs(), mutually_exclusive=True, field_complete=True
        )
        assert PAGE_VANCOUVER / scale == pytest.approx(CARD_VANCOUVER, abs=5e-4)

    def test_the_fossil_really_is_stale_and_the_rest_really_are_not(self):
        """If the stamps did not straddle the lag bound there is nothing to catch."""
        assert FRESH - FOSSIL > timedelta(days=7)
        stale = _resolve_stale_ids(_market(), _legs())
        assert stale == {FOSSIL_ID}

    def test_the_arms_are_silent_on_this_board_which_is_the_whole_residual(self):
        """`withheld_outcome_ids` is EMPTY here — measured, not assumed.

        Every leg the page refuses on this board is stored-NULL, and no arm can
        reach a leg that has no price. So the arms term contributes nothing and
        only the stale term can answer.
        """
        assert _market().__dict__["withheld_outcome_ids"] == []
        assert [r for r in MLS_CUP if r[2] is None] == [
            (FOSSIL_ID, "Other", None, FOSSIL)
        ]


class TestTheGateReadsBothTermsOfThePagesUnion:
    def test_a_stale_leg_makes_the_field_incomplete(self):
        """The defect: arms empty, page withholds, card used to read complete."""
        assert _field_has_withheld_legs(_market(), _legs()) is True

    def test_so_the_card_stops_dividing_and_agrees_with_its_own_page(self):
        incomplete = _field_has_withheld_legs(_market(), _legs())
        scale = _feed_display_scale(
            _legs(), mutually_exclusive=True, field_complete=not incomplete
        )
        assert scale == 1.0
        assert PAGE_VANCOUVER / scale == pytest.approx(PAGE_VANCOUVER, abs=1e-9)

    def test_the_arms_term_still_answers_on_its_own(self):
        """#8237's first cut must not be traded away for its own residual."""
        fresh_only = [r for r in MLS_CUP if r[2] is not None]
        assert (
            _field_has_withheld_legs(
                _market(withheld=[1707557]), _legs(fresh_only)
            )
            is True
        )

    def test_neither_term_means_complete(self):
        """THE CONTROL. Without this the fix could be a blanket `always raw`.

        Same board, same divisor, fossil removed: the gate must answer False and
        the card must go on dividing. A widening that took this row too would be
        invisible to every other assertion in the file.
        """
        fresh_only = [r for r in MLS_CUP if r[2] is not None]
        assert _field_has_withheld_legs(_market(), _legs(fresh_only)) is False
        assert _feed_display_scale(
            _legs(fresh_only), mutually_exclusive=True, field_complete=True
        ) == pytest.approx(PRICED_SUM, abs=1e-4)

    def test_a_settled_board_is_a_result_and_keeps_every_leg(self):
        assert _field_has_withheld_legs(_market(status="settled"), _legs()) is False

    def test_the_helper_itself_honours_the_open_bound(self):
        """Pinned on the HELPER, not only through its callers.

        Both consumers test `status` before they reach `_resolve_stale_ids`, so
        the bound inside it is a line no other assertion in this file can fail
        on — deleting it left all 61 green. It is not decoration: the call sites
        invoke the helper DIRECTLY, ahead of either status check, and the page
        adds its own stale term under exactly this condition
        (`futures.py`: ``if status == "open"``). A settled board must therefore
        answer with the empty set here, at the source.
        """
        assert _resolve_stale_ids(_market(status="settled"), _legs()) == set()
        assert _resolve_stale_ids(_market(status="closed"), _legs()) == set()
        # ...and the same board, open, is not vacuously empty.
        assert _resolve_stale_ids(_market(), _legs()) == {FOSSIL_ID}

    def test_a_carrier_with_no_status_cannot_crash_the_serializer(self):
        assert _field_has_withheld_legs(object(), _legs()) is False

    def test_a_stampless_board_fails_open(self):
        """A rehydrated leg carrying neither stamp resolves to None everywhere, so
        the predicate returns the empty set and the card keeps its numbers."""
        legs = [
            SimpleNamespace(id=i, name=n, current_probability=p)
            for i, n, p, _t in MLS_CUP
        ]
        assert _field_has_withheld_legs(_market(), legs) is False


class TestTheStaleSetIsComputedBeforeTheDropThatConsumesIt:
    """The ordering rule, and the only arm that can see it is a PRICED fossil.

    `_drop_stale_observation_legs` removes stale legs that print a price. A gate
    that derived the stale set from the POST-drop list would therefore answer
    False on exactly those boards — the "asked after the drop" shape CERT-3330
    blocked on #7632's first cut, re-entering through the other term.

    128718's own fossil is unpriced, so it survives the drop and CANNOT
    discriminate here. This board is that board with two priced legs moved back
    to the fossil's stamp — the production shape is #7537's market 3971707
    (*Super League Rugby Champion*), eleven of whose fourteen legs were last
    written at one identical microsecond a fortnight before the other three.
    """

    @staticmethod
    def _priced_fossil_board():
        rows = []
        for i, n, p, t in MLS_CUP:
            if i in (1707565, 1707556):  # Nashville, Inter Miami — priced fossils
                rows.append((i, n, p, FOSSIL))
            else:
                rows.append((i, n, p, t))
        return tuple(rows)

    def test_the_drop_really_does_remove_those_legs(self):
        """Anti-vacuity for the ordering guard below."""
        board = self._priced_fossil_board()
        kept = {o.id for o in _drop_stale_observation_legs(_market(), _legs(board))}
        assert 1707565 not in kept and 1707556 not in kept
        # The unpriced fossil is never dropped — a blank row prints no price.
        assert FOSSIL_ID in kept

    def test_asked_before_the_drop_the_gate_sees_them(self):
        board = self._priced_fossil_board()
        pre = _legs(board)
        stale = _resolve_stale_ids(_market(), pre)
        assert {1707565, 1707556} <= stale
        assert _field_has_withheld_legs(_market(), pre, stale_ids=stale) is True

    def test_and_the_drop_consumes_the_same_set_the_gate_was_given(self):
        """One rule, one evaluation — the drop must not re-derive its own."""
        board = self._priced_fossil_board()
        pre = _legs(board)
        stale = _resolve_stale_ids(_market(), pre)
        shared = {o.id for o in _drop_stale_observation_legs(_market(), pre, stale)}
        rederived = {o.id for o in _drop_stale_observation_legs(_market(), pre)}
        assert shared == rederived

    def test_the_call_sites_compute_it_before_they_drop(self):
        """The ordering is a property of the WIRING, so it is read off the wiring.

        A gate that is correct in isolation and asked after the drop ships inert;
        `TestTheGateIsAskedBeforeTheDrop` makes the same argument for the withheld
        term one file over.
        """
        for func_name in ("_score_futures", "_score_sports_mode_futures"):
            from app.routes import feed as feed_module

            source = inspect.getsource(getattr(feed_module, func_name))
            derive = source.index("_resolve_stale_ids(market, sorted_outcomes)")
            drop = source.index("_drop_stale_observation_legs(")
            gate = source.index("_field_has_withheld_legs(")
            assert derive < drop, f"{func_name}: stale set derived after the drop"
            assert derive < gate, f"{func_name}: gate asked before the set exists"
