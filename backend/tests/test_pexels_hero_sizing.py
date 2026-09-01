"""The Discover hero stops downloading raster the card cannot show.

Measured on production `/api/feed?limit=40` (2026-09-01): 14 of 46 unique hero
images used #565's `src.large` preset (`h=650&w=940`, delivered ~926 px wide,
mean 68,173 B, one outlier at 150,354 B) while the card's `aspect-[16/10]` box
renders 300-360 CSS px -- 720 device px at DPR 2. Capping those 14 to the
measured raster took them from 954,434 B to 608,890 B.

The other 32 rows use the legacy `h=350` preset (~516 px). Upsizing those to
720 would have ADDED ~1 MB, so the cap must never touch them. Several tests
below exist only to pin that direction.
"""

from urllib.parse import parse_qs, urlsplit

from app.utils.pexels_sizing import (
    HERO_RASTER_H,
    HERO_RASTER_W,
    cap_pexels_url,
    is_oversized_pexels_url,
)

BASE = "https://images.pexels.com/photos/8846076/pexels-photo-8846076.jpeg"
LARGE = f"{BASE}?auto=compress&cs=tinysrgb&h=650&w=940"
MEDIUM = f"{BASE}?auto=compress&cs=tinysrgb&h=350"


def _params(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


class _FakeSession:
    """Enough session to exercise the drain loop's control flow.

    Deliberately does not interpret the SQLAlchemy statements -- the risk being
    pinned is the loop (budget, batch advance, non-advancing bail), not the SQL
    dialect. Selects are served from a shrinking pool, mirroring the real
    filter: a capped row stops matching `w=940`, so the window advances.
    """

    def __init__(self, oversized: int, decoys: int):
        # Rows the util will cap, plus rows that match the SQL prefilter but
        # that `cap_pexels_url` leaves alone (the non-advancing case).
        self.pool = [f"{BASE}?auto=compress&cs=tinysrgb&h=650&w=940" for _ in range(oversized)]
        # A substring match on the SQL `w=940` filter that carries no `w`/`h`
        # param at all, so the util declines it and the window cannot advance.
        self.decoys = [f"{BASE}?raw=940" for _ in range(decoys)]
        self.selects = 0
        self.commits = 0

    async def execute(self, stmt):
        from sqlalchemy.sql import Select

        if isinstance(stmt, Select):
            self.selects += 1
            limit = stmt._limit_clause.value
            rows = [(i, u) for i, u in enumerate(self.pool[:limit])]
            if len(rows) < limit:
                rows += [(10_000 + i, u) for i, u in enumerate(self.decoys[: limit - len(rows)])]
            return _FakeResult(rows)
        # An update: the row no longer matches the filter, so drop it.
        if self.pool:
            self.pool.pop(0)
        return None

    async def commit(self):
        self.commits += 1


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def _run_cap(oversized: int, limit: int, batch_size: int, decoys: int = 0):
    import asyncio
    import contextlib
    import app.tasks.enrich_markets as em

    session = _FakeSession(oversized, decoys)

    @contextlib.asynccontextmanager
    async def _fake_session_cm():
        yield session

    original = em.get_task_session
    em.get_task_session = _fake_session_cm
    try:
        stats = asyncio.run(
            em.cap_oversized_market_images(limit=limit, batch_size=batch_size)
        )
    finally:
        em.get_task_session = original
    return stats, session


class TestOversizedDetection:
    def test_the_large_preset_is_oversized(self):
        assert is_oversized_pexels_url(LARGE) is True

    def test_the_legacy_medium_preset_is_not_oversized(self):
        # ~516 px delivered, already under the 720 raster. Enlarging it would
        # cost bytes, so it must not read as oversized.
        assert is_oversized_pexels_url(MEDIUM) is False

    def test_width_at_exactly_the_raster_is_not_oversized(self):
        assert is_oversized_pexels_url(f"{BASE}?w={HERO_RASTER_W}") is False

    def test_a_bare_height_is_compared_in_width_units(self):
        # `src.medium` sets only `h`; h=650 implies ~1040 px wide at 16:10.
        assert is_oversized_pexels_url(f"{BASE}?h=650") is True
        assert is_oversized_pexels_url(f"{BASE}?h={HERO_RASTER_H}") is False

    def test_a_sizeless_or_foreign_url_is_never_oversized(self):
        assert is_oversized_pexels_url(BASE) is False
        assert is_oversized_pexels_url("https://image.tmdb.org/t/p/w1280/bd.jpg") is False
        assert is_oversized_pexels_url("") is False

    def test_a_malformed_size_does_not_raise(self):
        # A non-numeric or zero size is unreadable, not oversized -- rewriting
        # on a guess would be worse than leaving it alone.
        assert is_oversized_pexels_url(f"{BASE}?w=wide") is False
        assert is_oversized_pexels_url(f"{BASE}?w=0") is False

    def test_a_lookalike_host_is_not_treated_as_pexels(self):
        assert is_oversized_pexels_url("https://images.pexels.com.evil.test/x.jpg?w=940") is False


class TestCapping:
    def test_capping_pins_the_exact_measured_raster(self):
        params = _params(cap_pexels_url(LARGE))
        assert params["w"] == str(HERO_RASTER_W)
        assert params["h"] == str(HERO_RASTER_H)

    def test_fit_crop_is_set_because_a_bounding_box_undershoots(self):
        # Without `fit=crop` Pexels treats w/h as a bounding box and `h` binds
        # for tall photos, delivering 600-675 px -- under the 720 the slot
        # needs. Measured: 561,996 B but 6 of 14 images under-wide.
        assert _params(cap_pexels_url(LARGE))["fit"] == "crop"

    def test_compression_params_survive_the_cap(self):
        params = _params(cap_pexels_url(LARGE))
        assert params["auto"] == "compress"
        assert params["cs"] == "tinysrgb"

    def test_the_photo_itself_is_unchanged(self):
        assert urlsplit(cap_pexels_url(LARGE)).path == urlsplit(LARGE).path
        assert urlsplit(cap_pexels_url(LARGE)).hostname == "images.pexels.com"

    def test_the_cap_never_upsizes_the_legacy_preset(self):
        # The load-bearing direction test: 32 of 46 production rows are this
        # preset, and rewriting them to 720x450 would add ~1 MB to the feed.
        assert cap_pexels_url(MEDIUM) == MEDIUM

    def test_non_pexels_and_sizeless_urls_pass_through_untouched(self):
        tmdb = "https://image.tmdb.org/t/p/w1280/bd.jpg"
        assert cap_pexels_url(tmdb) == tmdb
        assert cap_pexels_url(BASE) == BASE

    def test_capping_is_idempotent(self):
        once = cap_pexels_url(LARGE)
        assert cap_pexels_url(once) == once

    def test_a_capped_url_is_no_longer_oversized(self):
        assert is_oversized_pexels_url(cap_pexels_url(LARGE)) is False


class TestEnricherWiring:
    def test_the_fetcher_caps_before_it_returns(self):
        # Pins the write path: new rows must never store the 940 px preset,
        # or the repair pass below would have to run forever.
        import asyncio
        import app.tasks.enrich_markets as em

        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "photos": [
                        {
                            "width": 4000,
                            "height": 2500,
                            "alt": "a",
                            "src": {"large": LARGE, "medium": MEDIUM},
                        }
                    ]
                }

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, *a, **k):
                return _Resp()

        original_key, original_client = em.PEXELS_API_KEY, em.httpx.AsyncClient
        em.PEXELS_API_KEY = "test-key"
        em.httpx.AsyncClient = lambda *a, **k: _Client()
        try:
            url = asyncio.run(em._fetch_pexels_image("anything"))
        finally:
            em.PEXELS_API_KEY, em.httpx.AsyncClient = original_key, original_client

        assert url is not None
        assert _params(url)["w"] == str(HERO_RASTER_W)
        assert "w=940" not in url

    def test_the_repair_pass_drains_in_committed_batches_and_respects_its_budget(self):
        # 98,984 oversized rows in production: the drain has to cross batches,
        # commit as it goes, and still stop at the per-run budget.
        stats, session = _run_cap(oversized=1200, limit=1000, batch_size=400)
        assert stats["capped"] == 1000
        assert stats["batches"] == 3
        assert session.commits == 3
        # 400 + 400 + 200 exhausts the budget exactly. The loop condition must
        # end it there; without it the window clamps to 0 and the drain spends
        # one more `LIMIT 0` round trip to discover it is done.
        assert session.selects == 3

    def test_the_repair_pass_stops_when_the_population_is_drained(self):
        stats, _ = _run_cap(oversized=150, limit=5000, batch_size=400)
        assert stats["capped"] == 150
        # Budget was 5000 but only 150 existed -- it must not keep scanning.
        assert stats["batches"] == 1

    def test_a_window_that_cannot_advance_bails_instead_of_spinning(self):
        # The dangerous case: rows match the SQL `w=940` prefilter but the
        # util judges none of them oversized, so capping them changes nothing
        # and the same window returns forever. Without the bail this loops
        # until the budget, re-reading identical rows.
        stats, session = _run_cap(oversized=0, decoys=50, limit=5000, batch_size=400)
        assert stats["capped"] == 0
        assert stats["batches"] == 1
        assert session.selects == 1, "must not re-query a window it cannot advance"

    def test_the_repair_pass_is_reachable_without_a_pexels_key(self):
        # It is a pure URL rewrite; gating it behind the key would strand every
        # oversized row on any deploy where the key is unset.
        import inspect
        import app.tasks.enrich_markets as em

        assert hasattr(em, "cap_oversized_market_images")
        source = inspect.getsource(em.enrich_market_images)
        cap_at = source.index("cap_oversized_market_images(")
        gate_at = source.index("PEXELS_API_KEY")
        assert cap_at < gate_at, "the cap must run before the API-key early return"
