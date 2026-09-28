"""#9341 — a multi-course venue reads as a list, not as DataGolf's raw ';' join.

Production 2026-09-28, /categories/golf THIS WEEK card:
"Old Course St. Andrews;Carnoustie;Kingsbarns Golf Links · 15 golfers with odds".
Seven tournaments in that day's /api/golf carried the ';'. Every specimen below is
a real DataGolf `course` value from that payload.
"""

import pytest

from app.routes.golf import _display_venue


@pytest.mark.parametrize("course,shown", [
    ("Old Course St. Andrews;Carnoustie;Kingsbarns Golf Links",
     "Old Course St. Andrews, Carnoustie, Kingsbarns Golf Links"),
    ("Pete Dye Stadium Course;Nicklaus Tournament Course;La Quinta Country Club",
     "Pete Dye Stadium Course, Nicklaus Tournament Course, La Quinta Country Club"),
    # two different courses that differ only in their parenthetical stay two
    ("Torrey Pines Golf Course (South Course);Torrey Pines Golf Course (North Course)",
     "Torrey Pines Golf Course (South Course), Torrey Pines Golf Course (North Course)"),
    # the same course listed twice, once with its par, is one course
    ("Royal Johannesburg East Course;Royal Johannesburg East Course (Par 70)",
     "Royal Johannesburg East Course"),
    # single-course venues are untouched
    ("TPC Sawgrass", "TPC Sawgrass"),
    ("Sea Island Golf Club (Seaside Course)", "Sea Island Golf Club (Seaside Course)"),
    (" Pebble Beach Golf Links ; Spyglass Hill Golf Course ;",
     "Pebble Beach Golf Links, Spyglass Hill Golf Course"),
    ("", ""),
    (None, ""),
])
def test_venue_reads_as_a_list(course, shown):
    assert _display_venue(course) == shown
    assert ";" not in _display_venue(course)


def test_the_schedule_serves_the_display_form():
    import inspect

    from app.routes import golf

    src = inspect.getsource(golf)
    assert '"venue": _display_venue(t.course)' in src
    assert '"venue": t.course or ""' not in src
