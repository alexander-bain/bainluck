"""#12252 item 3: a test file that writes a calendar date within 30 days of today, and never
controls the clock, fails here — before the calendar reaches that date and turns master red.

The class, twice in one week:
  * Nov 2 — `#4079`'s "by October 31" market name aged past its own date
    (`test_card_keeps_non_exclusive_field_raw_7586.py`);
  * Nov 6 — `OBS_FRESH` aged past a 48 h bound (`test_yardstick_pair.py`, shard 7).
Neither file read the clock itself: the product code they called did. So a date literal
near today, in a file with NO freeze, is the shape this refuses.

  near date   an ISO date (``2026-11-20``), a ``datetime(2026, 11, 20, ...)`` /
              ``date(...)`` call, or a full month-name date (``November 20``), within
              30 days either side of today.
  a freeze    ``freezegun`` / ``freeze_time`` / ``time_machine``, an explicit ``now=``,
              or a ``monkeypatch.setattr`` on a clock name (``now``, ``utcnow``,
              ``today``, ``time``, ``datetime``, ``clock``).

**The allowlist (`wall_clock_allowlist.txt`) is every file that ALREADY carried a date
from Oct 8, 2026 on when this guard landed** (404 files), each with a one-line reason
from a measurement: ``scripts/timebomb_confirm.py`` ran them at +1, +31 and +60 days on
2026-11-07. Listing every dated file, and not only today's near ones, is deliberate: the
window moves with the calendar, and a guard that pulled an old file in on the day its
date came near would turn master red with no code change — the very failure it exists
to stop. So the guard bites at authoring time: a NEW file, or a file not on the list,
that writes a near date without a freeze.

Fix a finding by freezing the clock in that file (the usual answer), or, when the date
is genuinely data that no clock reads, add the file to the allowlist with its reason.
A listed file that no longer exists fails, so the list cannot rot.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
TESTS = BACKEND / "tests"
ALLOWLIST = TESTS / "wall_clock_allowlist.txt"
WINDOW_DAYS = 30

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
_ISO = re.compile(r"(?<!\d)(20\d\d)-(\d\d)-(\d\d)(?!\d)")
_CTOR = re.compile(r"\b(?:datetime|date)\(\s*(20\d\d)\s*,\s*(\d{1,2})\s*,\s*(\d{1,2})")
_MONTH = re.compile(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s*(20\d\d))?", re.I)
_FREEZE = re.compile(
    r"freezegun|freeze_time|time_machine|\bnow\s*="
    r"|monkeypatch\.setattr\([^)\n]*\b(?:now|utcnow|today|time|_now|datetime|clock)\b"
)


def dates_in(source: str, year: int) -> list[dt.date]:
    out = []
    for y, m, d in _ISO.findall(source) + _CTOR.findall(source):
        try:
            out.append(dt.date(int(y), int(m), int(d)))
        except ValueError:
            pass
    for name, d, y in _MONTH.findall(source):
        try:
            out.append(dt.date(int(y) if y else year, MONTHS[name.lower()], int(d)))
        except ValueError:
            pass
    return out


def near_unfrozen(source: str, today: dt.date) -> list[dt.date]:
    """The near dates of a file that never controls the clock; [] when it is safe."""
    if _FREEZE.search(source):
        return []
    return sorted({d for d in dates_in(source, today.year) if abs((d - today).days) <= WINDOW_DAYS})


def allowlist() -> dict[str, str]:
    out = {}
    for line in ALLOWLIST.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            path, _, reason = line.partition("  ")
            out[path.strip()] = reason.strip()
    return out


def test_no_unlisted_file_writes_a_near_date_without_a_freeze():
    today = dt.datetime.now(dt.timezone.utc).date()
    listed = allowlist()
    found = {}
    for path in sorted(TESTS.rglob("*.py")):
        rel = str(path.relative_to(BACKEND))
        if rel in listed or path == Path(__file__):
            continue
        near = near_unfrozen(path.read_text(errors="replace"), today)
        if near:
            found[rel] = [str(d) for d in near[:3]]
    assert not found, (
        "These test files write a date within 30 days of today and never freeze the clock, so "
        "they can turn red when the calendar reaches it (#12252 item 3). Freeze the clock in the "
        "file (freezegun / time_machine / an explicit now= / monkeypatch the clock), or, if no "
        "clock ever reads the date, add the file to tests/wall_clock_allowlist.txt with a "
        f"one-line reason:\n{found}"
    )


def test_every_allowlist_entry_exists_and_gives_a_reason():
    for path, reason in allowlist().items():
        assert (BACKEND / path).is_file(), f"{path} is listed but gone — remove its line"
        assert reason, f"{path} has no reason"


# --- the guard's own control: red on an unpinned fixture, green once pinned ----------

TODAY = dt.date(2026, 11, 7)


def test_an_unpinned_near_dated_fixture_is_refused_in_every_spelling():
    for spelling in ('OBS_AT = "2026-11-05T12:00:00Z"',
                     "NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)",
                     'name = "Will it happen by November 30?"',
                     'name = "by October 31, 2026"'):
        assert near_unfrozen(spelling, TODAY), spelling


def test_the_same_fixture_passes_once_the_clock_is_frozen():
    fixture = 'OBS_AT = "2026-11-05T12:00:00Z"\n'
    for freeze in ("from freezegun import freeze_time\n",
                   "result = producer(rows, now=OBS_AT)\n",
                   'monkeypatch.setattr(module, "utcnow", lambda: OBS_AT)\n',
                   "import time_machine\n"):
        assert near_unfrozen(fixture + freeze, TODAY) == [], freeze


def test_dates_outside_the_window_or_not_dates_are_left_alone():
    for source in ('KICKOFF = "2026-08-01T00:00:00Z"', "datetime(2027, 3, 1)",
                   'version = "2026-11-99"', 'label = "May 2"', "sha = 1202611070"):
        assert near_unfrozen(source, TODAY) == [], source
