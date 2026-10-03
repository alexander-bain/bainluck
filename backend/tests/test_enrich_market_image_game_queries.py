"""#10326 — a head-to-head game is illustrated with its sport, never its team names.

The specimen: futures_markets 61040985 "Packers vs. Lions" (polymarket, open,
`llm_sport_category='football'`, `event_id` 14780566), stored with pexels photo
32775211 — "Close-up of an African lioness in a wildlife reserve". Measured against
the live Pexels API on 2026-10-03, the query the deployed picker would build today,
"Packers Lions football", returns that same lioness first: the #4962 category
qualifier does not outweigh a team nickname that is also an animal.

`enrich_market_images` selects `image_url IS NULL`, so these assertions describe
what future picks ask for; rows that already hold a picture are not revisited.
"""

import contextlib

import pytest

from app.tasks import enrich_markets
from app.tasks.enrich_markets import _GAME_SPORT_QUERIES, _image_query_candidates


class TestAGameAsksForItsSport:
    def test_the_filed_specimen_asks_for_american_football_not_lions(self):
        assert _image_query_candidates("Packers vs. Lions", "football") == [
            "american football game"
        ], "this is the #10326 specimen, which came back a lioness"

    @pytest.mark.parametrize(
        "name",
        [
            "Bears vs. Eagles",  # five bald eagles, measured
            "Dolphins vs Rams",  # four dolphins, measured
            "Jaguars @ Colts",
            "Ravens v Broncos",
        ],
    )
    def test_no_team_name_reaches_pexels(self, name):
        (query,) = _image_query_candidates(name, "football")
        for team in name.replace("@", " ").replace(".", " ").split():
            if team.lower() in {"vs", "v"}:
                continue
            assert (
                team.lower() not in query.lower()
            ), f"{team!r} reached Pexels: {query!r}"

    def test_a_linked_row_whose_name_has_no_separator_still_asks_for_its_sport(self):
        # A prop on the game ("Lions to win by 7+") names one team and no "vs";
        # its `event_id` is what says it belongs to a game.
        assert _image_query_candidates(
            "Lions to win by 7+", "football", linked_to_game=True
        ) == ["american football game"]

    @pytest.mark.parametrize(
        "category, name",
        [
            ("soccer", "Arsenal vs. Chelsea"),
            ("basketball", "Bulls vs. Hornets"),
            ("baseball", "Cubs vs. Tigers"),
            ("hockey", "Penguins vs. Sharks"),
            ("tennis", "Sinner vs Alcaraz"),
            ("mma", "Jones vs. Aspinall"),
            ("boxing", "Canelo vs. Crawford"),
            ("esports", "CS: NaVi vs Legacy (BO3)"),
            ("cricket", "India vs. Australia"),
        ],
    )
    def test_every_listed_sport_asks_its_own_measured_phrase(self, category, name):
        assert _image_query_candidates(name, category) == [
            _GAME_SPORT_QUERIES[category]
        ]

    def test_the_category_token_is_matched_case_and_space_insensitively(self):
        assert _image_query_candidates("Packers vs. Lions", " Football ") == [
            "american football game"
        ]


class TestEverythingElseIsUnchanged:
    """The sport query takes over ONLY for a game in a listed sport."""

    def test_an_unlinked_sports_future_keeps_the_4962_queries(self):
        assert _image_query_candidates("Presidents Cup Winner", "golf") == [
            "Presidents Cup golf",
            "Presidents Cup",
        ]
        assert _image_query_candidates("Super Bowl Champion", "football") == [
            "Super Bowl Champion football",
            "Super Bowl Champion",
        ]

    def test_a_non_sport_head_to_head_keeps_the_name_query(self):
        # Politics "A vs. B" is not a game; its names are the subject.
        assert _image_query_candidates("Trump vs. Newsom 2028", "politics") == [
            "Trump Newsom politics",
            "Trump Newsom",
        ]

    def test_a_game_in_an_unlisted_sport_keeps_the_name_query(self):
        name = "PPA - Men's Doubles: Mackinnon / French vs Joseph"
        assert _image_query_candidates(name, "pickleball")[0].endswith("pickleball")

    def test_a_game_with_no_category_keeps_the_name_query(self):
        assert _image_query_candidates(
            "Packers vs. Lions", None, linked_to_game=True
        ) == ["Packers Lions"]

    def test_a_word_containing_v_is_not_a_separator(self):
        # "Vikings" / "Ravens" start or contain v; only a standalone token splits.
        assert _image_query_candidates("Vikings Super Bowl odds", "football") == [
            "Vikings Super Bowl odds football",
            "Vikings Super Bowl odds",
        ]


# ---------------------------------------------------------------------------
# The PASS: `enrich_market_images` must hand the row's event_id to the picker.
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self._selected = False

    async def execute(self, statement):
        if not self._selected:
            self._selected = True
            return _FakeResult(self._rows)
        return None

    async def commit(self):
        return None


@pytest.fixture
def asked(monkeypatch):
    monkeypatch.setattr(enrich_markets, "PEXELS_API_KEY", "test-key")

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(enrich_markets.asyncio, "sleep", _no_sleep)
    queries: list[str] = []

    def _arm(rows):
        session = _FakeSession(rows)

        @contextlib.asynccontextmanager
        async def _session(*_args, **_kwargs):
            yield session

        monkeypatch.setattr(enrich_markets, "get_task_session", _session)

        async def _fetch(query):
            queries.append(query)
            return None

        monkeypatch.setattr(enrich_markets, "_fetch_pexels_image", _fetch)
        return queries

    return _arm


@pytest.mark.asyncio
async def test_the_pass_reads_event_id_as_the_game_signal(asked):
    queries = asked([(61040985, "Lions to win by 7+", "football", 14780566)])

    await enrich_markets.enrich_market_images(limit=10)

    assert queries == ["american football game"]


@pytest.mark.asyncio
async def test_a_game_that_finds_nothing_falls_back_to_no_picture_not_the_team_names(
    asked,
):
    # A missing picture beats a lioness; the row stays NULL for the next pass.
    queries = asked([(61040985, "Packers vs. Lions", "football", None)])

    stats = await enrich_markets.enrich_market_images(limit=10)

    assert queries == ["american football game"]
    assert stats["requests"] == 1 and stats["found"] == 0


def test_the_select_carries_event_id():
    import inspect

    source = inspect.getsource(enrich_markets.enrich_market_images)
    assert "FuturesMarket.event_id" in source
