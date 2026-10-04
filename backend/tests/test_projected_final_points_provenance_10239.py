"""#10461 (source half of #10239): recorded vs cutoff-carried bookmaker history provenance.

The route stamps an in-window snapshot at its capture minute and re-stamps a
pre-cutoff snapshot at the cutoff minute, with nothing telling the two apart.
These guards pin the helper that names them, without touching the route.
"""

from __future__ import annotations

import ast
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path

import pytest

from app.utils import projected_final_points
from app.utils.projected_final_points import bookmaker_history_provenance

CUTOFF = datetime(2026, 10, 4, 17, 0, 0, tzinfo=timezone.utc)


def _route_keeps_capture_minute(captured_at: datetime, cutoff: datetime | None) -> bool:
    # The exact predicate `get_event_history` uses to keep the capture minute
    # (routes/events.py, bookmaker_history loop); everything else is re-stamped
    # at the cutoff.
    return cutoff is None or captured_at >= cutoff


class TestKind:
    def test_capture_equal_to_cutoff_is_recorded(self):
        result = bookmaker_history_provenance(captured_at=CUTOFF, cutoff=CUTOFF)
        assert result == {
            "kind": "recorded",
            "observed_at": "2026-10-04T17:00:00+00:00",
        }

    def test_capture_after_cutoff_is_recorded(self):
        captured = CUTOFF + timedelta(minutes=3, seconds=41)
        result = bookmaker_history_provenance(captured_at=captured, cutoff=CUTOFF)
        assert result == {
            "kind": "recorded",
            "observed_at": "2026-10-04T17:03:41+00:00",
        }

    def test_capture_before_cutoff_is_synthetic(self):
        captured = CUTOFF - timedelta(microseconds=1)
        result = bookmaker_history_provenance(captured_at=captured, cutoff=CUTOFF)
        assert result == {
            "kind": "synthetic",
            "observed_at": "2026-10-04T16:59:59.999999+00:00",
        }

    def test_full_history_without_cutoff_is_recorded(self):
        captured = CUTOFF - timedelta(days=6)
        result = bookmaker_history_provenance(captured_at=captured, cutoff=None)
        assert result == {
            "kind": "recorded",
            "observed_at": "2026-09-28T17:00:00+00:00",
        }

    @pytest.mark.parametrize(
        "offset",
        [
            timedelta(days=-2),
            timedelta(minutes=-1),
            timedelta(seconds=-1),
            timedelta(0),
            timedelta(seconds=1),
            timedelta(hours=5),
        ],
    )
    @pytest.mark.parametrize("cutoff", [CUTOFF, None])
    def test_kind_matches_the_routes_own_branch(self, offset, cutoff):
        captured = CUTOFF + offset
        result = bookmaker_history_provenance(captured_at=captured, cutoff=cutoff)
        expected = (
            "recorded" if _route_keeps_capture_minute(captured, cutoff) else "synthetic"
        )
        assert result is not None
        assert result["kind"] == expected


class TestTimezoneEquivalentInstants:
    def test_equal_instant_in_another_offset_is_recorded_and_keeps_its_own_offset(self):
        plus_two = timezone(timedelta(hours=2))
        captured = datetime(2026, 10, 4, 19, 0, 0, tzinfo=plus_two)  # == CUTOFF
        result = bookmaker_history_provenance(captured_at=captured, cutoff=CUTOFF)
        assert result == {
            "kind": "recorded",
            "observed_at": "2026-10-04T19:00:00+02:00",
        }

    def test_earlier_instant_with_a_later_wall_clock_is_synthetic(self):
        # 12:59 at UTC-4 is 16:59Z; the cutoff, 10:00 at UTC-7, is 17:00Z. The
        # capture's wall clock reads later, its instant is earlier.
        minus_four = timezone(timedelta(hours=-4))
        cutoff_local = datetime(
            2026, 10, 4, 10, 0, 0, tzinfo=timezone(timedelta(hours=-7))
        )  # == CUTOFF
        captured = datetime(2026, 10, 4, 12, 59, 0, tzinfo=minus_four)
        result = bookmaker_history_provenance(captured_at=captured, cutoff=cutoff_local)
        assert result == {
            "kind": "synthetic",
            "observed_at": "2026-10-04T12:59:00-04:00",
        }


class TestObservedAt:
    def test_is_the_original_capture_not_the_minute_truncated_or_cutoff_stamp(self):
        captured = datetime(2026, 10, 4, 16, 12, 37, 250000, tzinfo=timezone.utc)
        result = bookmaker_history_provenance(captured_at=captured, cutoff=CUTOFF)
        assert result is not None
        # The route would display this point at the cutoff minute (17:00); the
        # provenance keeps when the snapshot was actually captured.
        assert result["observed_at"] == captured.isoformat()
        assert (
            result["observed_at"] != CUTOFF.replace(second=0, microsecond=0).isoformat()
        )
        assert (
            result["observed_at"]
            != captured.replace(second=0, microsecond=0).isoformat()
        )

    def test_metadata_is_exactly_kind_and_observed_at(self):
        result = bookmaker_history_provenance(captured_at=CUTOFF, cutoff=None)
        assert result is not None
        assert set(result) == {"kind", "observed_at"}


class _NoAnswerTZ(tzinfo):
    def utcoffset(self, dt):
        return None

    def dst(self, dt):
        return None


class _ExplodingTZ(tzinfo):
    def utcoffset(self, dt):
        raise RuntimeError("tz database unavailable")

    def dst(self, dt):
        return None


class _AnswersOnceTZ(tzinfo):
    """Passes the aware check, then fails on the comparison/format that follows."""

    def __init__(self):
        self.calls = 0

    def utcoffset(self, dt):
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("tz database went away")
        return timedelta(0)

    def dst(self, dt):
        return None


class _ComparesAsEarlier:
    """Not an instant, but answers the reflected comparison instead of raising."""

    def __le__(self, other):
        return True

    def __ge__(self, other):
        return True


NAIVE = datetime(2026, 10, 4, 17, 0, 0)
INVALID_INSTANTS = [
    pytest.param(None, id="missing"),
    pytest.param(NAIVE, id="naive"),
    pytest.param(
        datetime(2026, 10, 4, 17, 0, tzinfo=_NoAnswerTZ()), id="tzinfo-without-offset"
    ),
    pytest.param(
        datetime(2026, 10, 4, 17, 0, tzinfo=_ExplodingTZ()), id="tzinfo-that-raises"
    ),
    pytest.param("2026-10-04T17:00:00+00:00", id="iso-string"),
    pytest.param(date(2026, 10, 4), id="date-not-datetime"),
    pytest.param(1791133200, id="epoch-int"),
    pytest.param(True, id="bool"),
    pytest.param(object(), id="object"),
    pytest.param(_ComparesAsEarlier(), id="compares-without-raising"),
]


class TestRefusal:
    @pytest.mark.parametrize("captured_at", INVALID_INSTANTS)
    @pytest.mark.parametrize("cutoff", [CUTOFF, None])
    def test_invalid_capture_refuses_without_raising(self, captured_at, cutoff):
        assert (
            bookmaker_history_provenance(captured_at=captured_at, cutoff=cutoff) is None
        )

    @pytest.mark.parametrize(
        "cutoff", [p for p in INVALID_INSTANTS if p.values[0] is not None]
    )
    def test_invalid_cutoff_refuses_without_raising(self, cutoff):
        assert bookmaker_history_provenance(captured_at=CUTOFF, cutoff=cutoff) is None

    def test_naive_cutoff_does_not_fall_back_to_full_history(self):
        # A naive cutoff is not "no cutoff": promoting it to recorded would invent evidence.
        before = CUTOFF - timedelta(hours=1)
        assert bookmaker_history_provenance(captured_at=before, cutoff=NAIVE) is None

    @pytest.mark.parametrize("cutoff", [CUTOFF, None])
    def test_tz_that_fails_after_the_aware_check_refuses_without_raising(self, cutoff):
        tz = _AnswersOnceTZ()
        captured = datetime(2026, 10, 4, 17, 0, tzinfo=tz)
        assert bookmaker_history_provenance(captured_at=captured, cutoff=cutoff) is None
        assert tz.calls >= 2  # the specimen really reached the second use

    def test_arguments_are_keyword_only(self):
        with pytest.raises(TypeError):
            bookmaker_history_provenance(CUTOFF, None)  # type: ignore[misc]


class TestInputsUnchangedAndPure:
    def test_inputs_are_not_mutated(self):
        captured = datetime(2026, 10, 4, 16, 12, 37, 250000, tzinfo=timezone.utc)
        cutoff = CUTOFF
        bookmaker_history_provenance(captured_at=captured, cutoff=cutoff)
        assert captured == datetime(
            2026, 10, 4, 16, 12, 37, 250000, tzinfo=timezone.utc
        )
        assert cutoff == datetime(2026, 10, 4, 17, 0, 0, tzinfo=timezone.utc)

    def test_module_imports_no_clock_io_or_app_code(self):
        tree = ast.parse(Path(projected_final_points.__file__).read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        assert imported == {"__future__", "datetime", "typing"}

    def test_helper_never_reads_the_clock(self):
        tree = ast.parse(Path(projected_final_points.__file__).read_text())
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert not called & {"now", "utcnow", "today", "time", "monotonic"}
