"""WHICH MARKET A SHOWCASE CARD IS ALLOWED TO POINT AT (#6249).

`/sport/{sport}` prints a card per showcase event — Super Bowl, Champions
League, World Series. Before this file the card had three branches (a live golf
tournament, a tournament hub, else *"Date TBD — odds available closer to the
event"*), so for every sport but tennis the third branch was reached **by
construction**: the page told a reader we had nothing for the Super Bowl while
`/futures/86832` served 32 priced teams, repriced that hour.

This module answers the only question that branch was missing: *is there an
open, priced market that IS this competition?*

═══ WHY AN ALLOWLIST OF IDENTITIES AND NOT A SEARCH ═══

Every generic answer measured on production picks a wrong market:

* `market_tier = 1` + `category = 'championship'` is not the championship. It
  holds "AL Reliever of the Year Winner?" and "Executive of the Year Winner?",
  and `baseball_mlb_world_series_winner` — the actual World Series market — is
  tier **5**. Neither column separates a title from an award.
* `canonical_market_key` REPEATS. Eight open MLB markets share
  `baseball:MLB:championship:2026`, so the key is a season bucket, not an
  identity.
* Name patterns over-admit in both directions. `Champions\\s+League.*Winner`
  matches "UEFA Women's Champions League 2026-27 Winner" and "Champions League:
  League Phase Winner"; `Super\\s+Bowl` matches "Was the Super Bowl rigged?".
  That over-admission is a live defect one surface over (#6250, where the men's
  and women's Champions League blend into one cell) and must not be imported
  here to save a lookup.

What IS stable is the pair (source, provider id):

* an Odds API futures key has no season in it —
  `americanfootball_nfl_super_bowl_winner`, `icehockey_nhl_championship_winner`
  — and the row is repriced continuously;
* a Kalshi SERIES ticker is the competition and the suffix is the season —
  `KXUCL-27`, `KXNHL-27`, `KXMLB-26` — so `^KXUCL-\\d+$` follows the Champions
  League into next season while refusing `KXUCLLEAGUE-27` (the league phase)
  and `KXWCW-27` (the women's World Cup) the way a name pattern cannot.

So each entry is a claim we have checked, and adding one is a deliberate act —
the same reasoning as `TOURNAMENT_HUB_SLUGS` in `frontend/lib/tournamentHubs.ts`,
one level out. Polymarket ids are integers minted per market and are never
declared here.

🔴 NO ENTRY IS THE HONEST ANSWER, NOT AN OVERSIGHT. "March Madness (Women's)"
and "College World Series" have no entry: the women's NCAA market resolved in
April, and no open market has been shown to be the college World Series rather
than the professional one. An event with no entry keeps the fallback card,
which is the *correct* card for Wimbledon in September.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select

from app.models import FuturesMarket, FuturesOutcome

logger = logging.getLogger(__name__)

#: A market must price at least this many outcomes before a card may claim we
#: have probabilities for it. One-outcome shells ("UEFA Women's Champions
#: League 2026-27 Winner" prices exactly one team) read as a broken page.
MIN_PRICED_OUTCOMES = 2


@dataclass(frozen=True)
class MarketIdentity:
    """One provider's stable name for a competition's title market."""

    source: str  # futures_markets.source
    external_id_pattern: str  # anchored regex on futures_markets.external_id


#: (sport_slug, showcase event `name`) → the identities that ARE that event.
#:
#: Sport-scoped for the same reason `tournamentHubHref` is: "U.S. Open" is a
#: golf major and "US Open" is a Grand Slam, and a name-only map routes one to
#: the other.
SHOWCASE_MARKET_IDENTITIES: dict[tuple[str, str], tuple[MarketIdentity, ...]] = {
    ("football", "Super Bowl"): (
        MarketIdentity("odds_api", r"^americanfootball_nfl_super_bowl_winner$"),
    ),
    ("football", "College Football Playoff"): (
        # `^KXNCAAF-\d+$` is the FBS national title. It refuses
        # `KXNCAAFFCS-27` (a different division) and `KXNCAAFFINALIST-27`
        # (making the final, not winning it) — both open, both tier 1.
        MarketIdentity("kalshi", r"^KXNCAAF-\d+$"),
        MarketIdentity("odds_api", r"^americanfootball_ncaaf_championship_winner$"),
    ),
    ("basketball", "March Madness (Men's)"): (
        MarketIdentity("odds_api", r"^basketball_ncaab_championship_winner$"),
    ),
    ("hockey", "Stanley Cup"): (
        MarketIdentity("kalshi", r"^KXNHL-\d+$"),
        MarketIdentity("odds_api", r"^icehockey_nhl_championship_winner$"),
    ),
    ("baseball", "World Series"): (
        # `^KXMLB-\d+$` is the title series. The hyphen is load-bearing: it
        # refuses `KXMLBAL-26` (the American League pennant) and the dozens of
        # `KXMLBALCY-26`-shaped award series that share the prefix.
        MarketIdentity("kalshi", r"^KXMLB-\d+$"),
        MarketIdentity("odds_api", r"^baseball_mlb_world_series_winner$"),
    ),
    ("soccer", "Champions League"): (
        MarketIdentity("kalshi", r"^KXUCL-\d+$"),
    ),
    ("soccer", "FIFA World Cup"): (
        # `^KXWC-\d+$` is the men's tournament; `KXWCW-27` is the women's and
        # is a different showcase event we do not yet list.
        MarketIdentity("kalshi", r"^KXWC-\d+$"),
    ),
}


#: Everything a slug may contribute to a log line. `sport_slug` arrives from the
#: URL path, and the route only 404s on an unknown one AFTER this module can be
#: called directly — so a newline in it would write a second, forged log line
#: (CodeQL `py/log-injection`, medium, on the first cut of this file). The
#: truncation is part of the fix: a 4KB slug is a log-flooding line, not a
#: diagnostic.
_LOGGABLE = re.compile(r"[^a-z0-9_-]")


def _loggable(sport_slug: str) -> str:
    return _LOGGABLE.sub("", sport_slug.lower())[:40] or "(unprintable)"


@dataclass(frozen=True)
class ShowcaseCandidate:
    """An open market that matched a declared identity."""

    market_id: int
    priced_outcomes: int
    resolution_date: datetime | None


def open_market_clause(identities: tuple[MarketIdentity, ...]):
    """SQL for "an OPEN market that is one of these declared identities".

    The status test lives in here rather than beside the caller's other
    `.where()` arguments because at that indentation the line was
    byte-identical to a mutant replacement in
    `scripts/evals/kalshi_segment_resolved_link_mutations.py`, and
    `test_mutation_guard.py`'s residue sweep — correctly — cannot tell a
    coincidence from a leaked mutant.
    """
    return and_(
        FuturesMarket.status == "open",
        or_(
            *[
                and_(
                    FuturesMarket.source == identity.source,
                    FuturesMarket.external_id.op("~")(identity.external_id_pattern),
                )
                for identity in identities
            ]
        ),
    )


def choose_candidate(
    candidates: list[ShowcaseCandidate], *, now: datetime
) -> ShowcaseCandidate | None:
    """The market a card points at, or None.

    Two competitions can be open under one identity at once: `KXUCL-26` (last
    season's, still carrying a resolution date two years out) sits beside
    `KXUCL-27`. The card wants the title that is decided NEXT, so a market
    whose resolution date has already passed is out — it is a field that
    should have settled — and the survivors rank by soonest resolution, with
    the undated Odds API rows last because a row that never says when it
    resolves cannot outrank one that does.
    """
    live = [
        candidate
        for candidate in candidates
        if candidate.priced_outcomes >= MIN_PRICED_OUTCOMES
        and (candidate.resolution_date is None or candidate.resolution_date > now)
    ]
    if not live:
        return None
    return min(
        live,
        key=lambda candidate: (
            candidate.resolution_date is None,
            candidate.resolution_date or now,
            -candidate.priced_outcomes,
            candidate.market_id,
        ),
    )


async def attach_showcase_markets(
    sport_slug: str, showcase_events: list[dict], db, *, now: datetime | None = None
) -> list[dict]:
    """Copy `showcase_events`, adding the market each card may point at.

    Every returned event carries `futures_market_id` and
    `futures_priced_outcomes`, both `None` when there is nothing to point at,
    so the shape a client reads never depends on the data — an absent key and
    a null would otherwise be the same "no market" arriving two ways.

    Resolution never fails the page. This is a navigation surface: if the
    lookup raises, the cards render exactly as they did before this module
    existed, and the failure is logged rather than 500ing a sport hub.
    """
    now = now or datetime.now(timezone.utc)
    enriched = [
        {**event, "futures_market_id": None, "futures_priced_outcomes": None}
        for event in showcase_events
    ]

    wanted = {
        event["name"]: SHOWCASE_MARKET_IDENTITIES[(sport_slug, event["name"])]
        for event in enriched
        if (sport_slug, event.get("name")) in SHOWCASE_MARKET_IDENTITIES
    }
    if not wanted:
        return enriched

    try:
        for event in enriched:
            identities = wanted.get(event["name"])
            if not identities:
                continue
            rows = await db.execute(
                select(
                    FuturesMarket.id,
                    FuturesMarket.resolution_date,
                    func.count(FuturesOutcome.id).label("priced_outcomes"),
                )
                .join(
                    FuturesOutcome,
                    and_(
                        FuturesOutcome.market_id == FuturesMarket.id,
                        FuturesOutcome.current_probability.isnot(None),
                    ),
                )
                .where(open_market_clause(identities))
                .group_by(FuturesMarket.id, FuturesMarket.resolution_date)
            )
            chosen = choose_candidate(
                [
                    ShowcaseCandidate(
                        market_id=row[0],
                        resolution_date=row[1],
                        priced_outcomes=row[2],
                    )
                    for row in rows.all()
                ],
                now=now,
            )
            if chosen is not None:
                event["futures_market_id"] = chosen.market_id
                event["futures_priced_outcomes"] = chosen.priced_outcomes
    except Exception:  # noqa: BLE001 — a hub page outlives its enrichment
        logger.warning(
            "showcase market lookup failed for sport_slug=%s",
            _loggable(sport_slug),
            exc_info=True,
        )
        return [
            {**event, "futures_market_id": None, "futures_priced_outcomes": None}
            for event in showcase_events
        ]

    return enriched


def unanchored_identities() -> list[tuple[tuple[str, str], str]]:
    """Declared patterns that are not anchored at both ends.

    An unanchored pattern is how `KXMLB` swallows `KXMLBALCY-26`; the guard
    test reads this rather than eyeballing the table.
    """
    return [
        (key, identity.external_id_pattern)
        for key, identities in SHOWCASE_MARKET_IDENTITIES.items()
        for identity in identities
        if not (
            identity.external_id_pattern.startswith("^")
            and identity.external_id_pattern.endswith("$")
        )
    ]


def identity_matches(pattern: str, external_id: str) -> bool:
    """Python-side mirror of the SQL `~` test, for guard tests."""
    return re.search(pattern, external_id) is not None
