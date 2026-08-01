"""Queue #296 — a grid-register cell is "settled" only on real authority.

Queue 295 derived a cell's settled/live state straight off the column::

    settled = outcome.is_winner is not None or market.status == "resolved"

which reads ``is_winner`` as if the column implied a settlement. It does not —
it implies only that *something wrote a value*, and #845 exists precisely
because ~30 ad-hoc phases write that column with wildly different standing.

Q296's Item 0 census measured the cost. All 61 outcomes of the two LIVE "MLB
World Series Champion 2026" markets (ids 1 and 114584) carried
``is_winner=False`` with ``resolution_source=NULL`` on ``status='open'`` —
authority tier -1, a grade nothing was entitled to write. Under the old rule
every one of those cells published as ``settled``/``eliminated``, which would
have rendered all 30 MLB teams eliminated from a season still being played.
Across the four fixed-roster leagues that was 289 of 847 outcomes.

That is the specific failure the register was built to prevent: a *wrong* entry
on the serving path is worse than a missing one, because ``missing`` renders an
honest empty cell while a fabricated "eliminated" looks like a real result.

The rule is now the ladder's own predicate, ``can_write_winner`` — not a second
copy of the policy that could drift from it. These tests pin both directions:
the poison class must NOT settle, and the authoritative classes must still
settle (including gotcha #33's Kalshi markets that settle but stay 'open').
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import grid_register_source as grs


def _market(mid=1, status="open", source="polymarket", name="MLB World Series Champion 2026"):
    return SimpleNamespace(
        id=mid, status=status, source=source, name=name,
        external_id=f"ext-{mid}",
    )


def _outcome(oid=10, market_id=1, name="Atlanta Braves", is_winner=None, resolution_source=None):
    return SimpleNamespace(
        id=oid, market_id=market_id, name=name,
        is_winner=is_winner, resolution_source=resolution_source,
    )


async def _run(market, outcome):
    """Drive build_candidates over exactly one market/outcome pair."""
    config = SimpleNamespace(slug="mlb", season_pattern="2026")
    entities = {"atlanta braves": ("atlanta braves", "Atlanta Braves")}

    scalars = SimpleNamespace(all=lambda: [outcome])
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(scalars=lambda: scalars))

    with patch.object(
        grs, "load_candidate_markets", AsyncMock(return_value=[(market, "championship")])
    ), patch.object(grs, "canonical_entities", AsyncMock(return_value=entities)):
        return await grs.build_candidates(session, config)


class TestSettledRequiresAuthority:
    @pytest.mark.asyncio
    async def test_unattributed_grade_on_open_market_stays_live(self):
        """The exact production regression: MLB 2026, is_winner=False, no source."""
        candidates, unresolved = await _run(
            _market(status="open"),
            _outcome(is_winner=False, resolution_source=None),
        )

        assert len(candidates) == 1
        assert candidates[0]["status"] == "live"
        assert candidates[0]["terminal_result"] is None
        assert unresolved == []

    @pytest.mark.asyncio
    async def test_guess_family_grade_on_open_market_stays_live(self):
        """Tier-0 poison (#754) must never promote a live cell to eliminated."""
        candidates, _ = await _run(
            _market(status="open"),
            _outcome(is_winner=False, resolution_source="pass2_guess"),
        )

        assert candidates[0]["status"] == "live"
        assert candidates[0]["terminal_result"] is None

    @pytest.mark.asyncio
    async def test_authoritative_settlement_on_open_market_settles(self):
        """Gotcha #33: Kalshi settles but the row stays status='open'.

        api_settlement is tier 3 and self-justifying, so these must STILL read as
        settled — the fix must not over-correct into calling real results live.
        """
        candidates, _ = await _run(
            _market(status="open", source="kalshi"),
            _outcome(is_winner=False, resolution_source="api_settlement"),
        )

        assert candidates[0]["status"] == "settled"
        assert candidates[0]["terminal_result"] == "eliminated"

    @pytest.mark.asyncio
    async def test_authoritative_winner_on_open_market_settles_as_won(self):
        candidates, _ = await _run(
            _market(status="open", source="kalshi"),
            _outcome(is_winner=True, resolution_source="api_settlement"),
        )

        assert candidates[0]["status"] == "settled"
        assert candidates[0]["terminal_result"] == "won"

    @pytest.mark.asyncio
    async def test_resolved_market_settles_on_any_classified_grade(self):
        """A resolved market is settled ground: clean_resolution (tier 1) counts."""
        candidates, _ = await _run(
            _market(status="resolved"),
            _outcome(is_winner=True, resolution_source="clean_resolution"),
        )

        assert candidates[0]["status"] == "settled"
        assert candidates[0]["terminal_result"] == "won"

    @pytest.mark.asyncio
    async def test_ungraded_outcome_on_open_market_is_live(self):
        candidates, unresolved = await _run(
            _market(status="open"),
            _outcome(is_winner=None, resolution_source=None),
        )

        assert candidates[0]["status"] == "live"
        assert unresolved == []

    @pytest.mark.asyncio
    async def test_ungraded_outcome_on_resolved_market_is_unresolved_not_eliminated(self):
        """Q295 called this settled and then, because is_winner was falsy, wrote
        terminal_result='eliminated' — inventing a result for a cell nobody
        graded. It has no honest status, so it is reported, not published."""
        candidates, unresolved = await _run(
            _market(status="resolved"),
            _outcome(is_winner=None, resolution_source=None),
        )

        assert candidates == []
        assert len(unresolved) == 1
        assert unresolved[0]["reason"] == "settled_market_ungraded"
        assert unresolved[0]["market_id"] == 1
        assert unresolved[0]["outcome_id"] == 10

    @pytest.mark.asyncio
    async def test_unresolved_rows_never_become_register_entries(self):
        """Ambiguity must not leak into the published file through this path."""
        from app.services.grid_register_source import candidates_to_register

        config = SimpleNamespace(slug="mlb", season_pattern="2026")
        candidates, unresolved = await _run(
            _market(status="resolved"),
            _outcome(is_winner=None, resolution_source=None),
        )
        register, ambiguities = candidates_to_register(candidates, unresolved, config)

        assert register["entries"] == []
        assert [a["reason"] for a in ambiguities] == ["settled_market_ungraded"]
