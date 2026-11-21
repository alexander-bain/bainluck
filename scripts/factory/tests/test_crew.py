from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crew import add_crew_week, add_day_replay


def test_week_counts_a_change_once_and_preserves_timed_visits_after_it_departs():
    now = "2026-11-21T14:03:00Z"
    first = "2026-11-21T13:00:00Z"
    second = "2026-11-21T13:20:00Z"
    finished = "2026-11-21T13:45:00Z"
    work = {"number": 13069, "builder": "F", "station": "Live", "live_at": finished}
    floor = {
        "generated_at": now,
        "changes": [
            {**work, "line": "Website", "journey": [
                {"station": "Test", "first_seen_at": first, "last_seen_at": second},
                {"station": "Ship", "first_seen_at": second, "last_seen_at": finished},
            ]},
            {**work, "line": "Apps", "journey": [
                {"station": "Test", "first_seen_at": first, "last_seen_at": second},
            ]},
            {"number": 13000, "builder": "F", "station": "Test", "line": "Apps"},
        ],
    }
    saved = add_crew_week(floor, [{"number": 13000, "created_at": first}])
    assert floor["crew_week"]["builders"]["F"] == {
        "changes": 1, "stations": ["Ship"], "hours": [5],
        "longest": {"number": 13000, "since": first},
    }

    tomorrow = {"generated_at": "2026-11-22T16:05:00Z", "changes": []}
    add_crew_week(tomorrow, [], saved)
    assert tomorrow["crew_week"]["builders"]["F"] == {
        "changes": 1, "stations": ["Ship"], "hours": [5],
    }
    monday = {"generated_at": "2026-11-23T08:00:00Z", "changes": []}
    add_crew_week(monday, [], saved)
    assert monday["crew_week"]["builders"]["F"]["changes"] == 0


def test_today_replays_a_move_after_it_ages_out_of_the_live_window():
    at = "2026-11-21T17:51:00Z"
    observed = "2026-11-21T18:00:00Z"
    move = {
        "number": 13295, "line": "Website", "from": "Review", "to": "Write",
        "at": at, "observed_at": observed,
    }
    first = {
        "generated_at": observed,
        "changes": [{"number": 13295, "builder": "W"}],
        "transitions": [move, {**move, "at": "2026-11-21T07:59:00Z"}],
        "events": [{"kind": "returned", "number": 13295, "line": "Website", "observed_at": observed}],
    }
    add_day_replay(first, {})
    events = first["day_replay"]["events"]
    assert len(events) == 1
    assert (events[0]["at"], events[0]["kind"], events[0]["builder"]) == (at, "returned", "W")
    later = {"generated_at": "2026-11-21T21:00:00Z", "changes": []}
    add_day_replay(later, first)
    assert later["day_replay"] == first["day_replay"]
    next_day = {"generated_at": "2026-11-22T08:00:00Z", "changes": []}
    add_day_replay(next_day, later)
    assert "day_replay" not in next_day
