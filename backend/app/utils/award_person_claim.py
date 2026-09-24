"""#7867, person half — a club's name token never claims a PERSON for that club.

THE DEFECT. `_build_related_futures` admits an outcome by name when neither its
ticker, its exact alias nor its stored ``team_id`` decides it, and the name
test is whole-token (#6806) over the sub-tokens `_team_name_patterns` emits:
``Duke Blue Devils`` → ``Duke``, ``Devils``, ``Blue``. Award markets list
PEOPLE, and a person's first or last name is often a whole token of some
club's name. Production 2026-09-24 (build v5013), ``/related-futures``:

    15317117 Duke Blue Devils         Doak Walker Award | Vaughn Blue       (`Blue`)
    15317117 Duke Blue Devils         Doak Walker Award | Duke Watson       (`Duke`)
    15317117 William and Mary Tribe   Heisman Trophy    | William "Pop" Watson III
    14781702 Washington Commanders    Offensive ROY ×5  | Mike Washington Jr.
    14780546 Green Bay Packers        Top Fantasy Rookie QB | Taylen Green

None of them is on that club's roster (the Duke rows are in none of Duke's
three box scores either; Mike Washington Jr.'s own first-TD ticker files him
under Las Vegas). The iPhone prints these rows in the event page's AWARDS
section, grouped under the club.

`team_label_identity` (the club half) cannot refuse them by design: it refuses
a token only when it is part of a DIFFERENT KNOWN CLUB, and a person is not in
``teams``. Its docstring names ``Duke Tobin`` as that limitation.

THE RULE. In an award-tier market (``market_tier == 3``), a CLUB-LEVEL pattern
(the team's names, sub-tokens and ``teams.alternate_names``) claims an outcome
only when it IS the whole label — the outcome is the club itself (``Duke``,
``Miami (FL)``). Otherwise only the club's ROSTER names claim it, which is how
the route admits a real player (``Jayson Tatum`` for Boston) today. No denylist,
no name-shape guess: the evidence that a person belongs to a club is the
roster, and a shared word is not evidence.

    Duke Blue Devils | Duke Watson        `Duke` is not the whole label      REFUSED
    Duke Blue Devils | Duke               `Duke` is the whole label          admitted (the club)
    Boston Celtics   | Jayson Tatum       roster name                        admitted
    any team         | Heisman | `Big Ten` no pattern at all                  unchanged

Replayed over 57 production payloads (16 NFL, 23 NCAAF, 8 MLB, 6 NHL, 4 WNBA;
2026-09-24): 660 award-tier rows, 17 refused — every one a person reached only
through a club word (``Thomas White`` on the White Sox for NL Rookie of the
Year, ``Tradarian Ball`` on Ball State, ``Boston Everitt`` on Boston College),
0 clubs, 0 rostered players. ``Maikel García`` on the Royals is placed by his
stored ``team_id``, which runs before this fallback and is untouched.

WHAT IT DOES NOT TOUCH. Every other tier (club futures, game props whose
labels carry a club token plus a suffix), the ticker / alias / ``team_id``
paths that run before the name fallback, and the market-name fallback after it.
A player who IS on the club but missing from a stale roster loses the row —
the same outcome as any player whose name shares no word with the club, which
is the behaviour for almost every player today.
"""

from __future__ import annotations

from app.utils.team_pattern_match import unescape_like_pattern

__all__ = ["AWARD_MARKET_TIER", "outcome_claim_patterns"]

#: ``FuturesMarket.market_tier`` for awards (``event_taxonomy``: 3 → "awards";
#: ``team_linking``: 3 → "award watch"). Its outcomes are people.
AWARD_MARKET_TIER = 3


def outcome_claim_patterns(
    market_tier: int | None,
    outcome_name: str | None,
    patterns: list[str],
    club_patterns: list[str],
) -> list[str]:
    """The subset of ``patterns`` allowed to claim this outcome for one side.

    ``patterns`` is the side's full list (club patterns plus roster names);
    ``club_patterns`` is its club-level subset. Both arrive ILIKE-escaped, as
    the route builds them: membership compares escaped to escaped, and the
    whole-label test reads the pattern back first, because the label is raw.

    Outside the award tier the list comes back unchanged (the same object).
    """
    if market_tier != AWARD_MARKET_TIER:
        return patterns
    club = {p.lower() for p in club_patterns}
    label = (outcome_name or "").strip().lower()
    return [
        p
        for p in patterns
        if p.lower() not in club or unescape_like_pattern(p).strip().lower() == label
    ]
