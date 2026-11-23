"""settled_hero — a finished game's hero resolves to the result, not to the last
price anyone happened to capture.

Standing ruling: *settled means settled* — heroes show winners. Today they do not.
The hero is whatever the blend last said, frozen at whenever capture stopped, so a
game that turned late publishes the losing team as the favorite. Measured through
the real route on production 2026-08-29 over a 44-event hash-sampled cohort of
settled decisive games:

    loser published as the favorite      5 / 44   (11.4%)
    reached a terminal 1.0 / 0.0         0 / 42

All five were verified against ESPN before any code was written, because a wrong
hero and a wrong *score* look identical from inside the API:

    Villanova 32 - William & Mary 35   hero(Villanova) 0.8199   ESPN: W&M won
    Panthers 16 - Texans 13            hero(Panthers)  0.4859   ESPN: Panthers won
    Watford 1 - Peterborough 5         hero(Watford)   0.6492   ESPN: Peterborough won
    Criciuma 0 - Fortaleza 2           hero(Criciuma)  0.6845   ESPN: Fortaleza won
    Sarmiento 2 - Estudiantes 0        hero(Sarmiento) 0.4533   ESPN: Sarmiento won

WHY ``completed`` AND NOT ``closed`` — the load-bearing decision in this module, and
the one place #1495's own acceptance criterion is wrong. Criterion 1 asks for
``status in (completed, closed)``. Honouring that would publish confident wrong
winners. ``closed`` scores are frequently a frozen MID-GAME snapshot that never took
its final value. Sampled 2026-08-29, ``closed`` + ``completed_at IS NOT NULL`` +
decisive, checked against ESPN:

    ours: Angels 3 - Phillies 1        ESPN: Angels 3 - Phillies 5    winner INVERTED
    ours: Giants 3 - Reds 0            ESPN: Giants 9 - Reds 10       winner INVERTED
    ours: Giants 5 - D-backs 6         ESPN: Giants 6 - D-backs 10    frozen, direction held
    ours: Athletics 0 - Orioles 2      ESPN: Athletics 3 - Orioles 4  frozen, direction held

Two of eight sampled rows would have crowned the team that lost, at 100%, in the
page title and the link preview. That is strictly worse than the stale probability
this module exists to replace: a stale number is wrong and looks uncertain, a
resolved number is wrong and looks authoritative. So the gate is ``completed``.
The same game often exists as BOTH a ``closed`` row with the frozen score and a
``completed`` row with the real one (15290828 vs 15293666 — the duplicate class of
#2263), which is why the narrow gate loses much less than it appears to.

``completed_at`` is required as well: it is the timestamp the completion path
writes, so its absence means nothing ever declared this game over.

PURE: no I/O, no DB, no clock. Display-only — this module never writes a score or a
probability back to the database (gotcha #21, and the same shape as
``_apply_settled_crown`` on the soccer side).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

__all__ = [
    "FINAL_UNRESOLVED_SOURCE",
    "FINISHED_STATUSES",
    "RESOLVABLE_STATUSES",
    "SETTLED_HERO_SOURCE",
    "SettledCurrentChance",
    "SettledHero",
    "apply_settled_current_odds",
    "is_finished_status",
    "resolve_settled_hero",
    "settled_current_chance",
]

#: The ONLY status whose score is trusted enough to crown a winner. See the module
#: docstring for the ESPN-verified reason ``closed`` is absent — it is a measurement,
#: not a preference, and widening this set needs a fresh one.
RESOLVABLE_STATUSES: frozenset[str] = frozenset({"completed"})

#: The value written to ``hero_probability_source``. Deliberately a NEW word rather
#: than reusing "blend": every read site that means "a live blended price" gates on
#: the literal string "blend", so reusing it would let a resolved result be labelled
#: "Live · Bain Luck blend" on a finished game.
SETTLED_HERO_SOURCE = "settled"

#: Every status that means the game is over, which is DELIBERATELY WIDER than
#: ``RESOLVABLE_STATUSES`` above.
#:
#: The asymmetry is the whole design. ``closed`` is not trustworthy enough to crown a
#: winner FROM THE SCORE — that is what the docstring's ESPN sample measures — but it
#: is more than trustworthy enough to know we must stop advertising a live forecast.
#: Trusting a status to WITHHOLD a claim is safe in a way trusting it to MAKE one is
#: not, so the two sets are separate and neither may be quietly widened into the other.
FINISHED_STATUSES: frozenset[str] = frozenset({"completed", "closed"})

#: The source written when the game is over and nothing resolved a winner.
#:
#: CERT-1938: leaving these rows labelled "blend" is what let ``/events/15293846``
#: publish "Bain Luck gives Matteo Berrettini a 84% win probability" six days after he
#: had won the match 7-6, 7-6, 6-0. The number itself is unchanged and still served —
#: this is a claim about what it MEANS, and "the last price before capture stopped" is
#: not a live blend. A reader that gates on "blend" now correctly declines it.
FINAL_UNRESOLVED_SOURCE = "final_unresolved"


def is_finished_status(status: Any) -> bool:
    """Is this game over? Tolerant of the same casing/whitespace as the gate above."""
    return isinstance(status, str) and status.strip().lower() in FINISHED_STATUSES


@dataclass(frozen=True)
class SettledHero:
    """A resolved terminal hero. ``result`` is from the HOME team's point of view."""

    home_probability: float
    away_probability: float
    result: str  # "home" | "away" | "draw"

    @property
    def source(self) -> str:
        return SETTLED_HERO_SOURCE


def _as_number(value: Any) -> Optional[float]:
    """Scores arrive as int, Decimal or str depending on the ingest. Anything that
    is not cleanly numeric is treated as absent rather than coerced — a score we
    cannot read is not a score we may crown a winner from."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def resolve_settled_hero(
    *,
    status: Any,
    home_score: Any,
    away_score: Any,
    completed_at: Any,
) -> Optional[SettledHero]:
    """Return the terminal hero for a trustworthily-settled event, else ``None``.

    ``None`` means "do not resolve" and leaves the caller's existing behaviour
    untouched — this function can only ever ADD a resolution, never suppress one.

    A draw resolves to 0.5/0.5 with ``result="draw"``. That is not the indeterminate
    0.5 the issue flags: it is carried by ``source="settled"`` plus an explicit
    ``result``, so a client can tell "nobody won" from "we do not know", which is
    exactly the distinction a bare 0.5 on a finished game destroys (#1495 criterion 4).
    """
    if not isinstance(status, str) or status.strip().lower() not in RESOLVABLE_STATUSES:
        return None
    if completed_at is None:
        return None

    home = _as_number(home_score)
    away = _as_number(away_score)
    if home is None or away is None:
        return None

    if home > away:
        return SettledHero(home_probability=1.0, away_probability=0.0, result="home")
    if away > home:
        return SettledHero(home_probability=0.0, away_probability=1.0, result="away")
    return SettledHero(home_probability=0.5, away_probability=0.5, result="draw")


@dataclass(frozen=True)
class SettledCurrentChance:
    """Resolved current-chance fields for a finished game (#13172 Option B).

    - ``settled`` decisive (home won): ``1.0 / 0.0`` (``100 / 0``), plus
      ``draw=0.0`` (``0``) on draw-priced sports.
    - ``settled`` decisive (away won): ``0.0 / 1.0`` (``0 / 100``), plus
      ``draw=0.0`` (``0``) on draw-priced sports.
    - ``settled`` draw on a draw-priced sport (soccer): ``0.0 / 0.0 / draw=1.0``
      (``0 / 0 / 100``) — never 50 and 50.
    - ``settled`` draw on a two-way sport (e.g. NFL tie): ``0.5 / 0.5``
      (``50 / 50``), ``draw=None``.
    - ``final_unresolved`` / ``None`` (finished without a verified result):
      all fields ``None`` — never the last live price.
    """

    home_probability: Optional[float]
    away_probability: Optional[float]
    draw_probability: Optional[float]
    home_rendered_percent: Optional[int]
    away_rendered_percent: Optional[int]
    draw_rendered_percent: Optional[int]
    resolved: bool


def settled_current_chance(
    hero: Any,
    *,
    sport_key: Any = None,
) -> SettledCurrentChance:
    """Derive current-chance values for a finished game from ``resolve_hero``.

    Caller gates on ``is_finished_status(served_status)``; live, scheduled,
    suspended, and postponed games never call this helper.
    """
    from app.utils.draw_priced_winner import sport_prices_a_draw

    if hero is None or getattr(hero, "source", None) != SETTLED_HERO_SOURCE:
        return SettledCurrentChance(
            home_probability=None,
            away_probability=None,
            draw_probability=None,
            home_rendered_percent=None,
            away_rendered_percent=None,
            draw_rendered_percent=None,
            resolved=False,
        )

    draw_priced = sport_prices_a_draw(sport_key)
    result = getattr(hero, "settled_result", None) or getattr(hero, "result", None)

    if result == "draw":
        if draw_priced:
            return SettledCurrentChance(
                home_probability=0.0,
                away_probability=0.0,
                draw_probability=1.0,
                home_rendered_percent=0,
                away_rendered_percent=0,
                draw_rendered_percent=100,
                resolved=True,
            )
        return SettledCurrentChance(
            home_probability=0.5,
            away_probability=0.5,
            draw_probability=None,
            home_rendered_percent=50,
            away_rendered_percent=50,
            draw_rendered_percent=None,
            resolved=True,
        )

    if result == "home" or (result is None and getattr(hero, "home_probability", None) == 1.0):
        return SettledCurrentChance(
            home_probability=1.0,
            away_probability=0.0,
            draw_probability=0.0 if draw_priced else None,
            home_rendered_percent=100,
            away_rendered_percent=0,
            draw_rendered_percent=0 if draw_priced else None,
            resolved=True,
        )

    return SettledCurrentChance(
        home_probability=0.0,
        away_probability=1.0,
        draw_probability=0.0 if draw_priced else None,
        home_rendered_percent=0,
        away_rendered_percent=100,
        draw_rendered_percent=0 if draw_priced else None,
        resolved=True,
    )


def apply_settled_current_odds(
    current_odds: Optional[dict[str, Any]],
    hero: Any,
    *,
    sport_key: Any = None,
    include_rendered: bool = True,
    fallback_metadata: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Overlay settled/unresolved current-chance fields onto ``current_odds``.

    Preserves every non-chance metadata field (``spread``, ``over_under``,
    ``bookmaker_count``, ``captured_at``, ``projected_*``, etc.) on an
    existing ``current_odds`` dict. When no dict existed yet, creates one for
    a resolved result and returns ``None`` for ``final_unresolved``.
    """
    from app.utils.draw_priced_winner import sport_prices_a_draw

    sc = settled_current_chance(hero, sport_key=sport_key)
    draw_priced = sport_prices_a_draw(sport_key)

    if current_odds is None:
        if not sc.resolved:
            return None
        out: dict[str, Any] = dict(fallback_metadata or {})
        out["home_probability"] = sc.home_probability
        out["away_probability"] = sc.away_probability
        if include_rendered:
            out["home_rendered_percent"] = sc.home_rendered_percent
            out["away_rendered_percent"] = sc.away_rendered_percent
        if draw_priced:
            out["draw_probability"] = sc.draw_probability
            if include_rendered:
                out["draw_rendered_percent"] = sc.draw_rendered_percent
        return out

    out = dict(current_odds)
    out["home_probability"] = sc.home_probability
    out["away_probability"] = sc.away_probability
    if include_rendered or "home_rendered_percent" in out or "away_rendered_percent" in out:
        out["home_rendered_percent"] = sc.home_rendered_percent
        out["away_rendered_percent"] = sc.away_rendered_percent
    if draw_priced:
        out["draw_probability"] = sc.draw_probability
        if include_rendered or "draw_rendered_percent" in out:
            out["draw_rendered_percent"] = sc.draw_rendered_percent
    return out
