"""#4962 — the enrichment PASS spends the candidate queries, and its quota.

`_image_query_candidates` decides WHAT to ask Pexels; this file is about what
`enrich_market_images` actually does with the list. Three things have to hold,
and none of them is visible from the pure function:

1. the category-qualified query goes first, and the bare one is only reached
   when the qualified one found nothing — a row can gain a picture, never lose
   one;
2. a row costs at most two requests, never a retry loop;
3. a PASS costs at most `limit` requests. The beat asks for `limit=200` six
   times a day against Pexels' 200 req/hr, so a fallback that spent a second
   request per row unchecked would double a pass into the quota wall. A row the
   budget runs out on keeps `image_url IS NULL` and is the next pass's first
   row — the select is ordered by `volume_24h desc`.

The fake session is deliberately dumb: the task's first `execute` is its SELECT
and every later one is an UPDATE it wrote. Nothing here touches a database.
"""

import contextlib

import pytest

from app.tasks import enrich_markets


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self._selected = False
        self.updates = 0
        self.committed = False

    async def execute(self, statement):
        if not self._selected:
            self._selected = True
            return _FakeResult(self._rows)
        self.updates += 1
        return None

    async def commit(self):
        self.committed = True


@pytest.fixture
def rig(monkeypatch):
    """Arm the task with a fake session, a real key and no inter-row sleep."""
    monkeypatch.setattr(enrich_markets, "PEXELS_API_KEY", "test-key")

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(enrich_markets.asyncio, "sleep", _no_sleep)

    def _arm(rows, answer):
        session = _FakeSession(rows)

        @contextlib.asynccontextmanager
        async def _session(*_args, **_kwargs):
            yield session

        monkeypatch.setattr(enrich_markets, "get_task_session", _session)

        asked: list[str] = []

        async def _fetch(query):
            asked.append(query)
            return answer(query)

        monkeypatch.setattr(enrich_markets, "_fetch_pexels_image", _fetch)
        return session, asked

    return _arm


PHOTO = ("https://images.pexels.com/photos/1/a.jpeg?auto=compress&w=1200", 1200, 800)

#: The cert's own specimen: "Presidents Cup Winner", `llm_sport_category='golf'`.
PRESIDENTS_CUP = (109001, "Presidents Cup Winner", "golf")


@pytest.mark.asyncio
async def test_the_qualified_query_goes_first_and_the_bare_one_is_never_asked(rig):
    session, asked = rig([PRESIDENTS_CUP], lambda _q: PHOTO)

    stats = await enrich_markets.enrich_market_images(limit=10)

    assert asked == ["Presidents Cup golf"], (
        "the category-qualified query must be the one that fetched the picture"
    )
    assert stats["found"] == 1 and stats["requests"] == 1
    assert session.updates == 1


@pytest.mark.asyncio
async def test_the_bare_query_is_the_fallback_when_the_qualified_one_finds_nothing(rig):
    _session, asked = rig(
        [PRESIDENTS_CUP],
        lambda q: None if q == "Presidents Cup golf" else PHOTO,
    )

    stats = await enrich_markets.enrich_market_images(limit=10)

    assert asked == ["Presidents Cup golf", "Presidents Cup"]
    assert stats["found"] == 1, "the row lost a picture it would have had before #4962"
    assert stats["requests"] == 2


@pytest.mark.asyncio
async def test_a_row_costs_at_most_two_requests_even_when_nothing_is_found(rig):
    _session, asked = rig([PRESIDENTS_CUP], lambda _q: None)

    stats = await enrich_markets.enrich_market_images(limit=10)

    assert len(asked) == 2
    assert stats["found"] == 0 and stats["errors"] == 1
    assert stats["fetched"] == 1, "`fetched` counts MARKETS; `requests` counts calls"


@pytest.mark.asyncio
async def test_a_row_with_no_category_signal_asks_exactly_once(rig):
    _session, asked = rig([(1, "Manchester United title", "other")], lambda _q: PHOTO)

    await enrich_markets.enrich_market_images(limit=10)

    assert asked == ["Manchester United title"]


@pytest.mark.asyncio
async def test_the_pass_never_spends_more_requests_than_its_limit(rig):
    # Four rows, every qualified query missing, so each row wants two requests.
    rows = [(i, f"Presidents Cup {i} Winner", "golf") for i in range(4)]
    _session, asked = rig(rows, lambda _q: None)

    stats = await enrich_markets.enrich_market_images(limit=3)

    assert len(asked) == 3, f"a pass with limit=3 issued {len(asked)} Pexels requests"
    assert stats["requests"] == 3


@pytest.mark.asyncio
async def test_the_budget_is_requests_not_rows_so_a_clean_pass_is_unchanged(rig):
    # Every qualified query hits: five rows, five requests — exactly what this
    # task spent for five rows before the fallback existed.
    rows = [(i, f"Team {i} championship", "soccer") for i in range(5)]
    session, asked = rig(rows, lambda _q: PHOTO)

    stats = await enrich_markets.enrich_market_images(limit=5)

    assert len(asked) == 5
    assert stats["requests"] == 5 and stats["found"] == 5
    assert session.updates == 5


@pytest.mark.asyncio
async def test_a_blank_query_row_is_skipped_without_spending_a_request(rig):
    _session, asked = rig([(1, "Will the A?", None), PRESIDENTS_CUP], lambda _q: PHOTO)

    await enrich_markets.enrich_market_images(limit=10)

    assert asked == ["Presidents Cup golf"]


# ---------------------------------------------------------------------------
# The D51 re-pick path's interlock (scripts/repair_4962_market_image_repick.py).
# ---------------------------------------------------------------------------


class TestTheRepickInterlock:
    """Clearing a picture is only a repair if the NEXT pick asks something else.

    The script refuses any row whose query the deployed code rebuilds
    identically — otherwise it deletes a photograph and re-fetches the same one.
    """

    @staticmethod
    def _script():
        import importlib.util
        import pathlib

        path = (
            pathlib.Path(__file__).resolve().parents[1]
            / "scripts"
            / "repair_4962_market_image_repick.py"
        )
        spec = importlib.util.spec_from_file_location("repair_4962", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_both_filed_rows_get_a_different_query(self):
        script = self._script()
        for name, category in [
            ("Presidents Cup Winner", "golf"),
            ("Will Taylor Swift meet with Pope Leo XIV before 2027?", "entertainment"),
        ]:
            old, new, changed = script.query_changed(name, category)
            assert changed, f"{name!r} would re-fetch the same photograph: {old!r}"
            assert old != new

    def test_the_legacy_extractor_reproduces_the_filed_defect(self):
        # The comparison is only worth anything if the "old" side is really the
        # query that fetched the Thunderbirds and the swimmer.
        script = self._script()
        assert script._legacy_image_keywords("Presidents Cup Winner", "golf") == "Presidents Cup"
        assert (
            script._legacy_image_keywords(
                "Will Taylor Swift meet with Pope Leo XIV before 2027?", "entertainment"
            )
            == "Will Taylor Swift meet"
        )

    def test_a_row_the_fix_does_not_move_is_reported_unchanged(self):
        # A name that reduces to its own category gains nothing and must not be
        # cleared.
        script = self._script()
        _old, _new, changed = script.query_changed("politics", "politics")
        assert changed is False

    def test_the_default_scope_is_exactly_the_two_filed_rows(self):
        script = self._script()
        assert script._parse_ids(None) == (16757297, 109295)
        assert script._parse_ids("1, 2 3") == (1, 2, 3)

    def test_the_producer_app_is_the_main_app_not_heavy(self):
        # `app.tasks.enrich_market_images` is not in HEAVY_TASKS, so the deploy
        # that will re-pick these rows is `bainluck`. If that ever changes, this
        # fails rather than the script silently gating on the wrong app.
        from app.tasks import HEAVY_TASKS

        script = self._script()
        assert "app.tasks.enrich_market_images" not in HEAVY_TASKS
        assert script.PRODUCER_APP == "bainluck"
