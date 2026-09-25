"""A prop card names the match it is about (#8524).

Polymarket lists a match as one EVENT ("Valorant: TYLOO vs Team Liquid (BO3) -
VCT Champions Group C") holding many sub-markets, and each sub-market's own
question carries no context at all. We name the row after that question, so
`/hub/esports` PROPS on 2026-09-25 03:10Z drew

    Map 2 Total Rounds: Over/Under 21.5        SERIES PROP   Over 52%
    Games Total: O/U 4.5                       SERIES PROP   Over 48%

with no team, match or date anywhere on the card. The match name lives only on
the event, and ingest already stores it: the grouped row of the same
`group_id` carries `market_metadata.event_title` (`tasks/polymarket.py`). This
module decides which cards borrow it; the route reads the titles.

🔴 **ONLY A MATCH GROUP LENDS, ONLY A MATCHLESS ROW BORROWS.** A `group_id` is
"one venue event", and many events are not matches — "MLB The Show 27 cover
athlete" holds a dozen "Will <player> be on the cover?" rows that already read
as complete questions, and an eyebrow restating the event over each of them is
noise. So the title is attached only when it names a matchup ("A vs B") and the
row's own name does not ("Map Handicap: KC (-1.5) vs XLG Gaming (+1.5)" already
names both sides and is left alone).

🔴 **THE VENUE'S WORDS, VERBATIM.** The title is served as Polymarket wrote it.
Cutting it down to "TYLOO vs Team Liquid" is `extract_matchup`'s job, which is a
matching input with its own owner (lane1, the producer half of #8524); a display
rule that re-parsed titles here would be a second copy of that parser.

Fail-open: a row with no `group_id`, or a group with no stored title, is served
exactly as before.
"""

import re
from typing import Any, Mapping

#: "A vs B" / "A vs. B" / "A VS B" — the shape every Polymarket match title uses.
_MATCHUP = re.compile(r"\bvs\b\.?", re.IGNORECASE)


def names_a_matchup(text: Any) -> bool:
    """True when `text` names two sides of a match."""
    return isinstance(text, str) and bool(_MATCHUP.search(text))


def _borrows(row: Any) -> bool:
    return (
        isinstance(row, dict)
        and bool(row.get("group_id"))
        and not row.get("event_title")
        and not names_a_matchup(row.get("name"))
    )


def groups_needing_a_matchup(sections: Mapping[str, list]) -> set[str]:
    """The `group_id`s whose title the route must read — nothing else is queried."""
    return {
        row["group_id"]
        for rows in sections.values()
        for row in (rows or [])
        if _borrows(row)
    }


def attach_group_matchups(
    sections: Mapping[str, list], titles: Mapping[str, str]
) -> dict[str, list]:
    """Return `sections` with each matchless row carrying its match's `event_title`.

    Never mutates: `build_hub`'s section lists and rows are shared with the
    league-futures payload it composed them from.
    """
    out: dict[str, list] = {}
    for name, rows in sections.items():
        new_rows = []
        for row in rows or []:
            title = titles.get(row.get("group_id")) if _borrows(row) else None
            if isinstance(title, str) and names_a_matchup(title.strip()):
                row = {**row, "event_title": title.strip()}
            new_rows.append(row)
        out[name] = new_rows
    return out
