"""Guard for the self-check feed parser (Queue #193 Item 3, CLAUDE.md L1-L4
matching-table freshness note).

The Discover feed returns a nested `items[].data` shape with a `type`
discriminator ('event' / 'futures' / 'tournament' / 'concept'). Only 'event'
cards carry game fields (home_team/away_team/sport); the others have sport=None
or no sport key. The old parser iterated every item and read ev.get("sport")
on non-event cards, which rendered every self-check row as `? @ ?` and made the
L1-L4 audit unrunnable. get_feed_events must filter to type == 'event'.
"""

import scripts.audit_event_matching as aem


_MIXED_FEED = {
    "items": [
        {
            "type": "event",
            "data": {
                "id": 1,
                "sport": "basketball_nba",
                "home_team": "Celtics",
                "away_team": "Knicks",
                "status": "live",
            },
        },
        {
            "type": "event",
            "data": {
                "id": 2,
                "sport": "baseball_mlb",
                "home_team": "Rays",
                "away_team": "Red Sox",
                "status": "completed",
            },
        },
        # futures cards leak through the old status filter (status='open') but
        # have sport=None and no teams -> the `? @ ?` rows we must exclude.
        {
            "type": "futures",
            "data": {
                "id": 3,
                "sport": None,
                "name": "Will the U.S. confirm aliens exist?",
                "status": "open",
            },
        },
        {"type": "tournament", "data": {"name": "The Open Championship"}},
        {"type": "concept", "data": {"name": "Fight Night", "status": "upcoming"}},
    ]
}


def test_get_feed_events_returns_only_event_cards(monkeypatch):
    monkeypatch.setattr(aem, "api_get", lambda path: _MIXED_FEED)
    events = aem.get_feed_events()
    # only the two type=='event' cards, never futures/tournament/concept
    assert len(events) == 2
    assert {e["id"] for e in events} == {1, 2}
    # every returned event carries real game fields — no `? @ ?` rows
    for e in events:
        assert e.get("home_team")
        assert e.get("away_team")
        assert e.get("sport")


def test_get_feed_events_excludes_non_event_types(monkeypatch):
    monkeypatch.setattr(aem, "api_get", lambda path: _MIXED_FEED)
    events = aem.get_feed_events()
    names = {e.get("name") for e in events}
    # the futures/tournament/concept names must never appear
    assert "Will the U.S. confirm aliens exist?" not in names
    assert "The Open Championship" not in names
    assert "Fight Night" not in names


def test_get_feed_events_sport_filter_still_works(monkeypatch):
    monkeypatch.setattr(aem, "api_get", lambda path: _MIXED_FEED)
    events = aem.get_feed_events(sport="baseball_mlb")
    assert [e["id"] for e in events] == [2]
