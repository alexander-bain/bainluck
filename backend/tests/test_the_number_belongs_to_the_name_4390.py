"""#4390 — THE SCRIPT stops printing one leg's probability under its sibling's name.

THE DEFECT, AS A READER MET IT. `/events/15307447` at 390px on 2026-09-09, 27
minutes before Andreeva v Gauff, under THE SCRIPT · Props:

    US OPEN WTA: MIRRA ANDREEVA VS COCO GAUFF
      No     37%
      Yes    37%

Two rows that are the two sides of one question, both printing 37%. One of them
is a false statement about its own label and a reader cannot tell which.

THE STORED DATA IS CORRECT — the numbers are made false on the way out. Market
`60457479` (polymarket, `container_member`), from `db-query`:

    | outcome | current | opening |
    |---------|---------|---------|
    | Yes     |  0.335  |  0.365  |
    | No      |  0.670  |  0.635  |

A proper pair on distinct ids. What production served, from the live payload:

    {"outcome_name": "No",  "over_probability": 0.33,  "pregame_mark": 0.365}
    {"outcome_name": "Yes", "over_probability": 0.335, "pregame_mark": 0.365}

WHY. `over_probability` and `pregame_mark` are normalised onto the OVER (yes)
axis — `over_prob = prob if is_over or not is_under else 1.0 - prob`, with
`is_under = name == "no"`. That is the right contract for a consumer reasoning
about the QUESTION, and `lib/propDivergence.ts` depends on it to collapse
Over/Under siblings. `_build_props_script` then paired that axis-normalised
number with `label = outcome_name` — the LEG's own name. The No row printed
1 − 0.635 = 0.365 under the word "No".

THE SURFACE ALREADY ANSWERS THIS QUESTION EVERYWHERE ELSE, which is why the fix
is to move the number and not the label. The same card, same screenshot:

    MIRRA ANDREEVA VS COCO GAUFF: SET 1 WINNER
      Coco Gauff       60%
      Mirra Andreeva   42%

Both sides of a two-way question, each on its OWN axis. So does the concept-page
builder (`utils/event_concept.py`) — it reads the leader's own `probability` and
own `opening_probability`, and its comment says a number belongs to a name. The
inverted legs were the only rows on the surface disagreeing.

SCOPE, MEASURED ON PRODUCTION, not estimated. Event-attached markets holding a
priced leg the rule inverts: **85,139** bare `No` legs and **191,928** `Under x`
legs. This is a class, not one match.

NAMED RESIDUAL, NOT FIXED HERE. #4189's own docstring predicted this row: "the
child 60457479 (the match winner, outcomes a bare 'Yes'/'No' carrying no
player's name) still reaches the rail". This ship makes the two NUMBERS true of
their labels. It does NOT give the bare "Yes"/"No" legs a question to be an
answer to — that naming defect is #4189's residual and stays open. A reader
after this ship sees "No 67% / Yes 34%", which is honest and still unnamed.

🔴 THE CONTROL ARM IS THE POINT. "The two rows differ" is satisfied perfectly by
a mutant that flips EVERY row, which would put 45% under "Over 8.5" and break
every prop on the site. So `TestRowsThatWereAlreadyTrueDoNotMove` pins
non-inverted rows byte-identical, and `TestTheOverUnderPair` asserts the Over
leg is untouched while only the Under leg moves. Both are red on an over-broad
flip that the "they differ" assertion alone calls a pass.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.events import (
    _build_props_script,
    _game_markets_cache,
    _own_axis,
    get_game_markets,
)
from app.utils.graded_card import rendered_percent

EVENT_ID = 15307447
MATCH_WINNER_ID = 60457479

#: Verbatim from `futures_outcomes` for market 60457479 on 2026-09-09:
#: (outcome id, name, current_probability, opening_probability).
THE_PRODUCTION_PAIR = [
    (225835414, "Yes", 0.335, 0.365),
    (225835415, "No", 0.670, 0.635),
]


# ---------------------------------------------------------------- fixtures --


def _make_result(scalar=None, rows=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _make_event():
    event = MagicMock()
    event.id = EVENT_ID
    event.home_team_name = "Coco Gauff"
    event.away_team_name = "Mirra Andreeva"
    event.status = "scheduled"
    event.sport_id = None
    event.sport = MagicMock()
    event.sport.key = "tennis_wta"
    event.commence_time = datetime(2026, 9, 9, 23, 0, tzinfo=timezone.utc)
    event.home_score = None
    event.away_score = None
    event.period = None
    event.game_clock = None
    event.box_score_data = None
    return event


def _make_market(*, id, name, market_type="container_member"):
    market = MagicMock()
    market.id = id
    market.name = name
    market.external_id = f"0x{id:064x}"
    market.event_id = EVENT_ID
    market.category = "game_prop"
    market.status = "open"
    market.source = "polymarket"
    market.sport_id = None
    market.llm_sport_category = "tennis"
    market.commence_time = datetime(2026, 9, 9, 23, 0, tzinfo=timezone.utc)
    market.market_type = market_type
    market.group_id = None
    market.group_type = None
    market.market_metadata = None
    return market


def _make_outcome(*, id, market_id, name, probability, opening):
    outcome = MagicMock()
    outcome.id = id
    outcome.market_id = market_id
    outcome.name = name
    outcome.current_probability = probability
    outcome.opening_probability = opening
    outcome.resolution_source = None
    outcome.is_winner = None
    return outcome


def _db_for(event, markets, outcomes):
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar=event),
            _make_result(rows=[]),        # #2693 folded_event_ids
            _make_result(rows=markets),
            _make_result(all_rows=[]),    # polymarket parent groups
            _make_result(rows=[]),        # unlinked fallback
            _make_result(rows=outcomes),
        ]
    )
    return db


async def _script_for(market_name, legs, *, market_type="container_member"):
    """Serve one market through the real endpoint, return its `props_script`.

    `legs` is [(outcome_id, name, current, opening)]. Nothing is stubbed between
    the outcome rows and the payload: this is the whole serializer, so it proves
    the orientation flag is REACHED and not merely defined.
    """
    event = _make_event()
    market = _make_market(id=MATCH_WINNER_ID, name=market_name, market_type=market_type)
    outcomes = [
        _make_outcome(id=oid, market_id=MATCH_WINNER_ID, name=n, probability=p, opening=o)
        for oid, n, p, o in legs
    ]
    payload = await get_game_markets(event.id, _db_for(event, [market], outcomes))
    return payload.get("props_script") or []


def _by_label(script):
    return {row["label"]: row for row in script}


@pytest.fixture(autouse=True)
def clear_game_markets_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


# --------------------------------------------------------- THE SHIP, served --


class TestTheShipThroughTheRealEndpoint:
    """The production specimen, through `get_game_markets` end to end."""

    @pytest.mark.asyncio
    async def test_the_fixture_actually_reaches_the_rail(self):
        # ANTI-VACUITY. Every assertion below is over `props_script` rows, and a
        # serializer that emitted nothing would satisfy all of them. If this
        # market ever stops classifying onto the rail, the ship tests must fail
        # loudly here rather than pass over an empty list.
        script = await _script_for(
            "US Open WTA: Mirra Andreeva vs Coco Gauff", THE_PRODUCTION_PAIR
        )
        assert len(script) == 2, script
        assert set(_by_label(script)) == {"Yes", "No"}

    @pytest.mark.asyncio
    async def test_the_no_row_prints_the_no_price(self):
        script = await _script_for(
            "US Open WTA: Mirra Andreeva vs Coco Gauff", THE_PRODUCTION_PAIR
        )
        no = _by_label(script)["No"]
        # Stored: opening 0.635, current 0.670. Previously served 0.365 / 0.33.
        assert no["pregame_mark"] == 0.635
        assert no["current"] == 0.67

    @pytest.mark.asyncio
    async def test_the_yes_row_is_untouched(self):
        script = await _script_for(
            "US Open WTA: Mirra Andreeva vs Coco Gauff", THE_PRODUCTION_PAIR
        )
        yes = _by_label(script)["Yes"]
        assert yes["pregame_mark"] == 0.365
        assert yes["current"] == 0.335

    @pytest.mark.asyncio
    async def test_the_two_rows_no_longer_print_the_same_number(self):
        # The reader-visible defect, in the reader's own units: THE SCRIPT
        # renders `pregame_mark` as a whole percent, and both rows read "37%".
        #
        # Through `rendered_percent` — the Python arm of the cross-runtime
        # rounding contract (#1933 / #3867) the page itself prints by — NOT
        # Python's `round()`, which is banker's rounding and answers 36 for the
        # 0.365 the screenshot shows as 37%. Asserting the browser's number with
        # Python's rule is the exact mistake that contract exists to stop.
        script = await _script_for(
            "US Open WTA: Mirra Andreeva vs Coco Gauff", THE_PRODUCTION_PAIR
        )
        rendered = {row["label"]: rendered_percent(row["pregame_mark"]) for row in script}
        assert rendered == {"No": 64, "Yes": 37}, rendered


# ------------------------------------------------ controls that CAN fail --


class TestRowsThatWereAlreadyTrueDoNotMove:
    """A row whose number already matched its label is byte-identical.

    This is the arm an over-broad flip fails. Kalshi's threshold shape carries
    no under leg at all, and it is the majority of the rail.
    """

    def test_a_threshold_leg_is_unchanged(self):
        props = [{
            "market_name": "NYY at BOS: Aaron Judge Home Runs",
            "outcome_name": "Aaron Judge: 1+",
            "over_probability": 0.55,
            "pregame_mark": 0.50,
            "_inverted": False,
        }]
        row = _build_props_script(props)[0]
        assert row["pregame_mark"] == 0.50
        assert row["current"] == 0.55

    def test_a_row_with_no_orientation_flag_is_unchanged(self):
        # Defensive: any caller that never learned about `_inverted` keeps the
        # pre-#4390 behaviour rather than silently flipping.
        props = [{
            "market_name": "M",
            "outcome_name": "Judge: 1+",
            "over_probability": 0.55,
            "pregame_mark": 0.50,
        }]
        row = _build_props_script(props)[0]
        assert row["pregame_mark"] == 0.50
        assert row["current"] == 0.55

    @pytest.mark.asyncio
    async def test_a_yes_only_market_is_unchanged_through_the_endpoint(self):
        script = await _script_for(
            "US Open WTA: Mirra Andreeva vs Coco Gauff",
            [(225835414, "Yes", 0.335, 0.365)],
        )
        assert len(script) == 1
        assert script[0]["pregame_mark"] == 0.365
        assert script[0]["current"] == 0.335


class TestTheOverUnderPair:
    """The other half of the rule's population: `Under x`, 191,928 priced legs."""

    def test_the_over_leg_is_untouched_and_the_under_leg_moves(self):
        props = [
            {"market_name": "Soto: Home Runs O/U 1.5", "outcome_name": "Over",
             "over_probability": 0.40, "pregame_mark": 0.42, "_inverted": False},
            {"market_name": "Soto: Home Runs O/U 1.5", "outcome_name": "Under",
             "over_probability": 0.40, "pregame_mark": 0.42, "_inverted": True},
        ]
        over, under = _build_props_script(props)
        assert (over["pregame_mark"], over["current"]) == (0.42, 0.40)
        assert (under["pregame_mark"], under["current"]) == (0.58, 0.60)


class TestGradingIsNotTouched:
    """The flip moves probabilities. WHAT HIT reads a verdict, not a price."""

    def test_an_inverted_leg_still_grades_the_same(self):
        props = [{
            "market_name": "M", "outcome_name": "Under 8.5",
            "over_probability": 0.20, "pregame_mark": 0.30,
            "_inverted": True, "hit": True, "actual": 6,
        }]
        row = _build_props_script(props)[0]
        assert row["graded_result"] == "hit"
        assert row["graded_label"] == "6 — hit"
        # …and the price still moved onto the leg's own axis.
        assert row["current"] == 0.80


class TestAbsentNumbersStayAbsent:
    """gotcha: "no number" and "0%" are different statements."""

    def test_none_survives_the_flip(self):
        props = [{"market_name": "M", "outcome_name": "No", "_inverted": True}]
        row = _build_props_script(props)[0]
        assert row["pregame_mark"] is None
        assert row["current"] is None

    def test_a_half_priced_inverted_row_flips_only_what_it_has(self):
        props = [{"market_name": "M", "outcome_name": "No", "over_probability": 0.25,
                  "pregame_mark": None, "_inverted": True}]
        row = _build_props_script(props)[0]
        assert row["pregame_mark"] is None
        assert row["current"] == 0.75


class TestTheHelperItself:
    def test_identity_when_not_inverted(self):
        assert _own_axis(0.365, False) == 0.365

    def test_complement_when_inverted(self):
        assert _own_axis(0.365, True) == 0.635

    def test_none_is_not_a_probability(self):
        assert _own_axis(None, True) is None
        assert _own_axis(None, False) is None

    def test_rounding_does_not_leak_float_noise(self):
        # 1 - 0.67 is 0.33000000000000007 in binary floating point; a raw
        # subtraction would serve that to the client.
        assert _own_axis(0.67, True) == 0.33
