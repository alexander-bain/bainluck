"""#12288 pre-flip regression guards (Fable 2:41 PM PT, Thu Nov 19):

1. No grouping row for a market with no live price or whose event has passed
   (pins past-ceremony #109566 'Oscar for Best Actor?' out in both pure-dict and DB paths).
2. No row title or member card name carries a merge note or a market id
   (e.g. '(averaged across venues on server: #5165726 + #27988771)').
3. One row per twin in every grouping: December Fed decision (57574250 + 109657)
   appears once across all sections of Fed & U.S. Macro, and 2035/2036 GDP growth
   is excluded by `max_horizon_years: 2`.
4. With groupings on, every non-replaced standing round-up keeps its exact seat
   (zero drift — CFP Picture stays at seat 13 -> 13), and every replacing grouping
   sits in the exact seat of the card it replaced.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.paired_metric_register import (
    PAIRED_METRIC_REGISTER_PATH,
    clean_card_face_title,
    hydrate_paired_metric_set_from_markets,
)
from app.utils.container_machinery import (
    _market_matches_query,
    _twin_market_key,
    load_machinery_definition,
    produce_container_machinery,
    register_machinery_slice1_candidates,
)
from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    insert_roundup_feed_items,
)

NOW = datetime(2026, 11, 19, 22, 40, tzinfo=timezone.utc)
_INTERNAL_TITLE_RE = re.compile(r"(?:#\d+|averaged\s+across\s+venues|on\s+server)", re.IGNORECASE)


def test_109566_withheld_or_stale_and_past_events_are_excluded_from_groupings() -> None:
    aq = {
        "kind": "markets",
        "title_all_tokens": ["oscar"],
        "any_tokens": ["best actor", "best actress"],
        "exclude_tokens": ["nomin", "supporting"],
        "shape": "field",
    }

    # Exact #109566 shape: all 16 prices withheld (empty screened top_outcomes), even if raw outcomes had 0.50
    m_109566_withheld = {
        "id": 109566,
        "name": "Oscar for Best Actor?",
        "status": "open",
        "source": "kalshi",
        "top_outcomes": [],
        "outcomes": [
            {"id": 1598463, "name": "Jesse Plemons", "probability": 0.50},
            {"id": 1598464, "name": "Dwayne Johnson", "probability": 0.50},
            {"id": 1598465, "name": "Brendan Fraser", "probability": 0.50},
        ],
    }
    assert _market_matches_query(m_109566_withheld, aq, now_dt=NOW) is False

    # Exact #109566 shape with stale Mar 12 last_updated timestamps even if prices were non-null
    m_109566_stale = {
        "id": 109566,
        "name": "Oscar for Best Actor?",
        "status": "open",
        "source": "kalshi",
        "top_outcomes": [
            {"id": 1598463, "name": "Jesse Plemons", "probability": 0.50, "last_updated": "2026-03-12T06:45:17+00:00"},
            {"id": 1598464, "name": "Dwayne Johnson", "probability": 0.50, "last_updated": "2026-03-12T06:45:17+00:00"},
            {"id": 1598465, "name": "Brendan Fraser", "probability": 0.50, "last_updated": "2026-03-12T06:45:17+00:00"},
        ],
    }
    assert _market_matches_query(m_109566_stale, aq, now_dt=NOW) is False

    # Past resolution_date is refused even with fresh prices
    m_past = {
        "id": 999109566,
        "name": "Oscars 2026: Best Actor Winner",
        "status": "open",
        "source": "polymarket",
        "resolution_date": "2026-03-15T23:59:00+00:00",
        "top_outcomes": [
            {"id": 1, "name": "Actor A", "probability": 0.55, "last_updated": "2026-11-19T22:00:00+00:00"},
            {"id": 2, "name": "Actor B", "probability": 0.30, "last_updated": "2026-11-19T22:00:00+00:00"},
            {"id": 3, "name": "Actor C", "probability": 0.15, "last_updated": "2026-11-19T22:00:00+00:00"},
        ],
    }
    assert _market_matches_query(m_past, aq, now_dt=NOW) is False

    # Live 2027 Best Actor passes cleanly
    m_live_actor = {
        "id": 57368169,
        "name": "Oscars 2027: Best Actor Winner",
        "status": "open",
        "source": "polymarket",
        "resolution_date": "2027-07-01T03:59:00+00:00",
        "top_outcomes": [
            {"id": 11, "name": "John Malkovich", "probability": 0.47, "last_updated": "2026-11-19T17:32:40+00:00"},
            {"id": 12, "name": "Actor B", "probability": 0.25, "last_updated": "2026-11-19T17:32:40+00:00"},
            {"id": 13, "name": "Actor C", "probability": 0.15, "last_updated": "2026-11-19T17:32:40+00:00"},
        ],
    }
    assert _market_matches_query(m_live_actor, aq, now_dt=NOW) is True


def test_no_row_title_carries_merge_note_or_market_id() -> None:
    assert (
        clean_card_face_title(
            "Oscar nominees: Best Picture (averaged across venues on server: #5165726 + #27988771)"
        )
        == "Oscar nominees: Best Picture"
    )
    reg = json.loads(Path(PAIRED_METRIC_REGISTER_PATH).read_text(encoding="utf-8"))
    for sid, sdata in (reg.get("sets") or {}).items():
        for mkey in ("stage_1_market", "stage_2_market"):
            mname = str((sdata.get(mkey) or {}).get("name") or "")
            assert not _INTERNAL_TITLE_RE.search(mname), f"{sid}.{mkey}.name leaks internal text: {mname!r}"

    # Even if a raw register dict still carried an internal merge note, hydration strips it
    raw_set = dict(reg["sets"]["oscars-2027-best-picture"])
    raw_set["stage_1_market"] = {
        **raw_set["stage_1_market"],
        "name": "Oscar nominees: Best Picture (averaged across venues on server: #5165726 + #27988771)",
    }
    markets_by_id = {
        5165726: {
            "id": 5165726,
            "name": "Oscar nominees: Best Picture",
            "status": "open",
            "source": "kalshi",
            "outcomes": [
                {"id": i + 1, "name": e["subject"], "probability": 0.80 - i * 0.05}
                for i, e in enumerate(raw_set["entries"][:5])
            ],
        },
        6173044: {
            "id": 6173044,
            "name": "Oscar Winner: Best Picture",
            "status": "open",
            "source": "kalshi",
            "outcomes": [
                {"id": 100 + i, "name": e["subject"], "probability": 0.50 - i * 0.08}
                for i, e in enumerate(raw_set["entries"][:5])
            ],
        },
    }
    hydrated = hydrate_paired_metric_set_from_markets(raw_set, markets_by_id)
    assert hydrated is not None
    assert not _INTERNAL_TITLE_RE.search(str(hydrated["stage_1_market"]["name"]))
    assert not _INTERNAL_TITLE_RE.search(str(hydrated["stage_2_market"]["name"]))
    assert not _INTERNAL_TITLE_RE.search(str(hydrated["subtitle"]))


@pytest.mark.asyncio
async def test_fed_and_macro_dedupes_december_twins_across_sections_and_drops_2035_gdp() -> None:
    assert _twin_market_key("Fed Decision in December?") == "fomc:december"
    assert _twin_market_key("Fed decision in Dec 2026?") == "fomc:december"
    assert _twin_market_key("December 2026 Fed Decision") == "fomc:december"
    assert _twin_market_key("Oscars 2027: Best Actor Winner") == "oscars:best actor"
    assert _twin_market_key("Oscar Winner: Best Actor") == "oscars:best actor"

    defn = load_machinery_definition("data/groupings/candidates/machinery-fed-and-macro.json")
    fresh = "2026-11-19T22:30:00+00:00"
    db = {
        "events": [],
        "paired_sets": {},
        "market_histories": {},
        "markets": [
            {
                "id": 57574217,
                "name": "Fed Decision in January?",
                "status": "open",
                "source": "polymarket",
                "resolution_date": "2027-01-28T04:59:00+00:00",
                "top_outcomes": [
                    {"id": 1, "name": "25 bps increase", "probability": 0.61, "last_updated": fresh},
                    {"id": 2, "name": "No change", "probability": 0.36, "last_updated": fresh},
                    {"id": 3, "name": "50+ bps increase", "probability": 0.02, "last_updated": fresh},
                ],
            },
            {
                "id": 57574250,
                "name": "Fed Decision in December?",
                "status": "open",
                "source": "polymarket",
                "resolution_date": "2026-12-10T04:59:00+00:00",
                "top_outcomes": [
                    {"id": 11, "name": "25 bps increase", "probability": 0.915, "last_updated": fresh},
                    {"id": 12, "name": "50+ bps increase", "probability": 0.052, "last_updated": fresh},
                    {"id": 13, "name": "No change", "probability": 0.030, "last_updated": fresh},
                ],
            },
            {
                "id": 109657,
                "name": "Fed decision in Dec 2026?",
                "status": "open",
                "source": "kalshi",
                "resolution_date": "2026-12-09T18:59:00+00:00",
                "top_outcomes": [
                    {"id": 21, "name": "Hike 25bps", "probability": 0.910, "last_updated": fresh},
                    {"id": 22, "name": "Hike >25bps", "probability": 0.055, "last_updated": fresh},
                    {"id": 23, "name": "Fed maintains rate", "probability": 0.035, "last_updated": fresh},
                ],
            },
            {
                "id": 113883,
                "name": "Fed rate cut by...?",
                "status": "open",
                "source": "polymarket",
                "resolution_date": "2027-06-30T00:00:00+00:00",
                "top_outcomes": [
                    {"id": 31, "name": "March 2027", "probability": 0.45, "last_updated": fresh},
                    {"id": 32, "name": "April 2027", "probability": 0.30, "last_updated": fresh},
                    {"id": 33, "name": "June 2027", "probability": 0.25, "last_updated": fresh},
                ],
            },
            {
                "id": 114367,
                "name": "What will the Fed rate be at the end of 2026?",
                "status": "open",
                "source": "polymarket",
                "resolution_date": "2026-12-31T00:00:00+00:00",
                "top_outcomes": [
                    {"id": 41, "name": "4.25%", "probability": 0.8738, "rendered_percent": 88, "last_updated": fresh},
                    {"id": 42, "name": "≥ 4.5%", "probability": 0.0660, "rendered_percent": 7, "last_updated": fresh},
                    {"id": 43, "name": "4.0%", "probability": 0.0301, "rendered_percent": 3, "last_updated": fresh},
                ],
            },
            {
                "id": 70732744,
                "name": "How many Fed rate hikes in 2026?",
                "status": "open",
                "source": "polymarket",
                "resolution_date": "2026-12-31T00:00:00+00:00",
                "top_outcomes": [
                    {"id": 51, "name": "1", "probability": 0.55, "last_updated": fresh},
                    {"id": 52, "name": "2", "probability": 0.30, "last_updated": fresh},
                    {"id": 53, "name": "0", "probability": 0.15, "last_updated": fresh},
                ],
            },
            {
                "id": 113012,
                "name": "US recession in 2027?",
                "status": "open",
                "source": "kalshi",
                "resolution_date": "2027-12-31T00:00:00+00:00",
                "top_outcomes": [
                    {"id": 61, "name": "Yes", "probability": 0.28, "last_updated": fresh},
                    {"id": 62, "name": "No", "probability": 0.72, "last_updated": fresh},
                ],
            },
            {
                "id": 108594,
                "name": "US real GDP growth in 2026?",
                "status": "open",
                "source": "kalshi",
                "resolution_date": "2027-02-01T00:00:00+00:00",
                "top_outcomes": [
                    {"id": 71, "name": "2.0% to 2.5%", "probability": 0.52, "last_updated": fresh},
                    {"id": 72, "name": "2.5% to 3.0%", "probability": 0.30, "last_updated": fresh},
                    {"id": 73, "name": "1.5% to 2.0%", "probability": 0.18, "last_updated": fresh},
                ],
            },
            # Far-horizon 2035 & 2036 GDP growth MUST be excluded by max_horizon_years: 2
            {
                "id": 9992035,
                "name": "US GDP growth in 2035?",
                "status": "open",
                "source": "kalshi",
                "resolution_date": "2036-02-01T00:00:00+00:00",
                "top_outcomes": [
                    {"id": 81, "name": "2%", "probability": 0.50, "last_updated": fresh},
                    {"id": 82, "name": "3%", "probability": 0.30, "last_updated": fresh},
                    {"id": 83, "name": "1%", "probability": 0.20, "last_updated": fresh},
                ],
            },
            {
                "id": 9992036,
                "name": "US GDP growth in 2036?",
                "status": "open",
                "source": "kalshi",
                "resolution_date": "2037-02-01T00:00:00+00:00",
                "top_outcomes": [
                    {"id": 91, "name": "2%", "probability": 0.50, "last_updated": fresh},
                    {"id": 92, "name": "3%", "probability": 0.30, "last_updated": fresh},
                    {"id": 93, "name": "1%", "probability": 0.20, "last_updated": fresh},
                ],
            },
        ],
    }

    res = await produce_container_machinery(db, defn, now=NOW)
    assert hasattr(res, "members"), f"Expected RoundupMembers, got {res}"
    shown_ids = [int(m["id"]) for m in res.members]
    # December Fed appears ONCE (57574250 shown, twin 109657 excluded & recorded as covered)
    assert (57574250 in shown_ids) != (109657 in shown_ids), f"December Fed duplicated or missing: {shown_ids}"
    assert 109657 in res.covered_market_ids or 57574250 in res.covered_market_ids
    # 2035 & 2036 GDP growth excluded
    assert 9992035 not in shown_ids
    assert 9992036 not in shown_ids
    assert 108594 in shown_ids


def test_standing_roundups_keep_exact_seats_and_replacers_sit_in_exact_replaced_seats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    saved_producers = dict(ROUNDUP_PRODUCERS)
    try:
        register_machinery_slice1_candidates()

        def _single(i: int) -> dict:
            return {
                "type": "futures",
                "score": 80.0 - i * 0.2,
                "data": {"id": 90000 + i, "name": f"Single {i}", "status": "open"},
            }

        def _standing(slug: str, *, sibling: bool = False) -> dict:
            return {
                "type": "bundle",
                "score": 60.0,
                "data": {
                    "id": f"roundup:{slug.removeprefix('roundup-')}",
                    "kind": "roundup",
                    "name": slug,
                    "collection_ref": {"slug": slug, "href": f"/collections/{slug}", "name": slug},
                    "roundup": {"kicker": "ROUND-UP", "relations": ["sibling"] if sibling else ["same_subject"], "rows": []},
                    "items": [],
                },
            }

        def _mach(slug: str, mids: list[int] | None = None, covered: list[int] | None = None) -> dict:
            prod = ROUNDUP_PRODUCERS[slug]
            all_mids = list(dict.fromkeys([*(mids or []), *(covered or [])]))
            return {
                "type": "bundle",
                "score": 70.0,
                "data": {
                    "id": f"roundup:{slug}",
                    "kind": "roundup",
                    "name": prod.name,
                    "collection_ref": {"slug": slug, "href": f"/collections/{slug}", "name": prod.name},
                    "roundup": {"kicker": prod.kicker, "relations": list(prod.relations), "rows": []},
                    "items": [{"type": "futures", "data": {"id": m, "status": "open"}} for m in (mids or [])],
                    "member_ids": all_mids,
                },
            }

        # Build a 60-seat base feed mirroring live production seats
        base = [_single(i) for i in range(60)]
        base[2] = {
            "type": "bundle",
            "score": 92.0,
            "data": {
                "id": "theme:story:oscars:6173044-65814223-65814224",
                "kind": "theme",
                "story_key": "story:oscars",
                "name": "Oscars",
                "items": [
                    {"type": "futures", "data": {"id": 6173044, "status": "open"}},
                    {"type": "futures", "data": {"id": 65814223, "status": "open"}},
                    {"type": "futures", "data": {"id": 65814224, "status": "open"}},
                ],
            },
        }
        base[5] = {
            "type": "bundle",
            "score": 90.0,
            "data": {
                "id": "theme:story:macro_rates:57574250-56995847",
                "kind": "theme",
                "story_key": "story:macro_rates",
                "name": "Fed & Rates",
                "items": [
                    {"type": "futures", "data": {"id": 57574250, "status": "open"}},
                    {"type": "futures", "data": {"id": 56995847, "status": "open"}},
                ],
            },
        }
        standing_seats = {
            13: ("roundup-cfp-picture", False),
            15: ("by-november-30", False),
            19: ("liga-profesional-relegation-2026", True),
            21: ("by-december-31", False),
            23: ("nhl-playoffs-2026-27", True),
            25: ("golf-this-week", False),
            28: ("gta-vi-album-features", True),
            30: ("for-scale-snow-in-dc", False),
            33: ("celtics-next-3-games", False),
            34: ("lakers-next-3-games", False),
            36: ("roundup-oscars-best-picture", False),
            38: ("roundup-nfl-division-front-runners", False),
        }
        for seat, (slug, sib) in standing_seats.items():
            base[seat - 1] = _standing(slug, sibling=sib)
        base[31] = {
            "type": "futures",
            "score": 61.0,
            "data": {"id": 108326, "name": "2028 U.S. Presidential Election winner?", "status": "open"},
        }

        mach_cards = [
            _mach("machinery-nfl-week"),
            _mach("machinery-nba-night"),
            _mach("machinery-oscars-best-picture", [6173044, 5165726]),
            _mach("machinery-2028-presidential", [112897], covered=[108326]),
            _mach("machinery-fed-and-macro", [57574217, 57574250]),
        ]
        spliced = insert_roundup_feed_items(
            base, mach_cards, page_window=20, now=NOW, preserve_existing_roundups=True
        )

        def _slug(it: dict) -> str:
            d = it.get("data") or {}
            return str((d.get("collection_ref") or {}).get("slug") or d.get("id") or "")

        spliced_slugs = [_slug(it) for it in spliced]

        # 1. Every non-replaced standing round-up keeps its EXACT seat (delta == 0!)
        for seat, (slug, _) in standing_seats.items():
            if slug == "roundup-oscars-best-picture":
                assert slug not in spliced_slugs
                continue
            assert spliced_slugs.index(slug) + 1 == seat, (
                f"{slug} moved from seat {seat} to {spliced_slugs.index(slug) + 1}"
            )

        # 2. Every replacing grouping sits in the EXACT seat of the card it replaced
        assert spliced_slugs[5] == "machinery-fed-and-macro"  # Seat 6 == Fed & Rates
        assert spliced_slugs[31] == "machinery-2028-presidential"  # Seat 32 == lone 108326
        assert spliced_slugs[35] == "machinery-oscars-best-picture"  # Seat 36 == old Best Picture
        assert not any(s.startswith("theme:story:macro_rates:") for s in spliced_slugs)
        assert "108326" not in spliced_slugs

        # 3. Non-replacing groupings sit strictly after the last standing round-up, in first 60 seats
        assert 38 < spliced_slugs.index("machinery-nba-night") + 1 <= 60
        assert 38 < spliced_slugs.index("machinery-nfl-week") + 1 <= 60
        assert spliced_slugs.index("machinery-nba-night") < spliced_slugs.index("machinery-nfl-week")
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved_producers)
