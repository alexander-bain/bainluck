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

It turns the ESPN scoreboard the page already reads into two facts per player:

* **the deepest round they are PROVEN to have reached**, and
* **the round they are PROVEN to have lost**, if any.

Nothing else.  There is no inference, no bracket walking, no "the tournament
has moved on so they must be out".  A knockout draw is full of ways to be
wrong about that — a half of the draw can run a round behind the other half,
and a walkover leaves no loser.  So the rule is:

    A CELL IS ONLY SETTLED BY A MATCH WE HOLD.

Everything unproven keeps its price and stays in the sum check, where it is
counted and reported rather than quietly corrected.  This under-claims by
construction and that is the point: a false "out" would erase a live player
from the grid, which is a worse failure than the one being fixed.

═══ WHY IT READS THE SCOREBOARD AND NOT ``build_results`` (CERT-2360) ═══

The obvious input was the decided-match list the page already serves.  It is
the wrong one, and the first presentation of this ship shipped that mistake:

``build_results`` publishes a SCORE UNDER TWO NAMES, so it drops a match unless
BOTH sides resolve to registered players — 147 of 467 scored competitions on
2026-09-09.  That strictness is right for a score row and wrong here, because
one unresolvable name takes the OTHER player's result with it.  Michael Zheng,
this issue's own headline case, appears in the served list only as a first-round
winner: the match he lost was dropped because of his opponent's name, so a
progress pass built on that list leaves his stale 52% Final cell exactly where
it was.

Publishing a score needs both names.  Knowing that ONE named player lost needs
one.  So this module resolves each side **independently** against the register
and asks the scoreboard's own ``winner_normalized`` whether that side won — a
question that is answerable about a resolved player whether or not their
opponent resolves.  ``build_results`` is untouched and stays strict; no partial
row reaches the results list.

The comparison errs safe in the one direction that matters.  A side is
eliminated only when its normalized name DIFFERS from the winner's, so any
failure to match names produces a missing elimination, never a false one.

═══ HOW A MATCH BECOMES A FACT ═══

For a completed match at round ``R``, for each side that resolves:

* the side **reached** ``R`` — they played in it;
* the winner **reached** the round after ``R`` (or won the title, if ``R`` is
  the final) — the draw admits them without another match being played;
* a side that is not the winner is **eliminated at** ``R``.

"Reached ``R``" implies reached every earlier round, so only the deepest index
is kept.  A match with no winner (in progress, abandoned) contributes only the
"reached ``R``" facts — being in a match that has not finished is not losing it.

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

#: Completion words that mean the match is over. ESPN's own vocabulary
#: (``espn_tennis.completion_of``) — a retirement and a walkover both decide a
#: match, and both eliminate the player who did not advance.
DECIDED_COMPLETIONS = frozenset({"final", "retired", "walkover"})

#: What one resolved side of one match contributes.
SIDE_WON = "won"
SIDE_LOST = "lost"
SIDE_PLAYED = "played"


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
    #: How many decided matches contributed at least one resolved side. Zero
    #: means this object settles nothing, which is what a cold scoreboard
    #: cache should look like.
    decided_matches: int = 0
    #: Of those, how many resolved only ONE side — the matches `build_results`
    #: drops whole and this pass keeps half of (CERT-2360). Reported because it
    #: is the size of the repair, and because a number that climbs is a name
    #: normalisation problem getting worse.
    partial_matches: int = 0

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
    register: dict[str, Any],
    results: Optional[dict[str, Any]] = None,
    *,
    draw_sizes: Optional[dict[str, Optional[int]]] = None,
) -> dict[str, DrawProgress]:
    """The ESPN scoreboard -> one :class:`DrawProgress` per draw.

    ``results`` is ``app.services.espn_tennis.parse_results``' output — the same
    object ``build_results`` reads, taken BEFORE its strict two-name join (see
    the module docstring for why that matters). ``{draw: {pair_key: row}}``,
    each row carrying ``players`` (two ESPN display names), ``espn_round``,
    ``winner_normalized`` and ``completion``.

    ``draw_sizes`` maps a draw to how many players its first round held, which
    is what makes ``"Round 2"`` mean ``R64`` in a slam and ``R32`` in a 64-draw.
    A draw with no size is skipped rather than guessed — filing a match under
    the wrong round would settle the wrong column, which is the wrong-question
    defect the register exists to refuse.
    """
    from app.services.espn_tennis import normalize_name
    from app.utils.tournament_register import TournamentRegister

    reg = TournamentRegister(register or {})
    # (draw, normalized name) -> entity_key. The same index `build_results`
    # builds, read one side at a time instead of two at once.
    by_name: dict[tuple[str, str], str] = {}
    for player in reg.players:
        key = (str(player.get("draw") or ""), normalize_name(player.get("display_name")))
        if player.get("entity_key"):
            by_name.setdefault(key, str(player.get("entity_key")))

    sides: list[dict[str, Any]] = []
    sizes = draw_sizes or {}
    for draw, found_by_pair in sorted(((results or {}).get("draws") or {}).items()):
        if not isinstance(found_by_pair, dict):
            continue
        for pair_key, found in sorted(found_by_pair.items()):
            if not isinstance(found, dict):
                continue
            round_key = _round_key(found.get("espn_round"), draw_size=sizes.get(str(draw)))
            if round_key is None:
                continue
            winner_normalized = found.get("winner_normalized") or None
            decided = (
                str(found.get("completion") or "").strip().lower() in DECIDED_COMPLETIONS
                and winner_normalized is not None
            )
            names = [n for n in (found.get("players") or []) if n]
            resolved = 0
            for name in names:
                normalized = normalize_name(name)
                entity_key = by_name.get((str(draw), normalized))
                if entity_key is None:
                    # THIS SIDE ONLY. An unresolvable opponent costs us their
                    # half of the match and nothing else — which is the whole
                    # of the CERT-2360 repair.
                    continue
                resolved += 1
                outcome = SIDE_PLAYED
                if decided:
                    outcome = SIDE_WON if normalized == winner_normalized else SIDE_LOST
                sides.append({
                    "draw": str(draw),
                    "round": round_key,
                    "entity_key": entity_key,
                    "outcome": outcome,
                    "match_key": f"{draw}:{pair_key}",
                })
            if decided and resolved == 1 and len(names) == 2:
                sides[-1]["partial"] = True
    return progress_from_sides(sides)


def progress_from_sides(sides: Iterable[dict[str, Any]]) -> dict[str, DrawProgress]:
    """Resolved match sides -> the proven facts, per draw.

    A side is ``{draw, round, entity_key, outcome, match_key}`` where
    ``outcome`` is ``won`` / ``lost`` / ``played``. Split out from the reader
    above so the arithmetic — deepest round, elimination, the champion, and the
    whole-field counts — is testable without a register or a scoreboard.
    """
    reached: dict[str, dict[str, int]] = {}
    eliminated: dict[str, dict[str, str]] = {}
    champions: dict[str, str] = {}
    decided_keys: dict[str, set[str]] = {}
    partial_keys: dict[str, set[str]] = {}

    for side in sides or []:
        draw = str(side.get("draw") or "")
        round_key = str(side.get("round") or "")
        entity_key = side.get("entity_key")
        index = ROUND_INDEX.get(round_key)
        if not draw or index is None or not entity_key:
            continue
        key = str(entity_key)
        outcome = str(side.get("outcome") or SIDE_PLAYED)
        match_key = str(side.get("match_key") or f"{draw}:{round_key}:{key}")

        draw_reached = reached.setdefault(draw, {})
        if index > draw_reached.get(key, -1):
            draw_reached[key] = index

        if outcome == SIDE_PLAYED:
            # In progress, or a result we cannot attribute. The "played in this
            # round" fact stands; nobody is knocked out by it.
            continue
        decided_keys.setdefault(draw, set()).add(match_key)
        if side.get("partial"):
            partial_keys.setdefault(draw, set()).add(match_key)

        if outcome == SIDE_LOST:
            eliminated.setdefault(draw, {}).setdefault(key, round_key)
        elif index + 1 < len(ROUNDS):
            if index + 1 > draw_reached.get(key, -1):
                draw_reached[key] = index + 1
        else:
            champions[draw] = key

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
            decided_matches=len(decided_keys.get(draw, ())),
            partial_matches=len(partial_keys.get(draw, ())),
        )
    return out


def _round_key(espn_round: Any, *, draw_size: Optional[int]) -> Optional[str]:
    """A match's round in the REGISTER's vocabulary, or ``None``.

    The register's own key is accepted first because it needs no draw size and
    cannot be ambiguous; ESPN's display name goes through the draw ingest's own
    reader rather than a second table of round names.
    """
    from app.services.espn_tennis import espn_round_key

    raw = str(espn_round or "").strip()
    if not raw:
        return None
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
    "SIDE_LOST",
    "SIDE_PLAYED",
    "SIDE_WON",
    "VERDICT_OUT",
    "VERDICT_REACHED",
    "DrawProgress",
    "build_progress",
    "progress_from_sides",
]
