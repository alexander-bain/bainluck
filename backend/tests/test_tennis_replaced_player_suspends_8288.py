"""#8288 — a player withdraws, ESPN fills the slot under the same competition id,
and the match we hold stops reading LIVE.

Specimens, production 2026-09-30 07:18Z (China Open WTA):

* ``15320690`` Marcinko v Frech, ``espn_id 184289``, LIVE from 02:00Z with no
  score. ESPN ``184289`` now lists Frech v Jacquemot, scheduled 11:00Z.
* ``15320688`` Golubic v Korneeva, ``espn_id 184283``, LIVE. ESPN ``184283`` now
  lists Kalieva v Golubic, FINAL.

The anchor pass refused both as ``no-candidate`` and stopped there. The refusal
is right (the competition's result is not ours to copy); the gap is that
nothing turned "one of our players is gone from our own competition" into a
state.
"""

from __future__ import annotations

from app.utils.espn_tennis_anchor import (
    REJECT_AMBIGUOUS,
    REJECT_NO_CANDIDATE,
    anchor_receipt,
    replaced_player,
)
from app.services.espn_tennis import scoreboard_competitions
from tests.test_espn_tennis_anchor import (
    _Event,
    _at,
    _competition,
    _install,
    _lost,
    _payload,
    _won,
)

CHINA_OPEN = "China Open"
KEYS = ["tennis_wta_china_open", "tennis_wta"]


def _board(*competitions):
    return [_payload(list(competitions), slug="womens-singles", event_name=CHINA_OPEN)]


def _frech_v_jacquemot():
    return _competition(
        "184289", ["Magdalena Frech", "Elsa Jacquemot"],
        date="2026-09-30T11:00Z",
    )


def _kalieva_v_golubic_final():
    return _competition(
        "184283", ["Elvina Kalieva", "Viktorija Golubic"], state="post",
        status_name="STATUS_FINAL", period=2, date="2026-09-30T03:10Z",
        linescores=[_won(6, 6), _lost(3, 2)],
    )


def _marcinko(status="live", espn_id="184289"):
    return _Event(
        15320690, "Marcinko", "Frech", status, _at("2026-09-30T02:00Z"),
        espn_id=espn_id,
    )


def _hold(ours, competitions, *, status="live", espn_id="184289", own=None):
    """`replaced_player` with the receipt the real matcher gives."""
    comps = scoreboard_competitions(_board(*competitions))
    by_id = {c["espn_competition_id"]: c for c in comps}
    receipt = anchor_receipt(ours, comps, our_commence_time=_at("2026-09-30T02:00Z"))
    return replaced_player(
        our_status=status,
        our_espn_id=espn_id,
        ours=ours,
        receipt=receipt,
        competition=by_id.get(own or espn_id),
    ), receipt


# ═══════════════════════════ the task, end to end ═══════════════════════════


class TestTheSpecimensLeaveLive:
    async def test_marcinko_v_frech_is_suspended_and_keeps_nothing_of_jacquemots(
        self, monkeypatch
    ):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _marcinko()
        _install(monkeypatch, payloads=_board(_frech_v_jacquemot()), errors=[],
                 sport_keys=KEYS, events=[event])

        stats = await _sync_tennis_from_espn()

        assert event.status == "suspended"
        assert stats["replaced_player_holds"] == 1
        assert stats["refused"] == {REJECT_NO_CANDIDATE: 1}
        # The refusal still stands: nothing of 184289's fixture reaches the row.
        assert event.commence_time == _at("2026-09-30T02:00Z")
        assert event.home_score is None and event.away_score is None
        assert event.completed_at is None
        assert stats["row_errors"] == 0

    async def test_golubic_v_korneeva_is_suspended_not_given_kalievas_final(
        self, monkeypatch
    ):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _Event(15320688, "Golubic", "Korneeva", "live",
                       _at("2026-09-30T02:00Z"), espn_id="184283")
        _install(monkeypatch, payloads=_board(_kalieva_v_golubic_final()), errors=[],
                 sport_keys=KEYS, events=[event])

        stats = await _sync_tennis_from_espn()

        assert event.status == "suspended", "not a Final: Korneeva never played"
        assert event.home_score is None and event.away_score is None
        assert event.completed_at is None
        assert stats["replaced_player_holds"] == 1
        assert stats["score_writes"] == 0

    async def test_a_scheduled_row_whose_player_withdrew_leaves_the_schedule(
        self, monkeypatch
    ):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _marcinko(status="scheduled")
        _install(monkeypatch, payloads=_board(_frech_v_jacquemot()), errors=[],
                 sport_keys=KEYS, events=[event])

        stats = await _sync_tennis_from_espn()

        assert event.status == "suspended"
        assert stats["replaced_player_holds"] == 1

    async def test_the_next_pass_writes_nothing_more(self, monkeypatch):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _marcinko(status="suspended")
        _install(monkeypatch, payloads=_board(_frech_v_jacquemot()), errors=[],
                 sport_keys=KEYS, events=[event])

        stats = await _sync_tennis_from_espn()

        assert event.status == "suspended"
        assert stats.get("replaced_player_holds", 0) == 0


class TestTheControlsStayLive:
    """Each clause of `replaced_player`, falsified on its own through the task."""

    async def test_an_unanchored_row_with_the_same_refusal_is_untouched(
        self, monkeypatch
    ):
        """No id means no record of which competition was ours, so a player
        missing from the draw is a finding, not a withdrawal."""
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _marcinko(espn_id=None)
        _install(monkeypatch, payloads=_board(_frech_v_jacquemot()), errors=[],
                 sport_keys=KEYS, events=[event])

        stats = await _sync_tennis_from_espn()

        assert event.status == "live"
        assert stats["refused"] == {REJECT_NO_CANDIDATE: 1}
        assert stats.get("replaced_player_holds", 0) == 0

    async def test_a_row_whose_own_competition_is_off_this_board_is_untouched(
        self, monkeypatch
    ):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _marcinko(espn_id="184000")
        _install(monkeypatch, payloads=_board(_frech_v_jacquemot()), errors=[],
                 sport_keys=KEYS, events=[event])

        stats = await _sync_tennis_from_espn()

        assert event.status == "live"
        assert stats.get("replaced_player_holds", 0) == 0

    async def test_a_row_whose_competition_still_holds_both_players_anchors(
        self, monkeypatch
    ):
        from app.tasks.espn_sync import _sync_tennis_from_espn

        event = _marcinko()
        _install(
            monkeypatch,
            payloads=_board(_competition(
                "184289", ["Magdalena Frech", "Anna Marcinko"],
                state="in", period=1, date="2026-09-30T02:00Z",
                linescores=[[{"value": 2.0}], [{"value": 1.0}]],
            )),
            errors=[], sport_keys=KEYS, events=[event],
        )

        stats = await _sync_tennis_from_espn()

        assert event.status == "live"
        assert stats["already_anchored"] == 1
        assert stats.get("replaced_player_holds", 0) == 0


class TestTheRuleRefusesEveryOtherShape:
    def test_the_specimen_is_named(self):
        gone, receipt = _hold(["Marcinko", "Frech"], [_frech_v_jacquemot()])
        assert receipt["absent_players"] == ["Marcinko"]
        assert gone == "Marcinko"

    def test_the_absent_player_may_be_either_side(self):
        gone, _ = _hold(["Frech", "Marcinko"], [_frech_v_jacquemot()])
        assert gone == "Marcinko"

    def test_a_settled_row_is_never_touched(self):
        for status in ("completed", "closed", "suspended"):
            gone, _ = _hold(["Marcinko", "Frech"], [_frech_v_jacquemot()], status=status)
            assert gone is None, status

    def test_neither_player_on_the_board_is_another_tournament(self):
        gone, receipt = _hold(["Andreeva", "Gauff"], [_frech_v_jacquemot()])
        assert receipt["reason"] != REJECT_NO_CANDIDATE
        assert gone is None

    def test_our_present_player_missing_from_our_own_competition_refuses(self):
        """Frech is on the board, but not in 184289 — whatever happened to our
        competition, it is not a one-slot replacement."""
        gone, receipt = _hold(
            ["Marcinko", "Frech"],
            [
                _competition("184289", ["Elsa Jacquemot", "Leolia Jeanjean"],
                             date="2026-09-30T11:00Z"),
                _competition("184290", ["Magdalena Frech", "Qinwen Zheng"],
                             date="2026-09-30T12:00Z"),
            ],
        )
        assert receipt["absent_players"] == ["Marcinko"]
        assert gone is None

    def test_the_absent_player_elsewhere_in_the_window_is_not_absent(self):
        """A draw that moved Marcinko to another competition is not a
        withdrawal; the receipt names nobody absent and the rule refuses."""
        gone, receipt = _hold(
            ["Marcinko", "Frech"],
            [
                _frech_v_jacquemot(),
                _competition("184300", ["Anna Marcinko", "Qinwen Zheng"],
                             date="2026-09-30T12:00Z"),
            ],
        )
        assert receipt["absent_players"] == []
        assert gone is None

    def test_a_placeholder_slot_is_not_a_replacement_yet(self):
        """ESPN can show the vacated slot as "Lucky Loser" before it names one.
        That is a draw position, not a person, so this pass refuses; the pass
        after ESPN fills the name suspends the row."""
        comp = scoreboard_competitions(_board(_frech_v_jacquemot()))[0]
        receipt = {"reason": REJECT_NO_CANDIDATE, "absent_players": ["Marcinko"]}
        args = dict(our_status="live", our_espn_id="184289",
                    ours=["Marcinko", "Frech"], receipt=receipt)
        assert replaced_player(**args, competition=comp) == "Marcinko"
        slot = {**comp, "players": ["Magdalena Frech", "Lucky Loser"]}
        assert replaced_player(**args, competition=slot) is None

    def test_only_a_no_candidate_refusal_with_one_absent_player_qualifies(self):
        comp = scoreboard_competitions(_board(_frech_v_jacquemot()))[0]
        args = dict(our_status="live", our_espn_id="184289",
                    ours=["Marcinko", "Frech"], competition=comp)
        assert replaced_player(**args, receipt={
            "reason": REJECT_NO_CANDIDATE, "absent_players": ["Marcinko"],
        }) == "Marcinko"
        assert replaced_player(**args, receipt={
            "reason": REJECT_AMBIGUOUS, "absent_players": ["Marcinko"],
        }) is None
        assert replaced_player(**args, receipt={
            "reason": REJECT_NO_CANDIDATE, "absent_players": ["Marcinko", "Frech"],
        }) is None

    def test_our_own_competition_moved_outside_the_window_still_holding_both(self):
        """The receipt only searches the tournament window, so it can call
        Marcinko absent while our own competition, rescheduled past the window,
        still names her. That is not a withdrawal."""
        gone, receipt = _hold(
            ["Marcinko", "Frech"],
            [
                _competition("184289", ["Magdalena Frech", "Anna Marcinko"],
                             date="2026-10-05T11:00Z"),
                _competition("184290", ["Magdalena Frech", "Elsa Jacquemot"],
                             date="2026-09-30T12:00Z"),
            ],
        )
        assert receipt["absent_players"] == ["Marcinko"]
        assert gone is None

    def test_a_competition_other_than_the_rows_own_is_refused(self):
        comp = scoreboard_competitions(_board(_frech_v_jacquemot()))[0]
        receipt = {"reason": REJECT_NO_CANDIDATE, "absent_players": ["Marcinko"]}
        assert replaced_player(
            our_status="live", our_espn_id="184000", ours=["Marcinko", "Frech"],
            receipt=receipt, competition=comp,
        ) is None
        assert replaced_player(
            our_status="live", our_espn_id="184289", ours=["Marcinko", "Frech"],
            receipt=receipt, competition=comp,
        ) == "Marcinko", "the strawman: the same inputs with the row's own id pass"
