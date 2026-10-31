"""PROBE (live review of #11830): a skipped repeat feeds `ConfirmedAt` exactly
what today's path (`PM_WS_REPEAT_SKIP_MS=0`) feeds it for the same repeat —
through a TailReceipts-shaped `note_input` (None when the leg has no event)
and a real-shaped `note_mark`, for a slate pair, a non-blend (prop) pair and a
bridged open pair whose second leg has no event of its own."""

from types import SimpleNamespace

import pytest

from tests.test_pm_repeat_skip_10090 import callbacks, quote


class Confirmed:
    def __init__(self):
        self.notes = []

    def note_input(self, event_id, outcome_id, probability, recv_wall):
        self.notes.append((event_id, outcome_id, probability, recv_wall))

    def note_mark(self, mark):
        self.note_input(mark.event_id, mark.outcome_id, mark.probability, mark.recv_wall)

    def note_withdrawal(self, *_args):
        pass


def _shape(r, case):
    confirmed = Confirmed()

    def note_input(event_id, outcome_id, probability, kind, venue_ts=None):
        if event_id is None:
            return None
        from app.tasks import live_blend_refresh as blend
        return SimpleNamespace(event_id=event_id, outcome_id=outcome_id,
                               probability=probability, recv_wall=blend._wall(),
                               args=(event_id, outcome_id, probability))

    r.ns["tail_receipts"].note_input = note_input
    r.ns["tail_receipts"].confirmed = confirmed
    if case == "non_blend":
        r.ns["non_blend_outcome_ids"].update({1, 2})
    elif case == "bridged":
        r.ns["open_outcome_ids"].update({1, 2})
        r.ns["event_id_by_outcome"].pop(2, None)
    return confirmed


async def _repeat_notes(monkeypatch, case, window_s):
    r = callbacks(monkeypatch, window_s=window_s)
    confirmed = _shape(r, case)
    await r.ns["handle_price"](quote())
    r.ns["price_buffer"].clear()
    confirmed.notes.clear()
    r.clock.t += 0.1
    await r.ns["handle_price"](quote())
    return r, confirmed.notes


@pytest.mark.parametrize("case", ["slate", "non_blend", "bridged"])
async def test_a_skipped_repeat_feeds_confirmed_at_what_todays_path_feeds(monkeypatch, case):
    today_r, today = await _repeat_notes(monkeypatch, case, 0.0)
    skip_r, skipped = await _repeat_notes(monkeypatch, case, 0.25)
    assert today_r.ns["stats"].get("repeats_skipped", 0) == 0
    assert skip_r.ns["stats"]["repeats_skipped"] == 1
    assert skipped == today
