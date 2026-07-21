"""Horizon Sentinel pure-logic tests (Queue #223 Item 1).

Live HTTP page-checks + httpx filing are exercised via the admin inline endpoint
(POST /api/admin/horizon-sentinel/run?inline=true), NOT here. These test the
pure calendar/phase/severity/rendering logic with an injected ``now``.

The Celery task ``horizon_sentinel`` registered in app.tasks shadows the module
name, so import the module via importlib (mirrors test_grid_sentinel)."""

import importlib
from datetime import date

hs = importlib.import_module("app.tasks.horizon_sentinel")


def _entry(**over):
    base = {
        "name": "Test Major 2026",
        "slug": "test-major-2026",
        "concept_key": "event:cycling:test-major-2026",
        "domain": "cycling",
        "start": "2026-07-04",
        "end": "2026-07-26",
        "archetype": "winner_field",
        "marquee": True,
        "date_confidence": "confirmed",
    }
    base.update(over)
    return base


class TestPhase:
    def test_in_progress_when_today_inside_window(self):
        assert hs.horizon_phase(_entry(), date(2026, 7, 21)) == "in_progress"

    def test_in_progress_on_boundaries(self):
        assert hs.horizon_phase(_entry(), date(2026, 7, 4)) == "in_progress"
        assert hs.horizon_phase(_entry(), date(2026, 7, 26)) == "in_progress"

    def test_past_after_window(self):
        assert hs.horizon_phase(_entry(), date(2026, 7, 27)) == "past"

    def test_t7_within_seven_days(self):
        assert hs.horizon_phase(_entry(), date(2026, 6, 28)) == "t7"  # 6 days out

    def test_t14_between_eight_and_fourteen(self):
        assert hs.horizon_phase(_entry(), date(2026, 6, 24)) == "t14"  # 10 days out

    def test_t30_between_fifteen_and_thirty(self):
        assert hs.horizon_phase(_entry(), date(2026, 6, 10)) == "t30"  # 24 days out

    def test_future_beyond_thirty(self):
        assert hs.horizon_phase(_entry(), date(2026, 5, 1)) == "future"

    def test_missing_start_is_future(self):
        assert hs.horizon_phase(_entry(start=None), date(2026, 7, 21)) == "future"


class TestSeverity:
    def test_in_progress_marquee_is_p0(self):
        assert hs.severity_for(_entry(marquee=True), "in_progress") == "p0"

    def test_in_progress_non_marquee_is_p1(self):
        assert hs.severity_for(_entry(marquee=False), "in_progress") == "p1"

    def test_t7_marquee_is_p1_non_marquee_p2(self):
        assert hs.severity_for(_entry(marquee=True), "t7") == "p1"
        assert hs.severity_for(_entry(marquee=False), "t7") == "p2"

    def test_t30_is_p3(self):
        assert hs.severity_for(_entry(), "t30") == "p3"

    def test_future_and_past_are_none(self):
        assert hs.severity_for(_entry(), "future") is None
        assert hs.severity_for(_entry(), "past") is None


class TestClassifyEntry:
    def test_in_progress_no_page_files_p0(self):
        f = hs.classify_entry(_entry(), date(2026, 7, 21), has_page=False)
        assert f is not None
        assert f["severity"] == "p0"
        assert f["phase"] == "in_progress"
        assert "no live page" in f["detail"]

    def test_has_page_is_green_no_finding(self):
        assert hs.classify_entry(_entry(), date(2026, 7, 21), has_page=True) is None

    def test_out_of_window_no_finding(self):
        assert hs.classify_entry(_entry(), date(2026, 5, 1), has_page=False) is None
        assert hs.classify_entry(_entry(), date(2026, 7, 27), has_page=False) is None

    def test_t14_marquee_no_page_is_p1(self):
        f = hs.classify_entry(_entry(), date(2026, 6, 24), has_page=False)
        assert f["severity"] == "p1"
        assert f["phase"] == "t14"


class TestFingerprintAndRendering:
    def test_fingerprint_is_stable_and_slug_scoped(self):
        fp1 = hs.horizon_fingerprint("tour-de-france-2026")
        fp2 = hs.horizon_fingerprint("tour-de-france-2026")
        fp3 = hs.horizon_fingerprint("the-open-2026")
        assert fp1 == fp2 and fp1 != fp3
        assert len(fp1) == 12

    def test_body_has_fingerprint_and_sections(self):
        f = hs.classify_entry(_entry(), date(2026, 7, 21), has_page=False)
        body = hs.build_horizon_issue_body(f)
        assert f"horizon-sentinel-fingerprint:{hs.horizon_fingerprint(f['slug'])}" in body
        assert "What to build" in body
        assert "IN PROGRESS" in body

    def test_p0_title_carries_marker(self):
        f = hs.classify_entry(_entry(), date(2026, 7, 21), has_page=False)
        title = hs.build_horizon_issue_title(f)
        assert title.startswith("[Horizon] P0 ")


class TestCalendarFile:
    def test_shipped_calendar_loads_and_contains_tdf(self):
        entries = hs.load_calendar()
        assert isinstance(entries, list) and len(entries) >= 5
        slugs = {e.get("slug") for e in entries}
        assert "tour-de-france-2026" in slugs
        tdf = next(e for e in entries if e["slug"] == "tour-de-france-2026")
        assert tdf["concept_key"] == "event:cycling:tour-de-france-2026"
        assert tdf["marquee"] is True

    def test_every_entry_has_required_fields(self):
        for e in hs.load_calendar():
            assert e.get("slug") and e.get("name")
            assert e.get("start") is not None
            assert "marquee" in e

    def test_missing_file_returns_empty(self):
        assert hs.load_calendar("/nonexistent/path/majors_calendar.yaml") == []
