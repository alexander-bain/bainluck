"""Guard tests for the US Open tournament register (UX-P130; answers #2167).

Every test here is anchored to a failure class the 2026-08-24 census actually
measured in production, not to a hypothetical.  The named specimens:

* both Polymarket outright fields carry an ``Other`` bucket pinned at 1.000000
  since 2026-05-12, which sorts FIRST on a probability-ordered board;
* Kalshi says ``Felix Auger-Aliassime``, Polymarket says ``Felix Auger
  Aliassime`` — two board rows for one player unless the normalizer drops spaces;
* every US Open singles match market sits under ``llm_sport_category =
  'table_tennis'`` and ``llm_gender`` is NULL on all 861,809 rows, so draw
  membership is register-owned;
* 15 Kalshi Cincinnati match markets from 2026-08-19 are graded but still
  ``status='open'`` with a resolution_date inside US Open week;
* all four outright fields are price-dark (last capture 2026-07-24 .. 08-17).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import app.utils.tournament_register as _tr
from app.utils.tournament_register import (
    DRAWS,
    TRANSITION_ONLY_FINDINGS,
    REGISTER_DIR,
    SCHEMA_VERSION,
    TournamentRegister,
    check_freshness,
    check_rendered_rows,
    classify,
    diff_against_inventory,
    is_non_player,
    load_register,
    normalize_player_name,
    us_open_2026_contract,
    validate_register,
    validate_transition,
)

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)

_MODULE_SOURCE = Path(_tr.__file__).read_text()


def _source(**overrides):
    block = {
        "source": "kalshi",
        "market_id": 34277822,
        "outcome_id": 152600806,
        "market_external_id": "KXATP-26USO",
        "outcome_external_id": "KXATP-26USO-SIN",
        "source_name": "Jannik Sinner",
        "status": "live",
        "terminal_result": None,
        "price_observed_at": (NOW - timedelta(hours=1)).isoformat(),
        "evidence": {"kind": "outright-field-census", "observed_at": NOW.isoformat()},
    }
    block.update(overrides)
    return block


def _player(**overrides):
    player = {
        "entity_key": "jannik-sinner",
        "display_name": "Jannik Sinner",
        "draw": "mens-singles",
        "seed": None,
        "country": None,
        "draw_slot": None,
        "section": None,
        "sources": [_source()],
    }
    player.update(overrides)
    return player


def _register(**overrides):
    register = {
        "schema_version": SCHEMA_VERSION,
        "tournament": "us-open",
        "season": "2026",
        "version": 1,
        "generated_at": NOW.isoformat(),
        "draw_released": False,
        "players": [_player()],
        "matchups": [],
    }
    register.update(overrides)
    return register


CONTRACT = us_open_2026_contract()


# ---------------------------------------------------------------------------
# Identity normalization — the Auger-Aliassime specimen
# ---------------------------------------------------------------------------

def test_normalizer_collapses_the_hyphen_space_split():
    """The measured two-rows-for-one-player case must resolve to one key."""
    assert normalize_player_name("Felix Auger-Aliassime") == normalize_player_name(
        "Felix Auger Aliassime"
    )


def test_normalizer_does_not_collapse_distinct_players():
    assert normalize_player_name("Jannik Sinner") != normalize_player_name("Jack Draper")


@pytest.mark.parametrize("name", ["Other", "other", "Any Other", "Field", "  OTHERS "])
def test_aggregate_buckets_are_not_players(name):
    """The Polymarket ``Other`` bucket pinned at 1.000 must never be a row."""
    assert is_non_player(name) is True


def test_real_player_is_not_mistaken_for_a_bucket():
    assert is_non_player("Jannik Sinner") is False


def test_register_rejects_an_aggregate_bucket_as_a_player():
    register = _register(
        players=[_player(entity_key="other", display_name="Other")]
    )
    assert "INVALID_NON_PLAYER_ENTITY" in validate_register(register, CONTRACT)


# ---------------------------------------------------------------------------
# Draw slots stay empty until the ceremony
# ---------------------------------------------------------------------------

def test_draw_slot_before_release_is_invalid():
    register = _register(draw_released=False, players=[_player(draw_slot=4)])
    assert "INVALID_DRAW_SLOT_BEFORE_RELEASE" in validate_register(register, CONTRACT)


def test_draw_slot_after_release_is_accepted():
    register = _register(draw_released=True, players=[_player(draw_slot=4)])
    assert validate_register(register, CONTRACT) == []


def test_draw_released_is_a_latch():
    """Un-latching would silently un-validate every committed slot."""
    current = _register(draw_released=True)
    proposed = _register(
        version=2, supersedes_version=1, draw_released=False,
    )
    assert "INVALID_DRAW_RELEASED_UNLATCH" in validate_transition(current, proposed, CONTRACT)


def test_valid_transition_is_clean():
    current = _register()
    proposed = _register(version=2, supersedes_version=1)
    assert validate_transition(current, proposed, CONTRACT) == []


# ---------------------------------------------------------------------------
# Membership: a market not in the register does not render
# ---------------------------------------------------------------------------

def test_unregistered_row_is_refused_at_the_render_boundary():
    register = _register()
    rendered = [
        {"entity_key": "jannik-sinner", "source": "kalshi", "state": "live", "probability": 0.525},
        # A stale Cincinnati match market that leaked into a date-window query.
        {"entity_key": "unknown-player", "source": "kalshi", "state": "live", "probability": 0.6},
    ]
    assert check_rendered_rows(register, rendered) == ["UNREGISTERED_RENDER_ROW"]


def test_registered_rows_render_clean():
    register = _register()
    rendered = [
        {"entity_key": "jannik-sinner", "source": "kalshi", "state": "live", "probability": 0.525}
    ]
    assert check_rendered_rows(register, rendered) == []


def test_settled_identity_must_not_render_as_a_live_probability():
    """'Settled means settled' enforced where the user would actually see it."""
    register = _register(
        players=[_player(sources=[_source(status="settled", terminal_result="eliminated")])]
    )
    rendered = [
        {"entity_key": "jannik-sinner", "source": "kalshi", "state": "live", "probability": 0.12}
    ]
    assert check_rendered_rows(register, rendered) == ["SETTLED_RENDERED_AS_LIVE"]


def test_missing_identity_renders_as_missing_not_as_a_number():
    register = _register(players=[_player(sources=[_source(status="missing")])])
    rendered = [{"entity_key": "jannik-sinner", "source": "kalshi", "state": "missing", "probability": None}]
    assert check_rendered_rows(register, rendered) == []


# ---------------------------------------------------------------------------
# Freshness — the price-dark boards
# ---------------------------------------------------------------------------

def test_price_dark_identity_is_flagged_stale():
    """All four US Open outright fields were dark at census time."""
    register = _register(
        players=[_player(sources=[_source(price_observed_at="2026-08-17T09:00:00+00:00")])]
    )
    assert check_freshness(register, NOW) == ["LIVE_PRICE_STALE"]


def test_never_observed_price_is_its_own_finding():
    """Distinct from stale: nobody has ever seen a price for this identity."""
    register = _register(players=[_player(sources=[_source(price_observed_at=None)])])
    assert check_freshness(register, NOW) == ["LIVE_PRICE_NEVER_OBSERVED"]


def test_fresh_price_is_clean():
    assert check_freshness(_register(), NOW) == []


def test_freshness_ignores_settled_identities():
    """A settled row has no live price to be stale about."""
    register = _register(
        players=[
            _player(sources=[_source(status="settled", terminal_result="won", price_observed_at=None)])
        ]
    )
    assert check_freshness(register, NOW) == []


def test_stale_price_is_a_render_finding_not_a_hard_invalid():
    """A dark board still renders — loudly degraded, never silently confident."""
    verdict = classify(["LIVE_PRICE_STALE"])
    assert verdict["classification"] == "render_contract_failure"


# ---------------------------------------------------------------------------
# Drift detection — the sentinel's comparison core
# ---------------------------------------------------------------------------

def _candidate(**overrides):
    row = {
        "source": "kalshi",
        "market_id": 34277822,
        "outcome_id": 152600806,
        "outcome_name": "Jannik Sinner",
        "status": "live",
        "terminal_result": None,
        "season": "2026",
    }
    row.update(overrides)
    return row


def test_matching_inventory_is_clean():
    assert diff_against_inventory(_register(), [_candidate()]) == []


def test_vanished_identity_is_drift():
    assert diff_against_inventory(_register(), []) == ["REGISTERED_IDENTITY_NOT_OBSERVED"]


def test_a_pure_rename_is_unambiguous_and_auto_versionable():
    findings = diff_against_inventory(_register(), [_candidate(outcome_name="J. Sinner")])
    assert findings == ["UNAMBIGUOUS_RENAME_DRIFT"]
    assert classify(findings)["action"] == "publish_new_version"


def test_a_hyphen_only_rename_is_not_drift_at_all():
    """Source punctuation churn must not wake the sentinel every night."""
    register = _register(
        players=[_player(sources=[_source(source_name="Felix Auger-Aliassime")])]
    )
    assert diff_against_inventory(
        register, [_candidate(outcome_name="Felix Auger Aliassime")]
    ) == []


def test_settlement_with_a_result_is_unambiguous():
    findings = diff_against_inventory(
        _register(), [_candidate(status="settled", terminal_result="eliminated")]
    )
    assert findings == ["UNAMBIGUOUS_SETTLEMENT_DRIFT"]


def test_settlement_without_a_result_needs_a_human():
    """Gotcha #33's shape: settled upstream but the winner is not knowable yet."""
    findings = diff_against_inventory(_register(), [_candidate(status="settled")])
    assert findings == ["SETTLEMENT_WITHOUT_RESULT"]
    assert classify(findings)["classification"] == "needs_ruling"


def test_two_candidates_on_one_identity_never_auto_resolve():
    findings = diff_against_inventory(_register(), [_candidate(), _candidate()])
    assert findings == ["AMBIGUOUS_CANDIDATES"]
    assert classify(findings)["action"] == "file_p2_needs_triage"


def test_one_poison_row_does_not_silently_drop():
    assert diff_against_inventory(_register(), [_candidate(), "nonsense"]) == ["POISON_CANDIDATE"]


def test_next_season_candidate_is_flagged():
    assert "NEXT_OR_OTHER_SEASON_CANDIDATE" in diff_against_inventory(
        _register(), [_candidate(), _candidate(outcome_id=999, season="2027")]
    )


# ---------------------------------------------------------------------------
# classify() ordering — severity must win over count
# ---------------------------------------------------------------------------

def test_a_single_hard_invalid_outranks_many_soft_findings():
    verdict = classify(["UNAMBIGUOUS_RENAME_DRIFT", "LIVE_PRICE_STALE", "REGISTER_PLAYER_NO_SOURCES"])
    assert verdict["classification"] == "invalid"
    assert verdict["publish"] is False


def test_clean_publishes_nothing():
    assert classify([]) == {"classification": "clean", "action": "no_change", "publish": False}


# Every finding string the module can emit, harvested from the source rather
# than hand-listed so a new one cannot be added without appearing here.
_HARVESTED = sorted(set(re.findall(r'"([A-Z][A-Z0-9]*(?:_[A-Z0-9]+){1,})"', _MODULE_SOURCE)))

# Transition findings gate publication via ``transition_ok`` and never reach
# classify(); they get their own test below rather than a silent exemption.
EMITTABLE_FINDINGS = [f for f in _HARVESTED if f not in TRANSITION_ONLY_FINDINGS]


def test_the_harvester_actually_found_the_findings():
    """A regex that silently matches nothing would make the next test vacuous."""
    assert len(EMITTABLE_FINDINGS) >= 25
    assert "SETTLEMENT_WITHOUT_RESULT" in EMITTABLE_FINDINGS
    assert "MATCHUP_NOT_A_PAIR" in EMITTABLE_FINDINGS


def test_transition_findings_block_publication():
    """The exemption above is only safe because this path actually gates."""
    for finding in sorted(TRANSITION_ONLY_FINDINGS):
        assert classify([], transition_ok=False)["publish"] is False, finding
    assert classify(["UNAMBIGUOUS_RENAME_DRIFT"], transition_ok=False)["publish"] is False
    assert classify(["UNAMBIGUOUS_RENAME_DRIFT"], transition_ok=True)["publish"] is True


def test_a_malformed_matchup_is_hard_invalid_not_clean():
    """The measured hole: MATCHUP_* matched no prefix, so it published."""
    assert classify(["MATCHUP_NOT_A_PAIR"])["classification"] == "invalid"
    assert classify(["SETTLED_WITHOUT_RESULT"])["classification"] == "invalid"


@pytest.mark.parametrize("finding", EMITTABLE_FINDINGS)
def test_every_emittable_finding_is_classified_by_something(finding):
    """A finding classified by nothing reads as green — worse than no finding.

    ``SETTLEMENT_WITHOUT_RESULT`` was exactly that: emitted by
    ``diff_against_inventory``, matched by no set, and therefore returned
    ``clean``/``no_change``.  This test is why it cannot happen again.
    """
    assert classify([finding])["classification"] != "clean", (
        f"{finding} is emitted but classified by no finding set — it reads as clean"
    )


# ---------------------------------------------------------------------------
# The committed US Open 2026 register — the artifact the page will read
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def committed():
    data = load_register("us-open", "2026")
    assert data is not None, f"no committed register in {REGISTER_DIR}"
    return data


def test_committed_register_validates(committed):
    assert validate_register(committed, CONTRACT) == []


def test_committed_register_has_both_draws_populated(committed):
    view = TournamentRegister(committed)
    for draw in DRAWS:
        assert len(view.draw_players(draw)) >= 20, draw


def test_committed_register_carries_no_aggregate_bucket(committed):
    """Regression guard: the ``Other`` row pinned at 1.000 must stay excluded."""
    for player in committed["players"]:
        assert not is_non_player(player["display_name"]), player


def test_committed_register_has_no_draw_slots_yet(committed):
    assert committed["draw_released"] is False
    assert all(p["draw_slot"] is None for p in committed["players"])


def test_committed_register_identities_are_unique(committed):
    seen = set()
    for player in committed["players"]:
        for block in player["sources"]:
            identity = (block["source"], block["market_id"], block["outcome_id"])
            assert identity not in seen, f"{identity} reused"
            seen.add(identity)


def test_committed_register_pins_only_the_four_census_fields(committed):
    """A market outside the census cannot enter the register by accident."""
    allowed = {"KXATP-26USO", "KXWTA-26USO", "139236", "139255"}
    for player in committed["players"]:
        for block in player["sources"]:
            assert block["market_external_id"] in allowed


def test_committed_register_is_currently_price_dark(committed):
    """Documents the shipping reality: boards are rich in identity, dark in price.

    If this ever fails because the capture rail resumed, that is the good news
    this program is waiting on (#2199) — flip the assertion then.
    """
    assert check_freshness(committed, NOW) == ["LIVE_PRICE_STALE"]


def test_committed_register_blend_coverage_is_reported(committed):
    view = TournamentRegister(committed)
    coverage = view.source_coverage()
    assert coverage.get("2_source", 0) >= 30, coverage
    assert sum(coverage.values()) == len(committed["players"])


def test_committed_register_market_ids_are_a_bounded_load(committed):
    view = TournamentRegister(committed)
    assert len(view.market_ids()) == 4
    assert len(view.market_ids("kalshi")) == 2


def test_committed_register_file_is_stable_json():
    path = REGISTER_DIR / "us-open-2026.json"
    text = path.read_text()
    assert json.loads(text) is not None
    assert text.endswith("\n")


def test_load_register_returns_none_for_an_absent_tournament():
    assert load_register("wimbledon", "2026") is None


def test_load_register_degrades_to_none_on_a_corrupt_file(tmp_path: Path):
    (tmp_path / "us-open-2026.json").write_text("{not json")
    assert load_register("us-open", "2026", directory=tmp_path) is None
