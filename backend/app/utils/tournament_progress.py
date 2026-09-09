"""WHAT THE DRAW HAS ALREADY DECIDED — read from the results, proven or nothing.

═══ THE DEFECT THIS EXISTS FOR (#4174) ═══

The playoff grid (``tournament_grid``) publishes one number per (player, round)
from the register's pinned reach markets.  That is correct on the morning of
the first round and progressively false afterwards, because a reach market for
a round that has already been PLAYED is not a forecast of anything — it is
either a resolved 1/0 that nobody re-polled, or a fossil quote frozen at the
moment the venue stopped trading it.

Measured on production 2026-09-09 09:52Z, quarter-final morning, men's singles:

    column   sum    slots   ratio
    R16      23.48    16     1.47    <- the round of 16 was OVER
    QF        5.00     8     0.63    <- every cell an unpolled 1.0 or 0.0
    SF        8.55     4     2.14
    Final     4.93     2     2.46
    Title     1.16     1     1.16

The Final column offering 2.46 finals is not "sources disagree".  Fourteen of
its contributors were **already out of the tournament** and were still being
published at their pre-elimination number — Michael Zheng at 52% to reach a
final he was knocked out of in the second round.  The Title column's whole
0.16 of overround is seventeen eliminated players carrying a 1% outright each.

═══ WHAT THIS MODULE DOES, AND THE ONE RULE IT OBEYS ═══

It turns the decided-match list the page already serves (``build_results``)
into two facts per player:

* **the deepest round they are PROVEN to have reached**, and
* **the round they are PROVEN to have lost**, if any.

Nothing else.  There is no inference, no bracket walking, no "the tournament
has moved on so they must be out".  A knockout draw is full of ways to be
wrong about that — a half of the draw can run a round behind the other half,
a walkover leaves no loser, and our own results join drops a match whose two
names do not both resolve to registered players (measured: 147 dropped of 467
scored).  So the rule is:

    A CELL IS ONLY SETTLED BY A MATCH WE HOLD.

Everything unproven keeps its price and stays in the sum check, where it is
counted and reported rather than quietly corrected.  This under-claims by
construction and that is the point: a false "out" would erase a live player
from the grid, which is a worse failure than the one being fixed.

═══ HOW A MATCH BECOMES A FACT ═══

For a completed match at round ``R`` between two players, with a winner:

* both players **reached** ``R`` — they played in it;
* the winner **reached** the round after ``R`` (or won the title, if ``R`` is
  the final) — the draw admits them without another match being played;
* the loser is **eliminated at** ``R``.

"Reached ``R``" implies reached every earlier round, so only the deepest index
is kept.  A match with no winner (in progress, abandoned) contributes the two
"reached ``R``" facts and no elimination — being in a match that has not
finished is not losing it.

``reached_counts`` is the count over the WHOLE field, not over the grid's rows:
the sum check's denominator is a fact about the round, and a round whose
sixteen places are taken has none left regardless of how many of those sixteen
players the grid happens to have a row for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from app.utils.tournament_register import ROUNDS

#: Round key -> its position in the draw. ``qualifying`` is index 0 and is
#: carried so a qualifier's loss still registers as an elimination.
ROUND_INDEX: dict[str, int] = {name: i for i, name in enumerate(ROUNDS)}

#: What the grid may be told about a (player, round) pair.
VERDICT_REACHED = "reached"
VERDICT_OUT = "out"

#: Completion words that mean the match is over. ESPN's vocabulary, via
#: ``build_results`` — a retirement and a walkover both decide a match, and
#: both eliminate the player who did not advance.
DECIDED_COMPLETIONS = frozenset({"final", "retired", "walkover"})


@dataclass(frozen=True)
class DrawProgress:
    """One draw's proven facts. Empty is a valid, honest answer."""

    #: entity_key -> deepest ROUNDS index the player is proven to have reached.
    reached: dict[str, int] = field(default_factory=dict)
    #: entity_key -> the round key they are proven to have lost at.
    eliminated: dict[str, str] = field(default_factory=dict)
    #: Who won the final, if the final has been played.
    champion: Optional[str] = None
    #: round key -> how many players in the WHOLE field are proven to have
    #: reached it. The sum check's denominator, not a grid row count.
    reached_counts: dict[str, int] = field(default_factory=dict)
    #: How many matches contributed. Zero means this object settles nothing,
    #: which is what a cold results cache should look like.
    decided_matches: int = 0

    def verdict(self, entity_key: Any, round_key: str) -> Optional[str]:
        """``reached`` / ``out`` / ``None`` for one reach cell.

        ``None`` is the common answer and the safe one: the tournament has not
        answered this question yet, or we cannot prove that it has.
        """
        index = ROUND_INDEX.get(round_key)
        if index is None:
            return None
        key = str(entity_key)
        deepest = self.reached.get(key)
        if deepest is not None and deepest >= index:
            return VERDICT_REACHED
        # Proven out, and proven not to have got this far. The second clause is
        # not redundant: a player eliminated in the semi-final REACHED the
        # semi-final, and only the columns beyond it are decided against them.
        if key in self.eliminated:
            return VERDICT_OUT
        return None

    def title_verdict(self, entity_key: Any) -> Optional[str]:
        """The same question for the title column, which is not a round."""
        key = str(entity_key)
        if self.champion is not None and key == self.champion:
            return VERDICT_REACHED
        if key in self.eliminated:
            return VERDICT_OUT
        return None

    def open_slots(self, round_key: str, slots: Optional[int]) -> Optional[int]:
        """How many places in ``round_key`` are still to be won.

        The number the still-open probabilities in that column have to add up
        to.  A round whose field is fully known returns ``0``, and a column
        with nothing left to decide is not a failed sum check — it is a
        finished one.
        """
        if slots is None:
            return None
        if round_key == "title":
            # Not a round and not in `reached_counts`: the title is open until
            # somebody has won the final, and then it is not.
            return 0 if self.champion else slots
        return max(slots - self.reached_counts.get(round_key, 0), 0)


EMPTY_PROGRESS = DrawProgress()


def build_progress(
    matches: Iterable[dict[str, Any]],
    *,
    draw_sizes: Optional[dict[str, Optional[int]]] = None,
) -> dict[str, DrawProgress]:
    """Decided matches -> one :class:`DrawProgress` per draw.

    ``matches`` is ``build_results(...)["matches"]``: each row carries ``draw``,
    ``round`` (ESPN's display name), ``players[].entity_key``, an optional
    ``winner_entity_key`` and a ``completion``.

    ``draw_sizes`` maps a draw to how many players its first round held, which
    is what makes ``"Round 2"`` mean ``R64`` in a slam and ``R32`` in a 64-draw.
    A draw with no size is skipped rather than guessed — filing a match under
    the wrong round would settle the wrong column, which is the wrong-question
    defect the register exists to refuse.
    """
    sizes = draw_sizes or {}
    reached: dict[str, dict[str, int]] = {}
    eliminated: dict[str, dict[str, str]] = {}
    champions: dict[str, str] = {}
    counted: dict[str, int] = {}

    for match in matches or []:
        if not isinstance(match, dict):
            continue
        draw = str(match.get("draw") or "")
        if not draw:
            continue
        round_key = _round_key(match, draw_size=sizes.get(draw))
        if round_key is None:
            continue
        index = ROUND_INDEX[round_key]

        players = [p for p in (match.get("players") or []) if isinstance(p, dict)]
        keys = [str(p.get("entity_key")) for p in players if p.get("entity_key")]
        if not keys:
            continue

        draw_reached = reached.setdefault(draw, {})
        for key in keys:
            if index > draw_reached.get(key, -1):
                draw_reached[key] = index

        completion = str(match.get("completion") or "").strip().lower()
        winner = match.get("winner_entity_key")
        winner = str(winner) if winner else None
        if completion not in DECIDED_COMPLETIONS or winner is None:
            # In progress, or a result we cannot attribute. The two "played in
            # this round" facts above stand; nobody is knocked out by it.
            continue

        counted[draw] = counted.get(draw, 0) + 1
        for key in keys:
            if key != winner:
                eliminated.setdefault(draw, {}).setdefault(key, round_key)

        if index + 1 < len(ROUNDS):
            if index + 1 > draw_reached.get(winner, -1):
                draw_reached[winner] = index + 1
        else:
            champions[draw] = winner

    out: dict[str, DrawProgress] = {}
    for draw in set(reached) | set(eliminated) | set(champions):
        draw_reached = reached.get(draw, {})
        counts: dict[str, int] = {}
        for deepest in draw_reached.values():
            # Reaching a round means having reached every earlier one, so a
            # player counts into every column up to their own depth.
            for name in ROUNDS[: deepest + 1]:
                counts[name] = counts.get(name, 0) + 1
        out[draw] = DrawProgress(
            reached=draw_reached,
            eliminated=eliminated.get(draw, {}),
            champion=champions.get(draw),
            reached_counts=counts,
            decided_matches=counted.get(draw, 0),
        )
    return out


def _round_key(match: dict[str, Any], *, draw_size: Optional[int]) -> Optional[str]:
    """A match's round in the REGISTER's vocabulary, or ``None``.

    ``build_results`` publishes the register's own key when it still holds the
    matchup and ESPN's display name otherwise, so both shapes arrive here. The
    register key is checked first because it needs no draw size and cannot be
    ambiguous; ESPN's name goes through the draw ingest's own reader rather
    than a second table of round names.
    """
    from app.services.espn_tennis import espn_round_key

    for candidate in (match.get("round"), match.get("source_round")):
        raw = str(candidate or "").strip()
        if not raw:
            continue
        if raw in ROUND_INDEX:
            return raw
        if draw_size:
            mapped = espn_round_key(raw, draw_size=draw_size)
            if mapped in ROUND_INDEX:
                return mapped
    return None


__all__ = [
    "DECIDED_COMPLETIONS",
    "EMPTY_PROGRESS",
    "ROUND_INDEX",
    "VERDICT_OUT",
    "VERDICT_REACHED",
    "DrawProgress",
    "build_progress",
]
