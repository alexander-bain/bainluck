"""A start time the venue has not announced yet is not a start time (#8841).

**SHIP: a playoff game whose start time is not announced shows its date and
"TBD", not a made-up "1:00 PM".** (Pillar: TRUTH.)

StatPal lists MLB postseason games before MLB has set their times. Measured at
the venue 2026-09-26 15:31Z (`/v1/mlb/season-schedule`): the regular season sits
in `tournament.match[]` with minute-precise UTC times (19:05, 23:10, 01:40 —
0 of 91 games on the hour), while the two Red Sox @ Yankees Wild Card games sit
in a separate `tournament.week[]` bucket ("MLB - Final") at `20:00` each. ESPN's
scoreboard for the same games says `timeValid=false`. StatPal carries no TBD
marker of its own, so the 20:00Z is its placeholder, and we printed it as a
real 1:00 PM PT first pitch.

The rule is deliberately narrow: an MLB `week[]` fixture, not started, whose
clock is exactly on the hour. It is MLB only because on-the-hour is the NORMAL
shape of a real NBA/NHL start (877 of 1208 NBA games, 1100 of 1327 NHL games),
so the same test there would hide real times.

The mark is stored as the instant it vouches for, not as a bare flag:
``provenance:start-placeholder:statpal:<YYYY-MM-DDTHH:MMZ>``. A reader says TBD
only while the row's ``commence_time`` still IS that instant, so any rail that
writes a real start (ESPN with a valid time, MLB, StatPal revising its own
stamp) retires the TBD by the act of writing, without having to know this tag
exists. The ``provenance:`` prefix is what `carry_provenance_tags` preserves
across the taxonomy task's wholesale ``event_tags`` replace.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

#: StatPal sports whose `week[]` bucket carries placeholder clocks. MLB only —
#: see the module note for why NBA/NHL cannot use the on-the-hour test.
STATPAL_PLACEHOLDER_START_SPORTS = frozenset({"mlb"})

START_PLACEHOLDER_TAG_PREFIX = "provenance:start-placeholder:statpal:"

_ON_THE_HOUR_RE = re.compile(r"^\s*\d{1,2}:00\s*$")
_TAG_INSTANT_FORMAT = "%Y-%m-%dT%H:%MZ"


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    return [value] if value else []


def statpal_placeholder_fixture_ids(data: Any, sport: str) -> frozenset[str]:
    """Ids of the fixtures in a StatPal schedule payload whose clock is a placeholder.

    Read from the payload rather than from the parsed fixtures because the
    parser flattens `match[]` and `week[]` into one list, and the bucket is the
    evidence.  Only the v1 season-schedule shape qualifies: a board that serves
    ``timezone`` or ``datetime_utc`` is a live board with a real local clock.
    """
    if sport not in STATPAL_PLACEHOLDER_START_SPORTS or not isinstance(data, dict):
        return frozenset()
    section = data.get("scores")
    tournament = section.get("tournament") if isinstance(section, dict) else None
    if not isinstance(tournament, dict):
        return frozenset()
    ids: set[str] = set()
    for week in _as_list(tournament.get("week")):
        if not isinstance(week, dict):
            continue
        for match in _as_list(week.get("match")):
            if not isinstance(match, dict):
                continue
            if match.get("datetime_utc") or match.get("timezone"):
                continue
            if str(match.get("status") or "").strip().lower() != "not started":
                continue
            if not _ON_THE_HOUR_RE.match(str(match.get("time") or "")):
                continue
            fixture_id = str(match.get("id") or "").strip()
            if fixture_id:
                ids.add(fixture_id)
    return frozenset(ids)


def _utc_minute(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(second=0, microsecond=0)


def start_placeholder_tag(instant: datetime) -> str:
    """The tag vouching that ``instant`` is a placeholder, not an announced start."""
    return START_PLACEHOLDER_TAG_PREFIX + _utc_minute(instant).strftime(_TAG_INSTANT_FORMAT)


def start_placeholder_tags(event_tags: Any) -> list[str]:
    """Every start-placeholder tag on a row, in stored order."""
    if not isinstance(event_tags, list):
        return []
    return [
        t for t in event_tags
        if isinstance(t, str) and t.startswith(START_PLACEHOLDER_TAG_PREFIX)
    ]


def start_is_tbd(
    event_tags: Any, commence_time: Optional[datetime], status: Optional[str]
) -> bool:
    """True when the row's start is a placeholder nobody has since replaced.

    Only a ``scheduled`` row can be TBD — once a game is live or final, it has
    started, whatever its stored stamp says.
    """
    if status != "scheduled" or commence_time is None:
        return False
    return start_placeholder_tag(commence_time) in start_placeholder_tags(event_tags)


def desired_start_placeholder_tags(
    *,
    fixture_is_placeholder: bool,
    fixture_start: Optional[datetime],
    commence_time: Optional[datetime],
) -> list[str]:
    """What the row's start-placeholder tags should be after a StatPal schedule read.

    The tag is written only while the row's stamp is StatPal's placeholder
    instant; a row another rail has moved gets none, whatever StatPal says.
    """
    if not fixture_is_placeholder or fixture_start is None or commence_time is None:
        return []
    if _utc_minute(fixture_start) != _utc_minute(commence_time):
        return []
    return [start_placeholder_tag(fixture_start)]


def needs_start_placeholder_write(
    event_tags: Any, desired: Iterable[str]
) -> bool:
    """Whether the stored start-placeholder tags differ from ``desired``."""
    return sorted(start_placeholder_tags(event_tags)) != sorted(desired)
