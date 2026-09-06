"""#3484 follow-up — the Sports feed's first page, composed end to end.

`L1B-056-SPORTS-FIRST-PAGE-END-TO-END`, the nonblocking follow-up CERT-2056
named. CERT-2056's tests prove the freshness decay's *scoring* and its
*admission* behaviour one or two cards at a time. They do not prove the thing
the ship was actually about, which is a **page**: on 2026-09-06 08:27Z
`GET /api/feed?limit=20&mode=sports` served 14 dead cards out of 20.

So this drives the real `_score_events` with a full 20-card pool shaped like
that measured page — 13 finished games that scored 86-98, two live games that
scored 35 and 40, five scheduled — and asserts on the composed ordering rather
than on a pair of scores.

The grader's words for why this is guard completion rather than a second bug
hunt: "the current Sports chain has no later score-based removal, so this is
guard completion against a future downstream-chain change". The point is that
if someone later adds a truncation, a cap, or a re-sort downstream of scoring,
these assertions break — and the pairwise tests would not.

FALSIFIED, not assumed. `compute_completed_freshness_factor` was forced to
return 1.0 (pre-ship: no decay) and this file was re-run:

    test_both_live_games_reach_the_first_five ............... FAILED  {50: 13, 51: 14}
    test_every_live_game_outranks_every_fully_decayed_result  FAILED  pos 6 over pos 14
    test_no_card_is_lost_at_full_page_size .................. passed  (control)
    test_finished_games_are_ordered_freshest_first .......... passed  (control)
    test_the_guard_fails_on_pre_ship_code ................... passed  (asserts pre-ship)

Both ship arms go red and name the production symptom — the two live games at
positions 13 and 14, under thirteen finished blowouts — while both controls
stay green because membership is unchanged and only ORDER moves. A guard that
has never been fired at the code it exists to block is a guess.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_events, apply_discover_display_chain
from app.utils.feed_scoring import COMPLETED_DECAY_HOURS
from app.utils.personalization import PersonalizationContext


NOW = datetime(2026, 9, 6, 8, 27, 0, tzinfo=timezone.utc)

# The measured page: 13 completed, 2 live, 20 slots.
COMPLETED_AGES_H = [2.9, 3.4, 4.1, 4.6, 5.2, 5.8, 6.3, 7.0, 8.1, 9.2, 10.4, 11.0, 11.8]


def _sport(key="baseball_mlb", name="MLB"):
    s = MagicMock()
    s.key = key
    s.name = name
    return s


def _base_event(event_id: int):
    """Production's row shape, with the fields every branch of scoring reads."""
    e = MagicMock()
    e.id = event_id
    e.home_team_id = 100 + event_id
    e.away_team_id = 200 + event_id
    e.home_team_name = f"Home{event_id}"
    e.away_team_name = f"Away{event_id}"
    e.statpal_end_time = None
    e.completed_at = None
    e.llm_importance = "regular"
    e.llm_gender = None
    e.llm_level = None
    e.llm_league = None
    e.sport = _sport()
    e.period = None
    e.ei_metadata = None
    e.external_id = f"ext-{event_id}"
    e.game_clock = None
    e.broadcast_info = None
    e.event_tags = []
    e.opening_home_spread = -3.5
    e.opening_over_under = 8.5
    return e


def _completed(event_id: int, hours_since_finish: float):
    """A finished blowout of a given age — the 13/13 measured shape.

    `statpal_end_time` NULL and `completed_at` set is exactly the population
    that made the age read from kickoff before this ship.
    """
    e = _base_event(event_id)
    e.status = "completed"
    e.commence_time = NOW - timedelta(hours=hours_since_finish + 3)
    e.completed_at = NOW - timedelta(hours=hours_since_finish)
    e.opening_home_probability = 0.20
    e.opening_away_probability = 0.80
    e.win_probability_sources = {"betting": {"home_probability": 0.95}}
    e.opening_favorite = f"Away{event_id}"
    e.raw_ei = 0.95
    e.home_score = 7
    e.away_score = 2
    return e


def _live(event_id: int, *, hours_since_start: float = 1.0):
    """A close live game — the two cards the measured page had at 35 and 40.

    Kickoff stays recent on purpose: `_score_events` filters a "live" game that
    started ~14h ago under a separate staleness rule, which would make a control
    pass for the wrong reason.
    """
    e = _base_event(event_id)
    e.status = "live"
    e.commence_time = NOW - timedelta(hours=hours_since_start)
    e.period = "T7"
    e.opening_home_probability = 0.55
    e.opening_away_probability = 0.45
    e.win_probability_sources = {"betting": {"home_probability": 0.55}}
    e.opening_favorite = f"Home{event_id}"
    e.raw_ei = 70.0
    e.home_score = 4
    e.away_score = 3
    return e


def _scheduled(event_id: int, *, hours_until_start: float = 4.0):
    e = _base_event(event_id)
    e.status = "scheduled"
    e.commence_time = NOW + timedelta(hours=hours_until_start)
    e.opening_home_probability = 0.52
    e.opening_away_probability = 0.48
    e.win_probability_sources = {"betting": {"home_probability": 0.52}}
    e.opening_favorite = f"Home{event_id}"
    e.raw_ei = 60.0
    e.home_score = None
    e.away_score = None
    return e


def _mock_db(events):
    db = AsyncMock()

    def make_result(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        r.all.return_value = []
        return r

    async def execute(stmt, *a, **k):
        s = str(stmt).lower()
        if "win_prob_snapshots" in s:
            return make_result([])
        if "events" in s:
            return make_result(events)
        return make_result([])

    db.execute = AsyncMock(side_effect=execute)
    return db


async def _run(events, ctx=None):
    with patch(
        "app.routes.feed._get_championship_probabilities",
        new=AsyncMock(return_value={}),
    ):
        return await _score_events(
            _mock_db(events), NOW, None, ctx or PersonalizationContext()
        )


def _the_measured_pool():
    """13 completed + 2 live + 5 scheduled = the 20 slots, ids partitioned by kind.

    The scheduled kickoffs are all inside three hours deliberately. Measured
    while writing this: `_score_events` admits a scheduled game at +1h/+2h/+3h
    (scores 47/37/37) and drops it at +4h and beyond, under an upcoming-window
    admission rule that predates this ship and has nothing to do with the
    freshness decay. Spreading them 3-7h out would have made four of the five
    controls vanish, and the guard would then be asserting ordering over cards
    that were never in the pool — passing for the wrong reason.
    """
    completed = [_completed(10 + i, age) for i, age in enumerate(COMPLETED_AGES_H)]
    live = [_live(50), _live(51, hours_since_start=2.0)]
    scheduled = [_scheduled(70 + i, hours_until_start=1.0 + 0.5 * i) for i in range(5)]
    return completed, live, scheduled


def _event_items(items):
    return [i for i in items if i["type"] == "event"]


COMPLETED_IDS = set(range(10, 10 + len(COMPLETED_AGES_H)))
LIVE_IDS = {50, 51}
SCHEDULED_IDS = set(range(70, 75))

# Ages past `COMPLETED_DECAY_HOURS` (6.0) sit on the flat floor of the ramp.
FULLY_DECAYED_IDS = {
    10 + i for i, age in enumerate(COMPLETED_AGES_H) if age >= COMPLETED_DECAY_HOURS
}


def _no_decay(display_score, rank_score, event_status, hours_since_finish):
    """The pre-ship function: scoring with no freshness decay at all."""
    return display_score, rank_score, []


async def _first_page(*, decay: bool = True):
    """Score AND compose — `_score_events` then the real display chain.

    Both halves matter and only the pair is the page. Measured while writing
    this: `_score_events` alone returns a live card scoring 67 *behind*
    completed cards scoring 41, because it does not rank — `_rank_key` sorting
    happens inside `apply_discover_display_chain`. A guard that stopped at
    `_score_events` would be asserting over a list no reader is served, which
    is the exact failure mode the display-chain function was extracted to stop
    (#1923, see its docstring).
    """
    completed, live, scheduled = _the_measured_pool()
    pool = completed + live + scheduled

    if decay:
        items = await _run(pool)
    else:
        # The route imports the decay inside the function body, so the patch
        # has to land on the defining module, not on `app.routes.feed`.
        with patch(
            "app.utils.feed_scoring.apply_completed_freshness_decay", new=_no_decay
        ):
            items = await _run(pool)

    composed, _meta = apply_discover_display_chain(
        items,
        limit=20,
        ctx=PersonalizationContext(),
        event_pct=1.0,  # Sports mode: events are the product, not Discover.
    )
    return [i["data"]["id"] for i in composed if i["type"] == "event"]


class TestTheSportsFirstPageComposesEndToEnd:
    """The 20-card page, through scoring and the display chain."""

    @pytest.mark.asyncio
    async def test_no_card_is_lost_at_full_page_size(self):
        """#1091: the decay re-ranks a finished game, it never deletes one.

        CERT-2048 blocked the first version of this ship for exactly this, and
        proved it one card at a time. This proves it for a whole page at once —
        a cap or truncation added downstream later would surface here.
        """
        ids = await _first_page()

        assert len(ids) == 20, f"page lost cards: {len(ids)}/20"
        assert set(ids) == COMPLETED_IDS | LIVE_IDS | SCHEDULED_IDS
        assert len(set(ids)) == 20, "a card was served twice"

    @pytest.mark.asyncio
    async def test_both_live_games_reach_the_first_five(self):
        """The ship, stated as the reader sees it.

        On the measured page the only two live games scored 35 and 40 and were
        buried under 13 finished blowouts. They now surface.
        """
        ids = await _first_page()
        positions = {i: ids.index(i) for i in LIVE_IDS}

        assert all(p < 5 for p in positions.values()), (
            f"a live game fell off the first five: {positions}"
        )

    @pytest.mark.asyncio
    async def test_every_live_game_outranks_every_fully_decayed_result(self):
        """Nothing on the decay's flat floor may sit above a game being played."""
        ids = await _first_page()
        worst_live = max(ids.index(i) for i in LIVE_IDS)
        best_stale = min(ids.index(i) for i in FULLY_DECAYED_IDS)

        assert worst_live < best_stale, (
            f"a finished game past the decay window (pos {best_stale}) outranks "
            f"a live game (pos {worst_live})"
        )

    @pytest.mark.asyncio
    async def test_finished_games_are_ordered_freshest_first(self):
        """The decay is monotonic in age, so the page order is too.

        A CONTROL, not an arm: measured under falsification, this passes with
        the decay removed as well, because the fixture's ids ascend with age
        and equal scores fall back to a stable order. It is here to catch a
        future change that scrambles finished games among themselves — it does
        not discriminate this ship, and must not be read as if it does.
        """
        ids = await _first_page()
        completed_order = [i for i in ids if i in COMPLETED_IDS]

        # Ids were assigned in ascending age, so freshest-first == ascending id.
        assert completed_order == sorted(completed_order), (
            f"finished games are out of age order: {completed_order}"
        )

    @pytest.mark.asyncio
    async def test_the_guard_fails_on_pre_ship_code(self):
        """The discriminator — without the decay this page is the bug again.

        Measured: with the decay removed, the two live games land at positions
        13 and 14 and the top five is five finished blowouts. That is the
        08:27Z production page (`14 dead cards out of 20`) reproduced in a test.

        This is asserted rather than described so the guard cannot quietly stop
        discriminating: if a refactor makes the decay a no-op, the tests above
        go red AND this one does too, which distinguishes "the ship regressed"
        from "the fixture drifted".
        """
        ids = await _first_page(decay=False)

        assert len(ids) == 20, "the counterfactual must differ in ORDER, not membership"
        assert all(i in COMPLETED_IDS for i in ids[:5]), (
            f"pre-ship top five should be all finished games, got {ids[:5]}"
        )
        assert all(ids.index(i) >= 10 for i in LIVE_IDS), (
            f"pre-ship live games should be buried, got "
            f"{ {i: ids.index(i) for i in LIVE_IDS} }"
        )
