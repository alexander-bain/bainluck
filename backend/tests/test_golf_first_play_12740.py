"""#12740: golf "Pregame"'s cutoff is the first poll that saw round-1 play.

Each rule in ``golf_first_play`` closes one way the cutoff could lie: set once,
round 1 only, this event only, never raises.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.utils import golf_first_play as gfp

T0 = datetime(2025, 3, 6, 12, 5, tzinfo=timezone.utc)


class _Redis:
    def __init__(self):
        self.store: dict = {}
        self.ttl: dict = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        self.ttl[key] = ex
        return True

    def get(self, key):
        return self.store.get(key)


def _p(rnd, thru):
    return SimpleNamespace(current_round=rnd, thru=thru)


def test_holes_done_reads_datagolfs_thru_strings():
    assert gfp._holes_done("1") and gfp._holes_done("18") and gfp._holes_done("F")
    assert not gfp._holes_done("") and not gfp._holes_done("0") and not gfp._holes_done(None)


def test_round_one_play_is_recorded_once_and_never_moves():
    r = _Redis()
    first = gfp.note_first_play(r, tour="pga", event_ids={"14"}, players=[_p(1, "2")], now=T0)
    later = gfp.note_first_play(
        r, tour="pga", event_ids={"14"}, players=[_p(1, "9")], now=T0 + timedelta(hours=3)
    )
    assert first == ["14"] and later == []
    assert gfp.read_first_play(r, "pga", "14") == T0
    assert r.ttl[gfp.first_play_key("pga", "14")] == gfp.FIRST_PLAY_TTL_S


def test_before_anyone_tees_off_nothing_is_recorded():
    r = _Redis()
    assert gfp.note_first_play(
        r, tour="pga", event_ids={"14"}, players=[_p(1, ""), _p(1, "0")], now=T0
    ) == []
    assert gfp.read_first_play(r, "pga", "14") is None


def test_a_first_sighting_in_round_two_records_nothing():
    # A cutoff dated inside the tournament would make "Pregame" a mid-event number.
    r = _Redis()
    assert gfp.note_first_play(
        r, tour="pga", event_ids={"14"}, players=[_p(2, "5"), _p(2, "F")], now=T0
    ) == []
    assert gfp.read_first_play(r, "pga", "14") is None


def test_no_event_id_means_no_write():
    r = _Redis()
    assert gfp.note_first_play(r, tour="pga", event_ids={None, ""}, players=[_p(1, "3")]) == []
    assert r.store == {}


def test_a_redis_failure_never_raises():
    class _Down:
        def set(self, *a, **k):
            raise ConnectionError("down")

        def get(self, *a, **k):
            raise ConnectionError("down")

    assert gfp.note_first_play(_Down(), tour="pga", event_ids={"14"}, players=[_p(1, "3")]) == []
    assert gfp.read_first_play(_Down(), "pga", "14") is None


def test_the_live_poll_names_only_the_in_play_events_markets():
    """The poll passes the ids of markets named for THIS in-play event only."""
    import inspect

    from app.tasks import datagolf

    src = inspect.getsource(datagolf._poll_datagolf_live)
    assert "note_first_play(" in src
    assert 'startswith(f"{_event_name} - ")' in src
    assert "_event_id_of(m.external_id)" in src
