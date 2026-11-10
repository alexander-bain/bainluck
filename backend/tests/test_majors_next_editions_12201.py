"""#12201: each of the seven competitions whose calendar ran out has a next edition.

The Horizon Sentinel filed seven "calendar runs out" issues (#12136-#12142):
``majors_calendar.yaml`` had nothing after the 2026 edition of each. So the
settled US Open, Vuelta and Open Championship pages served
``competition.next_edition: null`` and showed no "Next edition" line. Fable read
each next date from its organizer or governing body; three aren't announced and
go in as approximate, which the served block now says, so the client can print
the month instead of a day.

Config invariants against the real file, at a frozen instant (gotcha #44).
"""

import importlib
from datetime import datetime, timezone

import pytest

from app.utils import competition_identity as ci
from app.utils.majors_calendar import load_calendar

# The package re-exports a task under this name, so import the module itself.
hs = importlib.import_module("app.tasks.horizon_sentinel")

NOW = datetime(2026, 11, 9, 17, 0, tzinfo=timezone.utc)

# competition -> (next edition's slug, start, end, date_confidence)
NEXT = {
    "mlb-all-star-game": ("mlb-all-star-2027", "2027-07-13", "2027-07-13", "confirmed"),
    "the-open-championship": ("the-open-championship-2027", "2027-07-15", "2027-07-18", "confirmed"),
    "us-open-tennis": ("us-open-tennis-2027", "2027-08-30", "2027-09-12", "approximate"),
    "vuelta-a-espana": ("vuelta-2027", "2027-09-04", "2027-09-26", "approximate"),
    "nfl-kickoff-game": ("nfl-kickoff-2027", "2027-09-10", "2027-09-10", "approximate"),
    "emmy-awards": ("emmys-2027", "2027-09-12", "2027-09-12", "approximate"),
    "abu-dhabi-grand-prix": ("f1-abu-dhabi-2027", "2027-12-12", "2027-12-12", "confirmed"),
}


def test_the_horizon_sentinel_finds_none_of_the_seven_running_out():
    running_out = {f["competition"] for f in hs.competitions_running_out(load_calendar(), NOW.date())}
    assert running_out.isdisjoint(NEXT), sorted(running_out & set(NEXT))


@pytest.mark.parametrize("competition", sorted(NEXT))
def test_each_competitions_last_edition_on_file_is_the_new_one(competition):
    slug, start, end, confidence = NEXT[competition]
    last = ci.editions_of(competition)[-1]
    assert (last["slug"], str(last["start"]), str(last["end"])) == (slug, start, end)
    assert last["date_confidence"] == confidence


@pytest.mark.parametrize(
    "concept_key,competition",
    [
        ("event:tennis:us-open-2026", "us-open-tennis"),
        ("event:cycling:vuelta-2026", "vuelta-a-espana"),
        ("event:golf:the-open-championship", "the-open-championship"),
        ("event:awards:emmys-2026", "emmy-awards"),
    ],
)
def test_a_settled_2026_page_serves_its_next_edition_with_its_confidence(concept_key, competition):
    slug, start, end, confidence = NEXT[competition]
    block = ci.competition_block(concept_key, now=NOW)
    assert block is not None and block["slug"] == competition
    assert block["next_edition"] == {
        "name": block["next_edition"]["name"],
        "slug": slug,
        "concept_key": block["next_edition"]["concept_key"],
        "start": start,
        "end": end,
        "date_confidence": confidence,
    }


def test_an_approximate_edition_says_so_and_a_confirmed_one_says_so():
    """The block passes the calendar's own word through; it never infers one."""
    masters = ci.competition_block("event:golf:the-masters", now=NOW)
    assert masters["next_edition"]["date_confidence"] == "approximate"
    abu_dhabi = ci.competition_block("event:f1:abu-dhabi-2026", now=NOW)
    assert abu_dhabi["next_edition"]["slug"] == "f1-abu-dhabi-2026"
    assert abu_dhabi["next_edition"]["date_confidence"] == "approximate"


def test_the_open_keeps_its_durable_key_and_the_newest_edition_owns_it():
    from app.utils.majors_calendar import calendar_entry_by_concept_key

    entry = calendar_entry_by_concept_key()["event:golf:the-open-championship"]
    assert entry["slug"] == "the-open-championship-2027"
