"""Which editions have a container, and which provider ids name them. #2927.

THE ONE HAND-WRITTEN THING IN THIS PROGRAM IS AN ID, NEVER A MEMBER. The ship
is "nobody writes a list of what is in the US Open ever again", not "nobody
tells us the US Open exists". A tournament declaration below carries an
edition's slug, its dates, and the provider ids that name it at each venue —
five short lines — and every MEMBER of every section is then discovered from
those ids by `container_assembly`. Adding Wimbledon is a declaration, not code.

WHY THE ANCHORS ARE DECLARED AND NOT DISCOVERED. A Kalshi series ticker is the
venue's own grouping key; there is no endpoint that says "these two series are
the US Open". Discovery is the *members'* job. The alternative — inferring the
tournament from market names — is the name matching this whole program exists
to stop (`container_assembly`'s ordering constraint).

WHAT IS DELIBERATELY NOT HERE.
* **No member lists.** If you find yourself adding a market id, stop: that is
  the curated hub this program replaces.
* **No status.** A container is `live` or `final` when its AUTHORITY says so
  (D27), never because a file said it would be.
* **The windows are ours only until an authority carries them.** They are
  declared here with the evidence for each date, and every one is a date this
  lane measured rather than remembered — see `US_OPEN_2026`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class DeclaredAnchor:
    """One provider id that names one container.

    ``scope='edition'`` says this id belongs WHOLLY to this edition even though
    its kind is normally tour-wide. It is written into the anchor's own
    `claim_context`, so the exception is visible in the row rather than in a
    list of trusted series inside the gatherer.
    """

    provider: str
    provider_id: str
    id_kind: str
    #: The child container slug SUFFIX this anchor belongs to, or None for the
    #: root. `mens-doubles` -> `us-open-2026-mens-doubles`.
    draw: Optional[str] = None
    sport: Optional[str] = "tennis"
    scope: Optional[str] = None
    #: Why we believe this id names this edition. Carried into `claim_context`,
    #: because an anchor whose provenance is a memory is an anchor nobody dares
    #: delete.
    evidence: Optional[str] = None


@dataclass(frozen=True)
class TournamentDeclaration:
    tournament: str
    season: str
    display_name: str
    window_start: datetime
    window_end: datetime
    anchors: tuple = field(default_factory=tuple)
    sport: Optional[str] = "tennis"

    @property
    def root_slug(self) -> str:
        return f"{self.tournament}-{self.season}"

    def slug_for(self, draw: Optional[str]) -> str:
        return self.root_slug if draw is None else f"{self.root_slug}-{draw}"


def _utc(y, m, d) -> datetime:
    return datetime(y, m, d, tzinfo=timezone.utc)


#: US Open 2026. Every id below was read from `futures_markets` on production
#: on 2026-09-06 and cross-checked against Kalshi's own
#: `/markets?series_ticker=…&status=open` (standing notice 26: the venue
#: answers "does this exist", never our mirror).
#:
#: THE WINDOW, and where each end comes from:
#: * **2026-08-24** — the earliest US Open market we hold is
#:   `KXMIXEDDOUBLESMATCH`, whose 22 rows run 08-24 16:54Z → 08-27 04:09Z. The
#:   mixed-doubles draw is played in the week before the main draw, so it is
#:   the true left edge of the edition and a window starting at the main draw
#:   would refuse all 22.
#: * **2026-09-14** — one day past the men's final. The committed register's
#:   main draw opens Sunday 08-30, and the open Kalshi rows carry ticker dates
#:   through 26SEP07 with the draw still at the quarter-final stage, so the
#:   fortnight ends 09-13. The slack is one day, not one week: a window is a
#:   membership test and a loose one re-admits the next tournament.
#:
#: These dates are OURS, not an authority's, and that is a stated weakness
#: rather than a hidden one — D27 says a container's dates should come from
#: ESPN or StatPal, and the moment they do, this block is deleted rather than
#: corrected.
US_OPEN_2026 = TournamentDeclaration(
    tournament="us-open",
    season="2026",
    display_name="US Open 2026",
    window_start=_utc(2026, 8, 24),
    window_end=_utc(2026, 9, 14),
    anchors=(
        DeclaredAnchor(
            provider="kalshi",
            provider_id="KXATPMATCH",
            id_kind="series",
            draw="mens-singles",
            evidence="2,614 resolved + 14 open rows; tour-wide, bounded by the window",
        ),
        DeclaredAnchor(
            provider="kalshi",
            provider_id="KXWTAMATCH",
            id_kind="series",
            draw="womens-singles",
            evidence="2,511 resolved + 15 open rows; tour-wide, bounded by the window",
        ),
        DeclaredAnchor(
            provider="kalshi",
            provider_id="KXATPDOUBLES",
            id_kind="series",
            draw="mens-doubles",
            evidence="42 open rows on 2026-09-06, ALL for 09-18 → 09-20; the window is what keeps them out",
        ),
        DeclaredAnchor(
            provider="kalshi",
            provider_id="KXWTADOUBLES",
            id_kind="series",
            draw="womens-doubles",
            evidence="32 open rows on 2026-09-06, all 09-17 → 09-21; same",
        ),
        DeclaredAnchor(
            provider="kalshi",
            provider_id="KXMIXEDDOUBLESMATCH",
            id_kind="series",
            draw="mixed-doubles",
            evidence="22 rows, 08-24 → 08-27, the fan-week mixed draw",
        ),
        DeclaredAnchor(
            provider="kalshi",
            provider_id="KXHONEYDEUCE",
            id_kind="series",
            draw=None,
            scope="edition",
            evidence=(
                "'Number of Honey Deuces sold at the US Open' — the series is this "
                "tournament's and nothing else's, and its single market's only stored "
                "date is a 2027-01-01 expiry, so a window would refuse a real member"
            ),
        ),
    ),
)


#: Every edition the assembly pass knows about. A list, so the pass can walk it
#: and so a second tournament costs one entry.
DECLARED_TOURNAMENTS: tuple = (US_OPEN_2026,)


def declaration_for(slug: str) -> Optional[TournamentDeclaration]:
    """The declaration whose root slug is ``slug``, or None."""
    for declared in DECLARED_TOURNAMENTS:
        if declared.root_slug == slug:
            return declared
    return None
