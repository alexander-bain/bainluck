"""F1 — `canonical_market_key` is a CATEGORY, and a category cannot delete a row.

LAT-P086, Fable directive 2026-08-24 item 1 (pasted and reviewed by Alex).
This is the SECOND site of the defect ruled at `events.py:101-157` under
LAT-P038/#1769; that fix removed the canonical short-circuit from search's
dedup key and is pinned by `test_search_futures_dedup_identity.py`. The league
page kept its own copy of the same mistake, in a worse form: it does not merely
*rank* by the key, it **deletes siblings** by it (``seen_canonical`` in
``build_league``).

`compute_canonical_market_key` builds ``{sport}:{league}:{category}:{season}``.
Nothing in that string names a market.

**A correction the directive's census earns, stated rather than absorbed.**
The named JAY-Z / Bieber rows (ids 13792932, 13791149, 22915647, 20271688,
8430959) are all **`market_tier = 2`**, and `_assign_section` routes tiers 1, 2
and 4 to ``championship``, which ``continue``s into ``championship_census``
*before* this dedup block. Those five rows therefore never reach the league
page's dedup at all. They are a real specimen of the same defect, but its home
is ``GET /api/futures/compare`` — measured live on 2026-08-24, HTTP 200 in
0.60 s and 61 KB:

    GET /api/futures/compare?key=entertainment::game_prop:2026
      source_markets ............ 449   (423 distinct names)
      sum of member outcomes .... 890
      outcomes RETURNED .......... 10

Fifteen of the named rows are in there — "Will Jay Z release an album in 2026?",
"Will Justin Bieber perform at the 2026 Todo Mundo no Rio music festival?",
"Taylor Swift pregnant by March 31?", "Trump declassifies new UFO files by
December 31?" — merged into ONE comparison whose ten outcomes read "Yellow
Submarine", "Dune: Part Three", "Avengers: Doomsday", "August 31", "Yes", "No".
That route is DELETED by this queue (Alex ruled removal, zero consumers in both
trees), so its specimen is pinned by ``test_futures_compare_removed.py`` instead
of here. Captured payload: ``docs/audits/latency/lat-p086-compare-specimen.json``.

**The league page's own specimen is EPL, and it is bigger.** Production
2026-08-24, the route's exact 200-row pool query via the read-only `db-query`
rail, counting only rows that actually reach the dedup (tier not in 1/2/4):

    pool rows ........................... 200
    rows reaching the dedup ............. 168
    of those, carrying a canonical key ... 80
    distinct canonical keys among them .... 8
    rows DELETED by the canonical dedup ... 72

One key, ``soccer:EPL:championship:2026-27``, holds **23** of them — "EPL
Playmaker Award", "EPL: Next Chelsea Manager?", "Egypt Premier League: 2026-27
Runner-Up", "Ukrainian Premier League: 3rd Place Finish 2026-27", "English
Premier League: Top Goalscorer 2026-27", "Premier League: Teams relegated
(2026-27)". Twenty-two of the twenty-three are deleted so the twenty-third can
render. They are not duplicates of each other in any sense; they are not even
about the same league.

That 23 is the count *within the route's 200-row pool*, which is where the
deletion is observable. The full open population under the same key is **29**
dedup-eligible rows (1 at tier 3, 28 at tier 5), re-measured the same day, and
the whole corpus collapses **13,789 keyed dedup-eligible open rows onto 241
keys** — 13,548 deleted, 13,303 of them distinct names, with a single key
(``soccer::championship:2026``, the league-less slot) holding 8,749. The corpus
figure is the identity's failure rate, not any one page's loss: `build_league`
only ever dedups within the league it was asked for. See
``docs/audits/latency/lat-p086-f1-canonical-key-contamination.md``.

**And the deletion crosses sections.** That key spans tier 3 and tier 5, so it
covers both ``awards`` ("EPL Playmaker Award", tier 3) and the tier-5 rows. The
pool is ordered ``market_tier ASC``, so the award is seen first and appended to
``awards``; the first richer tier-5 row then runs
``sections[old_section] = [... if m["canonical_market_key"] != ck]`` and removes
it. A manager market deletes an award.

**The deletion is invisible to the census.** `section_counts` comes from the
tier resolver, which runs over `sections` *after* this loop, and `total` is
``shown + resolved_skipped``. Canonically-deleted rows are subtracted before
anything counts them, so the envelope reports a denominator that is too small.
Ruling 025 clause 3 forbids exactly that.

Both directions are asserted here (gotcha #43): the genuine cross-source
duplicate — one question written twice by two sources — must STILL collapse to
one row, or this fix would trade a deletion bug for a duplication bug.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.routes import league_futures as lf


# ---------------------------------------------------------------------------
# Fakes — the same shape the route's other seeded tests use
# ---------------------------------------------------------------------------


def _outcome(oid: int, name: str, prob: float, rank: int = 1):
    return SimpleNamespace(
        id=oid,
        name=name,
        current_probability=prob,
        opening_probability=None,
        probability_change_24h=0,
        rank=rank,
        team_id=None,
    )


def _market(
    *,
    market_id: int,
    name: str,
    canonical_market_key: str | None,
    market_tier: int | None,
    source: str = "polymarket",
    external_id: str | None = None,
    llm_sport_category: str = "soccer",
    llm_league: str | None = "epl",
    category: str = "other",
    n_outcomes: int = 2,
):
    """A market row.

    `market_tier` is REQUIRED and has no default on purpose. Tiers 1, 2 and 4
    are routed to ``championship`` and consumed by ``championship_census``
    before the dedup runs, so a specimen built at those tiers exercises none of
    this and renders nothing — which is how the first draft of this file came
    out 7/7 red for the wrong reason.
    """
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=market_id,
        name=name,
        source=source,
        external_id=external_id or f"EXT-{market_id}",
        category=category,
        llm_sport_category=llm_sport_category,
        llm_league=llm_league,
        market_tier=market_tier,
        status="open",
        event_id=None,
        outcomes=[
            # Deliberately mid-band probabilities: the two price-based skips in
            # `build_league` drop leaders >=97% and all-settled ladders, and a
            # specimen that vanished down THOSE paths would prove nothing about
            # this one.
            _outcome(market_id * 100 + i, f"Outcome {i}", 0.60 - 0.05 * i, rank=i + 1)
            for i in range(n_outcomes)
        ],
        resolution_date=now + timedelta(days=90),
        canonical_market_key=canonical_market_key,
        group_id=None,
    )


def _scalars_result(items):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    scalars.unique.return_value = scalars
    result.scalars.return_value = scalars
    return result


def _serve_pool(mock_db, items):
    """Answer the futures-pool query with `items` and everything after it empty.

    ``build_league`` runs the upcoming-games and recent-results rails after the
    pool query. A single `return_value` hands those rails these market rows as
    if they were events, and `_event_probability` then raises
    ``AttributeError: win_probability_sources`` forty times into the captured
    log — noise that buries the one assertion that matters.
    """
    pool, empty = _scalars_result(list(items)), _scalars_result([])
    calls = {"n": 0}

    def _execute(*_args, **_kwargs):
        calls["n"] += 1
        return pool if calls["n"] == 1 else empty

    mock_db.execute.side_effect = _execute


def _rendered_names(body: dict) -> set[str]:
    return {row["name"] for rows in body.get("sections", {}).values() for row in rows}


def _section_of(body: dict, name: str) -> str | None:
    for section, rows in body.get("sections", {}).items():
        for row in rows:
            if row["name"] == name:
                return section
    return None


# ---------------------------------------------------------------------------
# The named specimen — soccer:EPL:championship:2026-27, real production rows
# ---------------------------------------------------------------------------

#: Verified on production 2026-08-24 (`status='open'`, `event_id IS NULL`).
#: ids, tiers, sources, names and outcome counts are all real, and all six sit
#: under the SAME `canonical_market_key`. Ordered as the route's own
#: `market_tier ASC NULLS LAST` returns them.
EPL_SPECIMEN = [
    _market(
        market_id=59164820,
        name="EPL Playmaker Award",
        canonical_market_key="soccer:EPL:championship:2026-27",
        market_tier=3,
        source="kalshi",
        external_id="KXEPLPLAYMAKER-27",
        n_outcomes=1,
    ),
    _market(
        market_id=12727863,
        name="EPL: Next Chelsea Manager?",
        canonical_market_key="soccer:EPL:championship:2026-27",
        market_tier=5,
        n_outcomes=10,
    ),
    _market(
        market_id=58904929,
        name="Egypt Premier League: 2026-27 Runner-Up",
        canonical_market_key="soccer:EPL:championship:2026-27",
        market_tier=5,
        n_outcomes=2,
    ),
    _market(
        market_id=59156924,
        name="English Premier League: Top Goalscorer 2026-27",
        canonical_market_key="soccer:EPL:championship:2026-27",
        market_tier=5,
        n_outcomes=1,
    ),
    _market(
        market_id=59516454,
        name="Ukrainian Premier League: 3rd Place Finish 2026-27",
        canonical_market_key="soccer:EPL:championship:2026-27",
        market_tier=5,
        n_outcomes=3,
    ),
    _market(
        market_id=59516509,
        name="Premier League: Teams relegated (2026-27)",
        canonical_market_key="soccer:EPL:championship:2026-27",
        market_tier=5,
        n_outcomes=4,
    ),
]


class TestEplSpecimen:
    """Six unrelated live markets, one canonical key, one page."""

    async def test_every_genuine_member_renders(self, client, mock_db):
        _serve_pool(mock_db, list(EPL_SPECIMEN))

        resp = await client.get("/api/leagues/soccer_epl")
        assert resp.status_code == 200
        body = resp.json()

        names = _rendered_names(body)
        for m in EPL_SPECIMEN:
            assert m.name in names, (
                f"{m.name!r} was deleted by a sibling sharing "
                f"{m.canonical_market_key!r} — a category is not an identity"
            )

    async def test_the_award_is_not_deleted_by_a_manager_market(
        self, client, mock_db
    ):
        """The cross-section form, at its tightest: two rows, nothing else.

        "EPL Playmaker Award" is tier 3 → ``awards``. "EPL: Next Chelsea
        Manager?" is tier 5 and richer, so under the old rule it replaced the
        award and the removal filter reached into ``awards`` to delete it.
        """
        pair = [
            m
            for m in EPL_SPECIMEN
            if m.name in ("EPL Playmaker Award", "EPL: Next Chelsea Manager?")
        ]
        assert len(pair) == 2
        _serve_pool(mock_db, pair)

        resp = await client.get("/api/leagues/soccer_epl")
        body = resp.json()
        assert _rendered_names(body) == {
            "EPL Playmaker Award",
            "EPL: Next Chelsea Manager?",
        }
        assert _section_of(body, "EPL Playmaker Award") == "awards"

    async def test_the_denominator_counts_what_renders(self, client, mock_db):
        """Ruling 025 clause 3 — no silent subtraction before the count."""
        _serve_pool(mock_db, list(EPL_SPECIMEN))

        body = (await client.get("/api/leagues/soccer_epl")).json()
        rendered = sum(len(rows) for rows in body.get("sections", {}).values())
        assert rendered == len(EPL_SPECIMEN)
        assert body["total_markets"] == len(EPL_SPECIMEN)


class TestTierOneTwoFourNeverReachTheDedup:
    """Scope statement, so nobody reads this fix as covering the grid.

    The JAY-Z / Bieber rows are tier 2. They are counted by
    ``championship_census`` and rendered by the championship grid, not as
    cards, and they never enter ``build_league``'s dedup in either the old or
    the new form. This test exists to keep that true — if section routing ever
    lets tier 1/2/4 through, the dedup's blast radius changes and this file's
    specimens stop covering it.
    """

    async def test_tier_two_rows_are_census_only(self, client, mock_db):
        rows = [
            _market(
                market_id=13792932,
                name="Will Jay Z release an album in 2026?",
                canonical_market_key="entertainment::game_prop:2026",
                market_tier=2,
                llm_sport_category="soccer",
            ),
            _market(
                market_id=13791149,
                name="Taylor Swift pregnant by March 31?",
                canonical_market_key="entertainment::game_prop:2026",
                market_tier=2,
                llm_sport_category="soccer",
            ),
        ]
        _serve_pool(mock_db, rows)

        body = (await client.get("/api/leagues/soccer_epl")).json()
        assert _rendered_names(body) == set(), (
            "tier 1/2/4 is the grid's family; if these now render as cards the "
            "dedup's scope changed and this file needs new specimens"
        )


# ---------------------------------------------------------------------------
# The other direction (gotcha #43) — a real duplicate must still collapse
# ---------------------------------------------------------------------------


class TestGenuineDuplicateStillCollapses:
    """One question, two sources, two spellings — still ONE row.

    Tier 3 rather than tier 1: a tier-1 champion market is grid family and
    never reaches this code (see the class above). The pair below is the exact
    shape `events.py`'s docstring records as the only thing the deleted
    canonical arm was merging — "NBA: 2027 Champion" vs "NBA Championship
    Winner" — recovered there by `_fold_dedup_punctuation`, and it must be
    recovered here by the same function for the same reason.
    """

    def _pair(self):
        return [
            _market(
                market_id=701,
                name="NBA Championship Winner",
                canonical_market_key="basketball:NBA:championship:2026",
                market_tier=3,
                source="kalshi",
                llm_sport_category="basketball",
                llm_league="nba",
                external_id="KXNBA-CHAMP",
                n_outcomes=2,
            ),
            _market(
                market_id=702,
                name="2026 NBA Champion",
                canonical_market_key="basketball:NBA:championship:2026",
                market_tier=3,
                source="polymarket",
                llm_sport_category="basketball",
                llm_league="nba",
                external_id="POLY-NBA-CHAMP",
                n_outcomes=4,
            ),
        ]

    async def test_cross_source_duplicate_collapses_to_one(self, client, mock_db):
        _serve_pool(mock_db, self._pair())

        body = (await client.get("/api/leagues/basketball_nba")).json()
        assert body["total_markets"] == 1, (
            "the same question written by two sources must still merge — "
            "this fix removes a wrong identity, it does not remove dedup"
        )
        # And the survivor is the richer row, unchanged policy.
        assert _rendered_names(body) == {"2026 NBA Champion"}

    async def test_survivor_removal_does_not_take_innocent_rows(
        self, client, mock_db
    ):
        """The old removal filtered a whole section by canonical key.

        ``sections[old] = [m for m in sections[old]
        if m["canonical_market_key"] != ck]`` deletes EVERY row carrying that
        key, not the one being replaced. With 23 rows under one key that was
        only invisible because the dedup had already stopped 22 of them from
        being appended. The moment the key stops being the identity, that line
        becomes an indiscriminate delete — so it must key on the ROW.
        """
        rows = self._pair()
        rows.insert(
            1,
            _market(
                market_id=703,
                name="NBA Coach of the Year",
                canonical_market_key="basketball:NBA:championship:2026",
                market_tier=3,
                source="kalshi",
                llm_sport_category="basketball",
                llm_league="nba",
                external_id="KXNBA-COY",
                n_outcomes=3,
            ),
        )
        _serve_pool(mock_db, rows)

        names = _rendered_names((await client.get("/api/leagues/basketball_nba")).json())
        assert "NBA Coach of the Year" in names, (
            "an unrelated row sharing the category was collateral damage"
        )
        assert "2026 NBA Champion" in names
        assert "NBA Championship Winner" not in names


# ---------------------------------------------------------------------------
# Source guard — the short-circuit must not come back
# ---------------------------------------------------------------------------


BUILD_SRC = inspect.getsource(lf.build_league)
BUILD_CODE = "\n".join(
    line for line in BUILD_SRC.splitlines() if not line.lstrip().startswith("#")
)


def test_build_league_does_not_dedup_on_canonical_market_key():
    """`canonical_market_key` may be SERIALIZED; it may not decide survival."""
    assert "seen_canonical" not in BUILD_CODE, (
        "the canonical-keyed dedup map is back in build_league"
    )
    for forbidden in ("seen_canonical[", "in seen_canonical"):
        assert forbidden not in BUILD_CODE, forbidden


def test_build_league_uses_the_shared_name_key():
    """One implementation, not a second copy (doctrine clause 5)."""
    assert "_normalize_futures_dedup_key" in BUILD_CODE, (
        "the league page must consume the events-route dedup key, not "
        "re-implement one"
    )
