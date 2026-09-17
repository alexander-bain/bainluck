"""#6295 — what the serve-time fold does with the three repaired rows.

`b1c9d4395` (CERT-3000's repair) renames three kalshi-minted phantom rows that
the forward gate in `6ddeb4420` cannot reach, because they were already written:

    15312871  Bayer Leverkusen v Athletic Club   -> Levante v Bilbao
    15312872  Villarreal v Bayer Leverkusen      -> Villarreal v Levante
    15312896  Paris Saint-Germain v Genoa        -> Parma Calcio v Genoa

THE RENAME IS ONLY HALF THE OUTCOME A READER SEES. Each repaired row sits on a
page beside the REAL row for the same fixture, so the question the repair's own
suite cannot answer is what `fold_twin_events` does with the pair afterwards: a
renamed row that folds disappears into its twin and the reader is left with one
honest card, and a renamed row that does NOT fold becomes a SECOND card for a
fixture the page already carries. Both happen here, and the difference is three
hours.

The cert measured this by driving the fold over all 40 La Liga and Serie A rows
in the fixture window. That measurement is not re-runnable — it read production
at one instant — so this file pins its conclusion as fixtures, which is the
follow-up recorded on #6295 as
`6295-ADD-EXACT-POST-REPAIR-ROUTE-FOLD-GUARD`.

WHY THE TWO THAT FOLD, FOLD. `recover_kalshi_occurrence_starts` runs at the top
of `fold_twin_events` and subtracts `KALSHI_EXPECTED_EXPIRATION_PAD` (exactly
three hours) from a soccer row whose hour came from Kalshi's expected-expiration
instant. Both scheduled phantoms sit exactly that pad after their real row, so
the correction lands them on the same minute and the strict key sees one
fixture.

WHY THE THIRD DOES NOT, AND WHY THAT IS THE RIGHT ANSWER. `15312871` is stored
at 23:30Z against a true 19:30Z kick-off — FOUR hours, not the pad. The
recovery moves it to 20:30Z and it is still an hour out, so the fold correctly
refuses it: the pad is "not a tolerance and not a knob"
(`kalshi_occurrence_start`), and widening it to swallow this row would make an
exact recovery approximate for every soccer row on the site. The repaired row is
therefore a true name for a real fixture at a wrong hour — recorded under #2693,
not closed by this repair. That refusal is asserted here as a REQUIREMENT rather
than tolerated as a gap, so a later widening of the pad turns this file red.

Every value below is the production row as measured 2026-09-17 07:2xZ, not a
plausible-looking stand-in: ids, names, kick-offs, `commence_time_source` and
the espn/external anchors.

ONE GUARD IN THAT FUNCTION IS DELIBERATELY NOT COVERED HERE, AND IT IS WRITTEN
DOWN RATHER THAN LEFT TO BE DISCOVERED. `kalshi_occurrence_scheduled_start`
refuses a row on two independent arms: `external_id is not None` ("a schedule
provider reported this start") and `commence_time_source not in
KALSHI_OCCURRENCE_TIMED_SOURCES`. On this population the PROVENANCE arm always
answers first — every real row here is `espn`-timed — so deleting the
`external_id` arm leaves all ten cases green. That was measured, not assumed:
it is mutant M4 of this file and it SURVIVES, which makes it an equivalent
mutant on these three pairs rather than a hole in them. Covering it would mean
inventing a row that is Kalshi-timed and schedule-anchored at once, and no such
row is in the #6295 population. `test_the_real_row_is_never_moved` therefore
pins the arm that actually fires, and says so.
"""

from datetime import datetime, timedelta, timezone

from app.models.models import Event, Sport
from app.utils.event_twin_fold import fold_twin_events
from app.utils.kalshi_occurrence_start import (
    KALSHI_EXPECTED_EXPIRATION_PAD,
    kalshi_occurrence_scheduled_start,
)

UTC = timezone.utc

#: `sports.id` values are per-league here because the fold keys on the league,
#: and giving a pair two different ids would split it for a reason that has
#: nothing to do with what this file is testing.
LA_LIGA = Sport(id=1, key="soccer_spain_la_liga", name="La Liga")
SERIE_A = Sport(id=2, key="soccer_italy_serie_a", name="Serie A")


def _real(id, home, away, commence, sport, espn_id, external_id):
    """The schedule-provider row: ESPN named it and ESPN timed it.

    `external_id` is not decoration — see the module docstring.
    """
    row = Event(
        id=id,
        home_team_name=home,
        away_team_name=away,
        commence_time=commence,
        sport_id=sport.id,
        win_probability_sources={},
        status="scheduled",
        commence_time_source="espn",
        espn_id=espn_id,
        external_id=external_id,
    )
    # Assigning the relationship is what puts `sport` in the instance dict, so
    # `loaded_sport_key`'s `inspect(...).unloaded` test answers with the key
    # instead of `None`. A test that left it unloaded would silently disable the
    # kick-off recovery and then assert that nothing folded — passing for the
    # exact reason the product would be broken.
    row.sport = sport
    return row


def _phantom(id, home, away, commence, sport, status="scheduled"):
    """The kalshi-minted row: no anchor of any kind, hour from the venue."""
    row = Event(
        id=id,
        home_team_name=home,
        away_team_name=away,
        commence_time=commence,
        sport_id=sport.id,
        win_probability_sources={},
        status=status,
        commence_time_source="kalshi",
        espn_id=None,
        external_id=None,
    )
    row.sport = sport
    return row


# ── The three production pairs, before and after the repair ──────────────────

def _serie_a_pair(repaired):
    real = _real(
        15306081,
        "Parma",
        "Genoa",
        datetime(2026, 9, 20, 13, 0, tzinfo=UTC),
        SERIE_A,
        "401874801",
        "a48070d7ed928431ebe0d8ca2d6a8540",
    )
    phantom = _phantom(
        15312896,
        "Parma Calcio" if repaired else "Paris Saint-Germain",
        "Genoa",
        datetime(2026, 9, 20, 16, 0, tzinfo=UTC),
        SERIE_A,
    )
    return real, phantom


def _villarreal_pair(repaired):
    real = _real(
        15312073,
        "Villarreal",
        "Levante",
        datetime(2026, 9, 20, 16, 30, tzinfo=UTC),
        LA_LIGA,
        "401882857",
        "5502f6f20eccc2f2ed0d3904712e4a2c",
    )
    phantom = _phantom(
        15312872,
        "Villarreal",
        "Levante" if repaired else "Bayer Leverkusen",
        datetime(2026, 9, 20, 19, 30, tzinfo=UTC),
        LA_LIGA,
    )
    return real, phantom


def _levante_pair(repaired):
    """The FOUR-hour row. Both rows are `suspended` on production."""
    real = _real(
        15305825,
        "Levante",
        "Athletic Bilbao",
        datetime(2026, 9, 16, 19, 30, tzinfo=UTC),
        LA_LIGA,
        "401882870",
        "4ef67376b662c2859f73bde7f7210388",
    )
    real.status = "suspended"
    phantom = _phantom(
        15312871,
        "Levante" if repaired else "Bayer Leverkusen",
        "Bilbao" if repaired else "Athletic Club",
        datetime(2026, 9, 16, 23, 30, tzinfo=UTC),
        LA_LIGA,
        status="suspended",
    )
    return real, phantom


class TestTheTwoScheduledPhantomsFoldOnceRepaired:
    """The reader-visible half: two phantom cards leave the page."""

    def test_serie_a_phantom_folds_onto_parma_v_genoa(self):
        real, phantom = _serie_a_pair(repaired=True)

        fold = fold_twin_events([real, phantom])

        assert fold.dropped_ids == [15312896]
        assert fold.survivor_of == {15312896: 15306081}
        assert [e.id for e in fold.events] == [15306081]

    def test_la_liga_phantom_folds_onto_villarreal_v_levante(self):
        real, phantom = _villarreal_pair(repaired=True)

        fold = fold_twin_events([real, phantom])

        assert fold.dropped_ids == [15312872]
        assert fold.survivor_of == {15312872: 15312073}
        assert [e.id for e in fold.events] == [15312073]

    def test_the_survivor_is_the_schedule_anchored_row_not_the_phantom(self):
        """Which row SURVIVES is the whole point, not merely that one went.

        A fold that kept the kalshi-minted row would remove a duplicate and keep
        the copy with no anchor, no ESPN id and an hour three hours late — the
        page would look repaired and carry the worse of the two rows.
        """
        for real, phantom in (
            _serie_a_pair(repaired=True),
            _villarreal_pair(repaired=True),
        ):
            fold = fold_twin_events([real, phantom])

            (survivor,) = fold.events
            assert survivor.id == real.id
            assert survivor.espn_id == real.espn_id
            assert survivor.external_id is not None

    def test_neither_folds_before_the_repair(self):
        """The control: with the pre-repair names, both phantoms are served.

        This is what a reader met on the La Liga and Serie A pages, and it is
        what makes the two tests above statements about the RENAME rather than
        about the fold's own behaviour. Remove the repair and this file still
        passes here while the two tests above go red.
        """
        for real, phantom in (
            _serie_a_pair(repaired=False),
            _villarreal_pair(repaired=False),
        ):
            fold = fold_twin_events([real, phantom])

            assert fold.dropped_ids == []
            assert sorted(e.id for e in fold.events) == sorted(
                [real.id, phantom.id]
            )


class TestTheFourHourRowIsRefusedAndStaysRefused:
    """#2693's row. The refusal is required, not tolerated."""

    def test_the_repaired_levante_row_does_not_fold(self):
        real, phantom = _levante_pair(repaired=True)

        fold = fold_twin_events([real, phantom])

        assert fold.dropped_ids == []
        assert sorted(e.id for e in fold.events) == [15305825, 15312871]

    def test_the_recovery_leaves_it_exactly_one_hour_from_its_twin(self):
        """WHY it is refused, pinned as arithmetic rather than as an outcome.

        If a future change makes the row fold, this test says whether the pad
        was widened (the thing `kalshi_occurrence_start` forbids) or the stored
        hour was finally corrected (the #2693 fix, which is welcome). Without
        it, the test above would go red with no way to tell those apart.
        """
        real, phantom = _levante_pair(repaired=True)
        stored = phantom.commence_time

        fold_twin_events([real, phantom])

        assert phantom.commence_time == stored - KALSHI_EXPECTED_EXPIRATION_PAD
        assert phantom.commence_time - real.commence_time == timedelta(hours=1)

    def test_the_two_that_fold_are_separated_by_exactly_the_pad(self):
        """The same arithmetic on the folding pairs, from the other side."""
        for real, phantom in (
            _serie_a_pair(repaired=True),
            _villarreal_pair(repaired=True),
        ):
            gap = phantom.commence_time - real.commence_time

            assert gap == KALSHI_EXPECTED_EXPIRATION_PAD

    def test_the_real_row_is_never_moved(self):
        """Its `espn` provenance is what protects it — the arm that fires.

        Asserting the survivor's hour alone would pass for either reason, so the
        pure function is called directly on the real row: `None` is "this hour
        is not mine to move", and it is returned on the provenance arm. See the
        module docstring for why the `external_id` arm is not asserted here.
        """
        real, phantom = _levante_pair(repaired=True)
        stored_real = real.commence_time

        assert (
            kalshi_occurrence_scheduled_start(real, "soccer_spain_la_liga") is None
        )
        # …and the phantom beside it IS claimed, so the `None` above is a
        # decision about this row and not a function that never fires.
        assert kalshi_occurrence_scheduled_start(
            phantom, "soccer_spain_la_liga"
        ) == phantom.commence_time - KALSHI_EXPECTED_EXPIRATION_PAD

        fold_twin_events([real, phantom])

        assert real.commence_time == stored_real


class TestAllThreeTogetherOnOnePage:
    """The rows do not arrive one pair at a time — a league page holds them all.

    Folding pair-by-pair can hide a cross-pair mistake: three La Liga rows share
    a league key here, and `Levante` appears in two different fixtures on two
    different dates. A key that keyed on the league and the teams but not the
    minute would collapse those two, which is the mistake this case exists to
    catch.
    """

    def test_one_page_drops_exactly_the_two_scheduled_phantoms(self):
        rows = []
        for pair in (
            _serie_a_pair(repaired=True),
            _villarreal_pair(repaired=True),
            _levante_pair(repaired=True),
        ):
            rows.extend(pair)

        fold = fold_twin_events(rows)

        assert sorted(fold.dropped_ids) == [15312872, 15312896]
        assert sorted(e.id for e in fold.events) == [
            15305825,
            15306081,
            15312073,
            15312871,
        ]

    def test_the_two_levante_fixtures_are_never_collapsed_into_each_other(self):
        """`15312073` (Villarreal v Levante, Sep 20) and `15305825`
        (Levante v Athletic Bilbao, Sep 16) are different games."""
        rows = []
        for pair in (
            _villarreal_pair(repaired=True),
            _levante_pair(repaired=True),
        ):
            rows.extend(pair)

        fold = fold_twin_events(rows)

        surviving = {e.id for e in fold.events}
        assert {15312073, 15305825} <= surviving
