"""#8440 — the two halves of the venue-name-extension test fold names the same way.

The stored side is folded in SQL with ``translate(lower(name), _FOLD_FROM,
_FOLD_TO)``; the venue side in Python with :func:`fold_team_name`. If the two
ever disagree on a letter, "Assat Pori" stops reaching our "Ässät" — silently,
because a miss just mints a second row. The real-Postgres half is
``tests/integration/test_pm_venue_name_extension_8440_pg.py``.
"""

from types import SimpleNamespace

import pytest

from app.tasks.prediction_market_matching import (
    _FOLD_FROM,
    _FOLD_TO,
    _venue_name_extension_candidates,
    fold_team_name,
)


def test_translate_map_is_one_to_one_and_agrees_with_the_python_fold():
    assert len(_FOLD_FROM) == len(_FOLD_TO)
    for src, dst in zip(_FOLD_FROM, _FOLD_TO):
        assert len(dst) == 1 and dst.isascii(), src
        assert fold_team_name(src) == dst


@pytest.mark.parametrize(
    "venue, folded",
    [
        ("Assat Pori", "assat pori"),
        ("Ässät", "assat"),
        ("Málaga  CF", "malaga cf"),
        ("Kärpät Oulu", "karpat oulu"),
        (None, ""),
    ],
)
def test_fold_team_name(venue, folded):
    assert fold_team_name(venue) == folded


class _NoQuery:
    async def execute(self, statement):  # pragma: no cover - must not be reached
        raise AssertionError("the extension pass queried for a market it must skip")


def _market(source="polymarket", venue_start="2026-09-24T15:30:00+00:00"):
    meta = {} if venue_start is None else {"venue_game_start": venue_start}
    return SimpleNamespace(source=source, market_metadata=meta)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "market, team_b",
    [
        (_market(source="kalshi"), "Tappara Tampere"),
        (_market(venue_start=None), "Tappara Tampere"),
        (_market(), None),
    ],
    ids=["not-polymarket", "no-venue-stamp", "one-sided"],
)
async def test_the_pass_never_queries_outside_its_scope(market, team_b):
    matchup = SimpleNamespace(team_a="Lukko Rauma", team_b=team_b)
    assert await _venue_name_extension_candidates(_NoQuery(), matchup, market, None) == []
