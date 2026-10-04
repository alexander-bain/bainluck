"""#4974 reader slice 1: the pure checkpoint body (``app.utils.publication_reader``).

Each guard below names the mutant it exists to catch (boundary section A,
``4974-UX-READER-SLICE-1-BOUNDARY.md``). A vertex is one stored row and nothing
more: no connector, no hold, nothing derived from a neighbour.
"""

from datetime import datetime, timedelta, timezone

from app.utils import publication_reader as reader

T0 = datetime(2026, 10, 4, 23, 0, 0, tzinfo=timezone.utc)

TOP_LEVEL_KEYS = {"event_id", "schema_version", "time_basis", "truncated", "vertices"}
VERTEX_KEYS = {"rev", "t", "p"}


def _rows(n, start_rev=1):
    return [(start_rev + i, T0 + timedelta(seconds=i), 0.5) for i in range(n)]


class TestEmptyTable:
    def test_no_rows_serves_no_vertices_and_is_not_truncated(self):
        body = reader.publications_body(15300001, [], folded=False)
        assert body == {
            "event_id": 15300001,
            "schema_version": 1,
            "time_basis": "recorded_at_insert_before_commit",
            "truncated": False,
            "vertices": [],
        }

    def test_none_rows_reads_as_empty(self):
        assert reader.publications_body(1, None, folded=False)["vertices"] == []


class TestTheCap:
    """Mutant: drop the cap ⇒ 5001 rows are served as a silent prefix or whole."""

    def test_more_than_5000_rows_serves_nothing_and_says_truncated(self):
        body = reader.publications_body(1, _rows(5001), folded=False)
        assert body["truncated"] is True
        assert body["vertices"] == []

    def test_exactly_5000_rows_is_served_whole(self):
        body = reader.publications_body(1, _rows(5000), folded=False)
        assert body["truncated"] is False
        assert len(body["vertices"]) == 5000

    def test_the_cap_counts_rows_before_null_omission(self):
        # 5001 stored rows, one of them null: still more than the cap was read,
        # so what lies past it is unknown and nothing is served.
        rows = _rows(5001)
        rows[0] = (rows[0][0], rows[0][1], None)
        body = reader.publications_body(1, rows, folded=False)
        assert body["truncated"] is True
        assert body["vertices"] == []

    def test_the_route_reads_exactly_one_past_the_cap(self):
        assert reader.MAX_VERTICES == 5000
        assert reader.READ_LIMIT == 5001


class TestFoldedRowServesNothing:
    """Mutant: skip the fold check ⇒ a folded row serves its own checkpoints."""

    def test_folded_serves_no_vertices_even_with_rows(self):
        body = reader.publications_body(1, _rows(3), folded=True)
        assert body["vertices"] == []
        assert body["truncated"] is False

    def test_folded_is_not_truncated_even_past_the_cap(self):
        assert reader.publications_body(1, _rows(5001), folded=True)["truncated"] is False


class TestNullBlendIsOmitted:
    """Mutant: serve ``p: null`` ⇒ the null row reappears as a vertex."""

    def test_null_row_omitted_and_neighbours_served_exactly_as_stored(self):
        rows = [
            (7, T0, 0.41),
            (8, T0 + timedelta(seconds=5), None),
            (9, T0 + timedelta(seconds=9), 0.63),
        ]
        assert reader.publications_body(1, rows, folded=False)["vertices"] == [
            {"rev": 7, "t": "2026-10-04T23:00:00+00:00", "p": 0.41},
            {"rev": 9, "t": "2026-10-04T23:00:09+00:00", "p": 0.63},
        ]

    def test_non_finite_blend_is_omitted_not_served(self):
        # JSON cannot carry NaN/inf; omitting is the only answer that is not a 500.
        rows = [(1, T0, float("nan")), (2, T0, float("inf")), (3, T0, 0.5)]
        vertices = reader.publications_body(1, rows, folded=False)["vertices"]
        assert [v["rev"] for v in vertices] == [3]

    def test_a_zero_probability_is_a_value_not_a_null(self):
        vertices = reader.publications_body(1, [(1, T0, 0.0)], folded=False)["vertices"]
        assert vertices == [{"rev": 1, "t": "2026-10-04T23:00:00+00:00", "p": 0.0}]


class TestOrderIsRev:
    """Mutant: order by ``recorded_at`` (or not at all) ⇒ the rev sequence breaks."""

    def test_rev_order_holds_when_recorded_at_runs_backwards(self):
        # Insert stamps are taken before commit, so commit order (rev) and
        # recorded_at can disagree. Rows also arrive shuffled.
        rows = [
            (12, T0 + timedelta(seconds=1), 0.52),
            (10, T0 + timedelta(seconds=30), 0.50),
            (11, T0, 0.51),
        ]
        vertices = reader.publications_body(1, rows, folded=False)["vertices"]
        assert [v["rev"] for v in vertices] == [10, 11, 12]
        assert [v["t"] for v in vertices] == [
            "2026-10-04T23:00:30+00:00",
            "2026-10-04T23:00:00+00:00",
            "2026-10-04T23:00:01+00:00",
        ]


class TestTheBodyShape:
    """Mutant: add ``connects_to_previous`` / ``coverage`` ⇒ the key sets redden."""

    def test_exactly_five_top_level_keys(self):
        assert set(reader.publications_body(1, _rows(2), folded=False)) == TOP_LEVEL_KEYS

    def test_exactly_three_vertex_keys(self):
        for vertex in reader.publications_body(1, _rows(3), folded=False)["vertices"]:
            assert set(vertex) == VERTEX_KEYS

    def test_value_types(self):
        body = reader.publications_body("42", [(3, T0, 1)], folded=False)
        assert body["event_id"] == 42 and isinstance(body["event_id"], int)
        (vertex,) = body["vertices"]
        assert isinstance(vertex["rev"], int)
        assert isinstance(vertex["p"], float)
        assert isinstance(vertex["t"], str)


class TestTheClock:
    def test_t_is_recorded_at_in_utc(self):
        pacific = timezone(timedelta(hours=-7))
        stamp = datetime(2026, 10, 4, 16, 0, 0, 123456, tzinfo=pacific)
        (vertex,) = reader.publications_body(1, [(1, stamp, 0.5)], folded=False)["vertices"]
        assert vertex["t"] == "2026-10-04T23:00:00.123456+00:00"
        assert datetime.fromisoformat(vertex["t"]) == stamp

    def test_a_naive_stamp_is_read_as_utc(self):
        naive = datetime(2026, 10, 4, 23, 0, 0)
        (vertex,) = reader.publications_body(1, [(1, naive, 0.5)], folded=False)["vertices"]
        assert vertex["t"] == "2026-10-04T23:00:00+00:00"
