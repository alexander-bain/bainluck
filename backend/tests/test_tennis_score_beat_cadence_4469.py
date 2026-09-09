"""#4469 — the tennis score beat's cadence, and the class of bug that set it.

THE DEFECT WAS NOT A WRONG NUMBER, IT WAS TWO NUMBERS. `sync-tennis-from-espn`
shipped `crontab(minute="*/10")` with a comment directly above it arguing `*/5`,
both written in the same commit (`9a6a014c`, lane1/057 STEP 0). Nothing was red:
the entry was internally valid, the wiring allowlist checks names and not
cadences, and the only numeric guard on it — `SWEEP_WINDOW_COFIRE_CEILING` — is
a *ceiling*, so it stays quiet when a beat fires LESS than it could. A cadence
can therefore be half what its own reasoning says for a week and no test moves.

It was reader-visible, which is the whole reason this file exists rather than a
comment. Alex's wife used the site during Shelton-Alcaraz and said the score was
lagging the probability. live/122 reproduced it on production with a 15 s
sampler, 95 polls / 0 failures, on event 15307447 (Andreeva v Gauff):

    score stamp age (`linescore.observed_at`)   median 482.9 s   p90 596.7 s   max 629.2 s
    price stamp age (freshest source)           median   8.4 s   p90  31.4 s   max  36.7 s

The hero probability moved >=2% four times in that window and the score never
moved once. The 629 s max is this crontab plus runtime — so the crontab is the
term that sets the ceiling, and it is the term this fixes.

WHY 300 s AND NOT LOWER. The beat's own comment argues it: five minutes is a
wide margin under the standing "nothing the authority knows about is wrong for
more than an hour" bar, and it stays deliberately SLOWER than `tournament_slate`'s
three-minute read of the same ESPN scoreboard, because the slate renders the live
card while this writes the durable row. Tightening past the slate would invert
that and is a different decision from this one. The assertion is an upper bound
on the period for exactly that reason: it fails the regression (going slower)
and stays quiet if a later lane argues its way tighter.

NOT ASSERTED HERE, DELIBERATELY: that the score is fresh on the page. The green
`live · Ns ago` badge reports the PRICE's age (`freshestSourceStamp` never reads
`linescore.observed_at`) and is live/122's under #4469; and outside tennis the
score carries no stamp at all, so its lag is not measurable. A test here that
claimed page freshness would be claiming something this beat cannot deliver
alone.
"""

from celery.schedules import crontab

from app.tasks import celery_app

#: The bound the cadence argument commits to, in seconds. `*/5` on a crontab.
TENNIS_SYNC_MAX_PERIOD_S = 300.0

BEAT_NAME = "sync-tennis-from-espn"


def _entry():
    schedule = celery_app.conf.beat_schedule
    assert BEAT_NAME in schedule, (
        f"{BEAT_NAME} is not in the beat schedule at all. If it was renamed, "
        "this guard and the co-fire census in test_settlement_sweep_beat.py "
        "both need re-pointing — do not delete either."
    )
    return schedule[BEAT_NAME]


def _crontab_period_s(schedule) -> float:
    """The longest gap between two fires of a minute-only crontab, in seconds.

    Derived from the minutes the crontab actually fires on rather than parsed
    out of the `*/N` spelling, so `minute="0,5,10,..."` and `minute="*/5"` are
    graded the same and an uneven set is graded by its WORST gap, not its best.
    """
    minutes = sorted(schedule.minute)
    assert minutes, "a crontab that fires on no minute never runs"
    if len(minutes) == 1:
        return 3600.0
    gaps = [b - a for a, b in zip(minutes, minutes[1:])]
    gaps.append(minutes[0] + 60 - minutes[-1])  # the wrap across the hour
    return max(gaps) * 60.0


class TestTheTennisScoreBeatFiresAtTheCadenceItArgues:
    def test_the_period_is_at_most_five_minutes(self):
        """The regression direction. `*/10` fails this at 600 s."""
        schedule = _entry()["schedule"]
        period = _crontab_period_s(schedule)
        assert period <= TENNIS_SYNC_MAX_PERIOD_S, (
            f"{BEAT_NAME} fires every {period:.0f} s, over the {TENNIS_SYNC_MAX_PERIOD_S:.0f} s "
            "its own comment argues for. The score stamp measured 483 s median / 629 s "
            "max against an 8.4 s price stamp at the old cadence (#4469). Either bring "
            "the cadence back or move the argument, but do not leave them disagreeing."
        )

    def test_the_worst_gap_is_measured_not_the_best(self):
        """The helper grades the WORST gap, including the wrap past the hour.

        A cadence like `minute="0,1,2"` fires three times an hour and would pass
        any test that looked at the smallest gap or the fire count. It must not
        pass this one.
        """
        assert _crontab_period_s(crontab(minute="*/5")) == 300.0
        assert _crontab_period_s(crontab(minute="*/10")) == 600.0
        assert _crontab_period_s(crontab(minute="0,1,2")) == 3480.0
        assert _crontab_period_s(crontab(minute=31)) == 3600.0

    def test_it_is_still_a_crontab_on_background(self):
        """A numeric schedule would join `BACKGROUND_INTERVAL_FLOOR` instead.

        The beat is a crontab ON PURPOSE so it stays a countable co-fire in the
        settlement sweep's window census. Turning it into an interval would move
        it out of that census silently — the ceiling there would go DOWN, and a
        ceiling never complains about that.
        """
        entry = _entry()
        schedule = entry["schedule"]
        assert hasattr(schedule, "minute") and hasattr(schedule, "hour"), (
            f"{BEAT_NAME} is no longer a crontab. As a numeric interval it joins "
            "BACKGROUND_INTERVAL_FLOOR and leaves the sweep's co-fire census, which "
            "is a silent move in the direction no ceiling catches."
        )
        assert (entry.get("options") or {}).get("queue") == "background", (
            f"{BEAT_NAME} must name its queue explicitly rather than falling "
            "through to the default — see the fall-through census in "
            "test_typeahead_beat_budget.py, held at 45."
        )

    def test_it_stays_slower_than_the_slate_read_of_the_same_scoreboard(self):
        """`tournament_slate` reads the same ESPN board every 3 minutes.

        The beat's comment calls being slower than the slate deliberate: the
        slate renders the live card, this writes the durable row. If a later
        lane wants to go tighter than the slate, that is a real decision and it
        should have to come here and say so.
        """
        period = _crontab_period_s(_entry()["schedule"])
        assert period >= 180.0, (
            f"{BEAT_NAME} at {period:.0f} s is now at or faster than "
            "`tournament_slate`'s 180 s read of the same ESPN scoreboard. That "
            "inverts the split the beat's comment calls deliberate — argue it "
            "there first."
        )
