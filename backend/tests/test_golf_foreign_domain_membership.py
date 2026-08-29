"""UX-P168 — the golf page stops serving a darts tournament and an esports tournament.

Production, 2026-08-29: `/api/golf` served six tournaments. Two of them were not
golf, and both were badged **PGA Tour**:

| served name                | field                                   |
|----------------------------|-----------------------------------------|
| New Zealand Darts Masters  | Simon Whitlock, Gerwyn Price, James Wade |
| Asia Masters 2026          | Dplus Challengers, T1 Esports Academy    |

Both arrived through the same door and it is the one #1625 named: **membership
decided lexically.** `_GOLF_SIGNAL_RE` accepts a bare `masters`, `open`,
`classic`, `invitational` or `major` as a sufficient golf signal — and every one
of those words names an event in some other sport.

The two halves are separate defects and are asserted separately:

1. **The title says the sport and nobody was listening.** "New Zealand Darts
   Masters" says *darts*. `_NON_GOLF_RE` had drifted apart from the #1625
   authority's `FOREIGN_TERMS`, and neither listed darts.
2. **The title is domain-neutral and the FIELD is another sport.** "Asia Masters
   2026 Winner" names no domain at all; the esports lives entirely in the
   outcomes. `evaluate_membership` has always specified a check on
   `outcome_name` — no OPEN-tournament path ever ran it.

The fixture is the honest BEFORE, pulled from production before a line was
written (`tests/fixtures/uxp168_golf_foreign_domain.json`), because the site
moves: a tournament that is on the page today may have rolled off by the time
anyone re-reads this.

**The controls are the point of this file.** Tightening the lexical gate instead
would have been the obvious fix and it would have been wrong: measured over the
same production pull, five real golf markets — including the LPGA CPKC Women's
Open and the Rogers Charity Classic — pass *only* on a generic token. They are
asserted here as survivors so a future tightening cannot quietly delete them.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.routes.golf import _is_golf_market
from app.utils.golf_membership import (
    FOREIGN_TERMS,
    drop_foreign_field_markets,
    is_foreign_domain,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "uxp168_golf_foreign_domain.json"
BANKED = json.loads(FIXTURE.read_text())
MARKETS = {m["id"]: m for m in BANKED["markets"]}

DARTS = 58416367
ESPORTS = 38277227
# Controls, one per branch of `_is_golf_market`, all real golf, all must survive.
POLY_PGA = 59433935
KALSHI_GENERIC_TOKEN = 59512401  # "…British Masters…" — passes on `masters` alone
LPGA_GENERIC_TOKEN = 59172995  # "CPKC Women's Open…" — passes on `open` alone
KALSHI_PGA = 56775495
DATAGOLF = 59485745


def _market(market_id: int):
    """Rebuild one banked production row as the object the route filters."""
    row = MARKETS[market_id]
    market = SimpleNamespace(
        id=row["id"],
        name=row["name"],
        source=row["source"],
        external_id=row["external_id"],
    )
    # Set through __dict__ so the test exercises the same access the helper uses.
    market.__dict__["outcomes"] = [SimpleNamespace(name=o["name"]) for o in row["outcomes"]]
    return market


def _outcome_names(market_id: int) -> list[str]:
    return [o["name"] for o in MARKETS[market_id]["outcomes"]]


class TestTheBankedBeforeIsWhatWeClaim:
    """Vacuity companion for the whole file: assert the BEFORE actually held."""

    def test_the_two_defects_were_served_as_pga_tour_tournaments(self):
        served = {t["name"]: t for t in BANKED["served_tournaments_before"]}
        assert "New Zealand Darts Masters" in served
        assert "Asia Masters 2026" in served
        for name in ("New Zealand Darts Masters", "Asia Masters 2026"):
            assert served[name]["tour_label"] == "PGA Tour", (
                f"the BEFORE claim is that {name!r} was badged PGA Tour"
            )

    def test_the_esports_field_is_in_the_outcomes_not_the_title(self):
        row = MARKETS[ESPORTS]
        assert not is_foreign_domain(row["name"]), (
            "if the title named the domain, the name-side gate alone would be the fix "
            "and the outcome-side gate would be untested by this file"
        )
        foreign = [n for n in _outcome_names(ESPORTS) if is_foreign_domain(n)]
        assert foreign == ["T1 Esports Academy"], foreign

    def test_the_generic_token_controls_really_are_generic(self):
        """These survive on `masters`/`open` alone — that is why they are fragile."""
        for market_id in (KALSHI_GENERIC_TOKEN, LPGA_GENERIC_TOKEN):
            name = MARKETS[market_id]["name"].lower()
            assert not any(t in name for t in ("golf", "pga", "lpga", "dp world")), (
                f"{name!r} was chosen as a control because it carries NO golf-specific "
                "token; if it gained one it no longer guards the case it was chosen for"
            )


class TestTheDartsTournamentLeavesTheGolfPage:
    def test_the_darts_market_is_rejected(self):
        assert _is_golf_market(_market(DARTS)) is False

    def test_darts_is_in_the_membership_authority(self):
        assert "darts" in FOREIGN_TERMS

    def test_the_authority_covers_the_other_masters_sports(self):
        """Darts was the leak that was observed; it is not the only sport with a Masters."""
        for term in ("snooker", "cricket", "poker", "billiards", "chess"):
            assert term in FOREIGN_TERMS

    def test_the_rejection_is_by_domain_not_by_the_word_masters(self):
        """Vacuity companion: `masters` must still be a legal golf word."""
        assert _is_golf_market(_market(KALSHI_GENERIC_TOKEN)) is True


class TestTheEsportsTournamentLeavesTheGolfPage:
    def test_the_name_side_gate_cannot_see_it(self):
        """The title is domain-neutral, so `_is_golf_market` passes it. That is the gap."""
        assert _is_golf_market(_market(ESPORTS)) is True

    def test_the_field_side_gate_drops_it(self):
        kept = drop_foreign_field_markets([_market(ESPORTS)])
        assert kept == []

    def test_a_real_golf_field_survives_the_field_side_gate(self):
        """158 LPGA players, none of whom names a domain."""
        kept = drop_foreign_field_markets([_market(LPGA_GENERIC_TOKEN)])
        assert len(kept) == 1


class TestUnloadedOutcomesAreNotEvidence:
    """`markets_all` is eager-loaded, but this helper is importable from anywhere.

    An unloaded relationship must read as NO EVIDENCE and KEEP, never as a drop —
    and it must not fire a lazy load, which inside the async request would raise
    `MissingGreenlet` rather than return anything at all.
    """

    def test_a_market_with_no_loaded_outcomes_is_kept(self):
        market = SimpleNamespace(name="Some Open Winner", source="kalshi", external_id="x")
        assert len(drop_foreign_field_markets([market])) == 1

    def test_outcomes_are_never_touched_by_attribute_access(self):
        class Exploding:
            name = "Some Open Winner"

            @property
            def outcomes(self):  # pragma: no cover - must never be reached
                raise AssertionError("lazy load fired: use __dict__, not attribute access")

        assert len(drop_foreign_field_markets([Exploding()])) == 1


class TestTheRealGolfPopulationIsUntouched:
    """The fix must be a scalpel: exactly two markets, and no others."""

    @pytest.mark.parametrize(
        "market_id",
        [POLY_PGA, KALSHI_GENERIC_TOKEN, LPGA_GENERIC_TOKEN, KALSHI_PGA, DATAGOLF],
    )
    def test_real_golf_markets_survive_both_gates(self, market_id):
        market = _market(market_id)
        assert _is_golf_market(market) is True
        assert len(drop_foreign_field_markets([market])) == 1

    def test_the_measured_population_moved_by_exactly_two(self):
        pop = BANKED["population"]
        assert pop["passed_master_gate"] - pop["passed_uxp168_gate"] == 2

    def test_the_false_positive_sweep_found_exactly_one_market(self):
        """4,138 production outcomes scanned; only the esports market matched."""
        pop = BANKED["population"]
        assert pop["markets_with_a_foreign_domain_outcome"] == 1
        assert pop["outcomes_scanned_for_false_positives"] > 4000


# ---------------------------------------------------------------------------
# The route, not the helper.
#
# Everything above tests pure functions, and a pure-function guard stays green if
# someone deletes the CALL. So this drives the real `get_golf` over the banked
# production markets and asserts on the payload a reader is served.
# ---------------------------------------------------------------------------

from datetime import datetime  # noqa: E402

from app.routes.golf import get_golf  # noqa: E402


def _dt(value):
    return datetime.fromisoformat(value) if value else None


class _Outcome:
    def __init__(self, row):
        self.id = row["id"]
        self.name = row["name"]
        self.current_probability = row["current_probability"]
        self.opening_probability = row["current_probability"]
        self.is_winner = None
        self.american_odds = None
        self.outcome_metadata = None
        self.probability_change_24h = None
        self.previous_probability = None
        self.last_updated = None


class _Market:
    def __init__(self, row):
        self.id = row["id"]
        self.name = row["name"]
        self.source = row["source"]
        self.external_id = row["external_id"]
        self.llm_sport_category = row["llm_sport_category"]
        self.status = row["status"]
        self.commence_time = _dt(row["commence_time"])
        self.resolution_date = _dt(row["resolution_date"])
        self.market_metadata = None
        self.group_id = None
        self.market_tier = 3
        self.outcomes = [_Outcome(o) for o in row["outcomes"]]


class _Result:
    """One result object that answers every access shape `get_golf` uses."""

    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _Session:
    """First execute returns the golf markets; every later one returns nothing."""

    def __init__(self, markets):
        self._markets = markets
        self.calls = 0

    async def execute(self, *_args, **_kwargs):
        self.calls += 1
        return _Result(self._markets if self.calls == 1 else [])


@pytest.fixture
def served(monkeypatch):
    """Run the real route over the banked production markets."""

    async def _no_schedule():
        return []

    monkeypatch.setattr("app.routes.golf._get_golf_schedule", _no_schedule)

    async def _run():
        session = _Session([_Market(m) for m in BANKED["markets"]])
        return await get_golf(session)

    import asyncio

    return asyncio.run(_run())


class TestTheServedGolfPage:
    def test_the_darts_tournament_is_not_served(self, served):
        names = [t["name"] for t in served["tournaments"]]
        assert not any("Darts" in n for n in names), names

    def test_the_esports_tournament_is_not_served(self, served):
        names = [t["name"] for t in served["tournaments"]]
        assert not any("Asia Masters" in n for n in names), names

    def test_no_served_golfer_is_a_darts_player_or_an_esports_team(self, served):
        golfers = {
            g["name"] for t in served["tournaments"] for g in t.get("_all_golfers", [])
        }
        for intruder in ("Simon Whitlock", "Gerwyn Price", "T1 Esports Academy",
                         "Dplus Challengers"):
            assert intruder not in golfers

    def test_the_real_tournaments_are_still_served(self, served):
        """Vacuity companion: the page must not have been emptied to pass."""
        names = [t["name"] for t in served["tournaments"]]
        assert names, "the route served nothing — the assertions above are vacuous"
        assert any("Championship" in n or "Masters" in n or "Golfers" in n for n in names), names

    def test_a_real_golfer_still_reaches_the_page(self, served):
        golfers = {
            g["name"] for t in served["tournaments"] for g in t.get("_all_golfers", [])
        }
        assert golfers, "no golfers were served at all"


class TestTheSurvivalFlagsTheFrontendRigTrusts:
    """`served_tournaments_before[].survives_uxp168` is consumed by a jest rig.

    `frontend/__tests__/capture/golfForeignTournamentCapture.test.tsx` renders its
    AFTER column by filtering on that flag. A boolean baked into a fixture is a
    claim, so it is re-derived here from the SHIPPED predicate every run — if the
    two ever disagree, the artifact is drawing a page the backend does not serve.
    """

    def _survives(self, market_id: int) -> bool:
        market = _market(market_id)
        return _is_golf_market(market) and len(drop_foreign_field_markets([market])) == 1

    def test_every_flag_matches_the_shipped_predicate(self):
        """Re-derivable for the tournaments whose markets are banked in full."""
        for tournament in BANKED["served_tournaments_before"]:
            derivable = [m for m in tournament["market_ids"] if m in MARKETS]
            if not derivable:
                continue
            expected = any(self._survives(m) for m in derivable)
            assert tournament["survives_uxp168"] == expected, tournament["name"]

    def test_exactly_the_two_non_golf_tournaments_are_marked_dropped(self):
        dropped = [
            t["name"] for t in BANKED["served_tournaments_before"]
            if not t["survives_uxp168"]
        ]
        assert sorted(dropped) == ["Asia Masters 2026", "New Zealand Darts Masters"]

    def test_every_surviving_tournament_keeps_every_one_of_its_markets(self):
        """The fix is a scalpel: it must not shave markets off a real tournament."""
        for tournament in BANKED["served_tournaments_before"]:
            if not tournament["survives_uxp168"]:
                continue
            assert tournament["surviving_market_ids"] == tournament["market_ids"], (
                f"{tournament['name']} lost markets it should have kept"
            )

    def test_the_page_goes_from_six_tournaments_to_four(self):
        before = BANKED["served_tournaments_before"]
        after = [t for t in before if t["survives_uxp168"]]
        assert (len(before), len(after)) == (6, 4)
