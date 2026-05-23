from argparse import Namespace
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
import json

from sqlalchemy.dialects import postgresql

from scripts.export_discover_labeling_batch import (
    ITEM_FIELDS,
    PAIR_FIELDS,
    attach_batch_id,
    build_batch_metadata,
    build_candidate_statement,
    build_pairwise_rows,
    format_candidate_row,
    select_labeling_items,
    write_rows,
)


NOW = datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)


def test_build_candidate_statement_dedupes_groups_and_joins_outcomes():
    statement = build_candidate_statement(
        updated_since=NOW,
        candidate_pool_limit=100,
        statuses=("open",),
        sources=("kalshi", "polymarket"),
        categories=("politics",),
        min_volume_24h=100,
    )
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "futures_markets" in compiled
    assert "futures_outcomes" in compiled
    assert "row_number() OVER" in compiled
    assert "PARTITION BY coalesce(futures_markets.group_id" in compiled
    assert "candidates.dedup_rank = 1" in compiled
    assert "futures_markets.status IN ('open')" in compiled
    assert "futures_markets.source IN ('kalshi', 'polymarket')" in compiled
    assert "coalesce(futures_markets.llm_sport_category" in compiled
    assert "futures_markets.volume_24h >= 100" in compiled
    assert "array_agg(futures_outcomes.name)" in compiled


def test_format_candidate_row_adds_quality_and_interestingness_fields():
    row = {
        "market_id": 42,
        "source": "kalshi",
        "external_id": "KXOPENAI",
        "group_id": "story:ai",
        "name": "Will OpenAI release GPT-5 before July?",
        "category": "tech",
        "llm_sport_category": "tech",
        "market_type": "binary",
        "market_tier": 5,
        "status": "open",
        "leader_name": "Yes",
        "leader_probability": Decimal("0.680000"),
        "outcome_count": 2,
        "source_count": 2,
        "updated_at": NOW,
        "resolution_date": NOW,
        "volume_24h": Decimal("25000"),
        "movement_24h": Decimal("0.120000"),
        "image_url": "https://example.com/image.jpg",
        "hook_description": "A product timing market.",
        "outcome_names": ["Yes", "No"],
        "category_recent_count": 12,
        "category_feed_share": 0.12,
        "market_metadata": {
            "discover_llm": {
                "topic": "AI",
                "subtopic": "models",
                "archetype": "tech_frontier",
                "audience_scope": "broad",
                "salience_score": 0.8,
                "junk_flags": [],
            }
        },
    }

    formatted = format_candidate_row(row, now=NOW)

    assert formatted["candidate_id"] == "futures:42"
    assert formatted["leader_probability"] == 0.68
    assert formatted["movement_24h"] == 0.12
    assert formatted["category"] == "tech"
    assert formatted["llm_topic"] == "AI"
    assert formatted["quality_class"] == "compelling"
    assert "compelling_topic" in formatted["quality_reasons"]
    assert formatted["interestingness_score"] > 70
    assert formatted["card_snapshot"] == ""
    assert formatted["human_label"] == ""


def test_select_labeling_items_is_seeded_and_stable():
    rows = [
        {
            "candidate_id": f"futures:{idx}",
            "interestingness_score": 100 - idx,
            "category": "tech",
        }
        for idx in range(30)
    ]

    first = select_labeling_items(rows, limit=10, seed="seed-a")
    second = select_labeling_items(rows, limit=10, seed="seed-a")
    other = select_labeling_items(rows, limit=10, seed="seed-b")

    assert [row["candidate_id"] for row in first] == [
        row["candidate_id"] for row in second
    ]
    assert [row["candidate_id"] for row in first] != [
        row["candidate_id"] for row in other
    ]
    assert len(first) == 10
    assert len({row["candidate_id"] for row in first}) == 10


def test_batch_metadata_is_deterministic_and_counts_rows():
    rows = [
        {
            "candidate_id": "futures:1",
            "category": "tech",
            "quality_class": "compelling",
            "interestingness_score": 88.0,
        },
        {
            "candidate_id": "futures:2",
            "category": "politics",
            "quality_class": "normal",
            "interestingness_score": 55.0,
        },
    ]
    args = Namespace(
        output="/tmp/items.csv",
        metadata_output="/tmp/items.metadata.json",
        pairs_output="/tmp/items.pairs.csv",
        print_sql=False,
        format="csv",
        limit=2,
        seed="seed-a",
    )

    first = build_batch_metadata(
        args=args,
        rows=rows,
        pairs=[],
        updated_since=NOW,
        generated_at=NOW,
    )
    second = build_batch_metadata(
        args=args,
        rows=rows,
        pairs=[],
        updated_since=NOW,
        generated_at=NOW,
    )

    assert first["batch_id"] == second["batch_id"]
    assert first["row_count"] == 2
    assert first["category_counts"] == {"politics": 1, "tech": 1}
    assert first["quality_counts"] == {"compelling": 1, "normal": 1}
    assert "output" not in first["params"]


def test_build_pairwise_rows_is_deterministic_and_uses_batch_id():
    rows = attach_batch_id(
        [
            {
                "candidate_id": "futures:1",
                "name": "A",
                "category": "tech",
                "interestingness_score": 90,
            },
            {
                "candidate_id": "futures:2",
                "name": "B",
                "category": "tech",
                "interestingness_score": 80,
            },
            {
                "candidate_id": "futures:3",
                "name": "C",
                "category": "politics",
                "interestingness_score": 70,
            },
        ],
        batch_id="dlb_test",
    )

    first = build_pairwise_rows(rows, batch_id="dlb_test", pair_count=3, seed="seed-a")
    second = build_pairwise_rows(rows, batch_id="dlb_test", pair_count=3, seed="seed-a")

    assert first == second
    assert first
    assert all(pair["batch_id"] == "dlb_test" for pair in first)
    assert all(pair["row_type"] == "pair" for pair in first)
    assert {pair["pair_strategy"] for pair in first}
    snapshot = json.loads(rows[0]["card_snapshot"])
    assert snapshot["schema_version"] == "discover-card-v1"
    assert snapshot["batch_id"] == "dlb_test"


def test_write_rows_supports_item_csv_and_pair_jsonl():
    item_handle = StringIO()
    write_rows(
        [{"batch_id": "dlb_test", "candidate_id": "futures:1", "name": "Market"}],
        item_handle,
        fmt="csv",
        fields=ITEM_FIELDS,
    )
    assert item_handle.getvalue().splitlines()[0].startswith("batch_id,row_type")
    assert "dlb_test" in item_handle.getvalue()
    assert "card_snapshot" in ITEM_FIELDS

    pair_handle = StringIO()
    write_rows(
        [{"batch_id": "dlb_test", "pair_id": "pair:1", "row_type": "pair"}],
        pair_handle,
        fmt="jsonl",
        fields=PAIR_FIELDS,
    )
    assert '"pair_id": "pair:1"' in pair_handle.getvalue()
