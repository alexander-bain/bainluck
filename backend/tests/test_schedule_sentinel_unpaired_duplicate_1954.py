"""CERT-1954's specimen: a duplicated official id that never name-paired.

    BLOCK — THE SENTINEL STILL EMITS DUPLICATE-AUTHORITY DEFECTS ONLY FROM
    SUCCESSFULLY NAME-PAIRED ROWS.

The grader's reproduction, verbatim: one official NCAAB game, plus two scheduled
rows with **dissimilar names** sharing ``espn_id='espn-dup'``. That produced
``paired 0``, ``REAL 0``, ``UNVERIFIED 0`` and a literal **GREEN**, while a user
looking at the page sees two rows claiming to be one official game.

The cause was a precondition that should never have been one. The
``schedule_duplicate_identity`` finding was raised inside ``reconcile``'s loop
over ``paired["pairs"]``, so a defect that is decided **entirely within our own
data** — two of our rows assert the same official identifier — could only be
reported when one of those rows ALSO happened to pair to the official game by
name and clock. Stage 0 refuses to pair on a duplicated id (correctly), so the
rows fall through to name pairing; when the names are dissimilar they never pair
at all, and the contradiction stage 0 had already detected was thrown away.

Pairing is not evidence here. The truth game is *context* — nice to name in the
message, never required for the finding to be true — so the emission moved out of
the pairs loop into its own pass over ``duplicate_id_events``.

**Why NCAAB and not NBA.** NCAAB is ``partial_by_design``, so every MISSING it
raises is downgraded to ``watch`` and cannot colour the verdict. That strips away
the other route to RED and leaves the duplicate finding as the only thing that
can fail this league — which is exactly what makes the specimen sharp, and why a
green here was a true false-green rather than an artifact of a noisy fixture.

Discipline: gotcha #43 (both directions — the controls below assert the
legitimate cases are still not flagged) and gotcha #44 (``NOW`` is an absolute
constant; ``now`` is injected everywhere and no anchor reads the wall clock).
"""

import importlib
from datetime import datetime, timedelta, timezone

ss = importlib.import_module("app.tasks.schedule_sentinel")

# Mid-season for NCAAB, so nothing here is explained away as a quiet window —
# an offseason anchor would make these tests pass for the wrong reason.
NOW = datetime(2026, 1, 15, 6, 0, tzinfo=timezone.utc)

NCAAB = next(s for s in ss.SCHEDULE_LEAGUES if s.slug == "ncaab")
NBA = next(s for s in ss.SCHEDULE_LEAGUES if s.slug == "nba")

DUP = "espn-dup"


def _ago(hours):
    return NOW - timedelta(hours=hours)


def _truth(home, away, *, start, state="pre", hs=None, aws=None, key="g1"):
    return ss.TruthGame(key=key, home=home, away=away, start=start, state=state,
                        raw_state=state.title(), home_score=hs, away_score=aws,
                        doubleheader=False, game_number=1)


def _ours(eid, home, away, *, start, status="scheduled", espn_id=None):
    """Our event with healthy FKs — this specimen is about IDENTITY alone, so
    nothing else may be the reason a finding fires."""
    return ss.OurEvent(
        id=eid, home_name=home, away_name=away,
        home_team_id=1, away_team_id=2,
        home_fk_name=home, away_fk_name=away,
        status=status, home_score=None, away_score=None, commence_time=start,
        espn_id=espn_id, statpal_fixture_id=None, external_id=None,
    )


def _checks(findings):
    return {f["check"] for f in findings}


def _dupes(findings):
    classified = ss.classify_findings(findings, NCAAB, NOW)
    return [f for f in classified["real"]
            if f["check"] == "schedule_duplicate_identity"]


def _specimen():
    """THE grader's fixture. Names are deliberately dissimilar to the official
    game AND to each other, so no name pairing can occur and the duplicated id
    is the only signal in the window."""
    truth = [_truth("Duke Blue Devils", "North Carolina Tar Heels",
                    start=_ago(3), key="espn-official-1")]
    ours = [
        _ours(101, "Gonzaga Bulldogs", "Saint Marys Gaels",
              start=_ago(3), espn_id=DUP),
        _ours(102, "Purdue Boilermakers", "Illinois Fighting Illini",
              start=_ago(2), espn_id=DUP),
    ]
    return truth, ours


class TestTheUnpairedDuplicateSpecimen:

    def test_the_specimen_really_does_not_pair(self):
        """The premise, asserted rather than assumed.

        If a future name-matcher change made these rows pair, every assertion
        below would still pass — but it would be testing the OLD code path and
        the repair would be unguarded. This pins that the specimen still
        exercises the unpaired route.
        """
        truth, ours = _specimen()
        _, stats = ss.reconcile(truth, ours, NCAAB, NOW)
        assert stats["paired"] == 0, (
            "the specimen is only meaningful while these rows do NOT pair"
        )
        assert stats["paired_by_id"] == 0

    def test_two_unpaired_rows_sharing_one_official_id_is_RED(self):
        """THE ship. Was: paired 0, REAL 0, UNVERIFIED 0, literal GREEN."""
        truth, ours = _specimen()
        findings, _ = ss.reconcile(truth, ours, NCAAB, NOW)
        classified = ss.classify_findings(findings, NCAAB, NOW)

        assert ss.schedule_verdict(classified, covered=True) == "red", (
            "two of our rows claim one official game id and the sentinel called "
            "it green because neither row happened to name-pair"
        )

    def test_it_names_both_rows(self):
        """The BLOCK's second half: *name both rows*.

        Asserted twice over, because the two carry different weight. One finding
        per implicated row is the shape CERT-1954's predecessor certified; the
        `event_ids` set is what lets a filing act on the defect without a
        re-query, and it must list the SIBLING, not just the row it is filed on.
        """
        truth, ours = _specimen()
        findings, _ = ss.reconcile(truth, ours, NCAAB, NOW)
        dupes = _dupes(findings)

        assert len(dupes) == 2
        assert {f["event_id"] for f in dupes} == {101, 102}
        for f in dupes:
            assert f["event_ids"] == [101, 102]
            assert f["kind"] == "DUPLICATE"
            assert f["duplicated_id"] == DUP
            assert f["id_space"] == "espn_id"

    def test_it_says_the_official_game_was_not_in_view(self):
        """Honesty about what was NOT checked, which is this sentinel's whole
        reason to exist. The duplicated id names no game in this window's truth
        read, and the finding must say so rather than implying we matched one."""
        truth, ours = _specimen()
        findings, _ = ss.reconcile(truth, ours, NCAAB, NOW)
        f = _dupes(findings)[0]

        assert f["truth_game_in_window"] is False
        assert f["truth_key"] is None

    def test_a_partial_coverage_league_cannot_launder_it(self):
        """NCAAB is `partial_by_design`, which sends MISSING to `watch`. That
        downgrade must not reach a proven duplicate — otherwise the two leagues
        where coverage is thinnest are the two that can never report this."""
        truth, ours = _specimen()
        findings, _ = ss.reconcile(truth, ours, NCAAB, NOW)
        classified = ss.classify_findings(findings, NCAAB, NOW)

        watched = {f["check"] for f in classified["watch"]}
        assert "schedule_duplicate_identity" not in watched
        assert "schedule_duplicate_identity" not in {
            f["check"] for f in classified["explained"]
        }


class TestBothDirections:
    """gotcha #43. A guard that only ever fires is not a guard."""

    def test_two_unpaired_rows_with_DISTINCT_ids_stay_green(self):
        """The control that matters most: the rows are just as unpaired and just
        as dissimilar, and only the shared id is gone."""
        truth, ours = _specimen()
        ours = [ours[0], _ours(102, "Purdue Boilermakers",
                               "Illinois Fighting Illini",
                               start=_ago(2), espn_id="espn-other")]

        findings, _ = ss.reconcile(truth, ours, NCAAB, NOW)
        classified = ss.classify_findings(findings, NCAAB, NOW)

        assert "schedule_duplicate_identity" not in _checks(findings)
        assert ss.schedule_verdict(classified, covered=True) != "red"

    def test_unpaired_rows_with_no_id_at_all_are_not_duplicates(self):
        """Two rows that are individuated by nothing share no identity. `None`
        is not a value, and grouping on it would report every id-less pair in
        the window as one game — the failure direction that empties a page."""
        truth, ours = _specimen()
        ours = [
            _ours(101, "Gonzaga Bulldogs", "Saint Marys Gaels",
                  start=_ago(3), espn_id=None),
            _ours(102, "Purdue Boilermakers", "Illinois Fighting Illini",
                  start=_ago(2), espn_id=None),
        ]

        findings, _ = ss.reconcile(truth, ours, NCAAB, NOW)
        assert "schedule_duplicate_identity" not in _checks(findings)

    def test_three_rows_sharing_an_id_implicate_all_three(self):
        """The set is the set, not a pair. A two-element assumption anywhere in
        the path would silently drop the third row from the filing."""
        truth, ours = _specimen()
        ours.append(_ours(103, "Baylor Bears", "Houston Cougars",
                          start=_ago(1), espn_id=DUP))

        findings, _ = ss.reconcile(truth, ours, NCAAB, NOW)
        dupes = _dupes(findings)

        assert len(dupes) == 3
        assert {f["event_id"] for f in dupes} == {101, 102, 103}
        for f in dupes:
            assert f["event_ids"] == [101, 102, 103]

    def test_the_paired_route_still_reports(self):
        """The repair moved the emission; it must not have removed it. This is
        the ORIGINAL specimen 2 shape — rows whose names DO pair — and it must
        still be RED, or the fix traded one blind spot for another."""
        t1 = _truth("Boston Celtics", "Denver Nuggets", start=_ago(12),
                    state="final", hs=4, aws=2, key="espn-1")
        t2 = _truth("Miami Heat", "Chicago Bulls", start=_ago(6),
                    state="final", hs=1, aws=0, key="espn-2")
        o1 = _ours(1, "Boston Celtics", "Denver Nuggets", start=_ago(12),
                   status="completed", espn_id="espn-1")
        o2 = _ours(2, "Miami Heat", "Chicago Bulls", start=_ago(6),
                   status="completed", espn_id="espn-1")

        findings, _ = ss.reconcile([t1, t2], [o1, o2], NBA, NOW)
        classified = ss.classify_findings(findings, NBA, NOW)
        dupes = [f for f in classified["real"]
                 if f["check"] == "schedule_duplicate_identity"]

        assert len(dupes) == 2
        assert {f["event_id"] for f in dupes} == {1, 2}
        assert ss.schedule_verdict(classified, covered=True) == "red"

    def test_the_paired_route_names_its_truth_game(self):
        """The context the paired route has and the unpaired one does not. The
        two must be distinguishable in a filing, or an operator cannot tell
        'we found the official game' from 'we never saw it'."""
        t1 = _truth("Boston Celtics", "Denver Nuggets", start=_ago(12),
                    state="final", hs=4, aws=2, key="espn-1")
        o1 = _ours(1, "Boston Celtics", "Denver Nuggets", start=_ago(12),
                   status="completed", espn_id="espn-1")
        o2 = _ours(2, "Boston Celtics", "Denver Nuggets", start=_ago(12),
                   status="completed", espn_id="espn-1")

        findings, _ = ss.reconcile([t1], [o1, o2], NBA, NOW)
        dupes = [f for f in findings
                 if f["check"] == "schedule_duplicate_identity"]

        assert dupes, "a duplicated id with its official game present must report"
        assert dupes[0]["truth_game_in_window"] is True
        assert dupes[0]["truth_key"] == "espn-1"
