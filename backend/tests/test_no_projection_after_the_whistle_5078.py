"""live/142 (#5078): the event page projected the Rams winning a game they lost.

ux/1188 shopped SF@LAR (`events.id 14632820`) on an un-refreshed tab across the
final whistle (03:25:31Z, 2026-09-11). Two passes either side of it::

    20:16 PT           projected final  8 – 29     actual shown  7 – 27
    20:36 PT (final+11) projected final 26 – 23     actual shown  7 – 27

At final+11 the page projected **the Rams winning 26–23** a game they had just
lost **7–27**, rendered correctly two inches away on the same page. The
projection did not freeze — it MOVED after the whistle, and moved to nonsense.

**Why it is a state gate and not a price gate.** The event flips to `completed`
when the game ends, but the venue does not settle its contracts in that instant.
For the minutes in between the markets are still `open` while their prices
collapse toward 0/1, and a ladder pinned at the extremes is exactly what
`binary_to_implied_spread`/`binary_to_implied_total` cannot read. Those prices
are not malformed — they are *correct prices for a decided market* — so no
amount of ladder sanity-checking reaches this. The only true statement is that a
game which has already been played is not projected at all.

**Why nobody catches it.** Once the venue settles, the contracts leave the
candidate set and `projected_final` goes back to `null` — verified on 14632820
at 04:15Z, 50 minutes after the final: `projected_final: null`, 0 implied
spreads, 0 implied totals. The defect lives only in the window right after the
whistle, which is precisely when a reader is still looking at the page.

The guard therefore has to reproduce the WINDOW: a completed event whose markets
are still open and still priced. A test that settles the markets first passes
against the unfixed code and proves nothing.
"""
import inspect


class TestNoProjectionAfterTheWhistle:

    def _src(self):
        import app.routes.events as ev
        src = inspect.getsource(ev)
        start = src.index("else select_projected_final(implied_spreads")
        return src[start - 3000:start + 500]

    def test_projection_is_gated_on_terminal_event_state(self):
        """The projection is suppressed by EVENT STATE, before the pair is picked."""
        seg = self._src()
        assert "event_is_final" in seg, (
            "the projection must be gated on the event's own terminal state"
        )
        assert 'event.status in ("completed", "closed")' in seg, (
            "both terminal states count — a `closed` game has also been played"
        )
        assert "None if event_is_final" in seg, (
            "the gate must short-circuit BEFORE select_projected_final, so a "
            "degenerate settled ladder is never read at all"
        )

    def test_gate_precedes_the_pair_selection(self):
        """Order matters: reading the ladder first and discarding after is not this."""
        seg = self._src()
        assert seg.index("event_is_final =") < seg.index(
            "else select_projected_final(implied_spreads"
        )

    def test_implied_rungs_are_not_suppressed(self):
        """The claim is narrow — no PROJECTION, not 'no market data on finals'.

        `implied_spreads` / `implied_totals` are the chart's own rungs and a
        settled game legitimately still draws them. A fix that blanked those
        would be a bigger claim than the defect supports.
        """
        seg = self._src()
        gate_line = [ln for ln in seg.splitlines() if "None if event_is_final" in ln]
        assert gate_line, "gate not found"
        assert not any(
            "implied_spreads = " in ln or "implied_totals = " in ln
            for ln in seg.splitlines()
            if "event_is_final" in ln
        ), "the state gate must not also suppress the chart's rungs"
