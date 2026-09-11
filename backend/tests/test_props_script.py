"""#195: props-script payload contract (THE SCRIPT / DIVERGENCE / WHAT HIT).

Covers the pure helpers that build the event-page PropsSection payload
(`props_script`), the contract Lane 2's `frontend/components/event/PropsSection.tsx`
consumes. See `_build_props_script` / `_resolve_pregame_mark` in routes/events.py.
"""

from types import SimpleNamespace

from app.routes.events import _build_props_script, _resolve_pregame_mark


def _outcome(oid):
    return SimpleNamespace(id=oid)


def _market(meta):
    # __dict__.get is how the helper reads market_metadata (gotcha #26 lazy-load
    # safe); SimpleNamespace mirrors an ORM row's __dict__.
    return SimpleNamespace(market_metadata=meta)


class TestResolvePregameMark:
    def test_prefers_pinned_commence_mark_over_opening(self):
        m = _market({"pregame_mark": {"outcomes": {"7": 0.62}}})
        # is_over=True: raw is already the over probability.
        assert _resolve_pregame_mark(m, _outcome(7), True, False, 0.40) == 0.62

    def test_under_orientation_is_converted(self):
        m = _market({"pregame_mark": {"outcomes": {"7": 0.62}}})
        # is_under=True, is_over=False → over prob = 1 - raw.
        assert _resolve_pregame_mark(m, _outcome(7), False, True, 0.40) == 0.38

    def test_falls_back_to_opening_when_no_pin(self):
        assert _resolve_pregame_mark(_market(None), _outcome(7), True, False, 0.41) == 0.41

    def test_falls_back_when_outcome_not_in_pin(self):
        m = _market({"pregame_mark": {"outcomes": {"99": 0.5}}})
        assert _resolve_pregame_mark(m, _outcome(7), True, False, 0.33) == 0.33

    def test_returns_none_when_neither_available(self):
        assert _resolve_pregame_mark(_market({}), _outcome(7), True, False, None) is None

    def test_malformed_pin_does_not_raise(self):
        m = _market({"pregame_mark": {"outcomes": {"7": "not-a-number"}}})
        assert _resolve_pregame_mark(m, _outcome(7), True, False, 0.5) == 0.5


class TestBuildPropsScript:
    def test_script_state_fields(self):
        props = [{
            "market_name": "NYY at BOS: Aaron Judge Home Runs",
            "outcome_name": "Aaron Judge: 1+",
            "over_probability": 0.55,
            "pregame_mark": 0.50,
        }]
        script = _build_props_script(props)
        assert len(script) == 1
        row = script[0]
        assert row["label"] == "Aaron Judge: 1+"
        assert row["pregame_mark"] == 0.50
        assert row["current"] == 0.55
        assert row["graded_result"] is None
        assert row["graded_label"] is None
        assert row["key"] == "NYY at BOS: Aaron Judge Home Runs|Aaron Judge: 1+"

    def test_graded_hit_maps_and_labels(self):
        props = [{
            "market_name": "M",
            "outcome_name": "Judge: 1+",
            "over_probability": 0.9,
            "pregame_mark": 0.5,
            "hit": True,
            "actual": 2,
        }]
        row = _build_props_script(props)[0]
        assert row["graded_result"] == "hit"
        assert row["graded_label"] == "2 — hit"

    def test_graded_miss_maps(self):
        props = [{"market_name": "M", "outcome_name": "o", "over_probability": 0.1,
                  "pregame_mark": 0.5, "hit": False, "actual": 0}]
        row = _build_props_script(props)[0]
        assert row["graded_result"] == "miss"
        assert row["graded_label"] == "0 — miss"

    def test_graded_falls_back_to_is_winner_when_no_boxscore_hit(self):
        # Fallback only fires when authoritatively resolved (resolution_source set).
        props = [{"market_name": "M", "outcome_name": "o", "over_probability": 0.9,
                  "pregame_mark": 0.5, "is_winner": True,
                  "resolution_source": "api_settlement"}]
        row = _build_props_script(props)[0]
        assert row["graded_result"] == "hit"
        # No box-score actual → no numeric label.
        assert row["graded_label"] is None

    def test_ungraded_prop_does_not_render_as_miss(self):
        # is_winner defaults to False on UNRESOLVED outcomes (non-nullable column).
        # Without a resolution_source, the prop is not graded and must NOT render
        # as a confident "miss" (the live WNBA regression: Cardoso 6+/8+/10+ all
        # showed graded_result="miss" with resolution_source=None, actual=None).
        props = [{"market_name": "M", "outcome_name": "Kamilla Cardoso: 6+",
                  "over_probability": 0.8, "pregame_mark": 0.5,
                  "hit": None, "is_winner": False, "resolution_source": None,
                  "actual": None}]
        row = _build_props_script(props)[0]
        assert row["graded_result"] is None
        assert row["graded_label"] is None

    def test_authoritative_loss_still_renders_as_miss(self):
        # A real resolved loss (resolution_source set, is_winner False) DOES grade.
        props = [{"market_name": "M", "outcome_name": "o", "over_probability": 0.2,
                  "pregame_mark": 0.5, "is_winner": False,
                  "resolution_source": "api_settlement"}]
        row = _build_props_script(props)[0]
        assert row["graded_result"] == "miss"

    def test_a_typed_hit_grades_without_any_event_level_permission(self):
        """#5088 / T3-2, WITHDRAWING `test_not_finished_never_grades_even_with_hit_present`.

        That guard asserted the builder refused a typed `hit` unless the caller
        said the whole EVENT was finished, which is the defect this ship is: a
        question the third inning answered waited for the ninth. The builder now
        has no event-level input at all — the row's own evidence is the trigger —
        so the withdrawn assertion is not merely relaxed, it is unstatable.

        Who may set `hit` is unchanged and is where the safety lives:
        `_grade_settled_prop` (settled events only) and `_grade_closed_windows`
        (a window `prop_window_closed` has proven is over).
        """
        props = [{"market_name": "M", "outcome_name": "o", "over_probability": 0.9,
                  "pregame_mark": 0.5, "hit": True, "actual": 2}]
        row = _build_props_script(props)[0]
        assert row["graded_result"] == "hit"
        assert row["graded_label"] == "2 — hit"

    def test_a_graded_row_is_settled_and_an_ungraded_one_is_not(self):
        """`settled` is the per-ROW override PropsSection already reads.

        `rowState = item.settled ? "graded" : state` — so a row that carries a
        verdict renders WHAT HIT even while the section is still in script or
        divergence state. Both directions are asserted, because a flag that is
        always true reads exactly like a working one on the graded row.
        """
        graded, pending = _build_props_script([
            {"market_name": "M", "outcome_name": "graded", "over_probability": 0.9,
             "pregame_mark": 0.5, "hit": True, "actual": 2},
            {"market_name": "M", "outcome_name": "pending", "over_probability": 0.6,
             "pregame_mark": 0.5, "hit": None, "is_winner": False,
             "resolution_source": None},
        ])
        assert graded["settled"] is True
        assert pending["settled"] is False
        # And the pending row is pending, not lost — the #2089 statement.
        assert pending["graded_result"] is None

    def test_empty_props_yields_empty_script(self):
        assert _build_props_script([]) == []

    def test_missing_pregame_and_current_are_none_not_error(self):
        props = [{"market_name": "M", "outcome_name": "o"}]
        row = _build_props_script(props)[0]
        assert row["pregame_mark"] is None
        assert row["current"] is None
