"""One question, one card: drop the binary legs a grouped field already answers (#7400).

Polymarket serialises a multi-outcome question as a negative-risk EVENT whose
members are the individual binary markets, plus one grouped market holding the
whole field. We ingest both, they share a `FuturesMarket.group_id`, and a surface
that composes a section from that pool renders the ranked field and then every
one of its rows again as its own Yes/No card:

    /hub/esports  TOURNAMENT WINNERS (25)
        VCT Partnership 2027: Pacific — Paper Rex 93% · FULL SENSE 49% · +13 more
        Will Global Esports be a 2027 VCT Pacific partner team?   Yes 44%
        Will FULL SENSE be a 2027 VCT Pacific partner team?       Yes 49%
        …8 more, adjacent, at the top of the page

    /hub/mma      Who will become a UFC champion in 2026? (28 outcomes) + 22 legs

Measured on production 2026-09-20: 32 such cards across those two hubs, each
leg's Yes byte-identical to the parent row above it, and all 32 legs' contenders
verified present in the parent's full outcome list (32/32, zero unmatched).

🔴 **THE PREDICATE IS "A PARENT IS PRESENT", NOT "A GROUP IS SHARED".** A
`group_id` alone means "these markets belong to one venue event", which is very
often a set of genuinely distinct questions: `polymarket:806410` is 32 separate
roster-change questions ("Will Sentinels / Cloud9 / T1 make a roster change by
December?") and `polymarket:1048814` is three real props of one match (First
Blood in Game 2, Total Kills O/U in Game 2, in Game 3). Collapsing on
`group_id` alone deletes ~150 real cards — 90 on esports, 62 on tennis. What
makes a binary row REDUNDANT is that the same family also carries the grouped
market that already lists it, so that is what is tested.

🔴 **MEMBERSHIP IS NOT READ OFF `top_outcomes`.** That list is truncated to ten,
so 4 of 8 MMA legs sampled were absent from their 28-outcome parent's serialized
rows purely by truncation. The venue's own grouping is the evidence; the
truncated display list is not.

🔴 **KEEP THE PARENT, DROP THE LEGS.** One ranked field is the better card and in
both measured hubs the parent is already at index 0. The reverse would replace
one good card with 22 poor ones.

🔴 **SCOPED TO ONE SECTION.** A family whose parent sits under one heading and
whose legs sit under another is real and larger (measured the same day: tennis
`polymarket:766238` parent in MORE MARKETS with 33 legs in PROPS,
`polymarket:768652` 31 more, esports 7 more) but it is a different reader
experience and emptying a rendered section whole is its own decision — #7437.
This rule only removes a duplicate a reader meets inside one list.

Fail-open throughout: a row with no `group_id`, no `outcome_count`, or an
`outcome_count` this rule does not recognise is KEPT. The cost of keeping a card
is a duplicate; the cost of dropping one is a market the reader cannot reach.
"""

from typing import Any, Iterable, Mapping

#: A grouped market: more sides than a Yes/No, so it can hold a field of rows.
_PARENT_MIN_OUTCOMES = 3
#: A leg: exactly the two sides of one row of that field.
_LEG_OUTCOMES = 2


def _outcome_count(row: Any) -> int | None:
    if not isinstance(row, dict):
        return None
    count = row.get("outcome_count")
    return count if isinstance(count, int) else None


def _group_id(row: Any) -> str | None:
    if not isinstance(row, dict):
        return None
    group_id = row.get("group_id")
    return group_id if isinstance(group_id, str) and group_id else None


def _groups_with_a_parent(rows: Iterable[Any]) -> set[str]:
    """The `group_id`s in this section that carry a grouped market of their own."""
    return {
        group_id
        for row in rows
        if (group_id := _group_id(row))
        and (count := _outcome_count(row)) is not None
        and count >= _PARENT_MIN_OUTCOMES
    }


def is_leg_of_a_rendered_field(row: Any, groups_with_a_parent: set[str]) -> bool:
    """Is this row a binary restatement of a field already on the same list?"""
    group_id = _group_id(row)
    if group_id is None or group_id not in groups_with_a_parent:
        return False
    return _outcome_count(row) == _LEG_OUTCOMES


def drop_legs_of_a_rendered_field(
    sections: Mapping[str, list] | None,
) -> dict[str, list]:
    """Return `sections` with each grouped field's own legs removed from it.

    Per section, independently: find the families that have a parent present,
    then drop that family's two-outcome members. Every other row — every family
    with no parent, every unfamilied row, the parents themselves — is kept, in
    the order it arrived.

    A section can never be emptied by this rule: a family only loses legs where
    its parent is in the same section, and the parent is kept. That is asserted
    in the guard, and it is why nothing here has to re-add a heading.

    Neither the mapping nor its lists are mutated. `build_hub`'s `sections` share
    their list objects with a Redis-cached league payload, and mutating one in
    place re-composes every page that reads that slot (live/103's
    `census_sections` lesson, #3964 — the same shallow-copy shape).
    """
    kept: dict[str, list] = {}
    for name, rows in (sections or {}).items():
        rows = rows or []
        with_a_parent = _groups_with_a_parent(rows)
        kept[name] = (
            [r for r in rows if not is_leg_of_a_rendered_field(r, with_a_parent)]
            if with_a_parent
            else list(rows)
        )
    return kept
