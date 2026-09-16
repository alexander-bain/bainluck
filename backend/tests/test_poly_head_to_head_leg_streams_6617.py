"""#6617 / #837 — the head-to-head moneyline leg streams, so an MLB hero moves live.

WHY THIS FILE EXISTS.  Q500 (``test_poly_moneyline_leg_streams_q500.py``) taught
the fast lane to address a parent row one level down, through its outcomes'
condition ids, and that closed the three-way soccer case: each outcome resolves
to its own *"Will <team> win on <date>?"* market, ``outcomes ["Yes","No"]``, and
``yes_token_of`` reads the YES token.  A TWO-WAY head-to-head does not decompose
that way, and nothing downstream noticed.

MEASURED ON PRODUCTION, 2026-09-16 20:3x-20:4xZ.  The 120 s poll was healthy —
``prediction_market_live`` ``terminal: "complete"``, no budget stops, 68-84 s of
a 240 s budget — and the Polymarket socket was streaming (``blend stamped=163``
in one minute).  And yet, of the nine live events carrying a Polymarket hero
leg, EIGHT shared one identical stamp::

    event       speaker    clob_token_ids   polymarket stamp   kalshi stamp
    Frech       61113189   yes              20:39:22.772       20:38:58.300
    Oradea      61202789   yes              20:38:58.300       -
    AC Milan    60141468   NO               20:38:58.300       20:39:24.316
    Anderlecht  60141469   NO               20:38:58.300       20:39:24.316
    Leverkusen  60141464   NO               20:38:58.300       20:39:21.755
    Blue Jays   60683993   NO               20:38:58.300       20:39:26.641

One microsecond value across eight events is one writer in one transaction: the
poll.  The only leg with an off-beat stamp was the one whose speaker carried
tokens.  The Kalshi arm of the SAME events streamed at sub-30 s throughout.

THE CAUSE, read at the venue.  Gamma answers the Blue Jays outcome condition
``0xc72411a3…`` with ``question: "Detroit Tigers vs. Toronto Blue Jays"``,
``outcomes: ["Detroit Tigers","Toronto Blue Jays"]``, ``closed: false``,
``acceptingOrders: true``, a tight book (bid 0.25 / ask 0.26) and TWO
``clobTokenIds``.  The tokens were there the whole time.  ``yes_token_of`` finds
no ``"Yes"`` and correctly refuses rather than guessing — Q489's lesson — so the
leg was never subscribed and its hero could never beat the poll.  Gamma moved
Detroit 0.255 -> 0.195 inside one poll interval while our stored value sat at
0.255.

THE CLASS, not the anecdote.  Hero-speaking markets on the live+6h slate that
carry no ``clob_token_ids``: Gamma answered 20 outcome conditions, **10 fill
through the Yes path and 10 fill only through this one** — Tigers/Blue Jays,
Dodgers/Reds, Brewers/Pirates, Athletics/Rays.  Every MLB game on the board was
in the second half.  0 were unfillable.

THE FIX is additive by construction: ``token_for_outcome`` returns
``yes_token_of``'s answer whenever it has one, so no leg that streams today can
be moved, re-attributed or lost.  It only ever fills where the answer was None.

The tests below pin, in order: the Yes path is untouched and still wins; the
fallback attributes BY NAME and never by position; it refuses every shape it
cannot prove; it is reachable through ``topup_outcome_clob_tokens`` with our own
outcome name; and the name read failing degrades to the Yes path instead of
taking the socket's token pass down.
"""

import pytest
from sqlalchemy.sql.dml import Update

from app.tasks.polymarket_token_topup import (
    OUTCOME_TOKEN_METADATA_KEY,
    token_for_outcome,
    topup_outcome_clob_tokens,
    yes_token_of,
)

# The production shape, kept verbatim so the fixture cannot drift into a
# friendlier one (Gamma, 2026-09-16 20:4xZ).
H2H_CONDITION = "0xc72411a3a7e60129778fa76f3d26b7bf979eb796a4286f9bb50630b8733c7003"
H2H_MARKET_ID = 60683993
H2H_OUTCOME_ID = 228818208
H2H_OUTCOME_NAME = "Detroit Tigers"
H2H_OUTCOMES = ["Detroit Tigers", "Toronto Blue Jays"]
DETROIT_TOKEN = (
    "96452297639560164340055571485116188333678085236988248030546780615212535478902"
)
TORONTO_TOKEN = (
    "72500779374521262264246385685996947758365349906000000000000000000000000000000"
)

# The Q500 shape, so this file can prove the old path is untouched without
# importing that file's fixtures.
YES_CONDITION = "0xfa91ccd064fb0916295a44e03077ab8632b6943af710bebaae55a85954e3f1bf"
YES_TOKEN = "37424116597795289341416204452344360730704946170353838301223818699083921393924"
NO_TOKEN = "31073709865413954176470378439830005033155647149000000000000000000000000000000"


class _FakeMarket:
    def __init__(self, condition_id, clob_token_ids, outcomes):
        self.condition_id = condition_id
        self.clob_token_ids = list(clob_token_ids)
        self.outcomes = list(outcomes)


class _FakeService:
    def __init__(self, markets):
        self._markets = markets
        self.asked: list[list[str]] = []
        self.closed = False

    async def get_markets_by_conditions(self, condition_ids, **_kw):
        self.asked.append(list(condition_ids))
        return list(self._markets)

    async def close(self):
        self.closed = True


class _NameRows:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _SessionWithNames:
    """A session that answers the outcome-name SELECT and captures writes."""

    def __init__(self, name_rows=(), *, read_raises=None):
        self.updates: list = []
        self.reads: list = []
        self._name_rows = list(name_rows)
        self._read_raises = read_raises

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            self.updates.append(stmt)
            return _NameRows([])
        self.reads.append(stmt)
        if self._read_raises:
            raise self._read_raises
        return _NameRows(self._name_rows)


# ------------------------------------ the Yes path is untouched and wins ----


class TestTheYesPathIsUnchanged:
    def test_a_yes_market_still_resolves_through_the_yes_token(self):
        """The whole safety argument in one assertion: where Q500 worked, this
        function must return Q500's answer, byte for byte."""
        market = _FakeMarket(YES_CONDITION, [YES_TOKEN, NO_TOKEN], ["Yes", "No"])
        assert token_for_outcome(market, "Wolfsberger AC") == YES_TOKEN
        assert token_for_outcome(market, "Wolfsberger AC") == yes_token_of(market)

    def test_the_yes_token_wins_even_when_the_outcome_name_also_matches(self):
        """A market naming BOTH a "Yes" and our outcome is ambiguous in
        principle.  The Yes reading is the one Q500 proved against production,
        so it takes precedence and the fallback never sees this shape."""
        market = _FakeMarket(YES_CONDITION, [YES_TOKEN, NO_TOKEN], ["Yes", "Detroit Tigers"])
        assert token_for_outcome(market, "Detroit Tigers") == YES_TOKEN

    def test_the_no_token_is_still_never_returned(self):
        """Q500's three-way trap, re-pinned here because this file adds a second
        way to reach a token and must not open a second way to reach the NO."""
        market = _FakeMarket(YES_CONDITION, [YES_TOKEN, NO_TOKEN], ["Yes", "No"])
        assert token_for_outcome(market, "No") != NO_TOKEN


# --------------------------------------- the head-to-head fallback fills ----


class TestTheHeadToHeadFallback:
    def test_the_production_specimen_now_resolves_to_a_token(self):
        """Tigers vs Blue Jays, the exact Gamma payload of 2026-09-16.  Before
        this ship the answer was None and the leg never subscribed."""
        market = _FakeMarket(H2H_CONDITION, [DETROIT_TOKEN, TORONTO_TOKEN], H2H_OUTCOMES)
        assert yes_token_of(market) is None
        assert token_for_outcome(market, H2H_OUTCOME_NAME) == DETROIT_TOKEN

    def test_the_other_contender_gets_the_other_token(self):
        """Two outcome rows, two books, and neither may take the other's.  This
        is the assertion that the fallback is an attribution and not a pick."""
        market = _FakeMarket(H2H_CONDITION, [DETROIT_TOKEN, TORONTO_TOKEN], H2H_OUTCOMES)
        assert token_for_outcome(market, "Toronto Blue Jays") == TORONTO_TOKEN

    def test_it_is_not_assumed_to_be_index_zero(self):
        """The mutant this file exists to kill.  Returning `tokens[0]` passes
        every test above — both name a leg that happens to sit at index 0 or
        pairs with one.  Reverse Gamma's order and index-0 subscribes the WRONG
        team's book, and the rendered probability becomes the opponent's: the
        Q489 inversion, rebuilt one layer down."""
        market = _FakeMarket(
            H2H_CONDITION,
            [TORONTO_TOKEN, DETROIT_TOKEN],
            ["Toronto Blue Jays", "Detroit Tigers"],
        )
        assert token_for_outcome(market, H2H_OUTCOME_NAME) == DETROIT_TOKEN

    def test_names_match_case_and_whitespace_insensitively(self):
        market = _FakeMarket(H2H_CONDITION, [DETROIT_TOKEN, TORONTO_TOKEN], H2H_OUTCOMES)
        assert token_for_outcome(market, "  detroit tigers ") == DETROIT_TOKEN


# ------------------------------------------- what it refuses, and why -------


class TestTheFallbackRefusesWhatItCannotProve:
    def test_a_name_that_is_not_on_the_market_is_refused(self):
        """Our row and Gamma's market disagreeing about who is playing is a
        matching fact, not a token fact.  Dropping the tick beats writing some
        other game's book into this leg."""
        market = _FakeMarket(H2H_CONDITION, [DETROIT_TOKEN, TORONTO_TOKEN], H2H_OUTCOMES)
        assert token_for_outcome(market, "Baltimore Orioles") is None

    def test_a_duplicated_name_is_refused_rather_than_taking_the_first(self):
        """Two outcomes with one name cannot be told apart, and picking the
        first is precisely the positional guess this module refuses."""
        market = _FakeMarket(
            H2H_CONDITION, [DETROIT_TOKEN, TORONTO_TOKEN], ["Detroit Tigers", "Detroit Tigers"]
        )
        assert token_for_outcome(market, H2H_OUTCOME_NAME) is None

    def test_a_name_beyond_the_token_list_is_refused(self):
        """Index-aligned means aligned; a ragged pair is a shape we did not
        anticipate."""
        market = _FakeMarket(H2H_CONDITION, [DETROIT_TOKEN], H2H_OUTCOMES)
        assert token_for_outcome(market, "Toronto Blue Jays") is None

    def test_no_tokens_yields_none(self):
        market = _FakeMarket(H2H_CONDITION, [], H2H_OUTCOMES)
        assert token_for_outcome(market, H2H_OUTCOME_NAME) is None

    @pytest.mark.parametrize("name", [None, "", "   "])
    def test_a_missing_outcome_name_falls_through_to_the_yes_path(self, name):
        """No name is not an error — it is simply the Yes path, which is where
        every caller stood before this ship."""
        h2h = _FakeMarket(H2H_CONDITION, [DETROIT_TOKEN, TORONTO_TOKEN], H2H_OUTCOMES)
        yes = _FakeMarket(YES_CONDITION, [YES_TOKEN, NO_TOKEN], ["Yes", "No"])
        assert token_for_outcome(h2h, name) is None
        assert token_for_outcome(yes, name) == YES_TOKEN


# ------------------------------------------ reachable through the top-up ----


class TestTopupReachesTheHeadToHeadLeg:
    async def test_the_top_up_fills_a_head_to_head_outcome(self):
        """End to end on the production shape: the parent row's external_id is a
        bare Gamma event id, the outcome's condition id is addressable, and the
        name that decides the token comes from our own row."""
        service = _FakeService(
            [_FakeMarket(H2H_CONDITION, [DETROIT_TOKEN, TORONTO_TOKEN], H2H_OUTCOMES)]
        )
        session = _SessionWithNames([(H2H_OUTCOME_ID, H2H_OUTCOME_NAME)])

        filled = await topup_outcome_clob_tokens(
            session,
            [(H2H_MARKET_ID, H2H_OUTCOME_ID, H2H_CONDITION)],
            service=service,
        )

        assert service.asked == [[H2H_CONDITION]]
        assert filled == {H2H_OUTCOME_ID: (H2H_MARKET_ID, DETROIT_TOKEN)}

    async def test_the_filled_token_is_persisted_under_the_outcome_key(self):
        service = _FakeService(
            [_FakeMarket(H2H_CONDITION, [DETROIT_TOKEN, TORONTO_TOKEN], H2H_OUTCOMES)]
        )
        session = _SessionWithNames([(H2H_OUTCOME_ID, H2H_OUTCOME_NAME)])

        await topup_outcome_clob_tokens(
            session,
            [(H2H_MARKET_ID, H2H_OUTCOME_ID, H2H_CONDITION)],
            service=service,
        )

        assert len(session.updates) == 1
        assert OUTCOME_TOKEN_METADATA_KEY in str(
            session.updates[0].compile(compile_kwargs={"literal_binds": True})
        )

    async def test_a_head_to_head_outcome_persists_nothing_without_its_name(self):
        """THE NEGATIVE CONTROL, and it fails exactly one clause.  Same market,
        same condition, same tokens — only the name read comes back empty, and
        the leg falls back to the Yes path, which this market has no answer for.
        Without this, a `token_for_outcome` that ignored the name entirely and
        returned `tokens[0]` would pass every test above."""
        service = _FakeService(
            [_FakeMarket(H2H_CONDITION, [DETROIT_TOKEN, TORONTO_TOKEN], H2H_OUTCOMES)]
        )
        session = _SessionWithNames([])

        filled = await topup_outcome_clob_tokens(
            session,
            [(H2H_MARKET_ID, H2H_OUTCOME_ID, H2H_CONDITION)],
            service=service,
        )

        assert filled == {}
        assert session.updates == []

    async def test_a_failing_name_read_degrades_to_the_yes_path(self):
        """A name lookup must never take the socket's token pass down with it:
        the Yes markets keep filling and the next recycle retries.  This is the
        same posture the module already takes for a Gamma outage."""
        service = _FakeService(
            [
                _FakeMarket(YES_CONDITION, [YES_TOKEN, NO_TOKEN], ["Yes", "No"]),
                _FakeMarket(H2H_CONDITION, [DETROIT_TOKEN, TORONTO_TOKEN], H2H_OUTCOMES),
            ]
        )
        session = _SessionWithNames(read_raises=RuntimeError("names unavailable"))

        filled = await topup_outcome_clob_tokens(
            session,
            [
                (H2H_MARKET_ID, 221927369, YES_CONDITION),
                (H2H_MARKET_ID, H2H_OUTCOME_ID, H2H_CONDITION),
            ],
            service=service,
        )

        assert filled == {221927369: (H2H_MARKET_ID, YES_TOKEN)}

    async def test_both_shapes_fill_in_one_pass(self):
        """The live+6h slate is mixed — 10 Yes, 10 head-to-head — so the pass
        that serves it has to answer both without one starving the other."""
        service = _FakeService(
            [
                _FakeMarket(YES_CONDITION, [YES_TOKEN, NO_TOKEN], ["Yes", "No"]),
                _FakeMarket(H2H_CONDITION, [DETROIT_TOKEN, TORONTO_TOKEN], H2H_OUTCOMES),
            ]
        )
        session = _SessionWithNames(
            [(221927369, "Wolfsberger AC"), (H2H_OUTCOME_ID, H2H_OUTCOME_NAME)]
        )

        filled = await topup_outcome_clob_tokens(
            session,
            [
                (H2H_MARKET_ID, 221927369, YES_CONDITION),
                (H2H_MARKET_ID, H2H_OUTCOME_ID, H2H_CONDITION),
            ],
            service=service,
        )

        assert filled == {
            221927369: (H2H_MARKET_ID, YES_TOKEN),
            H2H_OUTCOME_ID: (H2H_MARKET_ID, DETROIT_TOKEN),
        }
