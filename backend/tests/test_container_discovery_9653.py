"""#9653 — readers find the right published NFL-week / MLB-postseason hub.

SHIP: readers find the correct published NFL-week/MLB-playoff hub from
Search/Browse/Discover (#9653, paired #9652 under #9217). Pillar: MATCHING /
DISCOVER.

What is pinned here, against ``app.services.container_discovery``:

* **off means nothing** — the producer's own switch, and the hub's switch
  (a card whose hub 404s is a dead link), each yield no card and no read;
  an un-migrated database yields no card and says why;
* **eligible only** — unpublished, withdrawn, unknown-state, nested, empty and
  wrong-edition collections are refused by the pure check even when the SQL
  returns them (a drifted query can only offer fewer, never a wrong one);
* **one identity, one destination** — the card's ``edition`` and
  ``destination`` are #9636's, byte for byte, for the same slug;
* **bounded** — two statements for one game and for five hundred; inputs are
  capped and the truncation is reported;
* **relevance, not a slot** — given games, only collections containing one of
  them come back, and ``matched_event_ids`` says which;
* **the handoff contract** — the representative fixtures the consumers build
  against are exactly what the producer emits.

The SQL's own filtering and aggregation are graded on real Postgres in
``tests/integration/test_container_discovery_real_postgres.py``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services import container_discovery as discovery
from app.utils.container_presentation import container_destination, edition_for_slug

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "container_discovery_9653"
HUB_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "container_hub_9636"

WINDOW_START = datetime(2026, 10, 1, 17, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 10, 8, 17, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# The session double
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _Session:
    """Answers the schema probe and the aggregate read; records every statement."""

    def __init__(self, rows=(), *, migrated=True):
        self.rows = list(rows)
        self.migrated = migrated
        self.statements = []
        self.params = []

    async def execute(self, sql, params=None):
        text_ = str(sql)
        self.statements.append(text_)
        self.params.append(params)
        if "to_regclass('public.container_corrections')" in text_:
            return _Result([(self.migrated, self.migrated)])
        if text_.startswith("WITH hub AS"):
            return _Result(self.rows)
        raise AssertionError(f"unexpected statement: {text_[:120]}")


def _row(
    slug="nfl-2026-week-5",
    *,
    id=70,
    name="NFL 2026 · Week 5",
    status="live",
    parent=None,
    publication="published",
    revision=4,
    games=4,
    questions=1,
    matched=(),
):
    """One row of the aggregate read, in ``_COLUMNS`` order."""
    return (
        id, name, slug, status, WINDOW_START, WINDOW_END,
        parent, publication, revision, games, questions, list(matched),
    )


def _as_dict(raw):
    return dict(zip(discovery._COLUMNS, raw))


@pytest.fixture
def switches_on(monkeypatch):
    monkeypatch.setenv("CONTAINER_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")


# ---------------------------------------------------------------------------
# Off means nothing
# ---------------------------------------------------------------------------


class TestOffMeansNothing:
    async def test_discovery_switch_off_reads_nothing(self, monkeypatch):
        monkeypatch.delenv("CONTAINER_DISCOVERY_ENABLED", raising=False)
        monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
        session = _Session([_row()])
        read = await discovery.discover_collections(session, event_ids=[501])
        assert read.collections == []
        assert read.reason == discovery.REASON_DISABLED
        assert session.statements == []

    async def test_hub_switch_off_reads_nothing(self, monkeypatch):
        """A card whose hub serves 404 is a dead link, so the hub's switch gates it."""
        monkeypatch.setenv("CONTAINER_DISCOVERY_ENABLED", "true")
        monkeypatch.setenv("CONTAINERS_READ_ENABLED", "false")
        session = _Session([_row()])
        read = await discovery.discover_collections(session, event_ids=[501])
        assert read.collections == []
        assert read.reason == discovery.REASON_HUB_DISABLED
        assert session.statements == []

    async def test_default_is_off(self, monkeypatch):
        monkeypatch.delenv("CONTAINER_DISCOVERY_ENABLED", raising=False)
        assert discovery.container_discovery_enabled() is False

    async def test_unmigrated_database_offers_nothing_and_says_why(self, switches_on):
        session = _Session([_row()], migrated=False)
        read = await discovery.discover_collections(session)
        assert read.collections == []
        assert read.reason == discovery.REASON_SCHEMA_ABSENT
        assert len(session.statements) == 1  # the probe; no aggregate read

    async def test_explicit_empty_inputs_read_nothing(self, switches_on):
        session = _Session([_row()])
        assert (await discovery.discover_collections(session, event_ids=[])).collections == []
        assert (await discovery.discover_collections(session, slugs=[])).collections == []
        assert session.statements == []

    async def test_unknown_league_offers_nothing(self, switches_on):
        session = _Session([_row()])
        read = await discovery.discover_collections(session, league="nba")
        assert read.collections == []
        assert session.statements == []


# ---------------------------------------------------------------------------
# Eligible only — the pure check, row by row
# ---------------------------------------------------------------------------


class TestEligibility:
    def test_published_root_nfl_week_is_offered(self):
        card, excluded = discovery.collection_card(_as_dict(_row()))
        assert excluded is None
        assert card["type"] == "collection"
        assert card["slug"] == "nfl-2026-week-5"
        assert card["revision"] == 4
        assert card["game_count"] == 4 and card["question_count"] == 1

    def test_published_mlb_postseason_is_offered(self):
        card, excluded = discovery.collection_card(
            _as_dict(_row("mlb-2026-postseason", name="MLB 2026 · Postseason"))
        )
        assert excluded is None
        assert card["edition"]["kind"] == "mlb_postseason"

    @pytest.mark.parametrize("state", ["unpublished", "withdrawn", "draft", None, "PUBLISHED"])
    def test_anything_but_published_is_refused(self, state):
        card, excluded = discovery.collection_card(_as_dict(_row(publication=state)))
        assert card is None
        assert excluded == discovery.EXCLUDED_NOT_PUBLISHED

    def test_a_nested_collection_is_refused(self):
        card, excluded = discovery.collection_card(_as_dict(_row(parent=12)))
        assert card is None
        assert excluded == discovery.EXCLUDED_NESTED

    @pytest.mark.parametrize(
        "slug",
        [
            "nfl-2026",  # a season: identity, but no hub this ship offers
            "nfl-2026-week-05",  # the adapter would never write it
            "nfl-2026-playoffs-week-1",  # unknown stage
            "mlb-2026-world-series",
            "us-open-2026",
            "",
        ],
    )
    def test_wrong_edition_is_refused(self, slug):
        card, excluded = discovery.collection_card(_as_dict(_row(slug)))
        assert card is None
        assert excluded == discovery.EXCLUDED_WRONG_EDITION

    def test_league_and_season_filters_refuse_other_editions(self):
        row = _as_dict(_row("nfl-2025-week-5"))
        assert discovery.collection_card(row, league="mlb") == (None, discovery.EXCLUDED_WRONG_EDITION)
        assert discovery.collection_card(row, season=2026) == (None, discovery.EXCLUDED_WRONG_EDITION)
        card, _ = discovery.collection_card(row, league="nfl", season=2025)
        assert card is not None

    def test_empty_collection_is_refused(self):
        card, excluded = discovery.collection_card(_as_dict(_row(games=0, questions=0)))
        assert card is None
        assert excluded == discovery.EXCLUDED_EMPTY

    def test_relevance_mode_refuses_a_collection_with_none_of_the_games(self):
        card, excluded = discovery.collection_card(_as_dict(_row()), matched_required=True)
        assert card is None
        assert excluded == discovery.EXCLUDED_NOT_MATCHED

    async def test_a_drifted_query_can_only_offer_fewer(self, switches_on):
        """The SQL returned rows it should not have; none of them reaches a reader."""
        rows = [
            _row(),
            _row("nfl-2026-week-6", id=71, publication="withdrawn"),
            _row("nfl-2026-week-7", id=72, parent=70),
            _row("nfl-2026", id=73),
            _row("nfl-2026-week-8", id=74, games=0, questions=0),
        ]
        read = await discovery.discover_collections(_Session(rows))
        assert [c["id"] for c in read.collections] == [70]
        assert read.excluded == {
            discovery.EXCLUDED_NOT_PUBLISHED: 1,
            discovery.EXCLUDED_NESTED: 1,
            discovery.EXCLUDED_WRONG_EDITION: 1,
            discovery.EXCLUDED_EMPTY: 1,
        }


# ---------------------------------------------------------------------------
# One identity, one destination
# ---------------------------------------------------------------------------


class TestOneIdentityOneDestination:
    @pytest.mark.parametrize(
        "slug", ["nfl-2026-week-5", "nfl-2026-postseason-week-2", "mlb-2026-postseason"]
    )
    def test_edition_and_destination_are_the_hubs(self, slug):
        card, _ = discovery.collection_card(_as_dict(_row(slug)))
        assert card["edition"] == edition_for_slug(slug)
        assert card["destination"] == container_destination(slug)
        assert card["destination"]["api"] == f"/api/containers/{slug}"
        # #9886: Search's entry opens the web hub, the same page a nested child opens.
        assert card["destination"]["web"] == f"/collections/{slug}"

    @pytest.mark.parametrize(
        "fixture", ["representative_nfl_week.json", "representative_mlb_postseason.json"]
    )
    def test_card_names_the_hub_the_9636_fixture_serves(self, fixture):
        """Against #9636's banked hub payload: same slug, edition, revision, name."""
        hub = json.loads((HUB_FIXTURE_DIR / fixture).read_text())["response"]
        head = hub["container"]
        card, _ = discovery.collection_card(
            _as_dict(
                _row(
                    hub["slug"],
                    id=head["id"],
                    name=head["name"],
                    status=head["status"],
                    revision=hub["revision"],
                )
            )
        )
        assert card["slug"] == hub["slug"]
        assert card["edition"] == hub["edition"]
        assert card["revision"] == hub["revision"]
        assert card["name"] == head["name"]
        assert card["destination"]["api"] == f"/api/containers/{hub['slug']}"


# ---------------------------------------------------------------------------
# Bounded
# ---------------------------------------------------------------------------


class TestBounded:
    async def test_two_statements_for_one_game_and_for_five_hundred(self, switches_on):
        one = _Session([_row(matched=[501])])
        many = _Session([_row(matched=[501])])
        await discovery.discover_collections(one, event_ids=[501])
        await discovery.discover_collections(many, event_ids=range(1, 501))
        assert len(one.statements) == len(many.statements) == 2

    async def test_inputs_are_capped_and_truncation_is_reported(self, switches_on):
        session = _Session([_row(matched=[1])])
        read = await discovery.discover_collections(
            session, event_ids=range(1, 701), slugs=[f"nfl-2026-week-{w}" for w in range(1, 61)]
        )
        params = session.params[-1]
        assert len(params["event_ids"]) == discovery.MAX_EVENT_IDS
        assert len(params["slugs"]) == discovery.MAX_SLUGS
        assert read.truncated == {"event_ids": 700, "slugs": 60}

    async def test_limit_is_clamped(self, switches_on):
        session = _Session([])
        await discovery.discover_collections(session, limit=10_000)
        assert session.params[-1]["limit"] == discovery.MAX_COLLECTIONS
        await discovery.discover_collections(session, limit=0)
        assert session.params[-1]["limit"] == 1

    def test_every_value_is_a_bind_parameter(self):
        """Gotcha #45: the statement is fixed fragments; no input reaches the text."""
        sql = discovery._discovery_sql(by_slug=True, by_prefix=True, by_season=True, by_events=True)
        for name in (":slugs", ":slug_prefix", ":season_token", ":event_ids", ":slug_pattern", ":limit"):
            assert name in sql
        assert "LIKE" not in sql

    async def test_filters_reach_the_statement(self, switches_on):
        session = _Session([])
        await discovery.discover_collections(session, league="nfl", season=2026, event_ids=[5])
        sql, params = session.statements[-1], session.params[-1]
        assert params["slug_prefix"] == "nfl-"
        assert params["season_token"] == "2026"
        assert params["event_ids"] == [5]
        assert "c.publication_state = 'published'" in sql
        assert "c.parent_container_id IS NULL" in sql
        assert "<> 'withdrawn'" in sql


# ---------------------------------------------------------------------------
# Relevance, not a slot
# ---------------------------------------------------------------------------


class TestRelevance:
    async def test_matched_games_are_named_and_order_is_the_querys(self, switches_on):
        rows = [
            _row("nfl-2026-week-5", id=70, matched=[503, 501]),
            _row("nfl-2026-week-6", id=71, matched=[510]),
        ]
        read = await discovery.discover_collections(_Session(rows), event_ids=[501, 503, 510])
        assert [c["id"] for c in read.collections] == [70, 71]
        assert read.collections[0]["matched_event_ids"] == [501, 503]

    async def test_no_games_matched_no_card(self, switches_on):
        read = await discovery.discover_collections(_Session([_row(matched=[])]), event_ids=[999])
        assert read.collections == []
        assert read.excluded == {discovery.EXCLUDED_NOT_MATCHED: 1}


# ---------------------------------------------------------------------------
# The handoff contract
# ---------------------------------------------------------------------------

_REPRESENTATIVE = {
    "search_by_games.json": {
        "request": "discover_collections(session, event_ids=[501, 502, 503])",
        "rows": [_row("nfl-2026-week-5", matched=[501, 502])],
        "kwargs": {"event_ids": [501, 502, 503]},
    },
    "browse_mlb.json": {
        "request": "discover_collections(session, league='mlb', season=2026)",
        "rows": [
            _row(
                "mlb-2026-postseason",
                id=81,
                name="MLB 2026 · Postseason",
                status="scheduled",
                revision=2,
                games=9,
                questions=6,
            )
        ],
        "kwargs": {"league": "mlb", "season": 2026},
    },
}


def _payload(read):
    return {
        "collections": read.collections,
        "reason": read.reason,
        "excluded": read.excluded,
        "truncated": read.truncated,
    }


class TestHandoffContract:
    @pytest.mark.parametrize("name", sorted(_REPRESENTATIVE))
    async def test_fixture_is_what_the_producer_emits(self, name, switches_on):
        spec = _REPRESENTATIVE[name]
        read = await discovery.discover_collections(_Session(spec["rows"]), **spec["kwargs"])
        produced = json.loads(json.dumps(_payload(read)))
        path = FIXTURE_DIR / name
        if os.getenv("BL_WRITE_9653_FIXTURES") == "1":
            FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "_representative": (
                            "REPRESENTATIVE FIXTURE for #9653/#9652 — the producer's output "
                            "for test rows; NOT production data. Regenerate with "
                            "BL_WRITE_9653_FIXTURES=1 (backend/tests/test_container_discovery_9653.py)."
                        ),
                        "request": spec["request"],
                        "response": produced,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
        banked = json.loads(path.read_text())
        assert banked["response"] == produced

    async def test_card_carries_the_fields_every_consumer_keys_on(self, switches_on):
        read = await discovery.discover_collections(_Session([_row()]))
        card = read.collections[0]
        # Search results are labelled by `text` and dispatched on `type`; a
        # client that does not know "collection" skips it like any unknown type.
        assert card["type"] == discovery.CARD_TYPE and card["text"] == card["name"]
        assert set(card["destination"]) == {"kind", "slug", "web", "api"}
        json.dumps(card)  # serializable as served


class TestSqlPatternAgreesWithTheAdapters:
    def test_the_prefilter_admits_exactly_the_discoverable_editions(self):
        """The SQL pre-filter and ``edition_for_slug`` must agree on every slug
        shape, or a slug the adapters never write spends the LIMIT (it did, on
        real Postgres, with ``week-09``). Python's ``re`` reads this POSIX
        pattern identically."""
        import re

        pattern = re.compile(discovery.DISCOVERABLE_SLUG_PATTERN)
        slugs = [
            f"nfl-{season}-{stage}week-{week}"
            for season in (2025, 2026)
            for stage in ("", "preseason-", "postseason-", "playoffs-")
            for week in ("0", "1", "01", "5", "09", "10", "18", "22", "99", "100")
        ] + ["mlb-2026-postseason", "mlb-26-postseason", "nfl-2026", "mlb-2026", "nfl-2026-week-"]
        for slug in slugs:
            edition = edition_for_slug(slug)
            offered = edition is not None and edition["kind"] in discovery.DISCOVERABLE_EDITIONS
            assert bool(pattern.match(slug)) == offered, slug
