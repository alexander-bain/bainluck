"""Queue #296 — the read-only grid-register proposal rail.

Register files are committed to the repo, but they can only be *generated*
against production inventory: there is no local DATABASE_URL, which is exactly
why Queue 295 shipped ``scripts/generate_grid_register.py`` with no register
beside it. Without a rail, the only ways to see a proposal were a one-off dyno
whose stdout is unreliable in the sandbox (gotcha #48) and whose filesystem is
thrown away, or hand-rolled SQL that would re-implement the matcher — i.e. the
guessing the register exists to abolish.

So the rail's contract is narrow and worth pinning:

* it reuses the SAME ``generate_register`` the generator and the daily sentinel
  share, so a proposal can never disagree with what the sentinel later diffs;
* it is strictly read-only — no register file, no market write (gotcha #21);
* a proposal that fails validation is returned WITH its findings and
  ``publishable: false``. Returning a bad register as if it were committable is
  the one failure that would put a wrong entry on the serving path, which is
  worse than a missing one because ``missing`` renders an honest empty cell.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException


def _register(entries, league="nba", season="2025-26"):
    return {
        "schema_version": "grid-register/v1",
        "league": league,
        "season": season,
        "version": 1,
        "generated_at": "2026-08-01T15:00:00+00:00",
        "entries": entries,
    }


def _entry(stage="championship", entity_key="oklahoma city thunder", source="kalshi", status="live"):
    entry = {
        "stage": stage,
        "entity_key": entity_key,
        "entity_name": "Oklahoma City Thunder",
        "source": source,
        "status": status,
        "market_id": 4242,
        "outcome_id": 9001,
        "external_id": "KXNBA-26-OKC",
        "evidence": {
            "kind": "generated_from_source_inventory",
            "observed_at": "2026-08-01T15:00:00+00:00",
            "market_name": "NBA Championship 2025-26",
        },
    }
    if status == "settled":
        entry["terminal_result"] = "won"
    return entry


class TestGridRegisterProposalRail:
    @pytest.mark.asyncio
    async def test_unknown_league_is_a_404_listing_valid_slugs(self):
        """A typo'd slug must fail loudly, not fall through to an empty register.

        An empty proposal for ``nba2`` looks exactly like a league with no
        inventory — silently publishable, and wrong.
        """
        from app.routes.admin import get_grid_register_proposal

        with patch("app.routes.admin._check_admin_secret"):
            with pytest.raises(HTTPException) as exc:
                await get_grid_register_proposal(
                    request=None, league="nba2", secret="s", db=AsyncMock()
                )

        assert exc.value.status_code == 404
        assert "nba2" in str(exc.value.detail)
        assert "nba" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_clean_proposal_is_publishable_with_counts_and_reasons(self):
        from app.routes.admin import get_grid_register_proposal

        register = _register([_entry(), _entry(entity_key="denver nuggets", status="settled")])
        unresolved = [
            {"reason": "entity_unresolved", "stage": "championship"},
            {"reason": "multiple_candidates", "stage": "division"},
            {"reason": "entity_unresolved", "stage": "conference"},
        ]

        with patch("app.routes.admin._check_admin_secret"), patch(
            "app.services.grid_register_source.generate_register",
            AsyncMock(return_value=(register, unresolved)),
        ), patch("app.utils.grid_register.validate_register", return_value=[]):
            result = await get_grid_register_proposal(
                request=None, league="nba", secret="s", db=AsyncMock()
            )

        assert result["league"] == "nba"
        assert result["season"] == "2025-26"
        assert result["entries_total"] == 2
        assert result["status_counts"] == {"live": 1, "settled": 1}
        assert result["unresolved_total"] == 3
        assert result["unresolved_reasons"] == {"entity_unresolved": 2, "multiple_candidates": 1}
        assert result["findings"] == []
        assert result["publishable"] is True
        assert result["register"] == register
        # The unresolved rows travel with the proposal — they are the review queue.
        assert result["unresolved"] == unresolved

    @pytest.mark.asyncio
    async def test_invalid_register_is_returned_but_never_publishable(self):
        """The guard that keeps a wrong entry off the serving path."""
        from app.routes.admin import get_grid_register_proposal

        register = _register([_entry(stage="not_a_stage")])

        with patch("app.routes.admin._check_admin_secret"), patch(
            "app.services.grid_register_source.generate_register",
            AsyncMock(return_value=(register, [])),
        ), patch(
            "app.utils.grid_register.validate_register",
            return_value=["entry 0: unknown stage 'not_a_stage'"],
        ):
            result = await get_grid_register_proposal(
                request=None, league="nba", secret="s", db=AsyncMock()
            )

        assert result["publishable"] is False
        assert result["findings"] == ["entry 0: unknown stage 'not_a_stage'"]
        # Still returned, so the reviewer can see WHAT is malformed.
        assert result["register"] == register

    @pytest.mark.asyncio
    async def test_include_entries_false_drops_the_body_but_keeps_the_census(self):
        from app.routes.admin import get_grid_register_proposal

        register = _register([_entry()])

        with patch("app.routes.admin._check_admin_secret"), patch(
            "app.services.grid_register_source.generate_register",
            AsyncMock(return_value=(register, [])),
        ), patch("app.utils.grid_register.validate_register", return_value=[]):
            result = await get_grid_register_proposal(
                request=None, league="nba", secret="s", db=AsyncMock(),
                include_entries=False,
            )

        assert result["register"] is None
        assert result["entries_total"] == 1
        assert result["status_counts"] == {"live": 1}

    @pytest.mark.asyncio
    async def test_rail_writes_no_register_file(self, tmp_path):
        """Read-only means read-only: generating a proposal must not publish it.

        Q295's generator writes atomically via temp+rename; this rail shares its
        observation path but must NOT share its write path.
        """
        from app.routes.admin import get_grid_register_proposal
        from app.utils.grid_register import REGISTER_DIR

        before = sorted(REGISTER_DIR.glob("*.json")) if REGISTER_DIR.is_dir() else []

        with patch("app.routes.admin._check_admin_secret"), patch(
            "app.services.grid_register_source.generate_register",
            AsyncMock(return_value=(_register([_entry()]), [])),
        ), patch("app.utils.grid_register.validate_register", return_value=[]):
            await get_grid_register_proposal(
                request=None, league="nba", secret="s", db=AsyncMock()
            )

        after = sorted(REGISTER_DIR.glob("*.json")) if REGISTER_DIR.is_dir() else []
        assert before == after

    @pytest.mark.asyncio
    async def test_admin_secret_is_enforced(self):
        from app.routes.admin import get_grid_register_proposal

        with patch(
            "app.routes.admin._check_admin_secret",
            side_effect=HTTPException(status_code=403, detail="forbidden"),
        ):
            with pytest.raises(HTTPException) as exc:
                await get_grid_register_proposal(
                    request=None, league="nba", secret="wrong", db=AsyncMock()
                )

        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_uses_the_shared_generator_path_not_a_private_copy(self):
        """If this rail ever forked its own matcher, proposals and the daily
        sentinel's diff would drift apart and every run would report phantom
        drift. Pin the shared call."""
        from app.routes.admin import get_grid_register_proposal

        shared = AsyncMock(return_value=(_register([]), []))
        db = AsyncMock()

        with patch("app.routes.admin._check_admin_secret"), patch(
            "app.services.grid_register_source.generate_register", shared
        ), patch("app.utils.grid_register.validate_register", return_value=[]):
            await get_grid_register_proposal(
                request=None, league="nba", secret="s", db=db
            )

        shared.assert_awaited_once()
        # Called with the caller's session and the resolved league config.
        assert shared.await_args.args[0] is db
        assert shared.await_args.args[1].slug == "nba"
