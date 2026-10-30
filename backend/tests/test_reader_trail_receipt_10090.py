"""#10090 — total unnecessary delay, server half: the receipt fields that let a
readout compute how long live game pages trailed a newer price our server held.

SHIP: Alex sees, every 5 minutes, the total seconds live game pages spent
trailing a newer price our server already held, plus the single worst case.

Speed's 04:18Z definition: an input is eligible when it would change the
blended value readers are shown; the server trails from our receipt of the
oldest eligible input readers lack until the first publication that carries it
(a DNPL preview, a stamp, or any writer's revision); total = union per event,
worst = longest single interval.

  field 1  `first_new_recv` on every stamps= item and preview publication,
           judged against the last value PUBLISHED (preview or stamp), so a
           stamp after its own preview carries `-`;
  field 2  previews=base_rev:seq@published_at@first_new_recv in the minute
           receipt, bounded like stamps=;
  field 3  the same stamps= item, with writer=, from every writer that
           advances the frame revision (Polymarket withdrawal, the sportsbook
           and model writers);
  parser   `trailing_readout.trailing`: per-event total / worst / over-1 s.

Each field's tests fail on the serving base 31baf599 (no such receipt part).
"""

import logging
from types import SimpleNamespace

import pytest

import app.tasks.live_blend_refresh as blend_mod
from app.tasks.live_blend_refresh import TailReceipts

LOGGER = "app.tasks.live_blend_refresh"
EPOCH = 1_791_321_600.0  # 2026-10-06T21:20:00Z, a minute boundary
E = 15338291
A, B = 501, 502


class _Clock:
    def __init__(self):
        self.t = 0.0


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(blend_mod, "_mono", lambda: c.t)
    monkeypatch.setattr(blend_mod, "_wall", lambda: EPOCH + c.t)
    return c


@pytest.fixture(autouse=True)
def _info(caplog, monkeypatch):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(blend_mod, "_live_handoff", {})


def _iso(t):
    return blend_mod._iso(EPOCH + t)


#: The price each headline outcome last had this run before a test's inputs:
#: a first input of a run never joins the trail (F1), so every test that
#: expects a credit starts from a prior.
SEED = 0.01


def _receipts(source="kalshi", seed=(A, B)):
    blend_mod._live_handoff[source] = frozenset({E})
    r = TailReceipts(source)
    r._last_p[E] = dict.fromkeys(seed, SEED)
    return r


def _input(r, clock, t, oid, p):
    clock.t = t
    return r.note_input(E, oid, p, "ticker")


def _commit(r, *rows):
    r.note_committed_rows([SimpleNamespace(id=oid, current_probability=p) for oid, p in rows])


def _preview(r, clock, t, p, seq, base_rev=100, reply="published", kind="blend"):
    clock.t = t
    r.note_preview(
        {"event_id": E, "p": p if kind == "blend" else None,
         "preview": {"kind": kind, "seq": seq, "base_rev": base_rev}},
        {"gen": 1, "seq": seq}, (reply,),
    )


def _stamp(r, clock, t, p, rev, mark, *, frame_rev=None, reread=False, commit=True):
    """A committed stamp of ``mark``'s flush. ``commit``: the flush's RETURNING
    row stored ``mark``'s own price first, as production notes it before
    staging (F2: no other input is credited from it)."""
    clock.t = t
    if commit and mark is not None:
        _commit(r, (mark.outcome_id, mark.probability))
    r.note_stamp_frame(E, rev if frame_rev is None else frame_rev, p, "live")
    if mark is not None:
        r.observe({E: mark}, EPOCH + t, {E}, t)
    disposition = ("stamped", 0.55, f"stamped-{rev}", None, rev, "live")
    if reread:
        disposition += (False,)
    r.resolve([E], {E: disposition}, {E: mark} if mark is not None else {}, EPOCH + t, t)


def _lines(caplog, kind="delivery-receipt"):
    out = []
    for rec in caplog.records:
        msg = rec.getMessage()
        if f"{kind} " in msg:
            out.append(dict(kv.split("=", 1) for kv in msg.split(f"{kind} ", 1)[1].split()
                            if "=" in kv))
    return out


def _close(r, caplog):
    r.close_all("test")
    lines = [line for line in _lines(caplog) if line["event"] == str(E)]
    assert lines, "the live event wrote a receipt line"
    return lines


def _stamps(lines):
    return [s.split("@") for line in lines if line["stamps"] != "-"
            for s in line["stamps"].split(";")]


def _previews(lines):
    return [p.split("@") for line in lines if line.get("previews", "-") != "-"
            for p in line["previews"].split(";")]


# ── field 1: first_new_recv ──────────────────────────────────────────────────


def test_a_stamp_after_its_own_preview_carries_no_first_new_recv(clock, caplog):
    r = _receipts()
    m1 = _input(r, clock, 0.1, A, 0.55)
    _input(r, clock, 0.2, B, 0.45)
    _commit(r, (A, 0.55), (B, 0.45))  # the flush's RETURNING rows, before staging
    _preview(r, clock, 0.4, 0.62, seq=7)
    _stamp(r, clock, 0.9, 0.62, 101, m1)
    lines = _close(r, caplog)
    (preview,) = _previews(lines)
    assert preview == ["100:7", _iso(0.4), _iso(0.1)]
    (stamp,) = _stamps(lines)
    assert len(stamp) == 6 and stamp[0] == "101"
    assert stamp[5] == "-"  # the preview had already shown both inputs


def test_a_stamp_with_no_preview_is_first_from_its_oldest_changed_input(clock, caplog):
    r = _receipts()
    m0 = _input(r, clock, 0.0, A, 0.50)
    _stamp(r, clock, 0.5, 0.60, 100, m0)
    _input(r, clock, 1.0, A, 0.50)  # a repeat: it cannot change anything
    m2 = _input(r, clock, 2.0, A, 0.52)
    _stamp(r, clock, 2.5, 0.61, 101, m2)
    stamps = _stamps(_close(r, caplog))
    assert [s[5] for s in stamps] == [_iso(0.0), _iso(2.0)]


def test_an_unchanged_blend_carries_no_change_readers_lacked(clock, caplog):
    r = _receipts()
    m0 = _input(r, clock, 0.0, A, 0.50)
    _stamp(r, clock, 0.5, 0.60, 100, m0)
    m1 = _input(r, clock, 1.0, B, 0.31)  # moved a leg, not the headline
    _stamp(r, clock, 1.5, 0.60, 101, m1)
    m2 = _input(r, clock, 2.0, A, 0.52)
    _stamp(r, clock, 2.5, 0.61, 102, m2)
    stamps = _stamps(_close(r, caplog))
    assert [s[5] for s in stamps] == [_iso(0.0), "-", _iso(2.0)]  # B was carried at 1.5


def test_a_revoke_puts_the_previewed_inputs_back_from_the_revoke_instant(clock, caplog):
    r = _receipts()
    m0 = _input(r, clock, 0.0, A, 0.50)
    _stamp(r, clock, 0.5, 0.60, 100, m0)
    m1 = _input(r, clock, 1.0, A, 0.55)
    _commit(r, (A, 0.55))
    _preview(r, clock, 1.2, 0.62, seq=3)
    _preview(r, clock, 5.0, None, seq=4, kind="revoke")  # readers fall back to 0.60
    _stamp(r, clock, 6.0, 0.62, 101, m1)
    lines = _close(r, caplog)
    assert [p[2] for p in _previews(lines)] == [_iso(1.0)]  # revokes are not listed
    assert [s[5] for s in _stamps(lines)] == [_iso(0.0), _iso(5.0)]


def test_a_preview_composed_on_an_older_revision_than_a_stamp_reaches_no_reader(clock, caplog):
    r = _receipts()
    m0 = _input(r, clock, 0.0, A, 0.50)
    _stamp(r, clock, 0.5, 0.60, 110, m0)
    m1 = _input(r, clock, 1.0, A, 0.55)
    _commit(r, (A, 0.55))
    _preview(r, clock, 1.2, 0.62, seq=3, base_rev=105)  # readers hold rev 110
    _stamp(r, clock, 2.0, 0.62, 111, m1)
    lines = _close(r, caplog)
    assert [p[2] for p in _previews(lines)] == ["-"]
    assert [s[5] for s in _stamps(lines)] == [_iso(0.0), _iso(1.0)]


def test_committed_rows_carry_only_the_price_that_was_stored(clock, caplog):
    r = _receipts()
    _input(r, clock, 0.1, A, 0.55)
    m2 = _input(r, clock, 0.2, A, 0.57)  # arrived after the write took its snapshot
    _commit(r, (A, 0.55))
    _preview(r, clock, 0.3, 0.62, seq=1)
    _stamp(r, clock, 0.8, 0.63, 101, m2)
    lines = _close(r, caplog)
    assert [p[2] for p in _previews(lines)] == [_iso(0.1)]
    assert [s[5] for s in _stamps(lines)] == [_iso(0.2)]


def test_a_preview_redis_refused_is_not_a_publication(clock, caplog):
    r = _receipts()
    m1 = _input(r, clock, 0.1, A, 0.55)
    _commit(r, (A, 0.55))
    _preview(r, clock, 0.3, 0.62, seq=1, reply="stale")
    _stamp(r, clock, 0.8, 0.62, 101, m1)
    lines = _close(r, caplog)
    assert _previews(lines) == []
    assert [s[5] for s in _stamps(lines)] == [_iso(0.1)]


def test_a_stamp_frame_noted_for_another_revision_is_not_credited(clock, caplog):
    """The value is taken only for the revision that committed: a stamp that
    rolled back left a frame value that must not speak for the next one."""
    r = _receipts()
    m1 = _input(r, clock, 0.1, A, 0.55)
    _stamp(r, clock, 0.5, 0.62, 101, m1, frame_rev=100)
    assert [s[5] for s in _stamps(_close(r, caplog))] == ["-"]


def test_a_reread_stamp_carries_what_has_committed(clock, caplog):
    r = _receipts()
    _input(r, clock, 0.1, A, 0.55)
    _commit(r, (A, 0.55))
    _input(r, clock, 0.2, B, 0.40)  # not stored yet
    _stamp(r, clock, 0.5, 0.62, 101, None, reread=True)
    m3 = _input(r, clock, 0.6, A, 0.56)
    _commit(r, (B, 0.40))  # m3's flush stores B too
    _stamp(r, clock, 0.9, 0.64, 102, m3)
    assert [s[5] for s in _stamps(_close(r, caplog))] == [_iso(0.1), _iso(0.2)]


def test_a_game_that_stops_being_live_keeps_nothing(clock):
    r = _receipts()
    m1 = _input(r, clock, 0.1, A, 0.55)
    clock.t = 0.5
    r.note_stamp_frame(E, 101, 0.99, "final")
    r.observe({E: m1}, EPOCH + 0.5, {E}, 0.5)
    r.resolve([E], {E: ("stamped", 0.99, "s", None, 101, "final")}, {E: m1}, EPOCH, 0.5)
    assert E not in r._trail and E not in r._live_events


def test_the_refresher_forwards_committed_rows_and_preview_sends(clock):
    r = blend_mod.LiveBlendRefresher("kalshi", min_refresh_interval_s=2.0)
    r.receipts = _receipts()
    m1 = _input(r.receipts, clock, 0.1, A, 0.55)
    r.note_committed_rows([SimpleNamespace(id=A, current_probability=0.55, last_updated=None,
                                           is_winner=None, resolution_source=None)])
    observe = r._preview_observer()
    assert observe is not None
    clock.t = 0.3
    observe({"event_id": E, "p": 0.62, "preview": {"kind": "blend", "seq": 2, "base_rev": 1}},
            {"gen": 1, "seq": 2}, ("published",))
    bucket = r.receipts._window[E]
    assert bucket["previews"] == [f"1:2@{_iso(0.3)}@{_iso(0.1)}"]
    assert m1.seq == 1


# ── R1 (lane1 review of 07cc2dd3): only headline inputs join the trail ───────
# `event_id_by_outcome` maps a live game's prop-board and non-blend outcomes to
# the game too, so without the arm's exclusion sets a prop's receipt became the
# `first_new_recv` of the next headline publication (0.0 s here, not 5.0 s).

PROP = 777  # a prop-board / non-blend outcome linked to the same live game


def _excl(r):
    r.trail_excluded = (set(), {PROP})
    return r


def test_R1_prop_excluded_preview(clock, caplog):
    r = _excl(_receipts())
    _input(r, clock, 0.0, PROP, 0.30)
    _commit(r, (PROP, 0.30))
    _input(r, clock, 5.0, A, 0.55)
    _commit(r, (A, 0.55))
    _preview(r, clock, 5.2, 0.62, seq=7)
    (pv,) = _previews(_close(r, caplog))
    assert pv[2] == _iso(5.0), pv


def test_R1_prop_excluded_stamp(clock, caplog):
    r = _excl(_receipts())
    _input(r, clock, 0.0, PROP, 0.30)
    m = _input(r, clock, 5.0, A, 0.55)
    _stamp(r, clock, 5.3, 0.62, 101, m)
    (st,) = _stamps(_close(r, caplog))
    assert st[5] == _iso(5.0) and st[4] == "2", st  # covered count unchanged


def test_R1_in_place_set_is_read_live(clock, caplog):
    aux = set()
    r = _receipts(); r.trail_excluded = (aux,)
    aux.add(PROP)  # a re-scope fills the arm's set in place
    _input(r, clock, 0.0, PROP, 0.30)
    m = _input(r, clock, 5.0, A, 0.55)
    _stamp(r, clock, 5.3, 0.62, 101, m)
    (st,) = _stamps(_close(r, caplog))
    assert st[5] == _iso(5.0), st


def _arm_wiring(path, consumer):
    """The `tail_receipts.trail_excluded` tuple of an arm's consumer, and every
    binding of a name it holds anywhere in that consumer (nested functions
    included): bound ONCE means the tuple holds the very set objects the
    re-scope refills in place."""
    import ast
    from pathlib import Path

    tree = ast.parse((Path(__file__).resolve().parents[1] / path).read_text())
    (fn,) = [n for n in ast.walk(tree)
             if isinstance(n, ast.AsyncFunctionDef) and n.name == consumer]
    (wired,) = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Attribute) and t.attr == "trail_excluded"
                        and isinstance(t.value, ast.Name) and t.value.id == "tail_receipts"
                        for t in n.targets)]
    assert isinstance(wired.value, ast.Tuple)
    names = [e.id for e in wired.value.elts]
    bindings = {name: [] for name in names}
    for node in ast.walk(fn):
        if isinstance(node, (ast.Nonlocal, ast.Global)):
            assert not set(node.names) & set(names), node.names
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, (ast.AnnAssign, ast.AugAssign,
                                                           ast.For, ast.AsyncFor,
                                                           ast.comprehension, ast.NamedExpr))
                   else [])
        for target in targets:
            for leaf in ast.walk(target):
                if isinstance(leaf, ast.Name) and leaf.id in bindings:
                    bindings[leaf.id].append(leaf.lineno)
    for name, lines in bindings.items():
        assert len(lines) == 1 and lines[0] < wired.lineno, (name, lines, wired.lineno)
    return names


def test_R1_kalshi_arm_wires_its_live_exclusion_sets():
    # `headline_aux_outcome_ids` IS `prices.headline_aux_outcome_ids`; both
    # sets are refilled with clear()/update() on a re-scope, never rebound.
    assert _arm_wiring("app/tasks/kalshi_ws.py", "_run_kalshi_ws_consumer") == [
        "headline_aux_outcome_ids", "non_blend_outcome_ids",
    ]


def test_R1_polymarket_arm_wires_its_live_non_blend_set():
    # `open_outcome_ids` stays OUT: a bridged open leg is its own game-winner
    # market's leg (`open_contract_event_candidates`), which `_read_groups`
    # reads by `FuturesMarket.event_id`; an unbridged one has no event and
    # never reaches the trail. Only venue refusals are left out of that read.
    assert _arm_wiring("app/tasks/polymarket_ws.py", "_run_polymarket_ws_consumer") == [
        "non_blend_outcome_ids",
    ]


# ── field 2: previews= in the minute receipt ─────────────────────────────────


def test_previews_are_bounded_like_stamps(clock, caplog, monkeypatch):
    monkeypatch.setattr(blend_mod, "DELIVERY_RECEIPT_MAX_PREVIEWS", 3)
    r = _receipts()
    for i in range(5):
        _input(r, clock, i, A, 0.50 + i / 100)
        _commit(r, (A, 0.50 + i / 100))
        _preview(r, clock, i + 0.5, 0.60 + i / 100, seq=i + 1)
    (line,) = _close(r, caplog)
    assert line["writer"] == "kalshi"
    assert [p[0] for p in _previews([line])] == ["100:1", "100:2", "100:3"]
    assert line["previews_dropped"] == "2"
    assert line["trail_dropped"] == "0"


def _overlong_scenario(clock, caplog, monkeypatch, budget):
    caplog.clear()
    monkeypatch.setattr(blend_mod, "_live_handoff", {})
    r = _receipts()
    m = None
    for i in range(6):
        m = _input(r, clock, i, A, 0.50 + i / 100)
        _commit(r, (A, 0.50 + i / 100))
        _preview(r, clock, i + 0.2, 0.60 + i / 100, seq=2 * i + 1)
        _preview(r, clock, i + 0.4, 0.60 + i / 100, seq=2 * i + 2)  # same value: `-`
    _stamp(r, clock, 7.0, 0.65, 101, m)
    clock.t = 30.0
    monkeypatch.setattr(blend_mod, "DELIVERY_RECEIPT_MAX_LINE_CHARS", budget)
    r.close_all("test")
    (msg,) = [rec.getMessage() for rec in caplog.records if "delivery-receipt run=" in rec.getMessage()]
    return msg, _lines(caplog)[0]


@pytest.mark.parametrize("cut", ["idle_only", "carrying_too"])
def test_an_overlong_line_drops_previews_carrying_nothing_first(clock, caplog, monkeypatch, cut):
    full, _ = _overlong_scenario(clock, caplog, monkeypatch, 100_000)
    # Six `-` items are ~38 characters each, six carrying ones ~66.
    budget = len(full) - (100 if cut == "idle_only" else 400)
    msg, line = _overlong_scenario(clock, caplog, monkeypatch, budget)
    assert len(msg) <= budget
    kept = _previews([line])
    carrying = [p for p in kept if p[2] != "-"]
    assert 0 < len(kept) < 12
    assert int(line["previews_dropped"]) == 12 - len(kept)
    if cut == "idle_only":
        assert len(carrying) == 6  # only items carrying nothing went
    else:
        assert len(carrying) == len(kept) < 6  # every `-` went before any carrying one
    assert len(_stamps([line])) == 1  # stamps are never trimmed


# ── R2 (lane1 review of 07cc2dd3): `outcomes=` is shed too, stamps never ─────


def _busy_game(r, clock, outcomes=497, stamps=40):
    t = 0.0
    for k in range(outcomes):
        t += 0.05
        _input(r, clock, t, 300_000_000 + k, 0.30)
    for k in range(stamps):
        t += 0.2
        m = _input(r, clock, t, A, 0.50 + k / 1000)
        _stamp(r, clock, t + 0.1, 0.60 + k / 1000, 1_000_000 + k, m)


def test_P2_busy_game_line_stays_under_10000_with_stamps(clock, caplog):
    # Retained capture w-20261030T041733Z: one game-minute had 497 outcomes and
    # a 10,052-byte line cut inside `outcomes=` (JSON unparseable, stamps lost).
    # 07cc2dd3 wrote this minute as a 13,876-character line.
    r = _receipts()
    _busy_game(r, clock)
    r.close_all("test")
    msgs = [rec.getMessage() for rec in caplog.records
            if "delivery-receipt" in rec.getMessage() and f"event={E} " in rec.getMessage()]
    assert msgs
    longest = max(msgs, key=len)
    assert len(longest) < 10_000, len(longest)


def test_a_busy_game_sheds_its_quietest_outcomes_and_keeps_every_stamp(clock, caplog):
    r = _receipts()
    _busy_game(r, clock)
    _input(r, clock, 40.0, 300_000_007, 0.31)  # one prop heard twice: kept
    r.close_all("test")
    (msg,) = [rec.getMessage() for rec in caplog.records if "delivery-receipt run=" in rec.getMessage()]
    (line,) = [ln for ln in _lines(caplog) if ln["event"] == str(E)]
    assert len(msg) <= blend_mod.DELIVERY_RECEIPT_MAX_LINE_CHARS
    assert len(_stamps([line])) == 40 and line["stamps_dropped"] == "0"
    kept = {int(item.split(":")[0]) for item in line["outcomes"].split(",")}
    assert A in kept and 300_000_007 in kept  # the most-heard outcomes stay
    assert int(line["outcomes_dropped"]) == 498 - len(kept) > 0
    # Totals still count every outcome the minute heard.
    assert line["accepted"] == str(497 + 40 + 1)
    # Never more than the one-at-a-time loop: the last outcome shed, put back,
    # would overrun the bound.
    last_shed = max(oid for oid in range(300_000_000, 300_000_497) if oid not in kept
                    and oid != 300_000_007)
    back = msg.replace(" outcomes=", f" outcomes={last_shed}:1:0:0:1,", 1)
    assert len(back) > blend_mod.DELIVERY_RECEIPT_MAX_LINE_CHARS


def test_outcomes_go_after_idle_previews_and_before_carrying_ones(clock, caplog, monkeypatch):
    # Shed every `-` preview (~38 chars each) and the lone outcome, nothing else.
    full, base = _overlong_scenario(clock, caplog, monkeypatch, 100_000)
    budget = len(full) - 6 * 38 - 10
    msg, line = _overlong_scenario(clock, caplog, monkeypatch, budget)
    assert len(msg) <= budget
    assert line["outcomes"] == "-" and line["outcomes_dropped"] == "1"
    assert line["accepted"] == base["accepted"]
    assert len([p for p in _previews([line]) if p[2] != "-"]) == 6


def test_trail_overflow_is_counted(clock, caplog, monkeypatch):
    legs = [A + 10 * i for i in range(4)]  # four legs: none supersedes another
    r = _receipts(seed=legs)
    r._trail.max_pending = 2
    m = None
    for i, leg in enumerate(legs):
        m = _input(r, clock, i, leg, 0.50 + i / 100)
    _commit(r, *((leg, 0.50 + i / 100) for i, leg in enumerate(legs)))
    _stamp(r, clock, 5.0, 0.61, 101, m)
    (line,) = _close(r, caplog)
    assert line["trail_dropped"] == "2"
    assert _stamps([line])[0][5] == _iso(2.0)  # the oldest kept, not the oldest received


# ── field 3: writer= from every writer that advances the revision ───────────


async def test_a_polymarket_withdrawal_is_credited_to_its_writer(clock, caplog):
    from app.tasks import polymarket_ws

    receipts = _receipts("polymarket")
    m0 = _input(receipts, clock, 0.0, A, 0.50)
    _stamp(receipts, clock, 0.5, 0.60, 100, m0)

    async def _publish(frames):
        return {(E, 101)}

    refresher = SimpleNamespace(
        receipts=receipts, _last_written_value={}, _last_refresh_at={}, _last_snapshot_at={},
        preview_events=(), _publish=_publish,
    )
    frame = {"event_id": E, "p": None, "source": None, "source_value": None,
             "updated_at": "2026-10-06T21:20:01.000+00:00", "status": "live",
             "rev": {str(E): 101}, "invalidation": True}
    await polymarket_ws._publish_committed_withdrawals(refresher, [frame])
    (line,) = _lines(caplog, "writer-receipt")
    assert line["writer"] == "polymarket_withdrawal" and line["event"] == str(E)
    assert line["stamps"] == "101@2026-10-06T21:20:01.000+00:00@-@-@0@-"
    # Readers refetched a bag this process did not compute: the next carrying
    # stamp is a change even at the old value.
    m1 = _input(receipts, clock, 2.0, A, 0.51)
    _stamp(receipts, clock, 2.5, 0.60, 102, m1)
    assert [s[5] for s in _stamps(_close(receipts, caplog))] == [_iso(0.0), _iso(2.0)]


def _nonvenue_commit(caplog, prior, sources, *, received_at, status="live"):
    from app.utils import nonvenue_live_push as push

    caplog.clear()
    sync = SimpleNamespace(info={}, in_nested_transaction=lambda: False)
    push._note_receipt(sync, E, "betting", prior, (sources, status, None, None), received_at)
    frame = {"event_id": E, "p": 0.6, "source": "betting", "source_value": 0.6,
             "updated_at": "2026-10-06T21:20:03.000+00:00", "status": status,
             "rev": {str(E): 77}}
    sync.info[push._PENDING] = [(None, frame, None, None, {})]
    push._after_commit(sync)
    return [rec.getMessage() for rec in caplog.records if "writer-receipt" in rec.getMessage()]


def test_a_sportsbook_write_that_moves_the_blend_is_first_from_the_poll(caplog):
    after = {"betting": {"value": 0.60, "updated_at": "2026-10-06T21:20:03+00:00"},
             "kalshi": {"value": 0.58, "updated_at": "2026-10-06T21:20:02+00:00"}}
    prior = {"betting": {"value": 0.52, "updated_at": "2026-10-06T21:19:03+00:00"}}
    (msg,) = _nonvenue_commit(caplog, prior, after, received_at=EPOCH + 1.5)
    assert msg == (f"nonvenue_live_push[betting]: writer-receipt writer=betting event={E} "
                   f"stamps=77@2026-10-06T21:20:03.000+00:00@{_iso(1.5)}@{_iso(1.5)}@1@{_iso(1.5)}")


def test_a_sportsbook_write_that_leaves_the_blend_is_not_a_change(caplog):
    entry = {"value": 0.60, "updated_at": "2026-10-06T21:20:03+00:00"}
    (msg,) = _nonvenue_commit(caplog, {"betting": dict(entry)}, {"betting": dict(entry)},
                              received_at=EPOCH + 1.5)
    assert msg.endswith("@1@-")


def test_a_writer_that_cannot_say_reads_unknown(caplog):
    after = {"betting": {"value": 0.60, "updated_at": "2026-10-06T21:20:03+00:00"}}
    (unmapped,) = _nonvenue_commit(caplog, None, after, received_at=EPOCH + 1.5)
    assert unmapped.endswith("@1@?")
    (untimed,) = _nonvenue_commit(caplog, {}, after, received_at=None)
    assert untimed.endswith("@-@-@1@?")
    assert _nonvenue_commit(caplog, {}, after, received_at=None, status="final") == []


def test_a_rolled_back_write_is_credited_nowhere():
    from app.utils import nonvenue_live_push as push

    sync = SimpleNamespace(info={})
    push._note_receipt(sync, E, "betting", {}, ({}, "live", None, None), EPOCH)
    tx = object()
    sync.info[push._PENDING] = [(tx, {"event_id": E}, None, None, {})]
    push._after_rollback(sync, tx)
    assert sync.info[push._RECEIPTS] == {}
    # A savepoint's write rolls back alone: its source leaves the credit, the
    # outer transaction's source stays.
    outer, savepoint = SimpleNamespace(parent=None), SimpleNamespace(parent=None)
    push._note_receipt(sync, E, "espn", {}, ({}, "live", None, None), None)
    push._note_receipt(sync, E, "mlb", {}, ({}, "live", None, None), None)
    sync.info[push._PENDING] = [(outer, {"event_id": E, "source": "espn"}, None, None, {}),
                                (savepoint, {"event_id": E, "source": "mlb"}, None, None, {})]
    push._after_rollback(sync, savepoint)
    assert set(sync.info[push._RECEIPTS][E]["priors"]) == {"espn"}


async def test_the_odds_poll_hands_its_receipt_instant_to_the_betting_write(monkeypatch):
    from tests.test_discovery_advances_betting_consensus_5426 import (
        FUTURE, _FakeEvent, _FakeSnapshot, _RecordingSession,
    )
    from app.tasks.odds_polling import _ingest_event_odds

    seen = {}

    async def _write(session, event, source, value, **kwargs):
        seen[source] = kwargs.get("received_at")

    queue = [0.57, 0.58, 0.59]

    async def _snapshot(session, event_id, bookmaker, event_data, snapshot_cache=None):
        return _FakeSnapshot(queue.pop(0), None, None), True

    monkeypatch.setattr("app.utils.nonvenue_live_push.write_nonvenue_probability", _write)
    monkeypatch.setattr("app.tasks.odds_polling._create_or_update_snapshot", _snapshot)
    await _ingest_event_odds(
        _RecordingSession(), _FakeEvent({}), {"bookmakers": [{"key": f"b{i}"} for i in range(3)]},
        FUTURE, {}, update_opening=False, received_at=EPOCH + 4.25,
    )
    assert seen == {"betting": EPOCH + 4.25}


# ── the parser ────────────────────────────────────────────────────────────────


def _wrapped(message, ts="2026-10-06T21:21:00.000000+00:00"):
    import json

    return f'{ts} app[worker-ws.1]: ' + json.dumps({"level": "INFO", "message": message}) + "\n"


def _t(seconds):
    return blend_mod._iso(EPOCH + seconds)


def test_the_parser_unions_each_events_seconds_once():
    from app.utils.trailing_readout import trailing

    stamps = ";".join([
        f"101@{_t(2.0)}@{_t(1.9)}@{_t(0.5)}@3@{_t(0.5)}",   # 1.5 s
        f"102@{_t(4.0)}@{_t(3.9)}@{_t(3.0)}@1@-",           # carried nothing new
        f"103@{_t(9.0)}@{_t(8.9)}@{_t(6.5)}@2@{_t(6.5)}",   # 2.5 s
    ])
    previews = ";".join([f"100:4@{_t(1.0)}@{_t(0.2)}", f"101:5@{_t(7.5)}@{_t(7.0)}"])
    lines = [
        _wrapped(f"live_blend_refresh[kalshi]: delivery-receipt run=a event={E} "
                 f"window_start={_t(0)} stamps={stamps} stamps_dropped=0 writer=kalshi "
                 f"previews={previews} previews_dropped=0 trail_dropped=0"),
        _wrapped(f"nonvenue_live_push[betting]: writer-receipt writer=betting event={E} "
                 f"stamps=77@{_t(12.0)}@{_t(11.0)}@{_t(11.0)}@1@{_t(11.0)}"),
    ]
    out = trailing(lines + lines)  # a capture's overlapping sessions replay lines
    event = out["events"][str(E)]
    # [0.2,1.0] [0.5,2.0] -> 1.8 s; [6.5,9.0] with [7.0,7.5] inside -> 2.5; [11,12] -> 1.0
    assert event["total_s"] == pytest.approx(5.3)
    assert event["worst_s"] == pytest.approx(2.5) and event["worst"]["kind"] == "stamp"
    assert event["over_1s"] == 3 and event["intervals"] == 5
    assert out["by_kind"] == {"stamp": 2, "preview": 2, "writer": 1}
    assert out["total_s"] == pytest.approx(5.3) and out["worst"]["event"] == str(E)
    assert "chart" in out and "no chart interval" in out["chart"]


def test_the_parser_counts_what_it_cannot_time():
    from app.utils.trailing_readout import trailing

    legacy = f"105@{_t(5.0)}@{_t(4.0)}@{_t(1.0)}@4"
    behind = f"106@{_t(5.0)}@{_t(4.0)}@{_t(1.0)}@4@{_t(5.2)}"  # DB clock behind the dyno
    lines = [
        _wrapped(f"live_blend_refresh[polymarket]: delivery-receipt run=b event=9 "
                 f"stamps={legacy};{behind} stamps_dropped=0"),
        _wrapped(f"nonvenue_live_push[espn]: writer-receipt writer=espn event=9 "
                 f"stamps=8@{_t(6.0)}@-@-@1@?"),
        _wrapped("live_blend_refresh[polymarket]: delivery-receipt-overflow run=b"),
    ]
    out = trailing(lines)
    assert out["legacy_items"] == 1 and out["unknown_recv"] == 1
    assert out["negative_clamped"] == 1
    assert out["events"]["9"]["total_s"] == 0.0


def test_the_parser_window_keeps_publications_inside_it():
    import datetime as dt

    from app.utils.trailing_readout import trailing

    stamps = f"1@{_t(10.0)}@-@-@1@{_t(4.0)};2@{_t(70.0)}@-@-@1@{_t(65.0)}"
    lines = [f"live_blend_refresh[kalshi]: delivery-receipt run=c event=3 stamps={stamps}"]
    since = dt.datetime.fromtimestamp(EPOCH + 8.0, dt.timezone.utc)
    until = dt.datetime.fromtimestamp(EPOCH + 60.0, dt.timezone.utc)
    out = trailing(lines, since=since, until=until)
    assert out["items"] == 1
    assert out["events"]["3"]["total_s"] == pytest.approx(2.0)  # clipped at since
    assert out["events"]["3"]["worst_s"] == pytest.approx(6.0)  # the worst is not


def test_the_parser_reads_a_retained_production_capture():
    """Two lines verbatim from worker-ws 2026-10-30 04:17Z (capture
    w-20261030T041733Z): before the fields, every item is legacy."""
    from app.utils.trailing_readout import trailing

    captured = [
        '2026-10-30T04:17:00.000680+00:00 app[worker-ws.1]: {"timestamp": "2026-10-30 04:17:00,000", '
        '"level": "INFO", "name": "app.tasks.live_blend_refresh", "message": "live_blend_refresh[polymarket]: '
        'delivery-receipt run=d92e6bbd event=15331072 window_start=2026-10-30T04:16:00.000+00:00 window_s=60.000 '
        'raw=100 accepted=100 changed=0 repeats=100 first=0 outcomes=255383312:3:0:3:0 '
        'stamps=605@2026-10-30T04:16:31.470224+00:00@2026-10-30T04:16:31.002+00:00@2026-10-30T04:15:27.234+00:00@113 '
        'stamps_dropped=0 sw=owed_past_withdrawal:off sw=preview_from_commit:on"}\n',
        '2026-10-30T04:17:00.010291+00:00 app[worker-ws.1]: {"timestamp": "2026-10-30 04:17:00,010", '
        '"level": "INFO", "name": "app.utils.preview_receipt", "message": "blend_preview[polymarket]: '
        'preview-receipt run=a8e0eab0 window_start=2026-10-30T04:16:00.000+00:00 published=664"}\n',
    ]
    out = trailing(captured)
    assert out["items"] == 1 and out["legacy_items"] == 1 and out["carrying_items"] == 0
    assert out["truncated_lines"] == 0


def test_the_parser_counts_a_cut_delivery_line_as_truncated():
    """The 10,052-byte line verbatim from the same capture: logplex cut it
    inside `outcomes=`, so its JSON does not parse and its stamps are gone.
    It is counted as truncated, never read as a minute with nothing in it."""
    import datetime as dt
    from pathlib import Path

    from app.utils.trailing_readout import receipt_items, trailing

    cut = (Path(__file__).parent / "fixtures" / "delivery_receipt_cut_line_10090.txt").read_text()
    assert len(cut.encode()) == 10_052 and "stamps_dropped=" not in cut
    out = trailing([cut])
    assert out["truncated_lines"] == 1 and out["items"] == 0 and out["total_s"] == 0
    (item,) = receipt_items([cut])
    assert item["kind"] == "truncated" and item["event"] == "15338186"
    # Windowed like an item, by the line's own window_start (04:20Z).
    at = dt.datetime(2026, 10, 30, 4, 20, tzinfo=dt.timezone.utc)
    assert trailing([cut], since=at + dt.timedelta(minutes=1))["truncated_lines"] == 0
    assert trailing([cut], since=at, until=at + dt.timedelta(minutes=1))["truncated_lines"] == 1
    # A cut too early to carry its window_start is still counted.
    early = cut[:cut.index(" window_start=")]
    assert trailing([early], since=at)["truncated_lines"] == 1


def test_receipts_written_by_the_consumer_fold_end_to_end(clock, caplog):
    from app.utils.trailing_readout import trailing

    r = _receipts()
    m0 = _input(r, clock, 0.0, A, 0.50)
    _commit(r, (A, 0.50))
    _preview(r, clock, 0.3, 0.61, seq=1)                 # [0.0, 0.3]
    _stamp(r, clock, 0.8, 0.61, 101, m0)                 # `-`
    m1 = _input(r, clock, 2.0, A, 0.53)
    _commit(r, (A, 0.53))
    r.note_stamp_frame(E, 102, 0.62, "live")
    clock.t = 3.2
    r.observe({E: m1}, EPOCH + 3.2, {E}, 3.2)
    r.resolve([E], {E: ("stamped", 0.53, _iso(3.2), None, 102, "live")}, {E: m1}, EPOCH, 3.2)
    r.close_all("test")
    out = trailing(rec.getMessage() for rec in caplog.records)
    event = out["events"][str(E)]
    assert event["intervals"] == 2
    assert event["total_s"] == pytest.approx(0.3 + 1.2, abs=1e-3)
    assert event["worst_s"] == pytest.approx(1.2, abs=1e-3) and event["over_1s"] == 1


# ── F1 + F2 (latency 1614Z validation): credit only an input whose own price ─
# committed and changed what readers see. All ten top intervals of 15:03–15:13Z
# were artifacts: one first observation (Kalshi, 110 s), nine non-moving
# Polymarket inputs credited at the next real move. Red on 62557fad's module.


def _retired(line):
    counts = dict(part.split(":") for part in line["trail_retired"].split(","))
    return {k: int(v) for k, v in counts.items()}, int(line["trail_first_skipped"])


def test_F1_the_kalshi_110s_first_observation_shape_credits_nothing(clock, caplog):
    # 15338663, 15:07:40.138 -> 15:09:30.091: the event entered Kalshi's live set,
    # both legs' first inputs sat at the stored 0.99 (no RETURNING row), and the
    # stamp 110 s later was "moved" only against nothing shown yet.
    r = _receipts(seed=())
    m = _input(r, clock, 0.138, A, 0.99)
    _input(r, clock, 0.140, B, 0.01)
    _stamp(r, clock, 110.091, 0.99475, 101, m, commit=False)
    lines = _close(r, caplog)
    assert [s[5] for s in _stamps(lines)] == ["-"]
    assert sum(_retired(line)[1] for line in lines) == 2


def test_F1_a_first_input_whose_price_is_stored_still_never_joins(clock, caplog):
    r = _receipts(seed=())
    m = _input(r, clock, 0.1, A, 0.60)
    _stamp(r, clock, 0.5, 0.61, 101, m)  # its own RETURNING row, even so
    m2 = _input(r, clock, 1.0, A, 0.62)  # the second input has a prior
    _stamp(r, clock, 1.4, 0.63, 102, m2)
    assert [s[5] for s in _stamps(_close(r, caplog))] == ["-", _iso(1.0)]


def test_F2_a_trade_then_midpoint_flicker_whose_row_never_moved_is_never_credited(clock, caplog):
    # A print at the bid, the midpoint back: the flush's write found the row
    # at 0.50 (no RETURNING row), so nothing readers see changed.
    r = _receipts()
    m0 = _input(r, clock, 0.0, A, 0.50)
    _stamp(r, clock, 0.3, 0.60, 100, m0)
    _input(r, clock, 1.0, A, 0.48)
    m2 = _input(r, clock, 1.1, A, 0.50)
    clock.t = 1.5
    r.observe({E: m2}, EPOCH + 1.5, {E}, 1.5)   # the flush committed, staged
    r.resolve([E], {E: ("unchanged", 0.50)}, {E: m2}, EPOCH + 1.5, 1.5)
    m3 = _input(r, clock, 30.0, A, 0.55)        # the next real move
    _stamp(r, clock, 30.4, 0.63, 101, m3)
    lines = _close(r, caplog)
    assert [s[5] for s in _stamps(lines)] == [_iso(0.0), _iso(30.0)]
    assert sum(_retired(line)[0]["flushed"] for line in lines) == 2


def test_F2_a_committed_leg_that_left_the_headline_unchanged_is_settled(clock, caplog):
    # Item #3 (15338587): the write landed, the reading found 0.03 unchanged
    # (`unobserved`), and the next real move credited the leg from its own
    # receipt 45.8 s earlier.
    r = _receipts()
    m0 = _input(r, clock, 0.0, A, 0.50)
    _stamp(r, clock, 0.3, 0.60, 100, m0)
    m1 = _input(r, clock, 1.0, A, 0.501)
    _commit(r, (A, 0.501))
    clock.t = 1.4
    r.observe({E: m1}, EPOCH + 1.4, {E}, 1.4)
    r.settle(E, [SimpleNamespace(id=A, current_probability=0.501)])  # the reading's rows
    r.resolve([E], {E: ("unobserved", 0.03)}, {E: m1}, EPOCH + 1.4, 1.4)
    m2 = _input(r, clock, 40.0, B, 0.47)
    _stamp(r, clock, 40.3, 0.64, 101, m2)
    lines = _close(r, caplog)
    assert [s[5] for s in _stamps(lines)] == [_iso(0.0), _iso(40.0)]
    assert sum(_retired(line)[0]["settled"] for line in lines) == 1


def test_F2_settle_keeps_an_input_committed_after_the_reading_took_its_rows(clock, caplog):
    r = _receipts()
    m0 = _input(r, clock, 0.0, A, 0.50)
    _stamp(r, clock, 0.3, 0.60, 100, m0)
    m1 = _input(r, clock, 1.0, A, 0.52)
    _commit(r, (A, 0.52))  # landed while the reading was in flight
    r.settle(E, [SimpleNamespace(id=A, current_probability=0.50)])  # it read 0.50
    _stamp(r, clock, 2.0, 0.62, 101, m1)
    assert [s[5] for s in _stamps(_close(r, caplog))] == [_iso(0.0), _iso(1.0)]


def test_F2_a_held_write_that_finally_commits_is_credited_from_its_own_receipt(clock, caplog):
    r = _receipts()
    m0 = _input(r, clock, 0.0, A, 0.50)
    _stamp(r, clock, 0.3, 0.60, 100, m0)
    m1 = _input(r, clock, 1.0, A, 0.55)  # its price write is held (lock): no flush commits it
    clock.t = 3.0
    r.observe({}, EPOCH + 3.0, set(), 3.0)
    _stamp(r, clock, 6.0, 0.64, 101, m1)  # it commits at last, and the stamp carries it
    assert [s[5] for s in _stamps(_close(r, caplog))] == [_iso(0.0), _iso(1.0)]


def test_F2_a_committed_price_whose_stamp_the_throttle_held_is_credited(clock, caplog):
    r = _receipts()
    m0 = _input(r, clock, 0.0, A, 0.50)
    _stamp(r, clock, 0.3, 0.60, 100, m0)
    m1 = _input(r, clock, 1.0, A, 0.55)
    _commit(r, (A, 0.55))
    clock.t = 1.2
    r.observe({E: m1}, EPOCH + 1.2, set(), 1.2)  # committed, not due: held
    _stamp(r, clock, 3.0, 0.64, 101, m1, commit=False)
    assert [s[5] for s in _stamps(_close(r, caplog))] == [_iso(0.0), _iso(1.0)]


def test_F2_a_newer_committed_price_supersedes_the_older_unshown_one(clock, caplog):
    r = _receipts()
    m0 = _input(r, clock, 0.0, A, 0.50)
    _stamp(r, clock, 0.3, 0.60, 100, m0)
    _input(r, clock, 1.0, A, 0.52)
    m2 = _input(r, clock, 2.0, A, 0.54)
    _stamp(r, clock, 2.5, 0.63, 101, m2)  # its RETURNING row stored 0.54
    lines = _close(r, caplog)
    assert [s[5] for s in _stamps(lines)] == [_iso(0.0), _iso(2.0)]
    assert sum(_retired(line)[0]["superseded"] for line in lines) == 1


# ── R1-R3 (lane1 1813Z review of 5694f7cc): a committed input stays through a ─
# newer commit, settle sweeps what it read, and never under a shown preview.
# P1, P2 and P5 are red on 5694f7cc.


def test_R1_P1_two_commits_inside_one_throttle_hold_credit_the_first(clock, caplog):
    # The throttle-held stamp above, but the outcome commits AGAIN before the
    # held stamp goes out: readers lacked the first commit all along.
    r = _receipts()
    m0 = _input(r, clock, 0.0, A, 0.50)
    _stamp(r, clock, 0.3, 0.60, 100, m0)
    m1 = _input(r, clock, 1.0, A, 0.55)
    _commit(r, (A, 0.55))
    clock.t = 1.2
    r.observe({E: m1}, EPOCH + 1.2, set(), 1.2)   # committed, not due: held
    m2 = _input(r, clock, 2.0, A, 0.56)
    _commit(r, (A, 0.56))
    clock.t = 2.2
    r.observe({E: m2}, EPOCH + 2.2, set(), 2.2)   # still held
    _stamp(r, clock, 6.0, 0.64, 101, m2, commit=False)
    lines = _close(r, caplog)
    assert [s[5] for s in _stamps(lines)] == [_iso(0.0), _iso(1.0)]
    assert sum(_retired(line)[0]["superseded"] for line in lines) == 0


def test_R1_P2_a_refused_preview_then_a_newer_commit_credit_the_first(clock, caplog):
    # Latency's item-#3 lead: the moved reading was refused (`stale`), so
    # nothing was published and nothing settled; the leg commits again 11 s
    # later and the next preview carries both. An 11 s hold, not 1 s.
    r = _receipts()
    m0 = _input(r, clock, 0.0, A, 0.50)
    _stamp(r, clock, 0.3, 0.60, 100, m0)
    _input(r, clock, 1.0, A, 0.55)
    _commit(r, (A, 0.55))
    _input(r, clock, 12.0, A, 0.56)
    _commit(r, (A, 0.56))
    _preview(r, clock, 13.0, 0.64, seq=1, base_rev=100)
    assert [p[2] for p in _previews(_close(r, caplog))] == [_iso(1.0)]


def test_R1_P3_a_flicker_committed_twice_then_read_unchanged_is_never_credited(clock, caplog):
    # A bid print commits, the midpoint commits back, the reading is unchanged:
    # settle sweeps the older committed print with the newer one it read.
    r = _receipts()
    m0 = _input(r, clock, 0.0, A, 0.50)
    _stamp(r, clock, 0.3, 0.60, 100, m0)
    _input(r, clock, 1.0, A, 0.48)
    _commit(r, (A, 0.48))
    m2 = _input(r, clock, 1.1, A, 0.50)
    _commit(r, (A, 0.50))
    clock.t = 1.5
    r.observe({E: m2}, EPOCH + 1.5, {E}, 1.5)
    r.settle(E, [SimpleNamespace(id=A, current_probability=0.50)])
    r.resolve([E], {E: ("unchanged", 0.60)}, {E: m2}, EPOCH + 1.5, 1.5)
    m3 = _input(r, clock, 30.0, A, 0.55)
    _stamp(r, clock, 30.4, 0.63, 101, m3)
    lines = _close(r, caplog)
    assert [s[5] for s in _stamps(lines)] == [_iso(0.0), _iso(30.0)]
    assert sum(_retired(line)[0]["settled"] for line in lines) == 2


def test_R3_P4_a_held_uncommitted_input_superseded_is_the_labelled_understatement(clock, caplog):
    # Reporting chat's case: readers show A; B arrives at 0 and its write is
    # held (no flush of the event commits it); C supersedes it at 10 and
    # commits; C first reaches readers at 11. Whether B would have moved the
    # blend is unknown (it never committed), so the trail credits from C:
    # 1 s, understating by up to 10 s (module LIMITS; counted `superseded`).
    r = _receipts()
    m0 = _input(r, clock, -1.0, A, 0.50)
    _stamp(r, clock, -0.7, 0.60, 100, m0)
    _input(r, clock, 0.0, A, 0.55)
    clock.t = 3.0
    r.observe({}, EPOCH + 3.0, set(), 3.0)
    _input(r, clock, 10.0, A, 0.57)
    _commit(r, (A, 0.57))
    _preview(r, clock, 11.0, 0.65, seq=1, base_rev=100)
    lines = _close(r, caplog)
    assert [p[2] for p in _previews(lines)] == [_iso(10.0)]
    assert sum(_retired(line)[0]["superseded"] for line in lines) == 1


def test_R2_P5_settle_never_retires_what_readers_lack_behind_a_shown_preview(clock, caplog):
    # Readers hold a PREVIEW of B (never stamped). C returns the leg to the
    # stored price; the reading equals the stored entry, but readers still
    # show B's preview, so C is news to them until a publication carries it.
    r = _receipts()
    m0 = _input(r, clock, 0.0, A, 0.50)
    _stamp(r, clock, 0.3, 0.60, 100, m0)
    _input(r, clock, 1.0, A, 0.55)
    _commit(r, (A, 0.55))
    _preview(r, clock, 1.3, 0.64, seq=1, base_rev=100)     # readers see B
    _input(r, clock, 2.0, A, 0.50)
    _commit(r, (A, 0.50))
    r.settle(E, [SimpleNamespace(id=A, current_probability=0.50)])  # unchanged vs stored
    _preview(r, clock, 9.0, 0.60, seq=2, base_rev=100)     # readers get C at last
    lines = _close(r, caplog)
    assert [p[2] for p in _previews(lines)] == [_iso(1.0), _iso(2.0)]
    assert sum(_retired(line)[0]["settled"] for line in lines) == 0


def test_F2_the_receipt_line_prints_every_retirement_reason(clock, caplog):
    r = _receipts()
    m0 = _input(r, clock, 0.0, A, 0.50)
    _stamp(r, clock, 0.3, 0.60, 100, m0)
    (line,) = _close(r, caplog)
    assert line["trail_retired"] == "superseded:0,flushed:0,settled:0"
    assert line["trail_first_skipped"] == "0"


def test_F2_the_refresher_settles_with_the_rows_its_reading_blended(clock):
    r = blend_mod.LiveBlendRefresher("kalshi", min_refresh_interval_s=2.0)
    r.receipts = _receipts()
    m0 = _input(r.receipts, clock, 0.0, A, 0.50)
    _stamp(r.receipts, clock, 0.3, 0.60, 100, m0)
    _input(r.receipts, clock, 1.0, A, 0.51)
    _commit(r.receipts, (A, 0.51))
    group = [SimpleNamespace(outcomes=[SimpleNamespace(id=A, current_probability=0.51),
                                       SimpleNamespace(id=B, current_probability=0.40)])]
    # Agreeing with process memory is not enough: the poll wrote 0.6105 since.
    polled = SimpleNamespace(win_probability_sources={"kalshi": {"value": 0.6105}})
    r._settle_trail(E, group, stored_row=polled, value=0.61)
    assert r.receipts._trail.retired(E)[0]["settled"] == 0
    stored = SimpleNamespace(win_probability_sources={"kalshi": {"value": 0.61}})
    r._settle_trail(E, group, stored_row=stored, value=0.61)
    assert r.receipts._trail.retired(E)[0]["settled"] == 1
    # A receipt failure never reaches the price path.
    r._settle_trail(E, [object()], stored_row=stored, value=0.61)


def test_F2_both_agreeing_dispositions_settle_the_trail():
    """`unobserved` and `unchanged` (which `preview_only` refines) are the
    readings whose value is the one last written or stored: each settles."""
    import ast
    import inspect
    import textwrap

    src = textwrap.dedent(inspect.getsource(blend_mod.LiveBlendRefresher._refresh_batch))
    settled = []
    for node in ast.walk(ast.parse(src)):
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        for i, stmt in enumerate(body):
            if (isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Tuple)
                    and stmt.value.elts and isinstance(stmt.value.elts[0], ast.Constant)
                    and stmt.value.elts[0].value in ("unobserved", "unchanged")
                    and any(isinstance(t, ast.Subscript)
                            and getattr(t.value, "attr", None) == "_dispositions"
                            for t in stmt.targets)):
                calls = [n.func.attr for s in body[i + 1:] for n in ast.walk(s)
                         if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
                assert "_settle_trail" in calls, stmt.value.elts[0].value
                settled.append(stmt.value.elts[0].value)
    assert sorted(settled) == ["unchanged", "unobserved"]


def test_the_parser_reads_retired_fields_and_lines_without_them():
    from app.utils.trailing_readout import trailing

    before = (f"live_blend_refresh[polymarket]: delivery-receipt run=a event=7 "
              f"window_start={_t(0)} stamps=1@{_t(5.0)}@-@-@1@{_t(2.0)} stamps_dropped=0 "
              f"writer=polymarket previews=- previews_dropped=0 trail_dropped=0 outcomes_dropped=0")
    after = (f"live_blend_refresh[polymarket]: delivery-receipt run=b event=7 "
             f"window_start={_t(60)} stamps=2@{_t(65.0)}@-@-@1@{_t(64.0)} stamps_dropped=0 "
             f"writer=polymarket previews=- previews_dropped=0 trail_dropped=0 "
             f"trail_retired=superseded:3,flushed:5,settled:2 trail_first_skipped=4 "
             f"outcomes_dropped=0 sw=preview_from_commit:on")
    out = trailing([_wrapped(before), _wrapped(after)])
    assert out["unretired_lines"] == 1 and out["retired_lines"] == 1
    assert out["trail_retired"] == {"superseded": 3, "flushed": 5, "settled": 2}
    # A first input is not a retire reason: its eligibility is unknown (N3).
    assert out["first_skipped_eligibility_unknown"] == 4
    assert out["items"] == 2 and out["events"]["7"]["total_s"] == pytest.approx(4.0)
    assert trailing([after])["unretired_lines"] == 0


def test_the_parser_never_reads_a_cut_or_malformed_retired_line_as_predating():
    from app.utils.trailing_readout import trailing

    head = (f"live_blend_refresh[polymarket]: delivery-receipt run=c event=7 "
            f"window_start={_t(0)} stamps=- stamps_dropped=0 "
            f"writer=polymarket previews=- previews_dropped=0 trail_dropped=0 ")
    lost = head + "trail_retired=superseded:3"            # cut before the final field
    gone = head                                            # cut before trail_retired
    bad = head + "trail_retired=superseded:x trail_first_skipped=1 outcomes_dropped=0"
    out = trailing([_wrapped(lost), _wrapped(gone.replace("run=c", "run=d")),
                    _wrapped(bad)])
    assert out["retired_cut_lines"] == 2 and out["retired_malformed_lines"] == 1
    assert out["unretired_lines"] == 0 and out["retired_lines"] == 0
    assert out["trail_retired"] == {} and out["first_skipped_eligibility_unknown"] == 0
