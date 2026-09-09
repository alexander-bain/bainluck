"""#4441 — a league hub must not caption itself with a season that has ended.

Seven leagues (`bundesliga`, `champions-league`, `epl`, `la-liga`, `nba`, `nfl`,
`nhl`) never overrode `LeagueConfig.season_pattern`, so they sat on the field
default `"2025-26"` and served it to readers on the day before the 2026 NFL
season's Week 1 — while the four European leagues among them were already a
month into 2026-27. Confirmed reader-visible, not inferred from config:
`GET /api/playoffs/{slug}` served `name: "NFL Playoffs 2025-26"` and
`season: "2025-26"` for nfl, epl and nba.

The guards here are deliberately CLOCK-FREE (gotcha #44: a test anchor that
branches on the clock is not an anchor). Neither asks "what season is it now?",
which is exactly the question a config cannot answer about itself. They ask two
questions a config CAN answer, and both have real failure modes:

  * `test_two_year_season_leagues_agree` — the tell that found this bug. Leagues
    whose season is written `YYYY-YY` all roll over together in the summer, so on
    any given day they are all in the same season. `ncaa-football` reading
    `2026-27` while `nfl` read `2025-26` could not both be right, and it is the
    disagreement — not the value — that proves one of them is stale. This is the
    RED-FIRST guard: it fails on the unfixed config.

  * `test_name_and_season_pattern_agree` — `season_pattern` is not the only place
    the season is written; it is also baked into the reader-facing `name`
    ("NFL Playoffs 2025-26"), and both are served. This guard passes before the
    fix and exists to catch the HALF-fix, where someone moves the pattern and
    leaves the name behind. Without it the hub would still say "2025-26".
"""

from __future__ import annotations

import re

import pytest

from app.config.league_configs import LEAGUE_CONFIGS

#: A season written as `YYYY-YY` — the two-calendar-year leagues.
TWO_YEAR_SEASON = re.compile(r"^(\d{4})-(\d{2})$")

#: A season written as a single `YYYY` — leagues played inside one calendar year.
ONE_YEAR_SEASON = re.compile(r"^\d{4}$")


def _two_year_leagues() -> dict[str, str]:
    return {
        slug: cfg.season_pattern
        for slug, cfg in LEAGUE_CONFIGS.items()
        if TWO_YEAR_SEASON.match(cfg.season_pattern or "")
    }


def test_every_season_pattern_is_a_shape_we_recognise() -> None:
    """A season we cannot parse is a season we cannot check — fail loudly.

    Guards the two tests below against silently skipping a league whose pattern
    stopped matching either shape (an empty string would slip past both).
    """
    unparseable = {
        slug: cfg.season_pattern
        for slug, cfg in LEAGUE_CONFIGS.items()
        if not (
            TWO_YEAR_SEASON.match(cfg.season_pattern or "")
            or ONE_YEAR_SEASON.match(cfg.season_pattern or "")
        )
    }
    assert not unparseable, (
        "these leagues have a season_pattern that is neither YYYY nor YYYY-YY, "
        f"so the season guards below cannot see them: {unparseable}"
    )


def test_two_year_season_leagues_agree() -> None:
    """All `YYYY-YY` leagues are in the same season on the same day.

    RED-FIRST: on the unfixed config this fails with
    `{'2025-26': [...7 leagues...], '2026-27': ['ncaa-football']}`.

    NBA/NHL run Oct-Jun, the NFL Sep-Feb, the European leagues Aug-May and
    college football Aug-Jan. The spans differ but the LABEL rolls over for all
    of them in the summer, so two of them carrying different `YYYY-YY` strings
    means one was updated and the others were forgotten.
    """
    by_season: dict[str, list[str]] = {}
    for slug, season in sorted(_two_year_leagues().items()):
        by_season.setdefault(season, []).append(slug)

    assert len(by_season) == 1, (
        "two-calendar-year leagues disagree about which season it is, so at "
        "least one hub is captioned with a season that has ended: "
        f"{ {s: v for s, v in sorted(by_season.items())} }"
    )


@pytest.mark.parametrize("slug", sorted(LEAGUE_CONFIGS))
def test_name_and_season_pattern_agree(slug: str) -> None:
    """The season baked into the reader-facing `name` matches `season_pattern`.

    `GET /api/playoffs/{slug}` serves BOTH (`name` and `season`), so a fix that
    moves only the pattern leaves the hub still reading "NFL Playoffs 2025-26".
    Only names that actually carry a year token are checked — a league whose
    name is seasonless is fine.
    """
    cfg = LEAGUE_CONFIGS[slug]
    name = cfg.name or ""
    carried = re.search(r"\b(\d{4}(?:-\d{2})?)\b", name)
    if carried is None:
        pytest.skip(f"{slug} does not put a season in its name")

    assert carried.group(1) == cfg.season_pattern, (
        f"{slug} serves name={name!r} and season={cfg.season_pattern!r} on the "
        "same payload, so a reader sees two different seasons for one hub"
    )
