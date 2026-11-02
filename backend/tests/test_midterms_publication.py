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
