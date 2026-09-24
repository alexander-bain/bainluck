"""The served evidence shape for win-probability points (#7878).

Codex's exact-head review of PR #8438 found the producer contract never reached
the wire: `_project_served_game_state` (#6546) strips `evidence_span` and every
provenance key before the response leaves the route. The shape now travels as
its own `evidence` key, computed by `app/utils/winprob_evidence.py` before that
projection. These are its unit cases; the route boundary itself is proven in
`tests/integration/test_winprob_evidence_wire_7878_pg.py`.
"""

from app.utils.winprob_evidence import (
    SERVED_CONTRACT,
    attach_served_evidence,
    served_evidence,
    validated_covered_through,
)

TS = "2026-09-21T19:00:00+00:00"
SPAN = {"contract": "7878.v1", "resolution_s": 300, "covered_through": "2026-09-21T19:04:00.000000Z"}


def _pt(ts=TS, **state):
    return {"timestamp": ts, "home_probability": 0.6, "game_state": state or None}


class TestSpanValidation:
    def test_the_retention_stamp_is_accepted(self):
        through = validated_covered_through({"evidence_span": SPAN}, TS)
        assert through is not None and through.isoformat() == "2026-09-21T19:04:00+00:00"

    def test_each_malformed_or_foreign_stamp_is_refused(self):
        bad = [
            {**SPAN, "contract": "7878.v0"},
            {**SPAN, "resolution_s": 600},
            {**SPAN, "resolution_s": True},
            {**SPAN, "resolution_s": "300"},
            {**SPAN, "covered_through": "2026-09-21 19:04:00"},
            {**SPAN, "covered_through": "2099-13-45T99:99:99.000000Z"},
            {**SPAN, "covered_through": "2026-09-21T18:59:00.000000Z"},  # before the reading
            "not-a-dict",
        ]
        for span in bad:
            assert validated_covered_through({"evidence_span": span}, TS) is None, span

    def test_no_state_or_no_stamp_proves_nothing(self):
        assert validated_covered_through(None, TS) is None
        assert validated_covered_through({"period": "1H"}, TS) is None


class TestServedEvidence:
    def test_a_plain_reading_carries_nothing(self):
        assert served_evidence(_pt(period="1H", market_name="x")) is None

    def test_a_stamped_reading_serves_its_span(self):
        ev = served_evidence(_pt(evidence_span=SPAN))
        assert ev == {"kind": "observed", "covered_through": "2026-09-21T19:04:00+00:00"}

    def test_provenance_kinds(self):
        assert served_evidence(_pt(poll_type="history_backfill", evidence_span=SPAN)) == {"kind": "candle"}
        assert served_evidence(_pt(backfill=True)) == {"kind": "price_history"}
        assert served_evidence(_pt(final=True)) == {"kind": "final"}

    def test_a_live_edge_never_inherits_the_span_it_copied(self):
        edge = {**_pt(evidence_span=SPAN), "live_edge": True}
        assert served_evidence(edge) == {"kind": "live_edge"}

    def test_a_terminal_row_is_not_evidence_even_when_stamped(self):
        assert served_evidence(_pt(evidence_span=SPAN), terminal_row=True) == {"kind": "terminal_row"}


class TestAttach:
    def test_finished_series_marks_the_last_stored_reading_not_the_synthetic_one(self):
        series = [_pt(), _pt("2026-09-21T19:10:00+00:00"), _pt("2026-09-21T21:00:00+00:00", final=True)]
        attach_served_evidence({"kalshi": series}, is_finished=True)
        assert "evidence" not in series[0]
        assert series[1]["evidence"] == {"kind": "terminal_row"}
        assert series[2]["evidence"] == {"kind": "final"}

    def test_a_live_series_has_no_terminal_row(self):
        series = [_pt(), _pt("2026-09-21T19:10:00+00:00")]
        attach_served_evidence({"kalshi": series}, is_finished=False)
        assert all("evidence" not in p for p in series)

    def test_a_stale_evidence_key_is_not_left_on_a_plain_reading(self):
        series = [{**_pt(), "evidence": {"kind": "candle"}}]
        attach_served_evidence({"kalshi": series}, is_finished=False)
        assert "evidence" not in series[0]

    def test_the_served_contract_names_its_version_and_resolution(self):
        assert SERVED_CONTRACT == {"v": "7878.v1", "resolution_s": 300}
