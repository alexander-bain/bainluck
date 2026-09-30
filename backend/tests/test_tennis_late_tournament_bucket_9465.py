"""#9465 — a tournament bucket that opens AFTER the tour-week pass chose its
holder: the late tournament row is labelled the holder's duplicate, and the
holder keeps its ESPN writes.

Specimen, production 2026-09-28 21:45Z: Borges v Djokovic (China Open, ESPN
competition 183455). #2774 put ESPN's id on Kalshi's ``15320661``
(``tennis_atp``) and labelled Polymarket's ``15320815`` its duplicate. At 18:07Z
the Odds API opened ``tennis_atp_china_open`` and minted ``15321024``. The ATP
page printed 15320661 (Kalshi + Polymarket, no sportsbooks) and search printed
15321024 (sportsbooks + Polymarket, no Kalshi): one match, two cards, two
numbers. The tournament pass's stamp was refused (id held) and the twin sweep
refused the pair (the bare row now carries a provider id).
"""

from __future__ import annotations

from app.utils.espn_tennis_anchor import (
    CONTEST_FOREIGN_ESPN_ID,
    CONTEST_SETTLED_GHOST,
    CONTEST_TOURNAMENT_CLAIMANT,
    pick_contest_canonical,
    with_held_competitions,
)
from app.utils.tennis_twin_pairs import TwinSweepPlan, TwinTag
from tests.test_espn_tennis_anchor import _Event, _at, _competition, _payload
from tests.test_tennis_tour_week_anchor_2774 import _install_generic, _TagRecorder

CHINA_OPEN = "China Open"
KEYS = ["tennis_atp", "tennis_atp_china_open", "tennis_other", "tennis_wta"]


def _claimant(event_id, sport_key=None, espn_id=None, has_result=False,
              tournament_keyed=False):
    return {
        "event_id": event_id,
        "sport_key": sport_key,
        "espn_id": espn_id,
        "has_result": has_result,
        "tournament_keyed": tournament_keyed,
    }


# ═══════════════════════════ the pure scope ═══════════════════════════


class TestWithHeldCompetitions:
    comps = [
        {"espn_competition_id": "183455", "event_name": CHINA_OPEN},
        {"espn_competition_id": "183440", "event_name": CHINA_OPEN},
        {"espn_competition_id": "183497", "event_name": "Japan Open"},
    ]

    def test_a_held_competition_stays_generic_after_its_bucket_opens(self):
        bucketless = [self.comps[2]]
        out = with_held_competitions(bucketless, self.comps, ["183455", None])
        assert [c["espn_competition_id"] for c in out] == ["183497", "183455"]

    def test_an_unheld_competition_of_a_bucketed_tournament_is_not_added(self):
        assert with_held_competitions([], self.comps, []) == []

    def test_a_bucketless_competition_is_never_listed_twice(self):
        out = with_held_competitions([self.comps[2]], self.comps, ["183497"])
        assert [c["espn_competition_id"] for c in out] == ["183497"]


# ═══════════════════════════ the pure contest ═══════════════════════════


class TestTheLateTournamentRow:
    def test_the_specimen_keeps_the_holder_and_labels_the_tournament_row(self):
        assert pick_contest_canonical("183455", [
            _claimant(15320661, "tennis_atp", espn_id="183455"),
            _claimant(15321024, tournament_keyed=True),
        ]) == (15320661, [15321024], None)

    def test_the_sport_key_alone_marks_a_tournament_row(self):
        assert pick_contest_canonical("183455", [
            _claimant(15320661, "tennis_atp", espn_id="183455"),
            _claimant(15321024, "tennis_atp_china_open"),
        ]) == (15320661, [15321024], None)

    def test_with_no_holder_the_old_refusal_stands(self):
        assert pick_contest_canonical("9", [
            _claimant(1, "tennis_atp"),
            _claimant(2, tournament_keyed=True),
        ]) == (None, [], CONTEST_TOURNAMENT_CLAIMANT)

    def test_a_tournament_holder_is_the_old_us_open_shape_and_is_refused(self):
        assert pick_contest_canonical("9", [
            _claimant(1, "tennis_atp"),
            _claimant(2, "tennis_atp_us_open", espn_id="9"),
        ]) == (None, [], CONTEST_TOURNAMENT_CLAIMANT)

    def test_a_holder_of_another_competition_is_refused(self):
        assert pick_contest_canonical("9", [
            _claimant(1, "tennis_atp", espn_id="8"),
            _claimant(2, tournament_keyed=True),
        ]) == (None, [], CONTEST_TOURNAMENT_CLAIMANT)

    def test_two_holders_are_refused(self):
        verdict = pick_contest_canonical("9", [
            _claimant(1, "tennis_atp", espn_id="9"),
            _claimant(3, "tennis_other", espn_id="8"),
            _claimant(2, tournament_keyed=True),
        ])
        assert verdict[0] is None and verdict[2] in (
            CONTEST_TOURNAMENT_CLAIMANT, CONTEST_FOREIGN_ESPN_ID)

    def test_a_scored_tournament_row_is_not_a_ghost(self):
        assert pick_contest_canonical("9", [
            _claimant(1, "tennis_atp", espn_id="9"),
            _claimant(2, tournament_keyed=True, has_result=True),
        ]) == (None, [], CONTEST_SETTLED_GHOST)


# ═══════════════════════════ the sweep never chains ═══════════════════════════


class TestTheSweepNeverLabelsOntoADuplicate:
    def test_a_canonical_that_is_itself_labelled_is_not_a_target(self):
        from app.tasks.tennis_twin_sweep import tags_to_write

        plan = TwinSweepPlan(
            tags=(TwinTag(15320661, 15321024, "participants agree"),
                  TwinTag(7, 8, "participants agree")),
            refusals=(), rows_considered=4, blocks_examined=2,
        )
        # 15321024 carries duplicate-of:15320661 — writing the first tag would
        # point the two rows at each other.
        assert tags_to_write(plan, {15321024}) == [TwinTag(7, 8, "participants agree")]

    def test_a_labelled_ghost_is_still_left_alone(self):
        from app.tasks.tennis_twin_sweep import tags_to_write

        plan = TwinSweepPlan(
            tags=(TwinTag(7, 8, "participants agree"),),
            refusals=(), rows_considered=2, blocks_examined=1,
        )
        assert tags_to_write(plan, {7}) == []
        assert tags_to_write(plan, set()) == [TwinTag(7, 8, "participants agree")]


# ═══════════════════════════ the task, end to end ═══════════════════════════


def _rows():
    holder = _Event(15320661, "Borges", "Djokovic", "scheduled",
                    _at("2026-09-30T02:00Z"), espn_id="183455",
                    commence_time_source="polymarket_venue")
    late = _Event(15321024, "Nuno Borges", "Novak Djokovic", "scheduled",
                  _at("2026-09-30T02:00Z"), commence_time_source="odds_api")
    return holder, late


def _board():
    return [_payload(
        [_competition("183455", ["Nuno Borges", "Novak Djokovic"],
                      date="2026-09-30T02:00Z")],
        event_name=CHINA_OPEN,
    )]


class TestTheLateBucketTask:
    async def test_the_specimen_shows_once(self, monkeypatch):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        holder, late = _rows()
        tags = _TagRecorder().install(monkeypatch)
        _install_generic(
            monkeypatch, payloads=_board(), sport_keys=KEYS,
            generic=[(holder, "tennis_atp")], tournament_events=[late],
        )

        stats = await _sync_tennis_from_espn()

        assert stats["generic_competitions"] == 0, "China Open has a bucket now"
        assert stats["generic_held_competitions"] == 1
        assert stats["generic_contests_resolved"] == 1
        assert tags.written == [(15321024, 15320661)]
        assert tags.backed_up == [(15321024, 15320661)], "backup before the write (D51)"
        assert late.espn_id is None, "the id stays on ONE row — merge-duplicate-events"
        assert holder.espn_id == "183455"
        assert stats["already_anchored"] == 1, "the holder keeps its ESPN channel"
        assert stats.get("stamp_refused", 0) == 0

    async def test_a_labelled_tournament_row_never_reopens_the_contest(
        self, monkeypatch
    ):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        holder, late = _rows()
        late.event_tags = ["provenance:duplicate-of:15320661"]
        late.home_score, late.away_score = 2, 1  # the Odds API settled its copy
        tags = _TagRecorder().install(monkeypatch)
        _install_generic(
            monkeypatch, payloads=_board(), sport_keys=KEYS,
            generic=[(holder, "tennis_atp")], tournament_events=[late],
        )

        stats = await _sync_tennis_from_espn()

        assert stats["labelled_rows_skipped"] == 1
        assert stats["contested_competitions"] == 0
        assert stats["already_anchored"] == 1, "the holder still gets ESPN's final"
        assert tags.written == []

    async def test_no_fold_no_label_but_the_holder_keeps_its_channel(self, monkeypatch):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        holder, late = _rows()
        tags = _TagRecorder(fold_live=False).install(monkeypatch)
        _install_generic(
            monkeypatch, payloads=_board(), sport_keys=KEYS,
            generic=[(holder, "tennis_atp")], tournament_events=[late],
        )

        stats = await _sync_tennis_from_espn()

        assert stats["ghost_tags_withheld_fold_dark"] == 1
        assert stats["already_anchored"] == 1
        assert tags.written == []

    async def test_control_with_no_holder_the_tournament_row_anchors_alone(
        self, monkeypatch
    ):
        """The ordinary tournament week: nobody holds 183455, so the Odds API
        row takes the id and nothing is labelled."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        _, late = _rows()
        tags = _TagRecorder().install(monkeypatch)
        _install_generic(
            monkeypatch, payloads=_board(), sport_keys=KEYS,
            generic=[], tournament_events=[late],
        )

        stats = await _sync_tennis_from_espn()

        assert stats["generic_held_competitions"] == 0
        assert late.espn_id == "183455"
        assert stats["anchored"] == 1
        assert tags.written == []
