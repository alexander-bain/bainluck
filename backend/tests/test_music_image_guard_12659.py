"""#12659: music/album/song/chart markets never wear TMDB film backdrops, and TVMaze CC BY-SA 4.0 posters enrich TV series."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks import enrich_tmdb
from app.utils.discover_image_policy import resolve_discover_market_image
from app.utils.futures_highlights import _CULTURAL_GRAVITY_T2
from app.utils.music_image_guard import (
    is_music_market_ineligible_for_tmdb,
    sanitize_market_image_fields,
    sanitize_market_image_url,
)

CENSUS_FALSE_POSITIVE_MUSIC_MARKETS = [
    '"FRESH" First Week Album Sales?',
    'Will "FRESH" first week sales be at least 60k?',
    'Will "FRESH" first week sales be at least 80k?',
    'Will "FRESH" first week sales be at least 100k?',
    'Will "FRESH" first week sales be at least 120k?',
    'Will "FRESH" first week sales be at least 140k?',
    'Will "FRESH" first week sales be at least 160k?',
    'Will "Stay" by The Kid LAROI (with Justin Bieber) be on the radio in GTA VI at launch?',
    'Will "God\'s Plan" by Drake be on the radio in GTA VI at launch?',
    'Will "Rockstar" by Post Malone, 21 Savage be on the radio in GTA VI at launch?',
    'Will "Blinding Lights" by The Weeknd be on the radio in GTA VI at launch?',
    'Will "As It Was" by Harry Styles be on the radio in GTA VI at launch?',
    'Will "Shape of You" by Ed Sheeran be on the radio in GTA VI at launch?',
    'Will "Mask Off" by Future be on the radio in GTA VI at launch?',
    'Will "Despacito" by Luis Fonsi, Daddy Yankee be on the radio in GTA VI at launch?',
    'Will "Look at Me!" by XXXTENTACION be on the radio in GTA VI at launch?',
    '"All I Want for Christmas Is You" · Billboard Hot 100 rank (Dec 19, 2026)',
    '"All I Want for Christmas Is You" · Billboard Hot 100 rank (Dec 26, 2026)',
    '"All I Want for Christmas Is You" · Billboard Hot 100 rank (Jan 2, 27)',
    'Will Taylor Swift release "Taylor Swift (Taylor\'s Version)" in 2026?',
    'Will "Empire State of Mind" be played at the 2027 Big Game halftime show?',
    'Will "99 Problems" be played at the 2027 Big Game halftime show?',
    'Will "Encore" be played at the 2027 Big Game halftime show?',
    'Will "Public Service Announcement" be played at the 2027 Big Game halftime show?',
    'Will "Run This Town" be played at the 2027 Big Game halftime show?',
    'Will "Crazy in Love" be played at the 2027 Big Game halftime show?',
    'Will "Holy Grail" be played at the 2027 Big Game halftime show?',
    'Will "Can I Get A..." be played at the 2027 Big Game halftime show?',
    'Will "Young Forever" be played at the 2027 Big Game halftime show?',
    'Will "Umbrella" be played at the 2027 Big Game halftime show?',
    'Will "Show Me What You Got" be played at the 2027 Big Game halftime show?',
    'Will "Apeshit" be played at the 2027 Big Game halftime show?',
]

GENUINE_FILM_AND_TV_MARKETS = [
    '"Ebenezer" Opening Weekend Box Office',
    '"How to Rob a Bank" Opening Weekend Box Office',
    '"Godzilla Minus Zero" 2nd Weekend Box Office',
    '"Ebenezer" Rotten Tomatoes Score?',
    'Will "Wicked: For Good" score at least 80 on the Rotten Tomatoes Tomatometer?',
    'Will "Michael" be nominated for Best Picture at the 99th Academy Awards?',
    'Will "Michael" make it into the IMDb Top 250?',
    'New "Stranger Things" episode released by December 31?',
    'Will "GTA VI" have a Metascore of at least 94?',
]


@pytest.mark.parametrize("name", CENSUS_FALSE_POSITIVE_MUSIC_MARKETS)
def test_every_census_music_market_is_blocked_from_tmdb(name: str) -> None:
    tmdb_url = "https://image.tmdb.org/t/p/w1280/xcSH4KdTxvVmLARyrEeZOYrHjGR.jpg"
    assert is_music_market_ineligible_for_tmdb(name) is True
    assert sanitize_market_image_url(tmdb_url, name) is None
    assert sanitize_market_image_fields(tmdb_url, 1280, 720, name) == (
        None,
        None,
        None,
    )


@pytest.mark.parametrize("name", GENUINE_FILM_AND_TV_MARKETS)
def test_genuine_film_and_tv_markets_keep_tmdb_art(name: str) -> None:
    tmdb_url = "https://image.tmdb.org/t/p/w1280/valid_backdrop.jpg"
    assert is_music_market_ineligible_for_tmdb(name) is False
    assert sanitize_market_image_url(tmdb_url, name) == tmdb_url
    assert sanitize_market_image_fields(tmdb_url, 1280, 720, name) == (
        tmdb_url,
        1280,
        720,
    )


def test_tvmaze_picker_enforces_kid_safe_horror_gate_and_cc_by_sa_attribution() -> None:
    # Non-horror TVMaze show returns CC BY-SA 4.0 portrait + source_page
    url, meta = enrich_tmdb._pick_tvmaze_image(
        {
            "id": 68407,
            "name": "Black Doves",
            "genres": ["Drama", "Thriller", "Espionage"],
            "url": "https://www.tvmaze.com/shows/68407/black-doves",
            "image": {
                "original": "https://static.tvmaze.com/uploads/images/original_untouched/642/1607270.jpg"
            },
        }
    )
    assert url == "https://static.tvmaze.com/uploads/images/original_untouched/642/1607270.jpg"
    assert meta is not None
    assert meta["license"] == "CC BY-SA 4.0"
    assert meta["source_page"] == "https://www.tvmaze.com/shows/68407/black-doves"

    # Horror TVMaze show (#7461) is refused
    h_url, h_meta = enrich_tmdb._pick_tvmaze_image(
        {
            "id": 2993,
            "name": "Stranger Things",
            "genres": ["Drama", "Horror", "Science-Fiction"],
            "url": "https://www.tvmaze.com/shows/2993/stranger-things",
            "image": {
                "original": "https://static.tvmaze.com/uploads/images/original_untouched/595/1489169.jpg"
            },
        }
    )
    assert h_url is None
    assert h_meta is None


def test_netflix_season_outcomes_resolve_verified_tvmaze_portraits_and_gravity() -> None:
    res = resolve_discover_market_image(
        name="What will be the top global Netflix show this week? (November 17)",
        category="entertainment",
        top_outcomes=[{"name": "Taken: Natalee Holloway: Season 1", "probability": 0.97}],
        image_url=None,
    )
    assert res["image_url"] == "https://static.tvmaze.com/uploads/images/original_untouched/649/1624431.jpg"
    assert res["image_presentation"] == "portrait"
    assert res["image_license"] == "CC BY-SA 4.0"
    assert res["image_source_page"] == "https://www.tvmaze.com/shows/95389/taken-natalee-holloway"

    res_bd = resolve_discover_market_image(
        name="What will be the #2 global Netflix show this week? (November 17)",
        category="entertainment",
        top_outcomes=[{"name": "Black Doves: Season 2", "probability": 0.42}],
        image_url=None,
    )
    assert res_bd["image_url"] == "https://static.tvmaze.com/uploads/images/original_untouched/642/1607270.jpg"
    assert res_bd["image_presentation"] == "portrait"

    assert _CULTURAL_GRAVITY_T2.search("What will be the top global Netflix show this week? (November 17)")
    assert _CULTURAL_GRAVITY_T2.search("What will be the top US Netflix movie this week? (November 17)")
    assert _CULTURAL_GRAVITY_T2.search('"Avengers: Doomsday" Opening Weekend Box Office')


@pytest.mark.asyncio
async def test_enrich_tmdb_clears_existing_music_false_positives_and_falls_back_to_tvmaze(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(enrich_tmdb, "TMDB_READ_TOKEN", "fake-token")

    existing_rows = [
        (
            68365223,
            '"FRESH" First Week Album Sales?',
            "https://image.tmdb.org/t/p/w1280/xcSH4KdTxvVmLARyrEeZOYrHjGR.jpg",
            {"tmdb": {"tmdb_id": 880841, "media_type": "movie", "title": "Fresh"}},
        ),
        (
            69847041,
            '"Ebenezer" Opening Weekend Box Office',
            "https://image.tmdb.org/t/p/w1280/ebenezer.jpg",
            {"tmdb": {"tmdb_id": 12345, "media_type": "movie", "title": "Ebenezer"}},
        ),
    ]
    candidate_rows = [
        (
            69855986,
            'Will "Umbrella" be played at the 2027 Big Game halftime show?',
            {},
        ),
        (
            70000001,
            'New "Black Doves" episode released by December 31?',
            {},
        ),
    ]

    executed_statements = []

    class _FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _FakeSession:
        def __init__(self):
            self._select_calls = 0
            self.committed = False

        async def execute(self, stmt):
            sql_str = str(stmt)
            if sql_str.lstrip().upper().startswith("SELECT"):
                self._select_calls += 1
                if self._select_calls == 1:
                    return _FakeResult(existing_rows)
                return _FakeResult(candidate_rows)
            executed_statements.append(stmt)
            return MagicMock()

        async def commit(self):
            self.committed = True

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    fake_session = _FakeSession()
    tmdb_mock = AsyncMock(return_value=(None, None))
    tvmaze_mock = AsyncMock(
        return_value=(
            "https://static.tvmaze.com/uploads/images/original_untouched/642/1607270.jpg",
            {
                "tvmaze_id": 68407,
                "name": "Black Doves",
                "license": "CC BY-SA 4.0",
                "source_page": "https://www.tvmaze.com/shows/68407/black-doves",
            },
        )
    )

    with (
        patch.object(enrich_tmdb, "get_task_session", return_value=fake_session),
        patch.object(enrich_tmdb, "_fetch_tmdb_image", tmdb_mock),
        patch.object(enrich_tmdb, "_fetch_tvmaze_image", tvmaze_mock),
        patch.object(enrich_tmdb.asyncio, "sleep", AsyncMock()),
    ):
        stats = await enrich_tmdb.enrich_tmdb_images(limit=10)

    assert stats["cleared_music_false_positives"] == 1
    assert stats["skipped_music"] == 1
    assert stats["checked"] == 1
    assert stats["found"] == 1
    assert stats["found_tvmaze"] == 1
    tvmaze_mock.assert_awaited_once_with("Black Doves")
    assert len(executed_statements) == 3
    assert fake_session.committed is True
