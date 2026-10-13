"""Fresh bounded NFL week links, independent of the current membership cache."""

from sqlalchemy import text

from app.services.container_discovery import _COLUMNS, _discovery_sql, collection_card
from app.utils.container_corrections import correction_schema_present
from app.utils.container_nfl import (
    NflWeek,
    STAGE_PRESEASON,
    STAGE_REGULAR,
    STAGE_POSTSEASON,
)
from app.utils.container_presentation import edition_for_slug

STAGES = (STAGE_PRESEASON, STAGE_REGULAR, STAGE_POSTSEASON)
# The presentation identity grammar accepts exactly 1..99 in each stage.
# Generate the complete representable range, not the discovery feed's latest20.
MAX_WEEK = 99
MAX_EDITIONS = len(STAGES) * MAX_WEEK


def week_order(edition):
    return STAGES.index(edition["stage"]), edition["week"]


def select_navigation(slug, rows):
    unavailable = {"slug": slug, "state": "unavailable", "previous": None, "next": None}
    identity = edition_for_slug(slug)
    if not identity or identity.get("kind") != "nfl_week" or len(rows) > MAX_EDITIONS:
        return unavailable
    cards = {}
    for row in rows:
        card, _ = collection_card(row, league="nfl", season=identity["season"])
        if card is None:
            continue
        if card["slug"] in cards:
            return unavailable  # Ambiguous destination identity cannot be navigated.
        cards[card["slug"]] = card
    if slug not in cards:
        return unavailable
    ordered = sorted(cards.values(), key=lambda card: week_order(card["edition"]))
    index = next(i for i, card in enumerate(ordered) if card["slug"] == slug)

    def link(card):
        edition = card["edition"]
        label = NflWeek(
            edition["season"], edition["week"], edition["stage"]
        ).display_name
        return {
            "slug": card["slug"],
            "label": label,
            "edition": edition,
            "destination": card["destination"],
        }

    return {
        "slug": slug,
        "state": "available",
        "previous": link(ordered[index - 1]) if index else None,
        "next": link(ordered[index + 1]) if index + 1 < len(ordered) else None,
    }


async def read_week_navigation(session, slug):
    identity = edition_for_slug(slug)
    if not identity or identity.get("kind") != "nfl_week":
        return {"slug": slug, "state": "not_applicable", "previous": None, "next": None}
    if not (await correction_schema_present(session)).columns:
        return {"slug": slug, "state": "unavailable", "previous": None, "next": None}
    slugs = [
        NflWeek(identity["season"], week, stage).slug
        for stage in STAGES
        for week in range(1, MAX_WEEK + 1)
    ]
    # One bounded aggregate with the existing published, top-level, live-member
    # eligibility and canonical destination. No hydration or provider calls.
    sql = _discovery_sql(
        by_slug=True, by_prefix=False, by_season=False, by_events=False
    )
    raw = (
        await session.execute(
            text(sql),
            {
                "slugs": slugs,
                "slug_pattern": r"^nfl-[0-9]{4}-(preseason-|postseason-)?week-[0-9]{1,2}$",
                "limit": MAX_EDITIONS + 1,
            },
        )
    ).fetchall()
    return select_navigation(slug, [dict(zip(_COLUMNS, row)) for row in raw])
