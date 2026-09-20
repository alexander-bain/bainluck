"""#7501 — a club with no ``teams.slug`` has no page.

THE DEFECT

``/sport/football/ncaaf/team/georgia-bulldogs`` renders *"We don't have a
football page for Georgia Bulldogs."* while ``GET /api/teams/15263`` serves that
club's record (3-0), its crest, five recent games, five upcoming and 23 futures.
Nothing is missing except the one column the URL resolves through: the route
matches ``Team.slug == identifier`` (``routes/teams.py``), and the row's slug is
NULL.

Measured on production 2026-09-20: **4,004 of 9,917 team rows (40.4%) hold a
NULL slug**; 1,314 of those are bound to an event inside 30 days and **855** have
their clean name-slug already held by a club in another sport, so they could not
take it even if something wrote one.

WHY THE COLUMN IS EMPTY

``teams.slug`` is written by exactly one thing: the ``f1a2b3c4d5e6`` migration,
on 2026-05-01, over the rows that existed that day. The mint —
``espn_helpers.upsert_team`` — constructs ``Team(name=..., sport_id=...)`` and
has never set a slug. So every club created since May has been born pageless,
and the population grows with the fixture list.

ONE MECHANISM, NOT TWO HALVES

The obvious shape is "assign at mint, and backfill the rows already there". It is
the wrong shape twice over. A forward-only fix repairs **zero** existing readers
(Georgia's row already exists, and always will). And a slug write inside
``upsert_team`` puts a UNIQUE-constrained INSERT in the per-market commit loop
(gotcha #13), which is the one place in the codebase where a failure must never
reach — an ``IntegrityError`` there costs an event its team binding to gain a
URL. So the column has a single owner: the filler below. ``upsert_team`` keeps
writing NULL and is not touched.

THE LADDER, AND THE TOKEN IT MINTS AGAINST

  1. ``slugify(name)``                         — the clean slug
  2. ``f"{base}-{url_league_segment(key)}"``   — the rung a collision composes
  3. ``f"{base}-{team_id}"``                   — terminal, cannot collide
  4. ``f"team-{team_id}"``                     — for a name that slugifies empty

Rung 2 is the load-bearing one and the migration got it wrong. The migration
suffixed ``sport_key.split("_")[-1]``; the URL the frontend builds
(``frontend/lib/teamUrls.ts`` → ``buildTeamPageUrl``) uses a *different* token,
and they agree only for two-part keys:

  ===========================  ==============  ==============  =========
  sport key                    migration       URL segment     reachable
  ===========================  ==============  ==============  =========
  ``americanfootball_ncaaf``   ``ncaaf``       ``ncaaf``       yes
  ``soccer_epl``               ``epl``         ``epl``         yes
  ``soccer_uefa_champs_league``  ``league``    ``ucl``         no
  ``soccer_efl_champ``         ``champ``       ``efl_champ``   no
  ``tennis_atp_us_open``       ``open``        ``atp_us_open`` no
  ===========================  ==============  ==============  =========

Copying the migration's token would leave tennis (221 rows) and every three-part
soccer key minting slugs no URL composes, and a census counting non-NULL slugs
would read the ship as delivered. So the map below is the LEAGUE HALF of
``SPORT_KEY_TO_PATH``, ported, with ``test_team_slug_url_map_matches_the_frontend``
holding the two copies together (same device as ``shippedCopyBans``).

WHAT THIS DELIBERATELY DOES NOT DO

It never re-slugs a row that already has one. Man City's Champions League row is
``manchester-city-league`` — unreachable from ``/sport/soccer/ucl/...``, and
correcting it would change a URL that is live today. Noted, left alone; a live
URL moves under its own ship, not as a side effect of a backfill.
"""

from __future__ import annotations

from app.utils.slugify import slugify

#: The LEAGUE half of ``SPORT_KEY_TO_PATH`` in ``frontend/lib/teamUrls.ts``.
#: Ported, not re-derived: a slug suffixed with anything else composes a URL the
#: frontend never builds. Kept in sync by
#: ``tests/test_team_slug_url_map_matches_the_frontend_7501.py``, which parses
#: the TypeScript — a comment asking the next reader to remember is not a guard.
URL_LEAGUE_SEGMENT: dict[str, str] = {
    "basketball_nba": "nba",
    "americanfootball_nfl": "nfl",
    "baseball_mlb": "mlb",
    "icehockey_nhl": "nhl",
    "basketball_ncaab": "ncaab",
    "americanfootball_ncaaf": "ncaaf",
    "basketball_wnba": "wnba",
    "soccer_usa_mls": "mls",
    "soccer_epl": "epl",
    "soccer_spain_la_liga": "laliga",
    "soccer_uefa_champs_league": "ucl",
    "soccer_germany_bundesliga": "bundesliga",
    "basketball_wncaab": "wncaab",
    "mma_mixed_martial_arts": "ufc",
    "golf_pga": "pga",
}

#: ``String(200)`` on the column. The base is cut well short of it so rungs 2-4
#: cannot be the thing that overflows — a suffix that gets truncated away is a
#: collision with the rung above it, which is exactly what the ladder exists to
#: avoid.
_MAX_SLUG = 200
_MAX_BASE = 150


def url_league_segment(sport_key: str | None) -> str | None:
    """The league path segment the frontend composes for this sport key.

    Mirrors ``buildTeamPageUrl``: the explicit map first, then the generic
    ``parts[1:].join("_")`` fallback, then ``None`` for a key with no underscore
    (for which the frontend builds no team URL at all, so no suffix we could
    invent would be reachable).
    """
    key = (sport_key or "").strip().lower()
    if not key:
        return None
    mapped = URL_LEAGUE_SEGMENT.get(key)
    if mapped:
        return mapped
    parts = key.split("_")
    if len(parts) >= 2:
        return "_".join(parts[1:])
    return None


def slug_candidates(name: str | None, sport_key: str | None, team_id: int) -> list[str]:
    """The ladder, best rung first, deduped, in order.

    Always returns at least one candidate: a row whose name slugifies to nothing
    (a name that is entirely punctuation or non-Latin script) still gets
    ``team-{id}``, because a reachable ugly URL beats no page. The last two rungs
    carry the primary key, so the list can only be exhausted by a club literally
    named after another club's id — in which case the caller counts the row
    ``unresolved`` and leaves it NULL rather than guessing.
    """
    base = slugify(name or "")[:_MAX_BASE].strip("-")
    out: list[str] = []

    def _add(candidate: str) -> None:
        candidate = candidate.strip("-")[:_MAX_SLUG].strip("-")
        if candidate and candidate not in out:
            out.append(candidate)

    if base:
        _add(base)
        segment = url_league_segment(sport_key)
        if segment:
            _add(f"{base}-{segment}")
        _add(f"{base}-{team_id}")
    _add(f"team-{team_id}")
    return out
