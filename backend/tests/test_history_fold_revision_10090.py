"""#10090 — `history_fold_revision`'s refusals, and where the history route reads it.

The causal proofs (removals committed before, between and after the reads,
twins, coalesced generations) need a server and live in
`tests/integration/test_history_fold_revision_10090_pg.py`. These are the
rules that need none: every doubt is ``None``, never a smaller vector, and the
route reads the vector after choosing its rows and before any history.
"""

import asyncio
import inspect

import pytest

from app.utils import event_history_cache as ehc
from app.utils.history_coverage import coverage_from_prefix, served_history_coverage

C, T, A = 101, 102, 103


def _claim(vector, *, loaded=4, rows=(C, T), complete=True, canonical=C):
    return coverage_from_prefix(
        vector,
        canonical_id=canonical,
        canonical_loaded_rev=loaded,
        read_row_ids=rows,
        membership_complete=complete,
    )


class TestThePrefixCertifiesExactlyTheRowsRead:
    def test_a_matching_prefix_is_the_claim(self):
        assert _claim({"101": 4, "102": 9}) == {"101": 4, "102": 9}

    @pytest.mark.parametrize(
        "vector,rows",
        [
            # A twin tagged after the series rows were chosen: never read.
            ({"101": 4, "102": 9, "103": 0}, (C, T)),
            # A twin untagged after: read, but no longer a member at the prefix.
            ({"101": 4}, (C, T)),
            # Same size, different rows.
            ({"101": 4, "103": 0}, (C, T)),
        ],
    )
    def test_membership_that_moved_makes_no_claim(self, vector, rows):
        assert _claim(vector, rows=rows) is None

    def test_a_canonical_bag_that_moved_since_its_load_makes_no_claim(self):
        assert _claim({"101": 5, "102": 9}, loaded=4) is None

    @pytest.mark.parametrize("loaded", [None, True, "4", 4.0])
    def test_an_unreadable_loaded_revision_makes_no_claim(self, loaded):
        assert _claim({"101": 4, "102": 9}, loaded=loaded) is None

    @pytest.mark.parametrize(
        "vector", [None, {}, {"101": 4, "102": None}, {"101": 4, "102": True}, [("101", 4)]]
    )
    def test_no_snapshot_vector_makes_no_claim(self, vector):
        assert _claim(vector) is None

    def test_an_incomplete_absorbed_fold_makes_no_claim(self):
        assert _claim({"101": 4, "102": 9}, complete=False) is None

    def test_a_canonical_outside_the_rows_makes_no_claim(self):
        assert _claim({"102": 9}, rows=(T,), canonical=C) is None


class TestOnlyAWholeBuildServesIt:
    def test_a_whole_build_serves_a_copy(self):
        prefix = {"101": 4}
        served = served_history_coverage(prefix, build_complete=True, on_demand_backfill=None)
        assert served == prefix and served is not prefix

    def test_a_partial_build_serves_none(self):
        assert served_history_coverage({"101": 4}, build_complete=False, on_demand_backfill=None) is None

    def test_a_refill_just_enqueued_serves_none(self):
        assert served_history_coverage(
            {"101": 4}, build_complete=True, on_demand_backfill={"enqueue": True}
        ) is None
        assert served_history_coverage(
            {"101": 4}, build_complete=True, on_demand_backfill={"enqueue": False}
        ) == {"101": 4}

    def test_no_prefix_serves_none(self):
        assert served_history_coverage(None, build_complete=True, on_demand_backfill=None) is None


class TestBuildMarks:
    def test_outside_a_build_completeness_is_unknown(self):
        assert ehc.build_is_complete() is False

    def test_inside_a_build_a_swallowed_read_flips_it(self):
        _marks, token = ehc.begin_marks()
        try:
            assert ehc.build_is_complete() is True
            ehc.mark_partial()
            assert ehc.build_is_complete() is False
        finally:
            ehc.end_marks(token)
        assert ehc.build_is_complete() is False


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return self


class _FoldSession:
    """Answers the two candidate reads of `serve_fold_absorbed_rows`."""

    def __init__(self, candidates):
        self.candidates = candidates
        self.calls = 0

    async def execute(self, statement, *a, **kw):
        self.calls += 1
        if self.calls == 1:
            return _Rows([(7, "soccer_epl")])
        return _Rows(self.candidates)


class TestTheAbsorbedFoldSaysWhetherItRanWhole:
    def _event(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace

        return SimpleNamespace(
            id=C, sport_id=7, sport=SimpleNamespace(key="soccer_epl"),
            commence_time=datetime(2026, 10, 19, 12, tzinfo=timezone.utc),
            home_team_name="Arsenal", away_team_name="Chelsea",
        )

    def _run(self, session):
        from app.utils import serve_fold_absorbed as sfa

        return asyncio.run(sfa.serve_fold_absorbed_rows_with_completeness(session, self._event()))

    def test_a_fold_that_raises_is_incomplete_and_folds_nothing(self, monkeypatch):
        from app.utils import serve_fold_absorbed as sfa

        def boom(rows):
            raise RuntimeError("fold failed")

        monkeypatch.setattr(sfa, "fold_twin_events", boom)
        monkeypatch.setattr(sfa, "loaded_sport_key", lambda e: "soccer_epl")
        rows, complete = self._run(_FoldSession([object()]))
        assert rows == [] and complete is False
        # The rows-only caller sees exactly what it always saw.
        assert asyncio.run(sfa.serve_fold_absorbed_rows(_FoldSession([object()]), self._event())) == []

    def test_a_candidate_read_at_the_cap_is_incomplete(self, monkeypatch):
        from types import SimpleNamespace

        from app.utils import serve_fold_absorbed as sfa

        monkeypatch.setattr(sfa, "loaded_sport_key", lambda e: "soccer_epl")
        monkeypatch.setattr(
            sfa, "fold_twin_events", lambda rows: SimpleNamespace(survivor_of={})
        )
        cands = [SimpleNamespace(id=1000 + i) for i in range(sfa.CANDIDATE_CAP)]
        assert self._run(_FoldSession(cands)) == ([], False)
        assert self._run(_FoldSession(cands[:-1])) == ([], True)

    def test_no_candidates_is_complete(self, monkeypatch):
        from app.utils import serve_fold_absorbed as sfa

        monkeypatch.setattr(sfa, "loaded_sport_key", lambda e: "soccer_epl")
        assert self._run(_FoldSession([])) == ([], True)


class TestTheRouteReadsItInTheRightPlace:
    """Source order is the read order here: the build is one straight line of
    awaits on one session. The real-Postgres gate proves the consequence."""

    def _src(self):
        from app.routes.events import get_event_odds_history

        return inspect.getsource(get_event_odds_history)

    def test_after_the_rows_are_chosen_and_before_any_history_read(self):
        src = self._src()
        prefix = src.index("await read_coverage_prefix(")
        assert src.index("folded_series_event_ids(db, event_id, absorbed)") < prefix
        for history_read in (
            "_snapshots_with_split_budget(",
            "select(ScoreSnapshot)",
            "select(ESPNSnapshot)",
            "select(WinProbSnapshot)",
            "select(FuturesMarket)",
        ):
            assert prefix < src.index(history_read), history_read

    def test_only_a_fresh_build_reads_it_and_nothing_borrows_the_pin(self):
        src = self._src()
        block = src[src.index("history_coverage = None"):src.index("await read_coverage_prefix(")]
        assert "if fresh:" in block
        served = src[src.index('"history_fold_revision"'):]
        served = served[: served.index("\n        ),")]
        assert "blend_edge_fold_revision" not in served
        assert "history_build_is_complete()" in served
        assert "on_demand_backfill" in served
