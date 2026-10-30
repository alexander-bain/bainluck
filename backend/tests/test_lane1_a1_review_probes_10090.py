"""lane1's review probes for A1 (4ed27c60): what the receipts say for a live
game's prop board once its commit queues no stamp. Real TailReceipts; the
flush is the shipped `flush_prices` on the Rank 3 rig."""

import pytest

import app.tasks.live_blend_refresh as lbr
import tests.test_flush_loop_live_aux_phase_10090 as bfile

AUX_A20 = bfile.AUX_A[:20]



def _rig(monkeypatch, receipts):
    built = bfile.rig(aux=bfile.AUX_A)
    monkeypatch.setattr(lbr, "_mono", lambda: built.clock["now"])
    staged = []

    class Capture:
        def stage(self, marks):
            marks = list(marks)
            staged.append(marks)
            receipts.stage(marks)

        def unowed(self, marks):
            receipts.unowed(marks)

    built.ns["tail_receipts"] = Capture()
    built.staged = staged
    return built


def _receipts():
    tr = lbr.TailReceipts("kalshi", coalesce_s=0.0)
    tr._live_events.add(bfile.LIVE_A)
    return tr


def _input(tr, built, oid, p=0.5):
    mark = tr.note_input(bfile.maps()[1][oid], oid, p, "ticker")
    built.ns["input_marks"][oid] = mark
    built.buffer[oid] = (p, p - 0.01, p + 0.01)
    return mark


def _refresher_side(tr, asked, now):
    """What `LiveBlendRefresher.refresh` does with the staged marks: observe
    (a staged event that is not due opens a throttle chain), then resolve the
    due events as stamped."""
    staged, wall = tr.take_staged()
    due = set(asked)
    tr.observe(staged, wall, due, now)
    tr.resolve(due, {e: ("stamped", 0.5, "t", 0.4, 1, "live") for e in due},
               staged, wall, now)


@pytest.mark.asyncio
async def test_r1_a_board_only_first_phase_opens_a_throttle_chain_with_nothing_owed(monkeypatch):
    tr = _receipts()
    built = _rig(monkeypatch, tr)
    for oid in AUX_A20:
        _input(tr, built, oid)
    assert await built.flush(0.0) is True
    asked = set().union(*(a for a, _d, _c in built.stamps)) if built.stamps else set()
    print("stamps:", built.stamps, "staged events:",
          [sorted({m.event_id for m in s}) for s in built.staged])
    for _ in built.stamps:
        _refresher_side(tr, asked, 1.0)
    # Nothing is owed for LIVE_A (A1's premise) — so no receipt chain may open.
    assert bfile.LIVE_A not in tr._open, (
        f"false hold: origin={tr._open[bfile.LIVE_A].origin}" if bfile.LIVE_A in tr._open else "")


@pytest.mark.asyncio
async def test_r1b_board_inputs_after_the_headline_wait_for_the_next_headline_stamp(monkeypatch):
    tr = _receipts()
    built = _rig(monkeypatch, tr)
    for oid in bfile.HEAD_A:
        _input(tr, built, oid)
    for oid in AUX_A20:
        _input(tr, built, oid)
    assert await built.flush(0.0) is True
    for asked, _d, _c in built.stamps:
        _refresher_side(tr, asked, 1.0)
    left = len(tr._uncovered.get(bfile.LIVE_A, ()))
    print("stamps:", built.stamps, "uncovered after flush:", left)
    assert left == 0, f"{left} board inputs still wait for a stamp that will not come"


def test_r2_the_refreshers_kalshi_read_has_exactly_the_four_terms_the_aux_rule_inverts():
    # A1 stops stamping on every outcome `kalshi_headline_aux_ticker` calls
    # aux, so a term ADDED to the read (and not to `feeds_win_prob_blend`)
    # would leave a read row unstamped. Pin the whole OR, not its members.
    import inspect
    import re

    body = inspect.getsource(lbr.LiveBlendRefresher._read_groups)
    block = body[body.index("outcome_join = and_("):body.index('elif self.source == "polymarket"')]
    terms = re.sub(r"\s+", "", block[block.index("or_(") + 4:block.rindex("),\n            )")])
    assert terms == (
        'FuturesMarket.external_id.is_(None),FuturesMarket.external_id=="",'
        'prefix.endswith("game"),prefix.in_(sorted(COMBAT_FIGHT_WINNER_PREFIXES'
        '|TENNIS_MATCH_WINNER_PREFIXES)),'
    ), "a new Kalshi read term must also change feeds_win_prob_blend (A1)"


@pytest.mark.asyncio
async def test_r1b_repeated_ticks_on_one_board_outcome_all_leave_the_queue(monkeypatch):
    tr = _receipts()
    built = _rig(monkeypatch, tr)
    for oid in bfile.HEAD_A:
        _input(tr, built, oid)
    for p in (0.40, 0.45, 0.50):  # three ticks of one prop before the flush
        _input(tr, built, AUX_A20[0], p)
    assert await built.flush(0.0) is True
    for asked, _d, _c in built.stamps:
        _refresher_side(tr, asked, 1.0)
    left = len(tr._uncovered.get(bfile.LIVE_A, ()))
    assert left == 0, f"{left} superseded board ticks still wait for a stamp"
