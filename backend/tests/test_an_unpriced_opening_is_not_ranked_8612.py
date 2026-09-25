"""#8612, ranking half — a card is not ranked on a move from an opening that was never a price.

The copy half (`test_an_unpriced_opening_is_no_baseline_8612.py`) stopped the
"since <date>" sentence. The same number still ranked the card: on
2026-09-25 the trace for Kanye West performs in Russia (market 59220073) read
`major_surprise` (+10) off the 0.94 opening stored on a 16c/96c book, served
at futures rank 9. And the settled filters let a stuck leader survive because
it "opened" under the threshold on such a number.

Both now refuse the legs `update_max_movement` lists in
`market_metadata['unpriced_opening_ids']`, and treat them exactly like a leg
with no opening. Absent means not judged: every control below is today's
behaviour.
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timezone
from types import SimpleNamespace

from app.routes import feed as feed_module
from app.routes.feed import _leader_opening, _market_runtime_filter_trace
from app.utils.futures_highlights import compute_futures_highlight
from app.utils.futures_market_snapshot import UNPRICED_OPENING_METADATA_KEY

KANYE_YES = 220051242
KANYE_NO = 220051243
NOW = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)


def _leg(oid, name, opening, current, change=0.0):
    return {"id": oid, "name": name, "opening_probability": opening,
            "probability": current, "probability_change_24h": change}


def _market(refused=None):
    metadata = {} if refused is None else {UNPRICED_OPENING_METADATA_KEY: list(refused)}
    return SimpleNamespace(market_metadata=metadata, updated_at=NOW, commence_time=None,
                           resolution_date=None)


KANYE_BOARD = [_leg(KANYE_YES, "Yes", 0.94, 0.077), _leg(KANYE_NO, "No", 0.06, 0.923)]


def _highlight(outcomes, refused=frozenset()):
    return compute_futures_highlight(
        market_tier=5, sport_category="entertainment", outcomes=outcomes, now=NOW,
        market_name="Kanye West performs in Russia by October 31?",
        refused_opening_ids=refused,
    )


class TestTheSurpriseScoreRefusesAListedLeg:
    def test_control_an_unjudged_board_still_scores_its_surprise(self):
        result = _highlight(KANYE_BOARD)
        assert "major_surprise" in result.reasons

    def test_the_specimen_board_scores_no_surprise_and_ten_points_less(self):
        control = _highlight(KANYE_BOARD)
        refused = _highlight(KANYE_BOARD, frozenset({KANYE_YES, KANYE_NO}))
        assert not {"major_surprise", "moderate_surprise"} & set(refused.reasons)
        assert control.score - refused.score == 10

    def test_an_unlisted_leg_on_the_same_board_still_scores(self):
        # Refusing one leg must not silence a real move beside it.
        board = [_leg(KANYE_YES, "Yes", 0.94, 0.077), _leg(7, "Other", 0.20, 0.35)]
        result = _highlight(board, frozenset({KANYE_YES}))
        assert "moderate_surprise" in result.reasons
        assert "major_surprise" not in result.reasons

    def test_every_feed_scoring_call_passes_the_refused_set(self):
        # Three serving paths score futures; one that forgets the kwarg ranks on
        # the unpriced opening again with every test here still green.
        tree = ast.parse(inspect.getsource(feed_module))
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "compute_futures_highlight"
        ]
        assert len(calls) == 3
        for call in calls:
            kwargs = {kw.arg: kw.value for kw in call.keywords}
            assert "refused_opening_ids" in kwargs, call.lineno
            value = kwargs["refused_opening_ids"]
            assert getattr(value.func, "id", None) == "unpriced_opening_ids", call.lineno


def _runtime(outcomes, leader, market, sport="basketball"):
    leader_prob = next(o["probability"] for o in outcomes if o["name"] == leader)
    return _market_runtime_filter_trace(
        market, outcomes, leader, leader_prob, NOW, sport_category=sport,
        newest_outcome_at=NOW,
    )


class TestTheSettledFiltersTreatAListedOpeningAsNone:
    # A sports binary leader at 65%, flat: it survived only because it opened at
    # 40%. If that 40% was a 2c/97c midpoint, it is a stuck market like any other.
    SOFT = [_leg(11, "Celtics", 0.40, 0.65), _leg(12, "Knicks", 0.60, 0.35)]
    # A leader at 92% still moving: it survived as an upset riser off 30%.
    RISER = [_leg(21, "Yes", 0.30, 0.92, 0.02), _leg(22, "No", 0.70, 0.08, -0.02)]

    def test_control_the_soft_settled_leader_survives_on_a_judged_opening(self):
        trace = _runtime(self.SOFT, "Celtics", _market())
        assert "soft_settled_binary" not in trace["blockers"]

    def test_a_listed_leader_opening_is_soft_settled(self):
        trace = _runtime(self.SOFT, "Celtics", _market([11]))
        assert "soft_settled_binary" in trace["blockers"]

    def test_listing_only_the_trailer_leaves_the_leader_alone(self):
        trace = _runtime(self.SOFT, "Celtics", _market([12]))
        assert "soft_settled_binary" not in trace["blockers"]

    def test_control_the_riser_survives_on_a_judged_opening(self):
        trace = _runtime(self.RISER, "Yes", _market())
        assert "effectively_resolved" not in trace["blockers"]
        assert "sports_effectively_settled" not in trace["blockers"]

    def test_a_listed_riser_opening_is_effectively_resolved(self):
        trace = _runtime(self.RISER, "Yes", _market([21]))
        assert "effectively_resolved" in trace["blockers"]
        assert trace["checks"]["leader_opening_probability"] is None

    def test_the_helper_reads_the_opening_when_nothing_is_listed(self):
        assert _leader_opening(self.RISER, "Yes", _market()) == 0.30
        assert _leader_opening(self.RISER, "Yes", _market([21])) is None
        assert _leader_opening(self.RISER, None, _market()) is None

    def test_the_sports_path_reads_the_leader_opening_through_the_helper(self):
        # The sports-mode loop inlines its own copy of these filters; it must
        # not keep a bare `opening_probability` lookup for the leader.
        source = inspect.getsource(feed_module)
        assert source.count("_leader_opening(") == 4  # def + three readers
        for bare in ('leader_opening = o.get("opening_probability")',
                     'leader_opening_prob = o.get("opening_probability")',
                     'leader_opening = outcome.get("opening_probability")'):
            assert bare not in source, bare
