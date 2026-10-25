"""#4082 — Discover's Fed & Rates bundle asks about the September FOMC decision ONCE.

THE SPECIMEN, found on production Discover (`https://bainluck.com`, 390px and
1440px, 2026-09-09). The `Fed & Rates` bundle (`story:macro_rates`,
`shared_question: "What does the Fed do next?"`) rendered three rows:

    row 1  109983    kalshi      Fed decision in Sep 2026?      55% chance
             Hike 25bps 55% · Fed maintains rate 46% · Hike >25bps 2%
             resolves 2026-09-16T17:59:00+00:00 (kalshi:KXFEDDECISION-26SEP)
    row 2  20570794  polymarket  Fed Decision in September?     54% chance
             25 bps increase 54% · No change 47% · 25 bps decrease 0%
             resolves 2026-09-16T00:00:00+00:00 (polymarket:481717)
    row 3  113752    polymarket  Fed rate hike in 2026?         71% chance
             resolves 2026-12-09T00:00:00+00:00

Rows 1 and 2 are the same September 16, 2026 FOMC rate decision, shown back to
back in one card at 55% and 54%. Both `_dedupe_same_question_members` (#4446)
and Removal 3 in `_comparison_title` (#6537/#8387) refused the pair on two
independent venue-phrasing artefacts:

1. **Outcome vocabulary**: Removal 3 only drops `2026` from `"Fed decision in
   Sep 2026?"` when `_same_priced_outcomes` sees the two rows pricing the same
   outcomes. Kalshi names its FOMC legs `"Hike 25bps"`, `"Fed maintains rate"`,
   `"Hike >25bps"`, `"Cut 25bps"`, `"Cut >25bps"` while Polymarket names the
   identical legs `"25 bps increase"`, `"No change"`, `"50+ bps increase"`,
   `"25 bps decrease"`, `"50+ bps decrease"` — zero raw string overlap.
2. **Abbreviated month vs full month**: Even after `2026` is set aside, `"Fed
   decision in Sep?"` and `"Fed Decision in September?"` share only two tokens
   (`{"fed", "decision"}`), one short of `_NEAR_MATCH_MIN_SHARED_TOKENS = 3`
   (jaccard 0.50).
"""

import pytest

from app.utils.cross_source_matching import is_same_question
from app.utils.discover_bundles import (
    _canonical_outcome_name,
    _comparison_title,
    _dedupe_same_question_members,
    _same_priced_outcomes,
    assemble_story_theme_bundles,
    fold_same_question_cards,
)

MACRO_STORY = "story:macro_rates"

KALSHI_SEP_DATE = "2026-09-16T17:59:00+00:00"
POLY_SEP_DATE = "2026-09-16T00:00:00+00:00"
POLY_DEC_DATE = "2026-12-09T00:00:00+00:00"


def _member(
    market_id: int,
    name: str,
    *,
    source: str,
    resolution_date: str | None,
    outcomes: list[tuple[str, float | None]],
    score: float = 90.0,
    story_key: str = MACRO_STORY,
) -> dict:
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "reason": "reason",
        "headline": name,
        "data": {
            "id": market_id,
            "name": name,
            "source": source,
            "llm_sport_category": "economics",
            "resolution_date": resolution_date,
            "top_outcomes": [
                {
                    "id": market_id * 10 + i,
                    "name": label,
                    "probability": prob,
                    "rank": i + 1,
                }
                for i, (label, prob) in enumerate(outcomes)
            ],
        },
        "_quality_story_key": story_key,
        "_sort_time": 1000 + market_id,
    }


def _fed_bundle_members() -> list[dict]:
    """The three rows served inside the #4082 Fed & Rates bundle."""
    return [
        _member(
            109983,
            "Fed decision in Sep 2026?",
            source="kalshi",
            resolution_date=KALSHI_SEP_DATE,
            outcomes=[
                ("Hike 25bps", 0.55),
                ("Fed maintains rate", 0.46),
                ("Hike >25bps", 0.02),
            ],
            score=90.0,
        ),
        _member(
            20570794,
            "Fed Decision in September?",
            source="polymarket",
            resolution_date=POLY_SEP_DATE,
            outcomes=[
                ("25 bps increase", 0.54),
                ("No change", 0.47),
                ("25 bps decrease", 0.004),
            ],
            score=86.0,
        ),
        _member(
            113752,
            "Fed rate hike in 2026?",
            source="polymarket",
            resolution_date=POLY_DEC_DATE,
            outcomes=[("Yes", 0.71), ("No", 0.29)],
            score=78.0,
        ),
    ]


def _ids(items: list[dict]) -> list[int]:
    return [item["data"]["id"] for item in items]


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


def test_the_fed_bundle_serves_the_september_fomc_decision_once():
    kept, folded = _dedupe_same_question_members(_fed_bundle_members())

    assert _ids(folded) == [20570794]
    assert _ids(kept) == [109983, 113752]


def test_the_folded_fomc_row_does_not_reappear_as_a_standalone_card():
    result = assemble_story_theme_bundles(_fed_bundle_members())

    bundle = next((it for it in result if it["type"] == "bundle"), None)
    assert bundle is not None
    assert bundle["data"]["member_ids"] == [109983, 113752]
    assert bundle["data"]["item_count"] == 2

    standalone_ids = [it["data"]["id"] for it in result if it["type"] == "futures"]
    assert 20570794 not in standalone_ids
    assert standalone_ids == []


def test_the_folded_duplicate_frees_a_member_slot_for_a_distinct_fed_question():
    result = assemble_story_theme_bundles(
        _fed_bundle_members(), max_items_per_bundle=2
    )

    bundle = next((it for it in result if it["type"] == "bundle"), None)
    assert bundle is not None
    assert bundle["data"]["member_ids"] == [109983, 113752]


def test_the_better_ranked_venue_survives_whichever_order_they_arrive_in():
    members = _fed_bundle_members()
    reversed_pair = [members[1], members[0], members[2]]

    kept, folded = _dedupe_same_question_members(reversed_pair)
    assert _ids(folded) == [109983]
    assert _ids(kept) == [20570794, 113752]


def test_the_standalone_fold_agrees_on_the_fomc_pair():
    members = _fed_bundle_members()
    pair = [members[0], members[1]]

    assert _ids(fold_same_question_cards(pair)) == [109983]


# ---------------------------------------------------------------------------
# Non-vacuity of both halves of the fix
# ---------------------------------------------------------------------------


def test_the_raw_titles_are_still_refused_by_is_same_question():
    assert not is_same_question(
        "Fed decision in Sep 2026?", "Fed Decision in September?"
    )
    assert not is_same_question(
        "Fed decision in Sep?", "Fed Decision in September?"
    )


def test_both_the_outcome_alias_and_the_month_expansion_are_required():
    members = _fed_bundle_members()
    kalshi = members[0]["data"]
    poly = members[1]["data"]

    raw_kalshi_names = {o["name"].lower() for o in kalshi["top_outcomes"]}
    raw_poly_names = {o["name"].lower() for o in poly["top_outcomes"]}
    assert raw_kalshi_names.isdisjoint(raw_poly_names)
    assert _same_priced_outcomes(kalshi, poly)

    left = _comparison_title(kalshi, poly)
    right = _comparison_title(poly, kalshi)
    assert left == "Fed decision in September ?"
    assert right == "Fed Decision in September?"
    assert is_same_question(left, right)


@pytest.mark.parametrize(
    "abbrev,full_month,month_num",
    [
        ("Jan", "January", "01"),
        ("Mar", "March", "03"),
        ("Jun", "June", "06"),
        ("Jul", "July", "07"),
        ("Sep", "September", "09"),
        ("Sept", "September", "09"),
        ("Oct", "October", "10"),
        ("Nov", "November", "11"),
        ("Dec", "December", "12"),
    ],
)
def test_every_abbreviated_fomc_meeting_month_folds_with_its_full_month_twin(
    abbrev: str, full_month: str, month_num: str
):
    close = f"2026-{month_num}-18T18:00:00+00:00"
    kalshi = _member(
        1,
        f"Fed decision in {abbrev} 2026?",
        source="kalshi",
        resolution_date=close,
        outcomes=[
            ("Fed maintains rate", 0.65),
            ("Cut 25bps", 0.25),
            ("Hike 25bps", 0.10),
        ],
    )
    poly = _member(
        2,
        f"Fed Decision in {full_month}?",
        source="polymarket",
        resolution_date=close,
        outcomes=[
            ("No change", 0.64),
            ("25 bps decrease", 0.26),
            ("25 bps increase", 0.10),
        ],
    )

    kept, folded = _dedupe_same_question_members([kalshi, poly])
    assert _ids(kept) == [1]
    assert _ids(folded) == [2]


# ---------------------------------------------------------------------------
# Negative controls — what must NEVER fold
# ---------------------------------------------------------------------------


def test_different_fomc_meeting_months_in_the_same_year_never_fold():
    sep_kalshi = _fed_bundle_members()[0]
    nov_poly = _member(
        99,
        "Fed Decision in November?",
        source="polymarket",
        resolution_date="2026-11-05T00:00:00+00:00",
        outcomes=[
            ("25 bps increase", 0.54),
            ("No change", 0.47),
            ("25 bps decrease", 0.004),
        ],
    )

    assert (
        _comparison_title(sep_kalshi["data"], nov_poly["data"])
        == "Fed decision in Sep ?"
    )
    kept, folded = _dedupe_same_question_members([sep_kalshi, nov_poly])
    assert folded == []
    assert _ids(kept) == [109983, 99]


def test_different_years_of_the_same_fomc_month_never_fold():
    sep_2026 = _fed_bundle_members()[0]
    sep_2027_stated = _member(
        98,
        "Fed decision in September 2027?",
        source="polymarket",
        resolution_date="2027-09-15T00:00:00+00:00",
        outcomes=[
            ("25 bps increase", 0.54),
            ("No change", 0.47),
            ("25 bps decrease", 0.004),
        ],
    )
    sep_2027_undated = _member(
        97,
        "Fed Decision in September?",
        source="polymarket",
        resolution_date="2027-09-15T00:00:00+00:00",
        outcomes=[
            ("25 bps increase", 0.54),
            ("No change", 0.47),
            ("25 bps decrease", 0.004),
        ],
    )

    for other in (sep_2027_stated, sep_2027_undated):
        kept, folded = _dedupe_same_question_members([sep_2026, other])
        assert folded == []
        assert len(kept) == 2


def test_different_central_banks_in_the_same_month_never_fold():
    """Production fixture 2026-08-29 carried Kalshi 59700002 ('Czech National
    Bank rate decision in September') beside Polymarket 20570794 ('Fed Decision
    in September?'). Both price a September hold/hike ladder; they are two
    central banks and must stay apart."""
    cnb = _member(
        59700002,
        "Czech National Bank rate decision in September",
        source="kalshi",
        resolution_date=KALSHI_SEP_DATE,
        outcomes=[
            ("Maintain current rate", 0.6465),
            ("Hike 25bps", 0.2837),
            ("Cut more than 50bps", 0.014),
        ],
    )
    ecb = _member(
        59700003,
        "ECB rate decision in Sep 2026?",
        source="kalshi",
        resolution_date=KALSHI_SEP_DATE,
        outcomes=[
            ("Maintain current rate", 0.60),
            ("Hike 25bps", 0.30),
            ("Cut 25bps", 0.10),
        ],
    )
    fed_poly = _fed_bundle_members()[1]

    for other_bank in (cnb, ecb):
        kept, folded = _dedupe_same_question_members([other_bank, fed_poly])
        assert folded == []
        assert len(kept) == 2


def test_opposing_rate_leaders_do_not_fold_under_removal_3():
    """If one venue has a 25bps hike leading and the other has hold ('No change')
    leading, `_same_priced_outcomes` refuses Removal 3."""
    members = _fed_bundle_members()
    kalshi = members[0]
    poly = members[1]
    poly["data"]["top_outcomes"] = [
        {"id": 1, "name": "No change", "probability": 0.68, "rank": 1},
        {"id": 2, "name": "25 bps increase", "probability": 0.28, "rank": 2},
        {"id": 3, "name": "25 bps decrease", "probability": 0.04, "rank": 3},
    ]

    assert not _same_priced_outcomes(kalshi["data"], poly["data"])
    kept, folded = _dedupe_same_question_members([kalshi, poly])
    assert folded == []
    assert len(kept) == 2


def test_gt25_cut_and_hike_aliases_are_load_bearing_for_removal_3():
    """R2(a): Positive pin where a `50+`/`>25` leg is load-bearing for both
    leader agreement and the 2-shared-leg field minimum."""
    dec_close = "2026-12-09T19:00:00+00:00"
    poly_dec_close = "2026-12-09T00:00:00+00:00"

    kalshi_cut = _member(
        301,
        "Fed decision in Dec 2026?",
        source="kalshi",
        resolution_date=dec_close,
        outcomes=[
            ("Cut >25bps", 0.55),
            ("Cut 25bps", 0.30),
            ("Fed maintains rate", 0.15),
        ],
    )
    poly_cut = _member(
        302,
        "Fed Decision in December?",
        source="polymarket",
        resolution_date=poly_dec_close,
        outcomes=[
            ("50+ bps decrease", 0.54),
            ("25 bps decrease", 0.31),
            ("25 bps increase", 0.15),
        ],
        score=85.0,
    )
    assert _same_priced_outcomes(kalshi_cut["data"], poly_cut["data"])
    kept, folded = _dedupe_same_question_members([kalshi_cut, poly_cut])
    assert _ids(kept) == [301]
    assert _ids(folded) == [302]
    assert _ids(fold_same_question_cards([kalshi_cut, poly_cut])) == [301]

    kalshi_hike = _member(
        303,
        "Fed decision in Dec 2026?",
        source="kalshi",
        resolution_date=dec_close,
        outcomes=[
            ("Hike >25bps", 0.55),
            ("Hike 25bps", 0.30),
            ("Fed maintains rate", 0.15),
        ],
    )
    poly_hike = _member(
        304,
        "Fed Decision in December?",
        source="polymarket",
        resolution_date=poly_dec_close,
        outcomes=[
            ("50+ bps increase", 0.54),
            ("25 bps increase", 0.31),
            ("25 bps decrease", 0.15),
        ],
        score=85.0,
    )
    assert _same_priced_outcomes(kalshi_hike["data"], poly_hike["data"])
    kept_h, folded_h = _dedupe_same_question_members([kalshi_hike, poly_hike])
    assert _ids(kept_h) == [303]
    assert _ids(folded_h) == [304]
    assert _ids(fold_same_question_cards([kalshi_hike, poly_hike])) == [303]


def test_exact_50bps_outcomes_do_not_canonicalize_to_gt25bps():
    """R1 & R2(b): Exact `50 bps` is `(25, 50]`, not `(25, inf)`, and must never
    canonicalize to `cut >25bps` or `hike >25bps`."""
    for exact_cut in (
        "50 bps decrease",
        "50bps decrease",
        "cut 50bps",
        "cut 50 bps",
    ):
        assert _canonical_outcome_name(exact_cut) != "cut >25bps"

    for exact_hike in (
        "50 bps increase",
        "50bps increase",
        "hike 50bps",
        "hike 50 bps",
    ):
        assert _canonical_outcome_name(exact_hike) != "hike >25bps"

    # Probe P6b: a board led by exact `50 bps decrease` + `75+ bps decrease`
    # does not share leader `Cut >25bps` with Kalshi.
    kalshi_gt25 = _member(
        401,
        "Fed decision in Dec 2026?",
        source="kalshi",
        resolution_date="2026-12-09T19:00:00+00:00",
        outcomes=[
            ("Cut >25bps", 0.50),
            ("Cut 25bps", 0.30),
            ("Fed maintains rate", 0.20),
        ],
    )
    poly_exact_50 = _member(
        402,
        "Fed Decision in December?",
        source="polymarket",
        resolution_date="2026-12-09T00:00:00+00:00",
        outcomes=[
            ("50 bps decrease", 0.50),
            ("25 bps decrease", 0.30),
            ("75+ bps decrease", 0.20),
        ],
        score=85.0,
    )
    assert not _same_priced_outcomes(kalshi_gt25["data"], poly_exact_50["data"])
    kept, folded = _dedupe_same_question_members([kalshi_gt25, poly_exact_50])
    assert folded == []
    assert _ids(kept) == [401, 402]
    assert _ids(fold_same_question_cards([kalshi_gt25, poly_exact_50])) == [401, 402]


def test_undated_month_expansion_requires_one_cycle_resolution_p1():
    """R3 (Probe P1): Kalshi-shaped undated `Fed decision in Sep?` (2026-09-16)
    beside Polymarket `Fed Decision in September?` (2027-09-15, one year apart)
    must stay TWO cards in both standalone fold and bundle assembly, as must an
    undated Sep 2026 row beside a stated `September 2027` row."""
    sep_2026_undated = _member(
        501,
        "Fed decision in Sep?",
        source="kalshi",
        resolution_date=KALSHI_SEP_DATE,
        outcomes=[
            ("Hike 25bps", 0.55),
            ("Fed maintains rate", 0.46),
            ("Hike >25bps", 0.02),
        ],
    )
    sep_2027_undated = _member(
        502,
        "Fed Decision in September?",
        source="polymarket",
        resolution_date="2027-09-15T00:00:00+00:00",
        outcomes=[
            ("25 bps increase", 0.54),
            ("No change", 0.47),
            ("25 bps decrease", 0.004),
        ],
        score=86.0,
    )
    sep_2027_stated = _member(
        503,
        "Fed Decision in September 2027?",
        source="polymarket",
        resolution_date="2027-09-15T00:00:00+00:00",
        outcomes=[
            ("25 bps increase", 0.54),
            ("No change", 0.47),
            ("25 bps decrease", 0.004),
        ],
        score=84.0,
    )

    assert (
        _comparison_title(sep_2026_undated["data"], sep_2027_undated["data"])
        == "Fed decision in Sep?"
    )

    for partner in (sep_2027_undated, sep_2027_stated):
        kept, folded = _dedupe_same_question_members([sep_2026_undated, partner])
        assert folded == []
        assert _ids(kept) == [501, partner["data"]["id"]]
        assert _ids(fold_same_question_cards([sep_2026_undated, partner])) == [
            501,
            partner["data"]["id"],
        ]
        bundled = assemble_story_theme_bundles([sep_2026_undated, partner])
        bundle = next((it for it in bundled if it["type"] == "bundle"), None)
        assert bundle is not None
        assert bundle["data"]["member_ids"] == [501, partner["data"]["id"]]

