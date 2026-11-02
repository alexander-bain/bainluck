"""A curated publication is previewed, atomic, exact, and revocable."""

import json

import pytest

from scripts import collection_publication as operator
from app.utils.midterms_collection import MANIFEST, MANIFEST_PATH, MARKET_IDS
from tests.test_collection_publication_operator import Result, Session


class CuratedSession(Session):
    def __init__(self):
        super().__init__(
            slug="midterms-2026",
            revision=0,
            edge_count=0,
            game_count=0,
            question_count=15,
            name="Midterms 2026",
            kind="theme",
        )
        self.exists = False
        self.edges = []
        self.extra_members = []
        self.children = 0

    async def execute(self, sql, params=None):
        statement = str(sql)
        if statement.startswith("SELECT pg_advisory_xact_lock"):
            return Result()
        if statement.startswith("SELECT id, kind, name, slug"):
            return Result([self.facts] if self.exists else [])
        if statement.startswith("SELECT child_id, class"):
            return Result(self.edges)
        if statement.startswith("SELECT child_type, child_id, class"):
            return Result(
                [("market", mid, section) for mid, section in self.edges]
                + self.extra_members
            )
        if statement.startswith("SELECT count(*) FROM containers"):
            return Result([(self.children,)])
        if statement.startswith("INSERT INTO containers"):
            self.exists = True
            return Result([(101,)])
        if statement.startswith("INSERT INTO event_edges"):
            self.edges.append((params["mid"], params["section"]))
            self.facts["edge_count"] += 1
            return Result()
        return await super().execute(sql, params)


def args(apply=False):
    result = [
        "--slug",
        "midterms-2026",
        "--curated-manifest",
        str(MANIFEST_PATH),
        "--operation",
        "publish",
        "--expected-revision",
        "0",
    ]
    if apply:
        result += [
            "--apply",
            "--actor",
            "Alex",
            "--reason",
            "Publish Fable's reviewed Midterms spec",
            "--evidence",
            '{"spec":"Alex 2026-11-01"}',
        ]
    return result


@pytest.fixture
def hydration(monkeypatch):
    async def load(db, ids):
        cards = {
            mid: {
                "id": mid,
                "name": f"Market {mid}",
                "source": "kalshi",
                "top_outcomes": [
                    {"name": "Republican", "probability": 0.6},
                    {"name": "Democratic", "probability": 0.4},
                ],
                "status": "open",
            }
            for mid in MARKET_IDS
        }
        cards[112905]["source"] = "polymarket"
        return (
            cards,
            {},
            [
                {
                    "market_id": 109085,
                    "name": "Maine Senate winner?",
                    "twin_state": "no_twin_found",
                    "polymarket_twin_ids": [],
                }
            ],
        )

    monkeypatch.setattr(operator, "load_midterms_cards", load, raising=False)


@pytest.mark.asyncio
async def test_curated_preview_accepts_reviewed_list_without_creating_rows(hydration):
    session = CuratedSession()
    receipt, code = await operator.run(operator.parse_args(args()), lambda: session)
    assert code == 0, receipt
    assert receipt["hand_curated_accepted"] is True
    assert receipt["twin_report"][0]["twin_state"] == "no_twin_found"
    assert session.exists is False
    assert session.commits == 0


@pytest.mark.asyncio
async def test_curated_apply_creates_fifteen_edges_and_uses_existing_publication_ledger(
    hydration,
):
    session = CuratedSession()
    receipt, code = await operator.run(operator.parse_args(args(True)), lambda: session)
    assert code == 0, receipt
    assert receipt["committed"] is True
    assert receipt["rollback"]["operation"] == "withdraw"
    assert len(session.edges) == 15
    assert session.facts["publication_state"] == "published"
    assert len(session.ledger) == 1
    assert session.commits == 1


def test_unreviewed_member_list_is_refused_before_database_access(tmp_path):
    changed = json.loads(json.dumps(MANIFEST))
    changed["sections"][2]["market_ids"].append(999)
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed))
    argv = args()
    argv[argv.index(str(MANIFEST_PATH))] = str(path)
    with pytest.raises(operator.OperatorRefused, match="reviewed Midterms"):
        operator.parse_args(argv)


@pytest.mark.asyncio
@pytest.mark.parametrize("extra_member,children", [(True, 0), (False, 1)])
async def test_curated_publish_refuses_non_market_members_or_nested_children(
    hydration, extra_member, children
):
    session = CuratedSession()
    session.exists = True
    session.edges = [
        (mid, s["key"]) for s in MANIFEST["sections"] for mid in s["market_ids"]
    ]
    if extra_member:
        session.extra_members = [("event", 123, "match_winner")]
    session.children = children
    receipt, code = await operator.run(operator.parse_args(args()), lambda: session)
    assert code == 1, receipt
    assert session.commits == 0


#: Production 2026-11-02: Kalshi 108619 and Polymarket 112905 as the venues name and price them.
KALSHI_BALANCE = {"Democrats sweep": 0.735, "D-House, R-Senate": 0.225, "Republicans sweep": 0.058,
                  "R-House, D-Senate": 0.007}
POLYMARKET_BALANCE = {"Democrats Sweep": 0.725, "R Senate, D House": 0.215, "Republicans Sweep": 0.045,
                      "D Senate, R House": 0.0065, "Other": 0.0005}


def _balance(hydration_cards, kalshi, polymarket):
    hydration_cards[108619]["top_outcomes"] = [{"name": n, "probability": p} for n, p in kalshi.items()]
    hydration_cards[112905]["top_outcomes"] = [{"name": n, "probability": p} for n, p in polymarket.items()]


def _members():
    return [
        {"id": mid, "type": "market", "class": s["key"], "source": "human"}
        for s in MANIFEST["sections"]
        for mid in s["market_ids"]
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("polymarket,refusal", [
    # Production: the 0.05% "Other" only Polymarket lists is dropped; the venues align.
    (POLYMARKET_BALANCE, None),
    # A 1% "Other" would be a visible number the card hides: refused on its own terms.
    ({**POLYMARKET_BALANCE, "Other": 0.01}, "at 1% or more that the primary does not: ['Other']"),
    # A real misalignment still refuses: Polymarket missing a split.
    ({n: p for n, p in POLYMARKET_BALANCE.items() if n != "D Senate, R House"}, "cannot align"),
])
async def test_the_venues_real_balance_outcomes_align(hydration, monkeypatch, polymarket, refusal):
    from app.utils.midterms_collection import present_midterms_sections

    real_load = operator.load_midterms_cards
    loaded = {}

    async def load(db, ids):
        cards, twins, report = await real_load(db, ids)
        _balance(cards, KALSHI_BALANCE, polymarket)
        loaded.update(cards)
        return cards, twins, report

    monkeypatch.setattr(operator, "load_midterms_cards", load, raising=False)
    session = CuratedSession()
    receipt, code = await operator.run(operator.parse_args(args()), lambda: session)
    if refusal is not None:
        assert code == 1 and refusal in receipt["error"], receipt
        return
    assert code == 0, receipt
    sections, _ = present_midterms_sections(_members(), loaded)
    (served,) = [m["card"] for s in sections for m in s["members"] if m["id"] == 108619]
    assert sorted(o["name"] for o in served["top_outcomes"]) == sorted(KALSHI_BALANCE)
    assert served["outcome_count"] == 4
