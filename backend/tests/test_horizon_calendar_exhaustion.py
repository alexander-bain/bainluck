"""LAT-P181 — the calendar reminder, out of the blocking suite and into an issue.

`tests/test_competition_identity.py` asserted that the Masters' next edition
started `2027-04-08`. That was TRUE, and it was a **bomb**: `majors_calendar.yaml`
is a forward horizon file whose last Masters entry ends 2027-04-11, so the
assertion was measured to go red on 2027-04-12 with no code change. On
2026-08-31 the identical shape — a literal aged past a rolling bound — took
`backend-tests (2)` red, skipped `deploy`, and cost fifteen hours with thirteen
certified branches stacked behind it.

**Blocking a deploy on a date: never. A date-based reminder: legitimate.** The
intent behind that literal was "keep the majors calendar populated", which is
worth knowing and is not worth an outage. These pin the relocation:

* the detector fires early enough to be planning rather than an emergency;
* it does not fire on a calendar that is comfortably stocked;
* it cannot go red on a date — it RETURNS findings, and the caller files them;
* an entry it cannot read is reported, never silently treated as fine.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

# NOT `from app.tasks import horizon_sentinel` — `app/tasks/__init__.py` binds
# that name to the Celery TASK, so the import silently yields a task object and
# every lookup below fails as `'horizon_sentinel' object has no attribute ...`.
import app.tasks.horizon_sentinel as hs

TODAY = date(2026, 9, 1)


def _entry(competition, slug, end, **kw):
    return {
        "competition": competition,
        "slug": slug,
        "name": f"{competition} {slug}",
        "domain": "golf",
        "start": end,
        "end": end,
        **kw,
    }


def test_a_competition_whose_last_edition_is_near_is_reported():
    out = hs.competitions_running_out(
        [_entry("the-masters", "masters-2027", TODAY + timedelta(days=30))], TODAY
    )
    assert [f["competition"] for f in out] == ["the-masters"]
    assert out[0]["days_left"] == 30
    assert "no edition of" in out[0]["detail"]


def test_a_well_stocked_calendar_reports_nothing():
    """The control. A detector that fires on everything is not a detector."""
    assert (
        hs.competitions_running_out(
            [_entry("the-masters", "masters-2028", TODAY + timedelta(days=400))], TODAY
        )
        == []
    )


def test_only_the_LAST_edition_counts():
    """A near-term edition is not exhaustion if a later one exists.

    Without this the detector would fire on every competition that happens to
    have an event this month, which is most of them, and a reminder that fires
    constantly is one nobody reads.
    """
    entries = [
        _entry("the-masters", "masters-2027", TODAY + timedelta(days=5)),
        _entry("the-masters", "masters-2028", TODAY + timedelta(days=370)),
    ]
    assert hs.competitions_running_out(entries, TODAY) == []


def test_an_already_expired_calendar_is_reported_MORE_urgently():
    out = hs.competitions_running_out(
        [_entry("the-masters", "masters-2026", TODAY - timedelta(days=10))], TODAY
    )
    assert out[0]["days_left"] == -10
    assert out[0]["severity"] == "p1", "past the end is worse than approaching it"


def test_an_undated_entry_is_reported_not_skipped():
    """Gotcha #53 — an entry this cannot read is not an entry that is fine.

    Sorted FIRST, because "cannot tell" is more urgent than "90 days", not less.
    """
    entries = [
        _entry("giro-ditalia", "giro-2027", TODAY + timedelta(days=40)),
        _entry("the-masters", "masters-????", None),
    ]
    out = hs.competitions_running_out(entries, TODAY)
    assert [f["competition"] for f in out] == ["the-masters", "giro-ditalia"]
    assert out[0]["days_left"] is None
    assert out[0]["severity"] == "p1"


def test_findings_are_sorted_soonest_first():
    entries = [
        _entry("a", "a-1", TODAY + timedelta(days=80)),
        _entry("b", "b-1", TODAY + timedelta(days=5)),
        _entry("c", "c-1", TODAY + timedelta(days=40)),
    ]
    assert [f["competition"] for f in hs.competitions_running_out(entries, TODAY)] == [
        "b",
        "c",
        "a",
    ]


def test_the_lead_window_is_a_parameter_and_is_load_bearing():
    entries = [_entry("the-masters", "masters-2027", TODAY + timedelta(days=120))]
    assert hs.competitions_running_out(entries, TODAY) == []
    assert hs.competitions_running_out(entries, TODAY, lead_days=200)


def test_the_fingerprint_is_stable_and_distinct_from_the_needs_page_one():
    """One issue per competition, reused every year the dates run out again.

    It must NOT collide with `horizon_fingerprint`, or an exhaustion notice would
    silently comment on an unrelated needs-page issue for the same slug.
    """
    assert hs.exhaustion_fingerprint("the-masters") == hs.exhaustion_fingerprint("the-masters")
    assert hs.exhaustion_fingerprint("the-masters") != hs.exhaustion_fingerprint("giro-ditalia")
    assert hs.exhaustion_fingerprint("the-masters") != hs.horizon_fingerprint("the-masters")


def test_the_issue_body_carries_the_dedupe_key_and_the_action():
    finding = hs.competitions_running_out(
        [_entry("the-masters", "masters-2027", TODAY + timedelta(days=30))], TODAY
    )[0]
    body = hs.build_exhaustion_issue_body(finding)
    assert hs.exhaustion_fingerprint("the-masters") in body
    assert "majors_calendar.yaml" in body
    assert "the-masters" in hs.build_exhaustion_issue_title(finding)


# --- The rule this exists to enforce ------------------------------------------


def test_the_detector_can_never_take_a_deploy_down():
    """🔴 THE POINT OF THE WHOLE RELOCATION, pinned as an executable claim.

    Every input — a stocked calendar, an exhausted one, an unreadable one, an
    empty one — must RETURN. If any of these raised or asserted, the reminder
    would be back in the blocking suite wearing a different hat.
    """
    for entries in (
        [],
        [_entry("a", "a-1", TODAY + timedelta(days=400))],
        [_entry("a", "a-1", TODAY - timedelta(days=4000))],
        [_entry("a", "a-1", None)],
        [{"slug": "orphan-with-no-competition", "end": None}],
        [{}],
    ):
        assert isinstance(hs.competitions_running_out(entries, TODAY), list)


@pytest.mark.parametrize("day", [date(2026, 1, 1), date(2027, 4, 12), date(2031, 12, 31)])
def test_the_detector_gives_the_same_answer_shape_at_every_clock(day):
    """`today` is a PARAMETER, not a read of the clock.

    That is what makes this testable at any instant and unable to surprise
    anyone on a date nobody chose — the property the assertion it replaced did
    not have.
    """
    out = hs.competitions_running_out(
        [_entry("the-masters", "masters-2027", date(2027, 4, 11))], day
    )
    assert isinstance(out, list)
    if out:
        assert out[0]["days_left"] == (date(2027, 4, 11) - day).days
