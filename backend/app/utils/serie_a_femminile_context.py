"""Require women's Serie A evidence before offering season/series context (#10319).

The event's clubs are not competition evidence: Parma also names a men's club.
This admission rule is deliberately confined to the new, exact competition key.
Other leagues retain their existing queries, and linked game props retain their
event-id authority. Unknown season context may be absent rather than misleading.
"""

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.sql.elements import ColumnElement

SPORT_KEY = "soccer_italy_serie_a_women"
_GENERIC_KEYS = ("soccer", "soccer_other")
_OWN_NAME = (
    r"(\yserie a femminile\y|\ywomen'?s serie a\y|"
    r"\yserie a[[:space:]]+\(?women\)?\y)"
)


def admission_condition(sport_key: str | None) -> ColumnElement[bool] | None:
    """Return a complete SQL admission fence, or no change for another league.

    Positive evidence is an exact Sport key, retained Kalshi product competition,
    or an unambiguous women's Serie A title. Conflicting identifiers/gender or a
    bare men's/ambiguous Serie A title refuse even when another signal matches.
    The predicate belongs before candidate limits and on the series query too.
    """
    if sport_key != SPORT_KEY:
        return None

    from app.models.models import FuturesMarket, Sport

    name = func.coalesce(FuturesMarket.name, "")
    own_name = name.op("~*")(_OWN_NAME)
    competition = func.lower(
        func.btrim(
            func.coalesce(
                FuturesMarket.market_metadata["competition"].astext,
                "",
            )
        )
    )
    own_competition = competition == "serie a femminile"
    own_sport = FuturesMarket.sport_id.in_(
        select(Sport.id).where(Sport.key == SPORT_KEY)
    )
    compatible_sport = or_(
        FuturesMarket.sport_id.is_(None),
        FuturesMarket.sport_id.in_(
            select(Sport.id).where(Sport.key.in_((*_GENERIC_KEYS, SPORT_KEY)))
        ),
    )
    gender = func.lower(func.btrim(func.coalesce(FuturesMarket.llm_gender, "")))
    conflicting_name = or_(
        and_(name.op("~*")(r"\yserie a\y"), not_(own_name)),
        name.op("~*")(r"\ymen('s)?\y"),
    )
    return and_(
        or_(own_sport, own_competition, own_name),
        compatible_sport,
        or_(competition == "", own_competition),
        gender.in_(("", "women")),
        not_(conflicting_name),
    )
