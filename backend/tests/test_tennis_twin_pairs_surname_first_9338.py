"""#9338 — a surname-first player's ghost row is found, and two full names are never fused.

THE DEFECT (production, read 2026-09-28 13:5xZ). Searching "Alcaraz" printed the
finished US Open match Wu Yibing v Carlos Alcaraz (``15301243``, final 0-3) and,
beside it, ``15301231`` "Wu / Alcaraz" — ``ATP · No result reported · Sep 3`` —
the id-less row a Polymarket line minted, still holding 10 of the match's
Polymarket markets three weeks later.

The twin sweep already judged the pair correctly: ``classify_pair`` returns
``TWIN_FOUND``. It never ran it. ``block_key`` reads the surname as the LAST
token, so ESPN's surname-first ``Wu Yibing`` blocked under ``yibing`` and the
ghost's ``Wu`` under ``wu``. Replayed on the sweep's own production population
(``commence_time`` in [now-45d, now-10d), 2,872 rows) the widened blocks add
exactly four tags — Wu/Alcaraz, Duckworth/Wu, Bu/Zheng, Bondar/Liang — lose none
and move none; on the live window (2,634 rows) they change nothing (43 -> 43).

THE HAZARD the first widening exposed, pinned here as a control:
``players_agree`` accepts ``Arthur Fery`` ~ ``Arthur Fils`` on the surname-first
reading ``('arthur', 'f')``. The last-token block had been hiding that. Widened,
it fused Fery–de Minaur (Cincinnati, 15204746 -> 15199617) with Fils–de Minaur
(15201186), and the rival guard's refusal cost the correct tag. A pair that
meets ONLY in a widened block must therefore be the ghost's own shape: one side
names the player by surname alone.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.tennis_twin_pairs import (  # noqa: E402
    TWIN_FOUND,
    TwinRow,
    block_key,
    block_keys,
    classify_pair,
    plan_twin_tags,
    surname_alone_pair_agrees,
)

T0 = datetime(2026, 9, 4, 0, 0, tzinfo=timezone.utc)


def ghost(event_id, home, away):
    return TwinRow(
        event_id=event_id,
        home_team_name=home,
        away_team_name=away,
        sport_key="tennis_atp",
        is_tournament_keyed=False,
        has_settled_result=False,
        is_id_anchored=False,
    )


def canonical(event_id, home, away, sport_key="tennis_atp_us_open"):
    return TwinRow(
        event_id=event_id,
        home_team_name=home,
        away_team_name=away,
        sport_key=sport_key,
        is_tournament_keyed=True,
        has_settled_result=True,
        is_id_anchored=True,
    )


def plan(rows, offsets_h):
    return plan_twin_tags(
        rows,
        commence_times={
            r.event_id: T0 + timedelta(hours=h) for r, h in zip(rows, offsets_h)
        },
    )


# The four production pairs the widened blocks reach (ghost, canonical, hours apart).
MEASURED = [
    (
        ghost(15301231, "Wu", "Alcaraz"),
        canonical(15301243, "Wu Yibing", "Carlos Alcaraz"),
        18,
    ),
    (
        ghost(15299594, "Duckworth", "Wu"),
        canonical(15299607, "James Duckworth", "Wu Yibing"),
        22,
    ),
    (
        ghost(15301170, "Bu", "Zheng"),
        canonical(15301172, "Bu Yunchaokete", "Michael Zheng"),
        23,
    ),
    (
        ghost(15294647, "Bondar", "Liang"),
        canonical(
            15291212, "Anna Bondár", "Liang En-shuo", "tennis_wta_monterrey_open"
        ),
        3,
    ),
]


class TestTheSurnameFirstGhostIsTagged:
    def test_the_specimen_was_always_confirmable_but_never_blocked_together(self):
        g, c, _ = MEASURED[0]
        assert classify_pair(g, c).outcome == TWIN_FOUND
        assert block_key(g.home_team_name, g.away_team_name) != block_key(
            c.home_team_name, c.away_team_name
        )

    def test_every_measured_pair_is_tagged_onto_its_canonical(self):
        for g, c, apart in MEASURED:
            p = plan([g, c], [0, apart])
            assert [(t.ghost_id, t.canonical_id) for t in p.tags] == [
                (g.event_id, c.event_id)
            ], (g, p.refusals)

    def test_a_flipped_ghost_is_tagged_too(self):
        p = plan(
            [ghost(1, "Alcaraz", "Wu"), canonical(2, "Wu Yibing", "Carlos Alcaraz")],
            [0, 18],
        )
        assert [(t.ghost_id, t.canonical_id) for t in p.tags] == [(1, 2)]

    def test_the_blocks_keep_the_legacy_key(self):
        # Widening only ADDS blocks: every pair the old sweep examined is still examined.
        for g, c, _ in MEASURED:
            for r in (g, c):
                assert block_key(r.home_team_name, r.away_team_name) in block_keys(
                    r.home_team_name, r.away_team_name
                )


class TestTwoFullNamesAreNeverFused:
    FERY_GHOST = ghost(15204746, "Arthur Fery", "Alex de Minaur")
    FERY = canonical(
        15199617, "Arthur Fery", "Alex de Minaur", "tennis_atp_cincinnati_open"
    )
    FILS = canonical(
        15201186, "Arthur Fils", "Alex de Minaur", "tennis_atp_cincinnati_open"
    )

    def test_the_hazard_is_real_in_the_confirm_step(self):
        # The looseness this guard exists for: players_agree fuses the two.
        assert classify_pair(self.FERY_GHOST, self.FILS).outcome == TWIN_FOUND

    def test_a_lone_wrong_canonical_in_reach_is_not_tagged(self):
        # With Fery's own row absent, only Fils is in reach — the shape where
        # the rival guard cannot help. Nothing may be tagged.
        p = plan([self.FERY_GHOST, self.FILS], [0, 48])
        assert p.tags == ()
        assert not surname_alone_pair_agrees(self.FERY_GHOST, self.FILS)

    def test_the_real_pair_keeps_its_tag_when_both_canonicals_are_in_reach(self):
        # Production 2026-08-17: the first widening lost this tag to a rival refusal.
        p = plan([self.FERY_GHOST, self.FERY, self.FILS], [7, 0, 48])
        assert [(t.ghost_id, t.canonical_id) for t in p.tags] == [(15204746, 15199617)]

    def test_a_different_surname_first_player_does_not_reach(self):
        # 'Wu' must not reach a different Wu: the canonical's other side decides.
        p = plan(
            [ghost(1, "Wu", "Alcaraz"), canonical(2, "Wu Yibing", "Jannik Sinner")],
            [0, 18],
        )
        assert p.tags == ()
