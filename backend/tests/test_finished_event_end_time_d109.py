"""D109 — a results list is ordered by when games ENDED, so the end must travel.

THE DEFECT, MEASURED ON PRODUCTION (2026-09-10, the 36 hours around the NFL
season opener):

    finished events            116
    with statpal_end_time        0     <- the only end time in the payload
    with completed_at          116
    fallback would serve       116
    still unordered              0

`ended_at` is built from StatPal alone, and StatPal had supplied an end time for
NOT ONE finished row. So the key was absent on every finished card, and
`buildFinishedSection` on /sports ordered "what just happened" by
`commence_time` — the wrong end of the game.

What that cost at T+30 on the opener (03:56Z), with the section's cap at 4:

    by completed_at                     by commence_time (what shipped)
    1 Seahawks   ended 03:26:32Z        1 Chicago Fire     began 00:30Z
    2 Royals     ended 03:03:05Z        2 Houston Dynamo   began 00:30Z
    3 White Sox  ended 02:44:04Z        3 Austin FC        began 00:30Z
    4 Chi Fire   ended 02:39:07Z        4 Minnesota Utd    began 00:30Z
                                        6 Seahawks         began 00:20Z  <- cut

The final had ENDED more recently than anything on the board and STARTED behind
eight fixtures that kicked off ten minutes later and finished fifty minutes
earlier. An NFL game runs 3h+; that is the whole mechanism.

Every anchor here is offset from an injected clock and never branches on the
real one (gotcha #44).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.odds_polling import get_statpal_end_time
from app.utils.event_completion import finished_event_end_time, statpal_end_time


NOW = datetime(2026, 9, 10, 3, 56, 0, tzinfo=timezone.utc)  # T+30 on the opener


class _Event:
    """Only the attributes the helpers read, so a shape change here is loud."""

    def __init__(self, *, statpal_end=None, sources=None, completed_at=None):
        self.statpal_end_time = statpal_end
        self.win_probability_sources = sources
        self.completed_at = completed_at


# ── the fallback itself ──────────────────────────────────────────────────────


def test_completed_at_is_used_when_statpal_never_reported_an_end():
    """The 116-of-116 case. Before D109 this returned None and the key vanished."""
    ended = NOW - timedelta(minutes=30)
    event = _Event(completed_at=ended)

    assert statpal_end_time(event) is None, "control: StatPal has nothing"
    assert finished_event_end_time(event) == ended


def test_statpal_outranks_completed_at_because_it_is_an_observation():
    """completed_at is a processing timestamp (gotcha #22); StatPal watched it."""
    observed = NOW - timedelta(minutes=40)
    written = NOW - timedelta(minutes=5)
    event = _Event(statpal_end=observed, completed_at=written)

    assert finished_event_end_time(event) == observed


def test_the_jsonb_mirror_counts_as_a_statpal_reading():
    observed = NOW - timedelta(minutes=40)
    event = _Event(
        sources={"statpal_end_time": observed.isoformat()},
        completed_at=NOW,
    )

    assert finished_event_end_time(event) == observed


def test_an_unparseable_jsonb_end_falls_through_rather_than_raising():
    """A bad string must not take down a feed build (gotcha #42)."""
    event = _Event(sources={"statpal_end_time": "not a date"}, completed_at=NOW)

    assert statpal_end_time(event) is None
    assert finished_event_end_time(event) == NOW


def test_no_end_anywhere_is_None_not_an_invented_time():
    """Absence stays absence — the key is present-only for exactly this reason."""
    assert finished_event_end_time(_Event()) is None


# ── the ordering this exists to make possible ────────────────────────────────


def test_the_nfl_final_leads_by_END_and_is_cut_by_START():
    """The production specimen, both orderings, with the cap applied.

    This is the whole ship in one assertion pair: the same eight rows, ordered
    by the two clocks, put a different set of four on the page.
    """
    CAP = 4  # FINISHED_SECTION_CAP
    # (label, commence, completed) — real values, 2026-09-10.
    rows = [
        ("seahawks_nfl_final", "00:20", "03:26:32"),
        ("royals", "23:40", "03:03:05"),
        ("white_sox", "23:40", "02:44:04"),
        ("chicago_fire", "00:30", "02:39:07"),
        ("houston_dynamo", "00:30", "02:38:07"),
        ("atletico_goianiense", "00:29", "02:37:55"),
        ("austin_fc", "00:30", "02:37:05"),
        ("minnesota_united", "00:30", "02:36:06"),
    ]

    def _at(hhmmss, *, previous_day):
        h, m, *rest = (int(p) for p in hhmmss.split(":"))
        s = rest[0] if rest else 0
        day = 9 if previous_day else 10
        return datetime(2026, 9, day, h, m, s, tzinfo=timezone.utc)

    built = [
        (
            label,
            _at(commence, previous_day=commence.startswith("23")),
            _at(completed, previous_day=False),
        )
        for label, commence, completed in rows
    ]

    by_end = [r[0] for r in sorted(built, key=lambda r: r[2], reverse=True)][:CAP]
    by_start = [r[0] for r in sorted(built, key=lambda r: r[1], reverse=True)][:CAP]

    assert by_end[0] == "seahawks_nfl_final", "ordered by END it leads"
    assert "seahawks_nfl_final" not in by_start, (
        "ordered by START the cap cuts it — this is the reported bug"
    )


def test_completed_at_ties_are_real_so_callers_must_break_them():
    """Three MLS rows shared 04:45:41.647571 to the microsecond — one sweep.

    Pinned because a sort that trusts this column to be unique will order a
    batch arbitrarily, and 'arbitrary' is not stable across runs.
    """
    batched = datetime(2026, 9, 10, 4, 45, 41, 647571, tzinfo=timezone.utc)
    portland = _Event(completed_at=batched)
    vancouver = _Event(completed_at=batched)
    lafc = _Event(completed_at=batched)

    ends = {
        finished_event_end_time(e) for e in (portland, vancouver, lafc)
    }
    assert ends == {batched}, "one instant for three different games"


# ── the alias must stay an alias ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "event",
    [
        _Event(statpal_end=NOW),
        _Event(sources={"statpal_end_time": NOW.isoformat()}),
        _Event(sources={"statpal_end_time": "not a date"}),
        _Event(completed_at=NOW),
        _Event(),
    ],
)
def test_odds_polling_alias_agrees_with_the_shared_reader(event):
    """`get_statpal_end_time` delegates; it must never drift into a 2nd reading.

    Note it is the STATPAL reader, not the fallback — the staleness net that
    calls it is asking "did a source watch this end?", and `completed_at` is
    that net's own output, so feeding it back in would be circular.
    """
    assert get_statpal_end_time(event) == statpal_end_time(event)


def test_the_alias_does_not_quietly_acquire_the_completed_at_fallback():
    """The regression that would make the staleness net grade its own writes."""
    event = _Event(completed_at=NOW)

    assert get_statpal_end_time(event) is None
    assert finished_event_end_time(event) == NOW
