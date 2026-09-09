"""#4189 — a decomposed container parent is not served beside its own children.

THE DEFECT, MEASURED. `GET /api/events/15307447/game-markets` on production,
2026-09-08 (Andreeva v Gauff, US Open QF). The event page's THE SCRIPT · Props
rail printed one group of eleven rows summing to 432%, in which eight rows were
not outcomes at all but the TITLES of the market's own sub-markets, every one of
them at the same price:

    41.5%   "US Open WTA: Mirra Andreeva vs Coco Gauff Set 1 Winner"
    40.5%   "US Open WTA: Mirra Andreeva vs Coco Gauff Set Handicap +/-1.5"
    40.5%   "US Open WTA: Mirra Andreeva vs Coco Gauff Match O/U 21.5"
    …
    35.5%   "Mirra Andreeva"                       ← a bare player name

WHERE THEY CAME FROM. Polymarket game events arrive as one container plus nested
sub-markets (gotcha #18), and decomposition already splits them correctly: on
`group_id = polymarket:986558` all nine children exist as their own properly
named, properly shaped rows — `Set 1 Winner: Andreeva vs Gauff`,
`Set Handicap: Gauff (-1.5) vs Andreeva (+1.5)`, four `Match O/U` rungs. What
survives is the `field` PARENT (`60457478`), still holding the union of its
children as raw outcome strings. `_extract_threshold` pulls `1.5` out of
"Set Handicap +/-1.5" and `21.5` out of "Match O/U 21.5", so each title cleared
the `threshold is not None` gate and was minted as a player prop. The eight
identical prices are the parent's single price stamped onto every decomposed
leg — not a pricing bug, and not a coincidence.

THE SHAPE VOCABULARY ALREADY SAYS SO. `app/utils/market_shape.py` defines
`container_member` as "a yes/no member of a decomposed field (shared group_id)
→ rolls up into a container". The container is the parent. Serving both is
serving the same markets twice, once in a shape nobody can read.

SCOPE, MEASURED, NOT ESTIMATED. 12,687 `(group_id, event_id)` pairs on
production hold a `field` parent alongside decomposed members, so this is a
class and not one match. Every event-linked sample is a Polymarket container —
"Colorado Rockies vs. New York Yankees - Player Props", "Igdir FK vs. Mardin
1969 Spor - More Markets", the match container above. The non-container `field`
markets that share a group with members ("Which cities face tornado risk on
August 23?") are all `event_id IS NULL` and never reach this serializer, which
is why the rule is safe to state in terms of shape alone.

RED-FIRST. On the parent commit `TestTheContainerParentLeavesTheRail` fails with
all nine title rows present on the rail.

🔴 THE CONTROL ARM IS THE POINT OF THIS FILE. "The titles are gone" is satisfied
perfectly by a serializer that returns nothing, which is the mutant that matters
for a removal. So `TestTheChildrenStillArrive` asserts the decomposed children
are STILL served with their own prices, and `TestAParentWithNoServedChildrenStays`
asserts the fail-safe: when decomposition has not produced children into the
served set, the parent is the only representation this event has and it must
survive. Both red on an over-broad suppression that the title assertions alone
would call a pass.

WHAT THIS DOES NOT FIX, said explicitly. The child `60457479` (the match winner,
outcomes a bare "Yes"/"No" carrying no player's name) still reaches the rail, and
the sibling Kalshi market `60490261` still sums to 102% across its two legs. Both
are named in #4189 and neither is a container-parent defect; see the issue.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.events import (
    _decomposed_container_parent_candidates,
    _game_markets_cache,
    get_game_markets,
)

GROUP = "polymarket:986558"

#: The parent's ten outcomes, verbatim from `futures_outcomes` for market
#: 60457478. Nine are sub-market titles; the tenth is a bare player name.
PARENT_OUTCOMES = [
    ("US Open WTA: Mirra Andreeva vs Coco Gauff Game Spread +/-2.5", 0.5550),
    ("US Open WTA: Mirra Andreeva vs Coco Gauff Match O/U 21.5", 0.5150),
    ("US Open WTA: Mirra Andreeva vs Coco Gauff Match O/U 22.5", 0.4600),
    ("US Open WTA: Mirra Andreeva vs Coco Gauff Set 1 O/U 9.5", 0.4450),
    ("US Open WTA: Mirra Andreeva vs Coco Gauff Match O/U 23.5", 0.4350),
    ("US Open WTA: Mirra Andreeva vs Coco Gauff Set 1 Winner", 0.4150),
    ("US Open WTA: Mirra Andreeva vs Coco Gauff Set 2 Winner", 0.4100),
    ("US Open WTA: Mirra Andreeva vs Coco Gauff Total Sets: O/U 2.5", 0.4100),
    ("US Open WTA: Mirra Andreeva vs Coco Gauff Set Handicap +/-1.5", 0.4050),
    ("Mirra Andreeva", 0.3550),
]

#: The decomposed children, all on the parent's `group_id`. These are what the
#: reader should be left with.
CHILDREN = [
    (60457480, "container_member", "Set 1 Winner: Andreeva vs Gauff"),
    (60457481, "container_member", "Set 2 Winner: Andreeva vs Gauff"),
    (60457487, "container_member", "Set Handicap: Gauff (-1.5) vs Andreeva (+1.5)"),
    (60486420, "container_member", "Game Spread: Gauff (-2.5) vs Andreeva (+2.5)"),
    (60457482, "quantity", "Mirra Andreeva vs. Coco Gauff: Total Sets O/U 2.5"),
    (60457483, "quantity", "Andreeva vs. Gauff: Set 1 Games O/U 9.5"),
    (60457484, "quantity", "Andreeva vs. Gauff: Match O/U 21.5"),
    (60457485, "quantity", "Andreeva vs. Gauff: Match O/U 22.5"),
    (60457486, "quantity", "Andreeva vs. Gauff: Match O/U 23.5"),
]

PARENT_ID = 60457478


# ---------------------------------------------------------------- fixtures --


def _make_result(scalar=None, rows=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _make_event(*, id=15307447):
    event = MagicMock()
    event.id = id
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


def _make_market(*, id, name, market_type, group_id, event_id=15307447):
    market = MagicMock()
    market.id = id
    market.name = name
    market.external_id = f"0x{id:064x}"
    market.event_id = event_id
    market.category = "game_prop"
    market.status = "open"
    market.source = "polymarket"
    market.sport_id = None
    market.llm_sport_category = "tennis"
    market.commence_time = datetime(2026, 9, 9, 23, 0, tzinfo=timezone.utc)
    market.market_type = market_type
    market.group_id = group_id
    market.group_type = None
    return market


def _make_outcome(*, id, market_id, name, probability):
    outcome = MagicMock()
    outcome.id = id
    outcome.market_id = market_id
    outcome.name = name
    outcome.current_probability = probability
    outcome.opening_probability = None
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


def _the_production_group(
    *, include_children=True, parent_shape="field", child_state="renderable"
):
    """The real `polymarket:986558` group, parent plus (optionally) children.

    🔴 `child_state` EXISTS BECAUSE `include_children=False` WAS THE WRONG
    CONTROL, and CERT-2335 is the receipt. "No child rows" and "child rows that
    render nothing" are different states, and only the first one was tested — so
    fourteen tests passed over a payload that, in the second state, came back
    entirely empty. Removing the rows removes them from the suppression
    predicate too, which is precisely the arm that cannot fail.

    The three states are the three ways a child can be SERVED without being
    RENDERED, which is the distinction the whole repair turns on:

    * ``renderable``   — the production shape: two real, distinct prices.
    * ``no_outcomes``  — the row is served and has no outcomes at all. The
                         render loop's first gate drops it.
    * ``no_real_price``— the row is served with outcomes, but every price is
                         zero, so `has_no_real_price` drops it.
    """
    markets = [
        _make_market(
            id=PARENT_ID,
            name="US Open WTA: Mirra Andreeva vs Coco Gauff",
            market_type=parent_shape,
            group_id=GROUP,
        )
    ]
    outcomes = [
        _make_outcome(id=900 + i, market_id=PARENT_ID, name=name, probability=prob)
        for i, (name, prob) in enumerate(PARENT_OUTCOMES)
    ]
    if include_children:
        for n, (mid, shape, name) in enumerate(CHILDREN):
            markets.append(
                _make_market(id=mid, name=name, market_type=shape, group_id=GROUP)
            )
            if child_state == "no_outcomes":
                continue
            # Two real, distinguishable prices so a survivor is identifiable.
            yes, no = (
                (0.0, 0.0) if child_state == "no_real_price" else (0.3950, 0.6050)
            )
            outcomes.append(
                _make_outcome(id=7000 + n * 2, market_id=mid, name="Yes", probability=yes)
            )
            outcomes.append(
                _make_outcome(id=7001 + n * 2, market_id=mid, name="No", probability=no)
            )
    return markets, outcomes


async def _payload(*, include_children=True, parent_shape="field", child_state="renderable"):
    event = _make_event()
    markets, outcomes = _the_production_group(
        include_children=include_children,
        parent_shape=parent_shape,
        child_state=child_state,
    )
    return await get_game_markets(event.id, _db_for(event, markets, outcomes))


def _every_rendered_name(payload):
    """Every outcome/market string the payload puts in front of a reader."""
    names = []
    for section in ("player_props", "totals", "spreads", "matchups", "other"):
        for row in payload.get(section) or []:
            if isinstance(row, dict):
                names.append(f"{row.get('market_name', '')}|{row.get('outcome_name', '')}")
    return names


@pytest.fixture(autouse=True)
def clear_game_markets_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


# ------------------------------------------------- the parent leaves the rail --


class TestTheContainerParentLeavesTheRail:
    @pytest.mark.asyncio
    async def test_no_sub_market_title_is_served_as_an_outcome(self):
        payload = await _payload()
        rendered = " ".join(_every_rendered_name(payload))
        for title, _prob in PARENT_OUTCOMES[:9]:
            assert title not in rendered, (
                f"the sub-market title {title!r} is still being served as an outcome"
            )

    @pytest.mark.asyncio
    async def test_the_bare_player_name_is_gone(self):
        payload = await _payload()
        bare = [
            n for n in _every_rendered_name(payload) if n.endswith("|Mirra Andreeva")
        ]
        assert bare == [], f"a bare player name is still on the rail: {bare}"

    @pytest.mark.asyncio
    async def test_the_eight_identical_prices_are_gone(self):
        """The parent's one price, stamped on every decomposed leg."""
        payload = await _payload()
        props = payload.get("player_props") or []
        at_4050 = [p for p in props if p.get("over_probability") == 0.4050]
        assert len(at_4050) <= 1, (
            f"{len(at_4050)} props still share the parent's single price: "
            f"{[p['outcome_name'] for p in at_4050]}"
        )

    def test_the_helper_names_the_parent_and_only_the_parent(self):
        markets, _ = _the_production_group()
        assert _decomposed_container_parent_candidates(markets) == {PARENT_ID}


# ------------------------------------------------- the control arm (mutants) --


class TestTheChildrenStillArrive:
    """🔴 'the titles are gone' is satisfied by serving NOTHING. This is the test
    that separates a de-duplication from a deletion."""

    @pytest.mark.asyncio
    async def test_the_payload_is_not_empty(self):
        payload = await _payload()
        assert _every_rendered_name(payload), (
            "the whole group was suppressed — this is a deletion, not a de-dup"
        )

    @pytest.mark.asyncio
    async def test_suppressing_the_parent_loses_nothing_else(self):
        """The differential, and the real invariant: LOST 0.

        Stated as "every child in `CHILDREN` is served" this test failed on a
        commit where the suppression was doing exactly the right thing — two of
        the `quantity` rungs ("Total Sets O/U 2.5", "Set 1 Games O/U 9.5") never
        reach the payload at all, dropped by the totals section's own
        pre-existing path, with the suppression ON and OFF alike. Asserting an
        absolute list would have made this file a guard on somebody else's
        behaviour, red for a reason that has nothing to do with #4189.

        So compare the two arms instead. Everything the serializer rendered
        before must still be rendered after, minus the parent's own rows and
        nothing besides.
        """
        _game_markets_cache.clear()
        before = set(_every_rendered_name(await _payload(parent_shape=None)))
        _game_markets_cache.clear()
        after = set(_every_rendered_name(await _payload(parent_shape="field")))

        parent_rows = {
            n for n in before
            if n.startswith("US Open WTA: Mirra Andreeva vs Coco Gauff|")
        }
        assert parent_rows, "the fixture never reproduced the defect"
        assert before - after == parent_rows, (
            "suppression removed rows that are not the parent's: "
            f"{(before - after) - parent_rows}"
        )
        assert after - before == set(), f"suppression invented rows: {after - before}"

    @pytest.mark.asyncio
    async def test_the_named_children_a_reader_should_see_are_served(self):
        """A concrete positive control, so this file does not rest entirely on a
        differential that an all-empty serializer would satisfy on both arms."""
        payload = await _payload()
        rendered = " ".join(_every_rendered_name(payload))
        for name in (
            "Set 1 Winner: Andreeva vs Gauff",
            "Set 2 Winner: Andreeva vs Gauff",
            "Set Handicap: Gauff (-1.5) vs Andreeva (+1.5)",
            "Game Spread: Gauff (-2.5) vs Andreeva (+2.5)",
            "Andreeva vs. Gauff: Match O/U 21.5",
        ):
            assert name in rendered, f"the decomposed child {name!r} was dropped too"

    @pytest.mark.asyncio
    async def test_the_childrens_own_prices_survive(self):
        payload = await _payload()
        rows = [
            r
            for section in ("player_props", "totals", "spreads", "matchups", "other")
            for r in (payload.get(section) or [])
            if isinstance(r, dict)
        ]
        assert any(
            r.get("over_probability") == 0.3950 or r.get("probability") == 0.3950
            for r in rows
        ), "the children are listed but carry none of their own prices"


class TestAParentWithNoServedChildrenStays:
    """The fail-safe. Without children in the served set the parent is the only
    representation the event has, and suppressing it deletes the market."""

    @pytest.mark.asyncio
    async def test_a_lone_parent_is_still_served(self):
        payload = await _payload(include_children=False)
        assert _every_rendered_name(payload), (
            "a container parent with no served children was suppressed anyway"
        )

    def test_the_helper_names_nobody_when_the_group_is_alone(self):
        markets, _ = _the_production_group(include_children=False)
        assert _decomposed_container_parent_candidates(markets) == set()


class TestAServedChildIsNotYetARenderedChild:
    """🔴 CERT-2335. THE ARM THE FIRST CONTROL COULD NOT REACH.

    `TestAParentWithNoServedChildrenStays` removes the child ROWS — which also
    removes them from the suppression predicate, so that arm can never fail. The
    dangerous state is the one in between: the child rows ARE served, so they
    suppress the parent, and then they are dropped by a gate further down the
    render loop and emit nothing themselves. Parent gone, children gone, group
    gone.

    The cert's independent falsifier is `child_state="no_outcomes"` below: it
    kept the parent and all nine children, removed only the children's outcomes,
    and got an entirely empty payload out of the shipped code — while the
    fourteen submitted tests stayed green.

    Both states are ways a market can be counted as served and still not reach
    the page, which is why the repair observes EMISSION instead of predicting it.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("child_state", ["no_outcomes", "no_real_price"])
    async def test_children_that_render_nothing_do_not_delete_the_group(
        self, child_state
    ):
        payload = await _payload(child_state=child_state)
        assert _every_rendered_name(payload), (
            f"with children served but unrenderable ({child_state}), the parent "
            "was suppressed and the children emitted nothing — the whole market "
            "vanished from the page. A parent may only be dropped in favour of "
            "children a reader can actually see."
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("child_state", ["no_outcomes", "no_real_price"])
    async def test_and_what_survives_is_the_PARENT_not_a_husk(self, child_state):
        """Non-empty is not enough — the surviving rows must be the parent's.

        Without this, a payload carrying some unrelated section would satisfy
        the assertion above while the match itself was still missing.
        """
        payload = await _payload(child_state=child_state)
        rendered = " ".join(_every_rendered_name(payload))
        assert "Mirra Andreeva" in rendered, (
            "the parent is the group's only remaining representation and its "
            "rows are what the reader must be left with"
        )

    @pytest.mark.asyncio
    async def test_the_renderable_case_is_unchanged_by_the_repair(self):
        """The control on the control: when children DO render, the parent still
        goes. Otherwise this repair would have quietly undone #4189 itself."""
        payload = await _payload(child_state="renderable")
        rendered = _every_rendered_name(payload)
        assert rendered, "the renderable case must still serve the children"
        assert not any("Set 1 Winner" in n and "US Open WTA:" in n for n in rendered), (
            "a sub-market TITLE is back on the rail — the repair has undone the "
            "suppression it was supposed to make safe"
        )

    def test_the_candidate_helper_still_only_names_candidates(self):
        """The predicate is unchanged, and that is deliberate.

        The repair did not tighten this set — a tightened predicate would still
        be a prediction, and the per-type branches below it can emit nothing for
        reasons no predicate can see. It moved the VERDICT to the render loop
        instead. So the parent is still a candidate in both broken states.
        """
        for child_state in ("no_outcomes", "no_real_price"):
            markets, _ = _the_production_group(child_state=child_state)
            assert _decomposed_container_parent_candidates(markets) == {PARENT_ID}


class TestShapesThisRuleMustNotTouch:
    def test_a_null_shape_parent_is_left_alone(self):
        """`market_type` is nullable and the backfill lags ingest, so an
        unshaped parent keeps today's behaviour rather than being guessed at."""
        markets, _ = _the_production_group(parent_shape=None)
        assert PARENT_ID not in _decomposed_container_parent_candidates(markets)

    def test_a_field_market_in_no_group_is_left_alone(self):
        markets, _ = _the_production_group()
        for m in markets:
            m.group_id = None
        assert _decomposed_container_parent_candidates(markets) == set()

    def test_a_field_market_whose_group_holds_no_members_is_left_alone(self):
        """Two `field` markets sharing a group is not a decomposition."""
        markets = [
            _make_market(id=1, name="A", market_type="field", group_id=GROUP),
            _make_market(id=2, name="B", market_type="field", group_id=GROUP),
        ]
        assert _decomposed_container_parent_candidates(markets) == set()

    def test_children_in_a_different_group_do_not_suppress_the_parent(self):
        markets = [
            _make_market(id=1, name="parent", market_type="field", group_id=GROUP),
            _make_market(
                id=2,
                name="someone else's child",
                market_type="container_member",
                group_id="polymarket:999999",
            ),
        ]
        assert _decomposed_container_parent_candidates(markets) == set()
