"""#6978 — the category hero counts what the page can REACH.

Production, 390px, read 2026-09-18 and re-measured 2026-09-20. `/economics`
said, twice:

    ● Economics markets · Live — 1,614 active markets
    1,614 economic prediction markets translated into plain probabilities.

and the page could reach 283 — its own nine section counts. On the 2026-09-20
bank the same two numbers were **1,732** and **352**. So the hero overstated by
**4.9x** and 1,380 of the markets it advertised were reachable from nowhere on
the page.

`/politics` contradicts itself in a single glance, because that page renders an
All chip beside the hero:

    hero:        6,965 markets · 2 sources
    All chip:    6,230

Both numbers came from the same route. The chip was right.

⚠️ AND THE WORD MAKES IT WORSE. The hero calls them "active". The rows it was
counting are the ones the route DROPPED — for reading settled
(`market_reads_settled`, gotcha #33: Kalshi leaves `status='open'` on a settled
market), for sitting past the stale cutoff, for being off-topic, or for being a
hard-excluded family (#7321). It advertised, as active, the markets it had just
refused for being decided.

═══ WHY THE OBVIOUS ONE-LINE FIX IS WRONG ON ONE OF THE TWO ROUTES ═══

#6978 proposed `total = sum(len(v) for v in themed.values())` for both routes —
count what survived the gate, the way `/entertainment` already does. On
`/politics` that is exactly right: every theme `_classify_theme` can return is
a served section, including the catch-all `other`, so the themed set and the
served sections are the same set, and the All chip sums precisely these.

On `/economics` it is **not**. That route's `_classify_theme` also always
returns a theme, worst case `"other"` — but `/economics` has no Other section.
Its `other` bucket is accepted by the loop and rendered by nothing. Measured on
the 2026-09-20 bank the gate drops only the `should_exclude_from_featured`
failures, so the one-liner would have moved that hero 1,732 -> ~1,700 and left
5x of the defect on the page while looking like a fix.

So the rule both routes now share is the stronger one, and it is stated in the
only place that knows the answer: **the hero is the sum of the sections the
payload actually serves.** `TestTheEconomicsCatchAllIsNotReachable` is the arm
that tells the two candidate fixes apart; without it this file passes on the
one that does not work.

═══ WHAT THIS FILE DELIBERATELY DOES NOT CLAIM ═══

`/entertainment` is out of scope and is NOT fixed here, and the reason is worth
writing down because #6978 records it as "NOT affected" and that is true only
of the defect this file repairs. Its `total` is already
`sum(len(v) for v in themed.values())` — the ACCEPTED set, so no dropped row is
counted and the word "active" is honest. But it serves counts for only three of
its buckets, so on the 2026-09-20 bank its hero read **925** against served
sections of **453** (music 254 + movies_tv 149 + tech_culture 50), with the
remaining buckets reaching the reader only through a 20-row `cultural_moments`
list that carries no count at all. That is a second, milder over-claim of a
different shape — it cannot be repaired by moving one line, because the honest
number does not exist in that payload yet. Filed separately; this file asserts
nothing about it rather than pinning it as correct.

═══ NON-VACUITY ═══

Every arm below runs on a fixture whose pre-gate pool and post-gate sections
DIFFER. An assertion that the hero equals the section sum cannot fail on a
fixture where nothing is dropped — `len(all_markets)` would satisfy it too —
so `TestTheFixtureActuallyDropsSomething` measures the gap first and fails if
it is zero. Gotcha #43's both-directions rule: the dropped rows go AND the
reachable rows stay counted.
"""

import ast
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes import economics as economics_module
from app.routes import politics as politics_module


# ---------------------------------------------------------------------------
# Mocks — the shared idiom from test_route_category_spotlight_featured_gate_uxp194
# ---------------------------------------------------------------------------


class _MockScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None

    def unique(self):
        return self


class _MockResult:
    def __init__(self, items):
        self._scalars = _MockScalars(items)

    def scalars(self):
        return self._scalars

    def all(self):
        return self._scalars.all()

    def first(self):
        return self._scalars.first()


def _market(
    *,
    market_id,
    name,
    category,
    source="kalshi",
    probability=0.35,
    external_id=None,
    settled=False,
    resolution_date=None,
):
    """A single-outcome market.

    ``settled=True`` is the gotcha #33 shape: ``status`` stays ``'open'`` while
    the leg carries a graded winner and a settlement source, which is the only
    thing `market_reads_settled` can see.
    """
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=external_id or f"mock{market_id}",
        source=source,
        category="news",
        llm_sport_category=category,
        outcomes=[
            SimpleNamespace(
                id=market_id * 10,
                name="Yes",
                current_probability=probability,
                probability_change_24h=0,
                rank=1,
                is_winner=True if settled else None,
                resolution_source="api_settlement" if settled else None,
            )
        ],
        market_metadata=({"shape": {"expected_winners": 1}} if settled else None),
        resolution_date=(
            resolution_date
            if resolution_date is not None
            else now + timedelta(days=30)
        ),
        updated_at=now,
        volume_24h=1000,
        image_url=None,
        hook_description=None,
        status="open",
    )


_LONG_AGO = datetime.now(timezone.utc) - timedelta(days=400)


def _politics_fixture():
    """Two markets the page renders, three it drops, one of each reason."""
    return [
        # REACHABLE — two different sections, so the sum is over more than one.
        _market(market_id=101, name="Will the Supreme Court hear the case?",
                category="politics"),
        _market(market_id=102, name="Who will be the 2028 Democratic nominee?",
                category="politics"),
        # DROPPED — settled at the venue while status stays 'open' (gotcha #33).
        _market(market_id=103, name="Who won the 2024 presidential election?",
                category="politics", settled=True),
        # DROPPED — past the stale cutoff.
        _market(market_id=104, name="Will the Senate confirm the nominee?",
                category="politics", resolution_date=_LONG_AGO),
        # DROPPED — off topic for this page.
        _market(market_id=105, name="Will the Lakers make the playoffs?",
                category="basketball_nba"),
    ]


def _economics_fixture():
    """Two markets the page renders, two it accepts into no section."""
    return [
        # REACHABLE — two different served sections.
        _market(market_id=201, name="Will the FOMC announce a rate cut in December?",
                category="economics"),
        _market(market_id=202, name="Will CPI inflation exceed 3% this year?",
                category="economics"),
        # ACCEPTED BY THE LOOP, SERVED BY NOTHING — the `other` catch-all.
        # This is the pair of rows that tells `sum(themed.values())` (wrong)
        # from `sum(section counts)` (right).
        _market(market_id=203, name="Will the widget index be published?",
                category="economics"),
        _market(market_id=204, name="Will the second widget index be published?",
                category="economics"),
    ]


PAGES = [
    pytest.param("/api/politics", _politics_fixture, id="politics"),
    pytest.param("/api/economics", _economics_fixture, id="economics"),
]


async def _payload(client, mock_db, path, markets):
    mock_db.execute.return_value = _MockResult(markets)
    resp = await client.get(path)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _section_sum(payload):
    return sum(t["count"] for t in payload["themes"].values())


# ============================================================================
# The ship
# ============================================================================


class TestTheHeroEqualsWhatThePageServes:
    @pytest.mark.parametrize("path,fixture", PAGES)
    async def test_total_markets_is_the_sum_of_the_served_sections(
        self, client, mock_db, path, fixture
    ):
        payload = await _payload(client, mock_db, path, fixture())
        assert payload["total_markets"] == _section_sum(payload), (
            f"{path} advertises {payload['total_markets']} markets while its "
            f"own sections reach {_section_sum(payload)} — the /politics All "
            "chip sums exactly these, so the hero and the chip must agree by "
            "construction (#6978)."
        )


class TestTheFixtureActuallyDropsSomething:
    """Without this, the arm above passes on `len(all_markets)` too."""

    @pytest.mark.parametrize("path,fixture", PAGES)
    async def test_the_pre_gate_pool_is_strictly_larger(
        self, client, mock_db, path, fixture
    ):
        markets = fixture()
        payload = await _payload(client, mock_db, path, markets)
        assert payload["total_markets"] < len(markets), (
            f"{path}'s fixture is not discriminating: the route reached "
            f"{payload['total_markets']} of {len(markets)} markets, so an "
            "assertion that the hero equals the section sum would also hold "
            "for the pre-gate pool this ship removed."
        )

    @pytest.mark.parametrize("path,fixture", PAGES)
    async def test_the_reachable_markets_are_still_counted(
        self, client, mock_db, path, fixture
    ):
        """The other direction (gotcha #43): the fix must not count nothing."""
        payload = await _payload(client, mock_db, path, fixture())
        assert payload["total_markets"] >= 2, (
            f"{path} reached {payload['total_markets']} markets; the fixture "
            "plants two in two different served sections and both must survive."
        )


# ============================================================================
# The arm that tells the two candidate fixes apart
# ============================================================================


class TestTheEconomicsCatchAllIsNotReachable:
    """`sum(len(v) for v in themed.values())` passes every arm above and fails here.

    `/economics` accepts an unclassifiable market into `themed["other"]` and
    then serves no Other section, so counting the themed set advertises a
    market the reader cannot get to. On the production bank that difference was
    ~1,300 markets — the whole defect.
    """

    async def test_an_unclassifiable_market_does_not_raise_the_hero(
        self, client, mock_db
    ):
        without = await _payload(
            client, mock_db, "/api/economics", _economics_fixture()[:2]
        )
        with_other = await _payload(
            client, mock_db, "/api/economics", _economics_fixture()
        )
        assert with_other["total_markets"] == without["total_markets"], (
            "two markets that classify to the `other` catch-all moved the "
            f"/economics hero from {without['total_markets']} to "
            f"{with_other['total_markets']}, but no section serves them — the "
            "hero is counting rows the reader cannot reach (#6978)."
        )

    async def test_control_a_classifiable_market_does_raise_it(
        self, client, mock_db
    ):
        """Without this the arm above would pass on a hero frozen at a constant."""
        base = _economics_fixture()[:2]
        plus = base + [
            _market(
                market_id=205,
                name="Will the unemployment rate fall below 4%?",
                category="economics",
            )
        ]
        without = await _payload(client, mock_db, "/api/economics", base)
        with_jobs = await _payload(client, mock_db, "/api/economics", plus)
        assert with_jobs["total_markets"] == without["total_markets"] + 1, (
            "a market that lands in the served `jobs` section must raise the "
            f"hero: {without['total_markets']} -> "
            f"{with_jobs['total_markets']}, expected "
            f"{without['total_markets'] + 1}."
        )


class TestASettledMarketIsNotAdvertisedAsActive:
    """The word in the hero is 'active'; `market_reads_settled` rows are not."""

    async def test_a_settled_politics_market_does_not_raise_the_hero(
        self, client, mock_db
    ):
        base = _politics_fixture()[:2]
        plus = base + [
            _market(
                market_id=106,
                name="Who won the 2020 presidential election?",
                category="politics",
                settled=True,
            )
        ]
        without = await _payload(client, mock_db, "/api/politics", base)
        with_settled = await _payload(client, mock_db, "/api/politics", plus)
        assert with_settled["total_markets"] == without["total_markets"], (
            "a market the route drops for reading SETTLED moved the hero from "
            f"{without['total_markets']} to {with_settled['total_markets']} — "
            "the page would be advertising a decided question as active."
        )


# ============================================================================
# Structural: the count is taken AFTER the sections, from the sections
# ============================================================================


class TestTheCountIsTakenFromTheSections:
    """The regression is one word wide, and re-introducing it is silent.

    `total = len(all_markets)` is a legal, passing-looking line that no
    behavioural test on a fixture without dropped rows can see. These arms read
    the source: the assignment must derive from `themes`, and it must sit below
    the statement that builds it.
    """

    ROUTES = [
        pytest.param(politics_module, "get_politics", id="politics"),
        pytest.param(economics_module, "get_economics", id="economics"),
    ]

    def _total_assignment(self, module, fn_name):
        src = inspect.getsource(getattr(module, fn_name))
        tree = ast.parse(ast.unparse(ast.parse(src)))
        fn = tree.body[0]
        found = []
        for i, node in enumerate(ast.walk(fn)):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "total" for t in node.targets
            ):
                found.append(node)
        assert found, f"{fn_name} has no `total = ...` assignment"
        assert len(found) == 1, (
            f"{fn_name} assigns `total` {len(found)} times; this guard reads "
            "one and would grade the wrong statement."
        )
        return found[0]

    @pytest.mark.parametrize("module,fn_name", ROUTES)
    def test_total_is_derived_from_themes(self, module, fn_name):
        node = self._total_assignment(module, fn_name)
        names = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
        assert "themes" in names, (
            f"{fn_name} computes its hero count from {sorted(names)} — it must "
            "read `themes`, the served sections, so a new gate above the loop "
            "cannot silently reopen the gap (#6978)."
        )
        assert "all_markets" not in names, (
            f"{fn_name} computes its hero count from `all_markets`, the "
            "PRE-GATE pool. That is the defect #6978 repaired."
        )

    @pytest.mark.parametrize("module,fn_name", ROUTES)
    def test_the_assignment_sits_below_the_sections_it_reads(
        self, module, fn_name
    ):
        """Positional, because `themes` must exist before it is summed.

        A move above the `themes = {...}` statement is a NameError at request
        time, not a wrong number — but it is the mutation an editor makes when
        tidying, so it is pinned rather than left to production.
        """
        src = inspect.getsource(getattr(module, fn_name))
        fn = ast.parse(ast.unparse(ast.parse(src))).body[0]
        themes_at = None
        total_at = None
        for i, stmt in enumerate(fn.body):
            if isinstance(stmt, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "themes" for t in stmt.targets
            ):
                themes_at = i
            if isinstance(stmt, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "total" for t in stmt.targets
            ):
                total_at = i
        assert themes_at is not None, f"{fn_name} has no top-level `themes = ...`"
        assert total_at is not None, f"{fn_name} has no top-level `total = ...`"
        assert total_at > themes_at, (
            f"{fn_name} assigns `total` at statement {total_at}, above the "
            f"`themes` it must sum at {themes_at}."
        )
