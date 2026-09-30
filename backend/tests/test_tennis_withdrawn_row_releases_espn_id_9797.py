"""#9797 — a withdrawn tennis match gives its ESPN id back, so the match ESPN
now lists under that id can be anchored.

#8288 suspends a row whose player withdrew and, on purpose, leaves its
``espn_id`` alone. ESPN keeps the competition id for the lucky loser, so the id
now names a DIFFERENT match that we also hold, and ``stamp_espn_id_if_unheld``
refused that match on every pass. Production, 2026-09-30 10:4xZ: all four rows
the hold had suspended still held their competition's id, e.g.

* ``15320486`` Musetti v Fery held ``183485``; ESPN lists ``183485`` as
  Fery v Faria at 02:00Z, and our Fery v Faria row printed a start 12 h late.
* ``15320690`` Marcinko v Frech held ``184289``; ESPN lists it as
  Frech v Jacquemot (the specimen these tests drive).
"""

from __future__ import annotations

from app.utils.espn_tennis_anchor import (
    ESPN_ID_RELEASED_TAG_PREFIX,
    REJECT_AMBIGUOUS,
    REJECT_NO_CANDIDATE,
    anchor_receipt,
    released_espn_id,
    replaced_player,
)
from app.services.espn_tennis import scoreboard_competitions
from tests.test_espn_tennis_anchor import _Event, _Session, _at, _competition
from tests.test_tennis_replaced_player_suspends_8288 import (
    KEYS,
    _board,
    _frech_v_jacquemot,
)

RELEASED_TAG = f"{ESPN_ID_RELEASED_TAG_PREFIX}184289"


class _LiveHolderSession(_Session):
    """The rig's session, with the holder probe read off the rows themselves.

    The parent answers ``espn_id_holder`` from a static map, which cannot show
    a holder going away mid-pass. This one answers it the way the database
    does: the row, other than the one being stamped, whose ``espn_id`` is the
    bound value right now. ``flushes`` counts the explicit flushes.
    """

    def __init__(self, sport_keys, events):
        super().__init__(sport_keys, events)
        self._rows = list(events)
        self.flushes = 0

    async def flush(self):
        self.flushes += 1

    async def execute(self, statement, *a, **kw):
        from sqlalchemy.sql.dml import Update

        if isinstance(statement, Update) or self._answers:
            return await super().execute(statement, *a, **kw)
        from tests.test_espn_tennis_anchor import _Result

        bound = {
            str(v) for v in statement.compile().params.values() if v is not None
        }
        for row in self._rows:
            if row.espn_id and str(row.espn_id) in bound and str(row.id) not in bound:
                return _Result([row.id])
        return _Result([])


def _install(monkeypatch, events):
    from app.services import espn_tennis as svc
    from app.tasks import espn_sync

    session = _LiveHolderSession(KEYS, events)
    payloads = _board(_frech_v_jacquemot())
    monkeypatch.setattr(svc, "fetch_scoreboards", lambda dates=None: (payloads, []))
    monkeypatch.setattr(espn_sync, "get_task_session", lambda: session)
    return session


def _withdrawn(status="suspended", espn_id="184289", tags=None):
    return _Event(
        15320690, "Marcinko", "Frech", status, _at("2026-09-30T02:00Z"),
        espn_id=espn_id, event_tags=tags or ["provenance:source:kalshi"],
    )


def _replacement():
    """The match ESPN now lists under 184289, held by us with no id and a
    start that is not ESPN's (the Fery v Faria shape: 12 h late)."""
    return _Event(
        15321636, "Magdalena Frech", "Elsa Jacquemot", "scheduled",
        _at("2026-09-30T23:00Z"), commence_time_source="odds_api",
        event_tags=["provenance:source:odds_api"],
    )


# ═══════════════════════════ the task, end to end ═══════════════════════════


class TestTheReplacementMatchGetsTheId:
    async def test_same_pass_the_withdrawn_row_releases_and_the_real_match_anchors(
        self, monkeypatch
    ):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        gone, real = _withdrawn(), _replacement()
        session = _install(monkeypatch, [gone, real])

        stats = await _sync_tennis_from_espn()

        assert gone.espn_id is None
        assert gone.status == "suspended", "the #8288 hold is unchanged"
        assert gone.event_tags == ["provenance:source:kalshi", RELEASED_TAG]
        assert stats["replaced_player_id_releases"] == 1
        assert session.flushes >= 1, "the release is flushed before any stamp"
        # The ship: the match that will be played now carries the id, and
        # ESPN's clock replaces the start nobody could correct.
        assert real.espn_id == "184289"
        assert stats["anchored"] == 1
        assert real.commence_time == _at("2026-09-30T11:00Z")
        assert real.commence_time_source == "espn"
        assert stats.get("stamp_refused", 0) == 0
        assert stats["row_errors"] == 0

    async def test_replacement_read_first_is_refused_this_pass_and_stamped_the_next(
        self, monkeypatch
    ):
        """Production's order: the tournament-keyed replacement is read before
        the generic row holding the id. One pass late, never never."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        gone, real = _withdrawn(), _replacement()
        _install(monkeypatch, [real, gone])
        first = await _sync_tennis_from_espn()

        assert first["stamp_refused"] == 1
        assert first["stamp_refused_holders"] == {"15321636": 15320690}
        assert first["replaced_player_id_releases"] == 1
        assert real.espn_id is None and gone.espn_id is None

        _install(monkeypatch, [real, gone])
        second = await _sync_tennis_from_espn()

        assert real.espn_id == "184289"
        assert real.commence_time == _at("2026-09-30T11:00Z")
        assert second["anchored"] == 1
        assert second.get("stamp_refused", 0) == 0
        assert second["replaced_player_id_releases"] == 0
        assert gone.event_tags.count(RELEASED_TAG) == 1, "released once, tagged once"

    async def test_a_live_row_is_held_and_released_in_one_pass(self, monkeypatch):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        gone = _withdrawn(status="live")
        _install(monkeypatch, [gone])

        stats = await _sync_tennis_from_espn()

        assert gone.status == "suspended"
        assert gone.espn_id is None
        assert stats["replaced_player_holds"] == 1
        assert stats["replaced_player_id_releases"] == 1


class TestTheControlsKeepTheirId:
    async def test_before_this_fix_the_holder_refused_the_real_match_forever(
        self, monkeypatch
    ):
        """The strawman: the same rows with the release unreachable (a settled
        withdrawn row) reproduce the production refusal."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        gone, real = _withdrawn(status="completed"), _replacement()
        for _ in range(2):
            _install(monkeypatch, [real, gone])
            stats = await _sync_tennis_from_espn()
            assert stats["stamp_refused"] == 1

        assert gone.espn_id == "184289", "a settled row keeps the id its result used"
        assert real.espn_id is None
        assert real.commence_time == _at("2026-09-30T23:00Z")
        assert stats["replaced_player_id_releases"] == 0

    async def test_a_row_whose_competition_still_holds_both_players_keeps_it(
        self, monkeypatch
    ):
        from app.services import espn_tennis as svc
        from app.tasks.espn_sync import _sync_tennis_from_espn

        gone = _withdrawn(status="scheduled")
        session = _install(monkeypatch, [gone])
        both = _board(_competition(
            "184289", ["Magdalena Frech", "Anna Marcinko"], date="2026-09-30T11:00Z",
        ))
        monkeypatch.setattr(svc, "fetch_scoreboards", lambda dates=None: (both, []))

        stats = await _sync_tennis_from_espn()

        assert gone.espn_id == "184289"
        assert stats["already_anchored"] == 1
        assert stats["replaced_player_id_releases"] == 0
        assert session.flushes == 0

    async def test_an_unanchored_row_with_the_same_refusal_releases_nothing(
        self, monkeypatch
    ):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        gone = _withdrawn(espn_id=None)
        _install(monkeypatch, [gone])

        stats = await _sync_tennis_from_espn()

        assert stats["refused"] == {REJECT_NO_CANDIDATE: 1}
        assert stats["replaced_player_id_releases"] == 0
        assert gone.event_tags == ["provenance:source:kalshi"]


# ═══════════════════════════ the rule, clause by clause ══════════════════════


def _release(ours, competitions, *, status="suspended", espn_id="184289", own=None):
    comps = scoreboard_competitions(_board(*competitions))
    by_id = {c["espn_competition_id"]: c for c in comps}
    receipt = anchor_receipt(ours, comps, our_commence_time=_at("2026-09-30T02:00Z"))
    return released_espn_id(
        our_status=status, our_espn_id=espn_id, ours=ours, receipt=receipt,
        competition=by_id.get(own or espn_id),
    )


class TestTheRule:
    def test_the_specimen_releases_its_id(self):
        assert _release(["Marcinko", "Frech"], [_frech_v_jacquemot()]) == "184289"

    def test_every_unsettled_status_releases_and_a_settled_one_never(self):
        for status in ("live", "scheduled", "suspended"):
            assert _release(["Marcinko", "Frech"], [_frech_v_jacquemot()],
                            status=status) == "184289", status
        for status in ("completed", "closed"):
            assert _release(["Marcinko", "Frech"], [_frech_v_jacquemot()],
                            status=status) is None, status

    def test_it_never_releases_where_the_hold_would_not_have_acted(self):
        """Same evidence as #8288: for every non-status shape the hold refuses,
        the release refuses too."""
        shapes = [
            (["Marcinko", "Frech"], [_frech_v_jacquemot()], "184000"),  # not our id
            (["Andreeva", "Gauff"], [_frech_v_jacquemot()], "184289"),  # other event
            (["Marcinko", "Frech"], [  # absent player moved, not withdrawn
                _frech_v_jacquemot(),
                _competition("184300", ["Anna Marcinko", "Qinwen Zheng"],
                             date="2026-09-30T12:00Z"),
            ], "184289"),
            (["Marcinko", "Frech"], [  # our present player gone from our comp too
                _competition("184289", ["Elsa Jacquemot", "Leolia Jeanjean"],
                             date="2026-09-30T11:00Z"),
                _competition("184290", ["Magdalena Frech", "Qinwen Zheng"],
                             date="2026-09-30T12:00Z"),
            ], "184289"),
        ]
        for ours, comps, espn_id in shapes:
            assert _release(ours, comps, espn_id=espn_id) is None, (ours, espn_id)
            comp_list = scoreboard_competitions(_board(*comps))
            receipt = anchor_receipt(
                ours, comp_list, our_commence_time=_at("2026-09-30T02:00Z"))
            assert replaced_player(
                our_status="live", our_espn_id=espn_id, ours=ours, receipt=receipt,
                competition={c["espn_competition_id"]: c for c in comp_list}.get(espn_id),
            ) is None

    def test_a_placeholder_slot_and_an_ambiguous_refusal_release_nothing(self):
        comp = scoreboard_competitions(_board(_frech_v_jacquemot()))[0]
        args = dict(our_status="suspended", our_espn_id="184289",
                    ours=["Marcinko", "Frech"])
        named = {"reason": REJECT_NO_CANDIDATE, "absent_players": ["Marcinko"]}
        assert released_espn_id(**args, receipt=named, competition=comp) == "184289"
        slot = {**comp, "players": ["Magdalena Frech", "Lucky Loser"]}
        assert released_espn_id(**args, receipt=named, competition=slot) is None
        assert released_espn_id(**args, competition=comp, receipt={
            "reason": REJECT_AMBIGUOUS, "absent_players": ["Marcinko"],
        }) is None

    def test_the_hold_is_unchanged_by_the_refactor(self):
        comp = scoreboard_competitions(_board(_frech_v_jacquemot()))[0]
        receipt = {"reason": REJECT_NO_CANDIDATE, "absent_players": ["Marcinko"]}
        base = dict(our_espn_id="184289", ours=["Marcinko", "Frech"],
                    receipt=receipt, competition=comp)
        assert replaced_player(our_status="live", **base) == "Marcinko"
        assert replaced_player(our_status="scheduled", **base) == "Marcinko"
        assert replaced_player(our_status="suspended", **base) is None
