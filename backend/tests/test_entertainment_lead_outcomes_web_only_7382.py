"""#7382 — the `/entertainment` lead row carries up to six priced rungs in an
additive `lead_outcomes` field, and `top_outcomes` does not move.

At 1280px the lead hero card spans both grid rows (421px, set by the two side
cards stacked beside it) and printed three rungs under a 196px blank band
(production read 2026-10-22 03:52Z, "Oscar Winner: Best Picture", 41 outcomes).
`trending[0]` — the web lead — now also carries `lead_outcomes`, up to six of
the same priced rungs, which only the web page reads.

Why a new field and not a wider `top_outcomes`: the app's `EntertainmentView`
prints `topOutcomes.prefix(isLead ? 5 : 3)`, so a wider shared field grows every
installed iPhone's lead from three rows to five. Pinned here:

* the rungs are the priced, non-withheld legs in price order (#6255, #8083) —
  six is a ceiling, never a pad — and `top_outcomes` is their prefix;
* NATIVE CONTROL: every served row other than the added key is byte-identical
  to what `_market_row`'s default builds, so `top_outcomes`, `outcome_count`
  and which markets trend are unchanged;
* only `trending[0]` carries the key, nowhere else in the payload;
* OLD CLIENTS: the app's `EntMarketRow` decodes an explicit key list that does
  not name it, so every shipped build ignores it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pathlib

import pytest

from app.routes import entertainment as ent

REPO = pathlib.Path(__file__).resolve().parents[2]

FIXED_NOW = datetime(2026, 10, 22, 3, 52, 0, tzinfo=timezone.utc)
FRESH = FIXED_NOW - timedelta(minutes=20)


def _leg(idx, name, prob):
    return SimpleNamespace(
        id=idx, name=name, current_probability=prob, rank=idx, last_updated=FRESH,
        is_winner=False, resolution_source=None, probability_change_24h=None,
        previous_probability=None,
    )


def _market(mid, ext, name, legs, *, category="entertainment"):
    return SimpleNamespace(
        id=mid, name=name, source="kalshi", external_id=ext, outcomes=legs,
        status="open", llm_sport_category=category, group_id=None,
        volume=100_000, volume_24h=59_000,
        resolution_date=datetime(2027, 12, 31, tzinfo=timezone.utc),
        market_metadata=None, image_url=None, hook_description=None,
        market_tier=2, event_id=None, updated_at=FRESH, created_at=FRESH,
    )


#: The production lead's top of field (`KXOSCARPIC-27`, read 2026-10-22 04:08Z
#: from `/api/futures/6173044`), with an UNPRICED leg and a WITHHELD leg placed
#: inside the six-slot window so the ceiling cannot be met by padding.
OSCAR_LEGS = [
    _leg(101, "The Odyssey", 0.455),
    _leg(102, "You Can See Everything", 0.245),
    _leg(103, "The Black Ball", 0.165),
    _leg(104, "Dune: Part Three", 0.095),
    _leg(105, "Unpriced Picture", None),
    _leg(106, "Withheld Picture", 0.04),
    _leg(107, "Wild Horse Nine", 0.025),
    _leg(108, "Artificial", 0.015),
    _leg(109, "Eighth Priced", 0.01),
    _leg(110, "Ninth Priced", 0.005),
]
WITHHELD = {106}


def oscar():
    return _market(6173044, "KXOSCARPIC-27", "Oscar Winner: Best Picture", list(OSCAR_LEGS))


def four_way():
    return _market(
        108264, "KXSPEED-100M", "When will IShowSpeed reach 100 million Youtube subscribers?",
        [_leg(201, "A", 0.40), _leg(202, "B", 0.30), _leg(203, "C", 0.20), _leg(204, "D", 0.10)],
    )


def binary():
    return _market(56775492, "KXBRADYWWE-28", "Tom Brady to fight in the WWE before 2028",
                   [_leg(301, "Yes", 0.50)])


def _db(markets):
    result_obj = MagicMock()
    result_obj.scalars.return_value.unique.return_value.all.return_value = list(markets)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result_obj)
    return db


async def _entertainment(markets, withheld=frozenset()):
    with patch("app.routes.entertainment.datetime") as dt, \
            patch.object(ent, "_withheld_price_outcome_ids",
                         AsyncMock(return_value=set(withheld))):
        dt.now.return_value = FIXED_NOW
        return await ent.get_entertainment(_db(markets))


def _trending(payload, market_id):
    rows = [r for r in payload["trending"] if r["market_id"] == market_id]
    assert len(rows) == 1, f"{market_id} not served once in trending: {payload['trending']}"
    return rows[0]


def _payload_rows(node):
    """Every dict in the payload, depth first."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _payload_rows(v)
    elif isinstance(node, list):
        for v in node:
            yield from _payload_rows(v)


@pytest.mark.asyncio
class TestTheLeadRowCarriesSixPricedRungs:
    async def test_a_wide_lead_serves_its_six_priced_rungs_in_price_order(self):
        payload = await _entertainment([oscar(), four_way(), binary()], WITHHELD)
        lead = payload["trending"][0]
        assert lead["market_id"] == 6173044, "fixture: the Oscar field must lead"
        assert [o["name"] for o in lead["lead_outcomes"]] == [
            "The Odyssey", "You Can See Everything", "The Black Ball",
            "Dune: Part Three", "Wild Horse Nine", "Artificial",
        ]
        assert [o["prob"] for o in lead["lead_outcomes"]] == [45.5, 24.5, 16.5, 9.5, 2.5, 1.5]
        # The shared field keeps its three, as their prefix.
        assert lead["lead_outcomes"][:3] == lead["top_outcomes"]
        assert len(lead["top_outcomes"]) == 3
        # Arity is the ladder's, not either slice's.
        assert lead["outcome_count"] == len(OSCAR_LEGS)

    async def test_the_unpriced_and_withheld_legs_never_fill_a_slot(self):
        payload = await _entertainment([oscar(), four_way(), binary()], WITHHELD)
        names = {o["name"] for o in payload["trending"][0]["lead_outcomes"]}
        assert "Unpriced Picture" not in names
        assert "Withheld Picture" not in names

    async def test_six_is_a_ceiling_never_a_pad(self):
        payload = await _entertainment([four_way()])
        lead = payload["trending"][0]
        assert lead["market_id"] == 108264, "fixture: the four-way must lead"
        assert len(lead["lead_outcomes"]) == 4
        payload = await _entertainment([binary()])
        assert len(payload["trending"][0]["lead_outcomes"]) == 1


@pytest.mark.asyncio
class TestTheSharedPayloadDoesNotMove:
    """The control the app depends on: nothing it reads changes."""

    async def test_every_trending_row_is_the_default_row_plus_one_key(self):
        markets = [oscar(), four_way(), binary()]
        payload = await _entertainment(markets, WITHHELD)
        default = {
            m.id: ent._market_row(m, withheld_ids=WITHHELD) for m in markets
        }
        assert len(payload["trending"]) == 3
        for i, row in enumerate(payload["trending"]):
            served = {k: v for k, v in row.items() if k != "lead_outcomes"}
            assert served == default[row["market_id"]], f"trending[{i}] moved"

    async def test_the_same_markets_trend_in_the_same_order(self):
        markets = [oscar(), four_way(), binary()]
        payload = await _entertainment(markets, WITHHELD)
        rows = [ent._market_row(m, withheld_ids=WITHHELD) for m in markets]
        assert [r["market_id"] for r in payload["trending"]] == [
            r["market_id"] for r in ent._build_trending(rows)
        ]

    async def test_only_the_lead_row_carries_the_key_anywhere_in_the_payload(self):
        """Side cards, `cultural_moments` and `themes` never see it.

        On this fixture the Oscar field is ALSO served in `cultural_moments`
        and the four-way in `themes.tech_culture`, so a key added by the
        shared builder `_market_row`, or on every trending row, reddens here.
        """
        payload = await _entertainment([oscar(), four_way(), binary()], WITHHELD)
        cultural = [r for r in payload["cultural_moments"] if r["market_id"] == 6173044]
        tech = [r for r in payload["themes"]["tech_culture"]["markets"]
                if r["market_id"] == 108264]
        assert len(cultural) == 1 and len(tech) == 1, "fixture no longer reaches both sections"
        carriers = [r for r in _payload_rows(payload) if "lead_outcomes" in r]
        assert carriers == [payload["trending"][0]]


class TestShippedAppsIgnoreTheKey:
    """Source control for old and current app builds.

    `EntMarketRow` is `Decodable` with an explicit `CodingKeys` list, and the
    app's decoder maps snake_case to camelCase, so `lead_outcomes` would only be
    read by a build that names `leadOutcomes`. No build does; the lead reads
    `topOutcomes`, which the class above pins as unchanged.
    """

    SWIFT = REPO / "ios" / "Bain Luck" / "Bain Luck"

    def test_the_app_row_model_does_not_name_the_key(self):
        src = (self.SWIFT / "Models" / "CategoryModels.swift").read_text()
        start = src.index("struct EntMarketRow: Decodable")
        body = src[start: src.index("\n}\n", start)]
        assert "case q, prob, src, marketId, externalId, kind, topOutcomes, outcomeCount" in body
        assert "leadOutcomes" not in body
        assert "init(from" not in body, "a hand-written decoder must be re-read for the key"

    def test_the_app_lead_reads_the_shared_field(self):
        src = (self.SWIFT / "Views" / "EntertainmentView.swift").read_text()
        assert "let outcomes = m.topOutcomes" in src
        assert "leadOutcomes" not in src
