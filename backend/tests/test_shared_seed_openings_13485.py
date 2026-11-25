"""#13485 — small one-winner fields carrying a uniform untraded seed are refused."""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from app.routes.futures import _format_market_detail
from app.utils.container_machinery import (
    discover_machinery_candidate_paths,
    load_machinery_definition,
    produce_container_machinery,
)
from app.utils.field_opening_coherence import (
    FIELD_MEAN_CEILING,
    FIELD_SUM_CEILING,
    OK,
    NOT_APPLICABLE_NOT_EXCLUSIVE,
    REFUSAL_VERDICTS,
    REFUSED_FIELD_NOT_A_DISTRIBUTION,
    REFUSED_MULTIPLE_CERTAIN_LEGS,
    REFUSED_SHARED_SEED_OPENINGS,
    SHARED_SEED_SUM_CEILING,
    classify_field_openings,
    field_openings_publishable,
)

# `/api/futures/2279151` — Pro Football: NFC South Champion (Nov 22, 2026)
NFC_SOUTH_2279151_ALL = [0.48, 0.48, 0.48, 0.48, 1.0]
NFC_SOUTH_2279151_ACTIVE = [0.48, 0.48, 0.48, 0.48]

# `/api/futures/6173044` — Oscar Winner: Best Picture (staggered capture, mean 0.058)
BEST_PICTURE_6173044 = [2.035 / 35] * 35


class TestSharedSeedOpeningsRule:
    def test_nfc_south_four_teams_at_48_percent_is_refused(self) -> None:
        assert classify_field_openings(NFC_SOUTH_2279151_ALL, mutually_exclusive=True) == (
            REFUSED_SHARED_SEED_OPENINGS
        )
        assert classify_field_openings(NFC_SOUTH_2279151_ACTIVE, mutually_exclusive=True) == (
            REFUSED_SHARED_SEED_OPENINGS
        )
        assert not field_openings_publishable(NFC_SOUTH_2279151_ALL, mutually_exclusive=True)
        assert not field_openings_publishable(NFC_SOUTH_2279151_ACTIVE, mutually_exclusive=True)
        assert REFUSED_SHARED_SEED_OPENINGS in REFUSAL_VERDICTS

    def test_three_honest_longshots_sharing_3_percent_are_kept(self) -> None:
        longshots = [0.03, 0.03, 0.03]
        assert classify_field_openings(longshots, mutually_exclusive=True) == OK
        assert field_openings_publishable(longshots, mutually_exclusive=True)

    def test_small_field_with_ordinary_overround_stays_kept(self) -> None:
        assert sum([0.42, 0.42, 0.42]) < SHARED_SEED_SUM_CEILING
        assert classify_field_openings([0.42, 0.42, 0.42], mutually_exclusive=True) == OK

    def test_best_picture_6173044_keeps_its_openings(self) -> None:
        assert sum(BEST_PICTURE_6173044) < FIELD_SUM_CEILING
        assert sum(BEST_PICTURE_6173044) / len(BEST_PICTURE_6173044) < FIELD_MEAN_CEILING
        assert classify_field_openings(BEST_PICTURE_6173044, mutually_exclusive=True) == OK

    def test_non_exclusive_shared_seed_stays_out_of_scope(self) -> None:
        assert classify_field_openings(NFC_SOUTH_2279151_ACTIVE, mutually_exclusive=False) == (
            NOT_APPLICABLE_NOT_EXCLUSIVE
        )

    def test_older_refusal_verdicts_keep_precedence(self) -> None:
        assert classify_field_openings([0.99] * 35, mutually_exclusive=True) == (
            REFUSED_FIELD_NOT_A_DISTRIBUTION
        )
        assert classify_field_openings([1.0, 1.0, 0.5, 0.5], mutually_exclusive=True) == (
            REFUSED_MULTIPLE_CERTAIN_LEGS
        )


def _nfc_south_market() -> SimpleNamespace:
    rows = [
        ("Carolina Panthers", 0.54, 0.48, 108, -117),
        ("Tampa Bay Buccaneers", 0.265, 0.48, 108, 277),
        ("Atlanta Falcons", 0.1055, 0.48, 108, 848),
        ("New Orleans Saints", 0.07, 0.48, 108, 1329),
        ("Other", None, 1.0, None, None),
    ]
    outcomes = [
        SimpleNamespace(
            id=13207560 + i,
            name=name,
            external_id=f"NFC-S-{i}",
            current_probability=cur,
            current_american_odds=am_cur,
            rank=i + 1,
            rank_change_24h=None,
            probability_change_24h=None,
            opening_probability=op,
            opening_american_odds=am_op,
            is_winner=False,
            resolution_source=None,
            last_updated=None,
        )
        for i, (name, cur, op, am_op, am_cur) in enumerate(rows)
    ]
    return SimpleNamespace(
        id=2279151,
        name="Pro Football: NFC South Champion",
        description=None,
        category="championship",
        source="polymarket",
        external_id="232642",
        status="open",
        sport=None,
        sport_id=None,
        event_id=None,
        market_type="field",
        market_tier=1,
        llm_sport_category="football",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=outcomes,
    )


class TestSerializerAndContainerWithholding:
    def test_futures_detail_withholds_all_openings_and_sets_flag(self) -> None:
        detail = _format_market_detail(_nfc_south_market(), None)
        assert detail["openings_withheld"] is True
        assert [o["name"] for o in detail["outcomes"][:4]] == [
            "Carolina Panthers",
            "Tampa Bay Buccaneers",
            "Atlanta Falcons",
            "New Orleans Saints",
        ]
        for o in detail["outcomes"]:
            assert "opening_probability" in o
            assert o["opening_probability"] is None
            assert o["opening_american_odds"] is None
        assert detail["outcomes"][0]["probability"] == pytest.approx(0.54)

    @pytest.mark.asyncio
    async def test_nfl_week_container_withholds_shared_48_openings(self) -> None:
        from tests.test_container_machinery_slice1_12288 import FIXED_NOW, _sample_snapshot

        paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
        nfl_defn = load_machinery_definition(paths_by_slug["machinery-nfl-week"])
        snapshot = copy.deepcopy(_sample_snapshot())
        for m in snapshot["markets"]:
            if m.get("id") == 2279147:
                m["id"] = 2279151
                m["name"] = "Pro Football: NFC South Champion"
                m["mutually_exclusive"] = True
                m["top_outcomes"] = [
                    {"id": 1, "name": "Carolina Panthers", "probability": 0.54, "opening_probability": 0.48},
                    {"id": 2, "name": "Tampa Bay Buccaneers", "probability": 0.265, "opening_probability": 0.48},
                    {"id": 3, "name": "Atlanta Falcons", "probability": 0.1055, "opening_probability": 0.48},
                    {"id": 4, "name": "New Orleans Saints", "probability": 0.07, "opening_probability": 0.48},
                ]
                break

        res = await produce_container_machinery(snapshot, nfl_defn, now=FIXED_NOW)
        assert hasattr(res, "sections"), res
        div_sec = next(s for s in res.sections if s.get("class") == "division_races")
        nfc_south = next(
            it for it in div_sec["visual_block"]["items"] if it.get("market_id") == 2279151
        )
        assert all(o.get("opening_probability") is None for o in nfc_south["outcomes"])
