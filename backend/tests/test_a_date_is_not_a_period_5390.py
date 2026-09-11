"""#5390 (#5012 layer 2) — ESPN's PRE-GAME status detail must never be stored
as a period.

THE ROW. Production 2026-09-10, event ``14632820``, 49ers @ Rams, ``tier:1``
primetime, two minutes after kickoff at 0-0, sitting at rank 2 of Discover page
one badged **"Overtime"**::

    "status": "live", "home_score": 0, "away_score": 0,
    "espn": {"game_clock": "0:00",
             "period": "Thu, September 10th at 8:35 PM EDT",
             "broadcast": "Netflix"}

ESPN keeps its pre-game ``status_detail`` in place until the first in-game
update lands. `parse_game_progress` found ``"10th"`` in that sentence and read
it as period 10; period 10 of a four-quarter sport is overtime.

discover/043m fixed the READER (`utils/highlights.py`, #5012). This file is the
WRITER, handed to live under standing notice 41. The two are independent: if the
writer stops storing dates the reader's refusal simply stops firing.

WHY NOTHING CAUGHT IT. `_sanitize_period` already existed, and its comment
already said these strings "should not be stored as period values in
game_state". It was applied at ONE of six call sites. The other five copied
``ee.status_detail`` straight into a period column, and no test anywhere
exercised the helper — `test_the_helper_had_no_test_before_this_file` is not a
joke, it is the reason a five-site bypass survived.

THE SECOND SHAPE. ESPN writes the pre-game detail two ways, and the pattern only
knew the long one. Measured on production ``events.period``::

    'Thu, May 14th at 6:00 PM EDT'   16   <- caught by the month-name branch
    '5/23 - TBD'                      3   <- MISSED
    '5/22 - TBD'                      1   <- MISSED
    '5/24 - TBD'                      1   <- MISSED

`test_the_short_numeric_date_escapes_the_month_name_branch` carries the control
that separates the two designs: the same string IS missed by the old pattern.

WHY THE FIX REFUSES RATHER THAN BLANKS. ESPN is not the only writer of this
column — `mlb_sync` and `statpal_sync` write it too, and ESPN is the slowest of
the three, so it routinely still says "pre-game" while MLB already says
"Top 1st". Clearing on every refusal would trade a wrong answer for a missing
one. The rule is: refuse the date, keep whatever honest value is already there,
and clear only when OUR stored value is the same class of garbage — which makes
the column self-heal and is why this ship needs no data migration.

MEASURED POPULATION (production 2026-09-11, whole ``events`` table)::

    period holds a date    96 rows   (82 closed, 14 completed)
    live / scheduled        0 rows

Zero live rows is not a clean bill of health: the defect window is only from the
status flip to ESPN's first in-game update, a few minutes per game, so a
point-in-time scan can never see it. Sunday's NFL slate is the next exposure —
``"September 13th"`` parses as period 13.
"""

import re
from datetime import datetime, timedelta, timezone

import pytest

from app.services.espn_api import ESPNAPIService
from app.tasks.espn_sync import _sanitize_period
from app.utils.espn_helpers import update_event_fields_from_espn

from tests.test_espn_api_parsing import LIVE_EVENT


# --------------------------------------------------------------------------
# Payloads: the specimen, its two date shapes, and an honest control.
# --------------------------------------------------------------------------

def _with_detail(detail: str, *, state="in", name="STATUS_IN_PROGRESS") -> dict:
    """LIVE_EVENT re-stamped with one ESPN ``status.type.detail``."""
    payload = {k: v for k, v in LIVE_EVENT.items()}
    payload["status"] = {
        "type": {"name": name, "state": state, "detail": detail},
        "period": LIVE_EVENT["status"].get("period"),
        "displayClock": LIVE_EVENT["status"].get("displayClock"),
    }
    return payload


#: The exact string production served for event 14632820.
THE_SPECIMEN = "Thu, September 10th at 8:35 PM EDT"

#: The shape the month-name branch could not see.
THE_SHORT_FORM = "5/23 - TBD"

#: What ESPN sends once the first in-game update lands.
AN_HONEST_PERIOD = "14:50 - 1st Quarter"


#: Every distinct non-numeric ``events.period`` value measured on production
#: 2026-09-11, taken as one corpus. The four ``Final/N`` entries are the reason
#: the numeric-date branch demands a digit on BOTH sides of the slash.
THE_REAL_VOCABULARY = [
    "Final", "FT", "Final/10", "Final/7", "Final/OT", "Final/8", "Final/11",
    "Final/SO", "Final/12", "Final/2OT", "Final/13", "Final/14",
    "Bottom 5th", "Top 6th", "Top 5th", "Bottom 6th", "Bottom 4th", "End 5th",
    "Top 4th", "Top 7th", "Top 8th", "Bottom 7th", "Top 9th", "Bottom 3rd",
    "Bottom 1st", "Bottom 2nd", "Top 3rd", "Middle 6th", "Bottom 8th",
    "Bottom 9th",
    "Canceled", "In Progress", "Scheduled", "Postponed", "Suspended",
    "Halftime",
    "End of 3rd Period", "End of 4th Quarter", "End of 2nd Half", "End of OT",
    "1:59 - 1st Half", "0:00 - 2nd Half", "3:05 - 4th Quarter",
    "0:00 - 4th Quarter", "2:00 - 1st Half",
]


KICKOFF = datetime.now(timezone.utc) - timedelta(minutes=2)


class _Event:
    """The columns `update_event_fields_from_espn` reads and writes."""

    def __init__(self, *, period=None, status="live"):
        self.id = 14632820
        self.status = status
        self.home_team_name = "Los Angeles Rams"
        self.away_team_name = "San Francisco 49ers"
        self.commence_time = KICKOFF
        self.commence_time_source = "espn"
        self.completed_at = None
        self.game_clock = None
        self.period = period
        self.home_score = None
        self.away_score = None
        self.broadcast_info = None
        self.llm_importance = None


class _Session:
    def __init__(self):
        self.statements = []
        self.added = []

    async def execute(self, statement):
        self.statements.append(statement)
        return None

    def add(self, obj):
        self.added.append(obj)


async def _sync(payload, *, stored_period=None):
    """Run the real writer and hand back the row it wrote."""
    ee = ESPNAPIService()._parse_event(payload)
    event = _Event(period=stored_period)
    await update_event_fields_from_espn(_Session(), event, ee, set(), {})
    return event


# --------------------------------------------------------------------------
# The defect, exercised through the writer that caused it.
# --------------------------------------------------------------------------

class TestTheWriterRefusesADate:
    @pytest.mark.asyncio
    async def test_the_specimen_never_reaches_the_period_column(self):
        # The whole bug in one assertion: a live 0-0 row whose ESPN detail is
        # still the kickoff sentence keeps NOTHING in period, rather than a
        # date that downstream reads as period 10.
        event = await _sync(_with_detail(THE_SPECIMEN))
        assert event.period is None
        assert "September" not in (event.period or "")

    @pytest.mark.asyncio
    async def test_the_control_a_real_period_is_still_written(self):
        # The red half. If this fix were "stop writing period" the test above
        # would pass for the wrong reason.
        event = await _sync(_with_detail(AN_HONEST_PERIOD))
        assert event.period == AN_HONEST_PERIOD

    @pytest.mark.asyncio
    async def test_the_short_numeric_date_is_refused_too(self):
        event = await _sync(_with_detail(THE_SHORT_FORM))
        assert event.period is None

    @pytest.mark.asyncio
    async def test_a_real_period_from_another_writer_survives_espns_date(self):
        # mlb_sync got there first with "Top 1st"; ESPN is still pre-game.
        # Refusing must not blank what a faster writer already knew.
        event = await _sync(_with_detail(THE_SPECIMEN), stored_period="Top 1st")
        assert event.period == "Top 1st"

    @pytest.mark.asyncio
    async def test_a_stale_date_already_stored_is_cleared_not_frozen(self):
        # Self-heal: both sides are garbage, so the column empties on the next
        # sync. This is what makes the 96 production rows need no migration.
        event = await _sync(
            _with_detail(THE_SPECIMEN), stored_period="Thu, May 14th at 6:00 PM EDT"
        )
        assert event.period is None

    @pytest.mark.asyncio
    async def test_no_espn_opinion_leaves_the_column_alone(self):
        event = await _sync(_with_detail(""), stored_period="Top 1st")
        assert event.period == "Top 1st"


# --------------------------------------------------------------------------
# The helper, against the vocabulary it has to live with.
# --------------------------------------------------------------------------

class TestTheSanitizer:
    def test_the_helper_had_no_test_before_this_file(self):
        # Not decoration. `_sanitize_period` shipped with a comment describing
        # exactly the bug it failed to prevent at five of six call sites, and
        # nothing asserted its behaviour. Both date shapes, in one place.
        assert _sanitize_period(THE_SPECIMEN) is None
        assert _sanitize_period(THE_SHORT_FORM) is None
        assert _sanitize_period(AN_HONEST_PERIOD) == AN_HONEST_PERIOD
        assert _sanitize_period(None) is None
        assert _sanitize_period("") is None

    @pytest.mark.parametrize("period", THE_REAL_VOCABULARY)
    def test_the_measured_vocabulary_is_never_refused(self, period):
        # The false-positive guard, run against the real corpus rather than a
        # few strings chosen to pass. `Final/10` and `Final/2OT` are the ones
        # that would break a naive `\d/\d` widening.
        assert _sanitize_period(period) == period

    def test_the_short_numeric_date_escapes_the_month_name_branch(self):
        # The control that says the widening is load-bearing: the OLD pattern
        # accepts the string this ship exists to refuse. If someone narrows
        # `_PREGAME_DATE_RE` back, this fails while the tests above still pass.
        month_names_only = re.compile(
            r"\b(January|February|March|April|May|June|July|August|September"
            r"|October|November|December)\b",
            re.IGNORECASE,
        )
        assert month_names_only.search(THE_SPECIMEN)
        assert not month_names_only.search(THE_SHORT_FORM)
        assert _sanitize_period(THE_SHORT_FORM) is None

    def test_a_slash_needs_digits_on_both_sides(self):
        # Stated as a property, so widening the constant re-derives it.
        assert _sanitize_period("Final/10") == "Final/10"
        assert _sanitize_period("5/23 - TBD") is None


# --------------------------------------------------------------------------
# Completeness. This one is a SOURCE SCAN, not a behaviour test — it cannot
# prove the sanitized code runs (the tests above do that for the writer). Its
# job is the sixth call site nobody has added yet.
# --------------------------------------------------------------------------

class TestNoSiteCopiesTheDetailRaw:
    def test_no_period_field_is_assigned_the_raw_status_detail(self):
        from pathlib import Path

        import app.routes.admin_providers as admin_providers
        import app.utils.espn_helpers as espn_helpers

        raw = re.compile(
            r"period\s*=\s*(?:ee|espn_event)\.status_detail"
            r"|\.period\s*=\s*(?:ee|espn_event)\.status_detail"
        )
        offenders = []
        for module in (espn_helpers, admin_providers):
            source = Path(module.__file__).read_text()
            offenders += [
                f"{Path(module.__file__).name}:{n}: {line.strip()}"
                for n, line in enumerate(source.splitlines(), 1)
                if raw.search(line)
            ]
        assert offenders == [], (
            "a period field is being assigned ESPN's raw status_detail; route "
            "it through _sanitize_period (#5390):\n" + "\n".join(offenders)
        )

    def test_the_scan_would_catch_the_bug_it_was_written_for(self):
        # An empty-result scan is worthless without proof it can be non-empty.
        raw = re.compile(r"\.period\s*=\s*ee\.status_detail")
        assert raw.search("            ev.period = ee.status_detail")
