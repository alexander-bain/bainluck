"""#7844 — a Discover card runs a coalition as a race one party is winning.

🔴 THE READER. Production page one, card 3, 390px, 2026-09-21 17:30Z, slug `0c58f558`
(`artifacts/d386-shop/nz-card-390-1730Z.png`):

    POLITICS · Resolves Jan 31, 2028
    Which parties will be part of the next government of New Zealand?
    New favorite: Green Party (68%)
     1  Green Party                     68%
     2  Labour Party                    54%
     3  National Party                  53%
     4  New Zealand First Party         50%
     5  Field and 2 more outcomes

The four printed legs sum to 225%. New Zealand governments are coalitions: Green,
Labour, National and NZ First are not competing for one slot, and the Greens at 68%
are not "beating" Labour at 54% — both can be in the next government, which is the
entire point of the question. The card borrowed the grammar it uses for
`2026-27 Stanley Cup® Finals Winner`, one card below it in the same edition, where
exactly one row can win.

** THE GATE ADMITTED IT, AND CORRECTLY BY ITS OWN TERMS. ** `lead_is_printable`
(#6187) asks whether a reader can SEE the lead the sentence asserts: 68 > 54, so yes.
Nobody asked whether it is a lead. On a mutually exclusive field the two questions
have the same answer, which is exactly why the gap never showed.

** TWO SIGNALS, BOTH REQUIRED. ** `futures_markets.mutually_exclusive` reads FALSE on
market 16624064 — the venue's own declaration — and the printed board sums past 100,
which is the proof a reader can carry out on the card itself. Alone, the flag
over-fires (12 of the 20 non-exclusive cards in the measured edition print copy that
is perfectly true); alone, the sum strips the comparative off 1,065 open tier≤3
markets that ARE flagged exclusive and still sum past 1.00 — the #4895 family, where
the comparative is the truth.

** MEASURED ON THE SERVED EDITION, NOT ON THE FUNCTION ** (`/api/feed?limit=200`,
17:40Z, 97 cards / 71 futures, `artifacts/d387-7844/`): 20 carry the flag false and
EIGHT change copy — this card (175 over its three served legs), `Which parties will
be in next Swedish Government?` (219), `Which parties will win a seat in the 2026
Knesset` (235), `Top 5 Most Searched Passings on Google in the US 2026` — "Dolly
Parton leads at 93%" on a TOP-FIVE list (241) — `2027 PPA Tour Finals: Player to
Qualify` (282) and `: To Reach the Final` (207), `Dancing with the Stars S35 · Top 3
Finishers` (189), `What will be said on the next Lemonade Stand Podcast` (270).
Thirty-seven exclusive cards print a comparative and none of them moves.

** THE REMEDY IS A REFUSAL, NOT A RENORMALIZATION. ** 225% is the honest answer here.
Normalizing a coalition board to 100 would be the defect. The copy falls through to
the standing form the module already builds for a tied board — "Green Party at 68%" —
which says what that number means.

THE GUARDS STAND IN FOUR PLACES:

* THROUGH THE SERVED CARD, `_score_futures` run for real, because a ban on a
  producer is not a ban on a surface (#4160's lesson). The exclusive TWIN of the
  same board is asserted to keep its comparative in the same test class: it is both
  the control that this did not widen AND the proof that the refusing test is not
  green by absence — if the fixture stopped producing a card, or stopped producing a
  comparative for any other reason, the twin reds.
* at the HELPER, where the two signals are combined;
* at the COMPOSERS, all three, because `generate_futures_headline` produces the
  string the reader actually read and a fix reaching only `reason` leaves it on screen;
* at ALL SIX ROUTE SITES structurally, because the parameter's default is silent
  (`None` keeps today's copy) and an unadopted call site is therefore a live defect
  here, not a loud one.
"""

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _card_field_is_a_race, _score_futures
from app.utils.feed_reasons import (
    field_is_a_race,
    generate_futures_context_summary,
    generate_futures_headline,
    generate_futures_reason,
)
from app.utils.personalization import PersonalizationContext

#: The real board, read back from `futures_outcomes` for market 16624064 on
#: 2026-09-21. All eight rows, because the divisor decision (`_feed_display_scale`)
#: is taken over every outcome and not over the three the card slices: these sum to
#: 3.885, past the 2.0 ladder cutoff, which is why the card prints its raw basis and
#: a reader can add 68 + 54 + 53 up to 175 in the first place. A three-row fixture
#: would be normalized and would prove nothing.
NZ_COALITION_BOARD = [
    ("Green Party", 0.675, 0.58, 0.77),
    ("Labour Party", 0.540, 0.45, 0.63),
    ("National Party", 0.530, 0.45, 0.61),
    ("Yes", 0.505, 0.21, 0.80),
    ("New Zealand First Party", 0.500, 0.32, 0.90),
    ("No", 0.495, None, None),
    ("ACT New Zealand", 0.460, 0.47, 0.88),
    ("Te Pāti Māori", 0.180, 0.07, 0.89),
]

NZ_QUESTION = "Which parties will be part of the next government of New Zealand?"

#: Every comparative this ship is responsible for suppressing, same list as #6187's.
#: "New favorite" is one of them: it is the comparative with the number removed, not
#: a weaker form of it.
COMPARATIVES = ("leads", " lead ", "lead;", "New favorite", "favorite")


def _comparatives_in(text: str) -> list[str]:
    return [word for word in COMPARATIVES if word in (text or "")]


# ─────────────────────────── the served card ──────────────────────────────────


class _Outcome:
    def __init__(self, id, name, probability, bid, ask):
        self.id = id
        self.name = name
        self.external_id = None
        self.current_probability = probability
        self.probability_change_24h = 0.0
        self.opening_probability = None
        self.rank = None
        self.rank_change_24h = None
        self.team_id = None
        self.calibration_probability = None
        self.current_yes_bid = bid
        self.current_yes_ask = ask


class _Market:
    """A real object so `__dict__.get(...)` reads work, as in #4160's harness."""

    def __init__(self, id, *, mutually_exclusive):
        now = datetime.now(timezone.utc)
        self.id = id
        self.name = NZ_QUESTION
        self.source = "polymarket"
        self.external_id = f"poly-{id}"
        self.sport_id = None
        self.sport = None
        self.category = "politics"
        self.llm_sport_category = "politics"
        self.market_tier = 2
        self.canonical_market_key = None
        self.group_id = "polymarket:431563"
        self.group_type = "polymarket_event"
        self.image_url = None
        self.hook_description = None
        self.hook_generated_at = None
        self.hook_leader_at_generation = None
        self.market_metadata = {}
        self.curation_score_adj = 0
        self.volume_24h = 250000
        self.updated_at = now
        self.commence_time = now - timedelta(days=1)
        # Far out, as the real one is (Jan 31, 2028), so no deadline template
        # takes the sentence away from the leader clause under test.
        self.resolution_date = now + timedelta(days=480)
        self.status = "open"
        self.created_at = now - timedelta(days=200)
        self.llm_league = None
        self.llm_gender = None
        self.llm_level = None
        self.market_type = "field"
        #: THE ONE FIELD UNDER TEST.
        self.mutually_exclusive = mutually_exclusive
        self.outcomes = [
            _Outcome(1000 + index, name, probability, bid, ask)
            for index, (name, probability, bid, ask) in enumerate(NZ_COALITION_BOARD)
        ]


def _mock_db(markets):
    db = AsyncMock()

    def make_result(*a, **k):
        r = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [m.id for m in markets]
        unique = MagicMock()
        unique.all.return_value = markets
        scalars.unique.return_value = unique
        r.scalars.return_value = scalars
        r.all.return_value = []
        return r

    db.execute = AsyncMock(side_effect=make_result)
    return db


async def _serve(markets):
    """The real scorer, the real card, the strings a reader is handed."""
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.routes.feed._get_canonical_source_counts",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        return await _score_futures(
            _mock_db(markets),
            datetime.now(timezone.utc),
            None,
            PersonalizationContext(),
        )


async def _served_card(*, mutually_exclusive):
    """The card, served.

    🔴 THE TWO FIXTURES CARRY DIFFERENT IDS ON PURPOSE. The route's market-load
    artifact is keyed on the market IDS ALONE, so two fixtures differing only in a
    column read back whichever one was built first — measured here: composing the
    coalition board and then its exclusive twin inside one event loop returns the
    coalition's copy for both, in either order. Today each test gets a fresh loop
    and a fresh artifact, so the collision does not fire; the distinct ids mean it
    cannot start firing silently the day that changes, which is the shape of it
    that matters — the twin is this file's non-vacuity proof, and a poisoned twin
    is a test that agrees with itself.
    """
    items = await _serve(
        [_Market(1 if mutually_exclusive else 2, mutually_exclusive=mutually_exclusive)]
    )
    futures = [i for i in items if i["type"] == "futures"]
    # The eligible denominator. Without this a change that dropped the card would
    # pass the refusal test having proved nothing (the standing trap: a guard on a
    # card the feed already refuses is green by absence).
    assert len(futures) == 1, f"the coalition fixture was not served: {items}"
    return futures[0]


def _slots(item: dict) -> dict[str, str]:
    return {
        "headline": item.get("headline") or "",
        "reason": item.get("reason") or "",
        "context_summary": item.get("context_summary") or "",
    }


class TestTheCoalitionCardThroughTheRoute:
    """The two halves of the same board, served by `_score_futures` itself."""

    @pytest.mark.asyncio
    async def test_no_slot_calls_a_coalition_member_the_favourite(self):
        card = await _served_card(mutually_exclusive=False)
        offenders = {
            slot: (text, _comparatives_in(text))
            for slot, text in _slots(card).items()
            if _comparatives_in(text)
        }
        assert not offenders, f"the coalition card still runs as a race: {offenders}"

    @pytest.mark.asyncio
    async def test_the_card_still_says_where_the_leader_stands(self):
        """A refusal that emptied the card would be the same defect, silent.

        The reader loses the comparative and keeps the fact: 68% is what the Greens
        are bid to be part of the next government, and the card must still say so.
        """
        card = await _served_card(mutually_exclusive=False)
        spoken = " | ".join(_slots(card).values())
        assert "Green Party" in spoken, f"the leader is no longer named: {spoken!r}"
        assert "68%" in spoken, f"the leader's standing is gone: {spoken!r}"

    @pytest.mark.asyncio
    async def test_the_exclusive_twin_keeps_its_comparative(self):
        """The control AND the proof that the test above is not green by absence.

        Byte-identical board, `mutually_exclusive=True`. If this stops printing a
        comparative — because the fixture stopped being served, because the copy
        moved, because a later refusal swallowed it — the refusal test above has
        stopped testing anything and this reds instead of it.
        """
        card = await _served_card(mutually_exclusive=True)
        spoken = " | ".join(_slots(card).values())
        assert _comparatives_in(
            spoken
        ), f"an exclusive field lost its comparative: {spoken!r}"

    @pytest.mark.asyncio
    async def test_removing_the_refusal_restores_the_defect(self):
        """The strawman: the guard must be able to fail.

        `field_is_a_race` is patched to its pre-#7844 answer — the constant True it
        effectively was — and the served card is re-read. If the comparative does
        not come back, this test is asserting something the route was doing anyway.
        """
        with patch("app.routes.feed.field_is_a_race", return_value=True):
            card = await _served_card(mutually_exclusive=False)
        spoken = " | ".join(_slots(card).values())
        assert _comparatives_in(spoken), (
            "with the refusal removed the card printed no comparative, so the "
            f"refusal above proves nothing: {spoken!r}"
        )


class TestTheRouteHalfReadsThePrintedBoard:
    """`_card_field_is_a_race` — the flag and the percents THE CARD PRINTS."""

    @staticmethod
    def _market(flag):
        return _Market(2, mutually_exclusive=flag)

    @staticmethod
    def _rows(*percents):
        return [{"rendered_percent": percent} for percent in percents]

    def test_a_coalition_board_over_a_hundred_is_not_a_race(self):
        assert (
            _card_field_is_a_race(self._market(False), self._rows(68, 54, 53)) is False
        )

    def test_an_exclusive_board_over_a_hundred_still_is(self):
        assert _card_field_is_a_race(self._market(True), self._rows(68, 54, 53)) is True

    def test_a_coalition_board_under_a_hundred_still_is(self):
        assert _card_field_is_a_race(self._market(False), self._rows(40, 30, 25)) is True

    def test_a_market_with_no_flag_at_all_keeps_todays_copy(self):
        """An absent column reads as "unknown", never as a falsy refusal."""

        class _Bare:
            pass

        assert _card_field_is_a_race(_Bare(), self._rows(68, 54, 53)) is True


class TestTheHelper:
    """`field_is_a_race`, at its own boundary."""

    def test_both_signals_are_needed(self):
        assert field_is_a_race(False, [68, 54, 53]) is False
        assert field_is_a_race(True, [68, 54, 53]) is True
        assert field_is_a_race(False, [40, 30, 25]) is True

    def test_the_boundary_is_the_hundred_a_reader_adds_up(self):
        assert field_is_a_race(False, [50, 50]) is True
        assert field_is_a_race(False, [51, 50]) is False

    def test_an_unknown_flag_keeps_todays_copy(self):
        assert field_is_a_race(None, [68, 54, 53]) is True
        assert field_is_a_race(rendered_percents=[68, 54, 53]) is True

    def test_a_board_that_cannot_be_added_up_keeps_todays_copy(self):
        """Fewer than two printed percents: there is nothing for a reader to sum."""
        assert field_is_a_race(False, []) is True
        assert field_is_a_race(False, [68]) is True
        assert field_is_a_race(False, [68, None]) is True
        assert field_is_a_race(False, None) is True

    def test_unpriced_rows_are_skipped_not_counted_as_zero(self):
        assert field_is_a_race(False, [68, None, 54]) is False


class TestTheComposers:
    """All three, because the reader reads all three."""

    SHARED = dict(
        highlight_reasons=["leader_change"],
        leader_name="Green Party",
        leader_probability=0.675,
        rendered_leader_percent=68,
        rendered_runner_up_percent=54,
        market_name=NZ_QUESTION,
    )

    def _copy(self, *, race):
        headline = generate_futures_headline(**self.SHARED, card_field_is_a_race=race)
        reason = generate_futures_reason(
            NZ_QUESTION,
            ["leader_change"],
            leader_name="Green Party",
            leader_probability=0.675,
            rendered_leader_percent=68,
            rendered_runner_up_percent=54,
            card_field_is_a_race=race,
        )
        context = generate_futures_context_summary(
            headline=headline, **self.SHARED, card_field_is_a_race=race
        )
        return {"headline": headline, "reason": reason, "context_summary": context}

    def test_no_composer_prints_a_comparative_on_a_coalition(self):
        offenders = {
            slot: text
            for slot, text in self._copy(race=False).items()
            if _comparatives_in(text)
        }
        assert not offenders, offenders

    def test_every_composer_keeps_it_on_a_race(self):
        spoken = " | ".join(self._copy(race=True).values())
        assert _comparatives_in(spoken), spoken

    def test_an_uninformed_caller_is_unchanged(self):
        """The silent default, asserted rather than assumed.

        This is the property that makes the parameter safe to add to three public
        composers at once: every caller in the repo that has not been taught it —
        and every caller outside this route — composes exactly what it composed
        before.
        """
        assert self._copy(race=None) == self._copy(race=True)


# ───────────────────────── the six route sites ────────────────────────────────

#: The three composers whose copy the parameter gates.
_COMPOSERS = {
    "generate_futures_reason",
    "generate_futures_headline",
    "generate_futures_context_summary",
}

#: Both card builders in `routes/feed.py`. Three composer calls each.
_ROUTE_SCORERS = ["_score_futures", "_score_sports_mode_futures"]

_FEED_SOURCE = (
    Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"
).read_text()


def _composer_calls(function_name: str):
    for node in ast.walk(ast.parse(_FEED_SOURCE)):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ):
            return [
                (call.lineno, call.func.id, {k.arg for k in call.keywords})
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id in _COMPOSERS
            ]
    raise AssertionError(f"{function_name} is gone from routes/feed.py")


@pytest.mark.parametrize("scorer", _ROUTE_SCORERS)
def test_every_route_site_says_whether_the_field_is_a_race(scorer):
    """An unadopted call site restores the live defect instead of failing loudly.

    Adding a fourth serving path without the keyword reds this; deleting one reds
    the arity assertion below rather than passing vacuously.
    """
    calls = _composer_calls(scorer)
    assert len(calls) == 3, f"{scorer} composes {len(calls)} card strings, expected 3"
    unadopted = [
        (lineno, name) for lineno, name, kwargs in calls
        if "card_field_is_a_race" not in kwargs
    ]
    assert not unadopted, f"{scorer} composes copy without the refusal: {unadopted}"
