"""#2774 — the tour week: a board tournament no bucket names is anchored through
the generic buckets, and a match written twice there shows ONCE.

Specimen, production 2026-09-28 13:20Z: Alcaraz v Michelsen (Japan Open, ESPN
competition 183497) was two rows — Kalshi's ``15320475`` (``tennis_atp``,
"Alcaraz"/"Michelsen") and Polymarket's ``15320816`` (``tennis_other``, full
names). Neither carried an id, so the tournament-scoped anchor never looked at
them and the twin sweep refused them as "neither tournament-keyed".
"""

from __future__ import annotations

from app.services.espn_tennis import TBD_SHORT_DETAIL
from app.utils.espn_tennis_anchor import (
    CONTEST_FOREIGN_ESPN_ID,
    CONTEST_SETTLED_GHOST,
    CONTEST_TOURNAMENT_CLAIMANT,
    bucketless_competitions,
    carried_start,
    generic_sport_keys,
    pick_contest_canonical,
)
from tests.test_espn_tennis_anchor import (
    _Event,
    _Result,
    _Session,
    _at,
    _competition,
    _payload,
)

JAPAN_OPEN = "Kinoshita Group Japan Open Tennis Championships"
KEYS = ["tennis_atp", "tennis_atp_us_open", "tennis_other", "tennis_wta"]


def _claimant(event_id, sport_key, espn_id=None, has_result=False):
    return {
        "event_id": event_id,
        "sport_key": sport_key,
        "espn_id": espn_id,
        "has_result": has_result,
    }


# ═══════════════════════════ the pure scope ═══════════════════════════


class TestTheScope:
    def test_a_tournament_a_bucket_names_is_never_the_generic_passs(self):
        comps = [
            {"espn_competition_id": "1", "event_name": "US Open"},
            {"espn_competition_id": "2", "event_name": JAPAN_OPEN},
        ]
        assert [c["espn_competition_id"] for c in bucketless_competitions(KEYS, comps)] == ["2"]

    def test_with_no_bucket_at_all_every_tournament_is_bucketless(self):
        comps = [{"espn_competition_id": "1", "event_name": "US Open"}]
        assert bucketless_competitions(["tennis_atp"], comps) == comps

    def test_generic_keys_are_the_three_that_name_no_event(self):
        assert generic_sport_keys(KEYS + ["basketball_nba"]) == [
            "tennis_atp", "tennis_other", "tennis_wta",
        ]


# ═══════════════════════════ the pure contest ═══════════════════════════


class TestPickContestCanonical:
    def test_the_specimen_keeps_the_tour_row(self):
        assert pick_contest_canonical("183497", [
            _claimant(15320816, "tennis_other"),
            _claimant(15320475, "tennis_atp"),
        ]) == (15320475, [15320816], None)

    def test_the_tour_key_beats_a_lower_id_in_tennis_other(self):
        """The WTA rail lists only `tennis_wta`: keeping the `tennis_other`
        copy would take the match off the page it is on today."""
        canonical, ghosts, _ = pick_contest_canonical("9", [
            _claimant(100, "tennis_other"),
            _claimant(200, "tennis_wta"),
        ])
        assert (canonical, ghosts) == (200, [100])

    def test_the_row_already_holding_the_id_wins_so_the_card_never_flips(self):
        canonical, ghosts, _ = pick_contest_canonical("9", [
            _claimant(100, "tennis_atp"),
            _claimant(300, "tennis_other", espn_id="9"),
        ])
        assert (canonical, ghosts) == (300, [100])

    def test_lowest_id_breaks_a_tie_and_every_other_row_is_a_ghost(self):
        canonical, ghosts, _ = pick_contest_canonical("9", [
            _claimant(15320529, "tennis_other"),
            _claimant(15320519, "tennis_other"),
            _claimant(15320520, "tennis_other"),
        ])
        assert (canonical, sorted(ghosts)) == (15320519, [15320520, 15320529])

    def test_a_tournament_keyed_claimant_is_refused(self):
        assert pick_contest_canonical("9", [
            _claimant(1, "tennis_atp"),
            _claimant(2, "tennis_atp_us_open"),
        ]) == (None, [], CONTEST_TOURNAMENT_CLAIMANT)

    def test_a_claimant_holding_another_espn_id_is_refused(self):
        assert pick_contest_canonical("9", [
            _claimant(1, "tennis_atp"),
            _claimant(2, "tennis_other", espn_id="8"),
        ]) == (None, [], CONTEST_FOREIGN_ESPN_ID)

    def test_a_scored_ghost_is_refused(self):
        assert pick_contest_canonical("9", [
            _claimant(1, "tennis_atp"),
            _claimant(2, "tennis_other", has_result=True),
        ]) == (None, [], CONTEST_SETTLED_GHOST)

    def test_a_scored_canonical_is_fine(self):
        assert pick_contest_canonical("9", [
            _claimant(1, "tennis_atp", has_result=True),
            _claimant(2, "tennis_other"),
        ]) == (1, [2], None)


# ═══════════════════════════ the carried start ═══════════════════════════


def _start(at, source):
    return {"commence_time": _at(at) if at else None, "commence_time_source": source}


class TestCarriedStart:
    def test_the_venue_start_replaces_a_kalshi_date(self):
        assert carried_start(
            _start("2026-09-29T05:00Z", "kalshi"),
            [_start("2026-09-30T01:00Z", "polymarket_venue")],
        ) == (_at("2026-09-30T01:00Z"), "polymarket_venue")

    def test_a_weaker_source_never_overwrites_a_stronger_one(self):
        assert carried_start(
            _start("2026-09-30T01:00Z", "polymarket_venue"),
            [_start("2026-09-29T05:00Z", "kalshi")],
        ) is None

    def test_two_rows_of_one_source_do_not_overrule_each_other(self):
        assert carried_start(
            _start("2026-09-28T10:40Z", "polymarket_venue"),
            [_start("2026-09-28T08:30Z", "polymarket_venue")],
        ) is None

    def test_ghosts_that_disagree_carry_nothing(self):
        assert carried_start(
            _start("2026-09-28T05:00Z", "kalshi"),
            [_start("2026-09-28T10:40Z", "polymarket_venue"),
             _start("2026-09-28T08:30Z", "polymarket_venue")],
        ) is None

    def test_ghosts_that_agree_carry_their_one_start(self):
        assert carried_start(
            _start("2026-09-28T05:00Z", "kalshi"),
            [_start("2026-09-28T08:40Z", "polymarket_venue"),
             _start("2026-09-28T08:40Z", "polymarket_venue")],
        ) == (_at("2026-09-28T08:40Z"), "polymarket_venue")

    def test_an_unrecorded_canonical_source_is_left_alone(self):
        """The registry gives an unrecorded source no immunity but also no
        licence to be overwritten by the venue — `None` over it is refused."""
        assert carried_start(
            _start("2026-09-28T05:00Z", None),
            [_start("2026-09-28T08:40Z", "polymarket_venue")],
        ) is None


# ═══════════════════════════ the task, end to end ═══════════════════════════


class _TagRecorder:
    def __init__(self, *, fold_live=True):
        self.fold_live = fold_live
        self.backed_up = []
        self.written = []

    def install(self, monkeypatch):
        from app.tasks import tennis_twin_sweep as sweep

        async def ensure_backup(session, tags, current):
            self.backed_up.extend((t.ghost_id, t.canonical_id) for t in tags)
            return len(tags)

        async def write_tags(session, tags, progress_every=0):
            self.written.extend((t.ghost_id, t.canonical_id) for t in tags)
            return len(tags), []

        async def tagged_now(session, ids):
            return {g for g, _ in self.written if g in set(ids)}

        monkeypatch.setattr(sweep, "ensure_backup", ensure_backup)
        monkeypatch.setattr(sweep, "write_tags", write_tags)
        monkeypatch.setattr(sweep, "tagged_now", tagged_now)
        monkeypatch.setattr(sweep, "fold_is_live", lambda: self.fold_live)
        return self


def _install_generic(monkeypatch, *, payloads, sport_keys, generic, holders=None,
                     tournament_events=None):
    """`generic` is [(event, sport_key)] — the generic read selects both."""
    from app.services import espn_tennis as svc
    from app.tasks import espn_sync

    events = [e for e, _ in generic] + list(tournament_events or [])
    session = _Session(sport_keys, events, holders)
    answers = [session._answers[0]]
    if tournament_events is not None:
        answers.append(_Result(list(tournament_events)))
    answers.append(_Result(list(generic)))
    session._answers = answers
    monkeypatch.setattr(svc, "fetch_scoreboards", lambda dates=None: (payloads, []))
    monkeypatch.setattr(espn_sync, "get_task_session", lambda: session)
    return session


def _specimen_rows():
    kalshi = _Event(15320475, "Alcaraz", "Michelsen", "scheduled",
                    _at("2026-09-29T05:00Z"), commence_time_source="kalshi")
    poly = _Event(15320816, "Carlos Alcaraz", "Alex Michelsen", "scheduled",
                  _at("2026-09-30T01:00Z"), commence_time_source="polymarket_venue")
    return kalshi, poly


def _japan_open_board():
    return [_payload(
        # The real board, 13:20Z: midnight-ET placeholder, shortDetail "TBD".
        [_competition("183497", ["Alex Michelsen", "Carlos Alcaraz"],
                      date="2026-09-30T04:00Z", short_detail=TBD_SHORT_DETAIL)],
        event_name=JAPAN_OPEN,
    )]


class TestTheTourWeekTask:
    async def test_the_specimen_shows_once(self, monkeypatch):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        kalshi, poly = _specimen_rows()
        tags = _TagRecorder().install(monkeypatch)
        _install_generic(
            monkeypatch, payloads=_japan_open_board(), sport_keys=KEYS,
            generic=[(kalshi, "tennis_atp"), (poly, "tennis_other")],
        )

        stats = await _sync_tennis_from_espn()

        assert kalshi.espn_id == "183497"
        assert poly.espn_id is None, "the id goes on ONE row — merge-duplicate-events"
        assert tags.written == [(15320816, 15320475)]
        assert tags.backed_up == [(15320816, 15320475)], "backup before the write (D51)"
        assert stats["generic_contests_resolved"] == 1
        assert stats["ghost_tags_planned"] == 1
        assert stats["ghost_tags_confirmed"] == 1
        assert stats["anchored"] == 1
        # ESPN's date is its TBD placeholder, so the only start worth printing
        # is the venue's — carried onto the one card that is kept.
        assert kalshi.commence_time == _at("2026-09-30T01:00Z")
        assert kalshi.commence_time_source == "polymarket_venue"
        assert stats["start_carried_from_ghost"] == 1

    async def test_control_a_named_tournament_keeps_the_old_scope(self, monkeypatch):
        """The same two rows against a US Open board: the tournament bucket
        owns it, the generic pass has no competition, nothing is written."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        kalshi, poly = _specimen_rows()
        tags = _TagRecorder().install(monkeypatch)
        board = [_payload([_competition(
            "183497", ["Alex Michelsen", "Carlos Alcaraz"], date="2026-09-30T04:00Z",
        )], event_name="US Open")]
        _install_generic(
            monkeypatch, payloads=board, sport_keys=KEYS,
            generic=[(kalshi, "tennis_atp"), (poly, "tennis_other")],
            tournament_events=[],
        )

        stats = await _sync_tennis_from_espn()

        assert stats["generic_competitions"] == 0
        assert kalshi.espn_id is None and poly.espn_id is None
        assert tags.written == []

    async def test_a_refused_stamp_labels_nobody(self, monkeypatch):
        """Another row already holds 183497: the canonical never gets the id,
        so hiding the other card would hide it behind nothing."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        kalshi, poly = _specimen_rows()
        tags = _TagRecorder().install(monkeypatch)
        _install_generic(
            monkeypatch, payloads=_japan_open_board(), sport_keys=KEYS,
            generic=[(kalshi, "tennis_atp"), (poly, "tennis_other")],
            holders={"183497": 99},
        )

        stats = await _sync_tennis_from_espn()

        assert kalshi.espn_id is None
        assert stats["generic_contests_resolved"] == 1
        assert stats["ghost_tags_planned"] == 0
        assert kalshi.commence_time == _at("2026-09-29T05:00Z"), (
            "no anchor, no carry: the start rides the same gate as the label")
        assert tags.written == []

    async def test_no_fold_no_label(self, monkeypatch):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        kalshi, poly = _specimen_rows()
        tags = _TagRecorder(fold_live=False).install(monkeypatch)
        _install_generic(
            monkeypatch, payloads=_japan_open_board(), sport_keys=KEYS,
            generic=[(kalshi, "tennis_atp"), (poly, "tennis_other")],
        )

        stats = await _sync_tennis_from_espn()

        assert stats["ghost_tags_withheld_fold_dark"] == 1
        assert tags.written == []

    async def test_a_row_already_labelled_is_left_out_and_its_twin_anchors_alone(
        self, monkeypatch
    ):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        kalshi, poly = _specimen_rows()
        poly.event_tags = ["provenance:duplicate-of:15320475"]
        tags = _TagRecorder().install(monkeypatch)
        _install_generic(
            monkeypatch, payloads=_japan_open_board(), sport_keys=KEYS,
            generic=[(kalshi, "tennis_atp"), (poly, "tennis_other")],
        )

        stats = await _sync_tennis_from_espn()

        assert stats["generic_events_considered"] == 1
        assert kalshi.espn_id == "183497"
        assert stats["generic_contests_resolved"] == 0
        assert tags.written == []

    async def test_a_scored_ghost_keeps_the_old_refusal(self, monkeypatch):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        kalshi, poly = _specimen_rows()
        poly.home_score, poly.away_score = 2, 0
        tags = _TagRecorder().install(monkeypatch)
        _install_generic(
            monkeypatch, payloads=_japan_open_board(), sport_keys=KEYS,
            generic=[(kalshi, "tennis_atp"), (poly, "tennis_other")],
        )

        stats = await _sync_tennis_from_espn()

        assert stats["generic_contests_refused"] == {CONTEST_SETTLED_GHOST: 1}
        assert kalshi.espn_id is None and poly.espn_id is None
        assert tags.written == []
