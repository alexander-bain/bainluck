"""#12095 Decide 37-B: the ranking eval harness — slates, event fields, sheet.

Pinned here:

* off by default: with ``RANKING_SNAPSHOTS`` unset no snapshot is taken (no
  read at all), the feed envelope has no ``ranker_version``, and an event row
  carries no slate fields (its INSERT is exactly as before);
* the features: one shape for every card type; 1h/7d movement always UNKNOWN
  (None); stale only from a known price age; a flag that does not apply is
  None, never False;
* the slate: served cards first in served order, then unserved futures; never
  more than 500 candidates; the slate id is the deck's edition;
* the writer: one row, the deploy sha, 90-day retention; a degraded or empty
  deck writes nothing; a failed pool read still stores the served order;
* the grading sheet; the admin capture refuses while off; the migration adds
  no foreign key and creates only what it says.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from starlette.requests import Request

import app.utils.ranking_slate_capture as capture_mod
from app.models.models import RankingSlateSnapshot
from app.utils.ranking_eval import (
    MAX_CANDIDATES,
    RANKER_VERSION_FIELD,
    RANKING_SNAPSHOTS_ENV,
    build_slate,
    card_features,
    grading_sheet,
    ranker_version,
    ranking_snapshots_enabled,
)
from app.utils.ranking_slate_capture import snapshot_ranking_slate

BACKEND = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 6, 12, 15, tzinfo=timezone.utc)
ON = {RANKING_SNAPSHOTS_ENV: "1", "HEROKU_SLUG_COMMIT": "abcdef1234567890"}


def futures(mid, *, prob=0.4, observed="2026-11-06T12:00:00+00:00", status="open", names=("A", "B")):
    return {
        "type": "futures",
        "score": 90,
        "headline": "h",
        "data": {
            "id": mid,
            "name": f"Market {mid}",
            "llm_sport_category": "politics",
            "status": status,
            "source_count": 2,
            "sources": ["kalshi", "polymarket"],
            "group_id": f"polymarket:{mid}",
            "resolution_date": "2026-12-31T00:00:00+00:00",
            "price_observed_at": observed,
            "top_outcomes": [
                {"name": n, "probability": prob if i == 0 else 0.1, "movement": None}
                for i, n in enumerate(names)
            ]
            if prob is not None
            else [],
        },
    }


def event(eid=7, status="live"):
    return {
        "type": "event",
        "score": 97,
        "data": {
            "id": eid,
            "home_team": "Columbus Blue Jackets",
            "away_team": "Dallas Stars",
            "sport": "icehockey_nhl",
            "sport_label": "NHL",
            "status": status,
            "commence_time": "2026-11-06T00:00:00+00:00",
            "hero_probability": 0.47,
            "win_probability_sources": {
                "kalshi": {"value": 0.465, "updated_at": "2026-11-06T12:10:00+00:00"},
                "betting": {"value": 0.48, "updated_at": "2026-11-06T12:14:00+00:00"},
                "betting_book_count": 15,
            },
        },
    }


# ── switch and version ──────────────────────────────────────────────────────


def test_the_switch_is_off_unless_set():
    assert not ranking_snapshots_enabled({})
    assert not ranking_snapshots_enabled({RANKING_SNAPSHOTS_ENV: "0"})
    assert ranking_snapshots_enabled({RANKING_SNAPSHOTS_ENV: "1"})


def test_ranker_version_is_the_sha_then_the_release_then_unknown():
    assert ranker_version({"HEROKU_SLUG_COMMIT": "abcdef1234567890"}) == "abcdef123456"
    assert ranker_version({"HEROKU_RELEASE_VERSION": "v6180"}) == "v6180"
    assert ranker_version({}) == "unknown"


# ── features ────────────────────────────────────────────────────────────────


class TestCardFeatures:
    def test_futures_features_and_unknown_movement_windows(self):
        f = card_features(futures(1), now=NOW, market_facts={1: {"movement_24h": 0.03}})
        assert f["item_key"] == "futures:1"
        assert f["title"] == "Market 1" and f["category"] == "politics"
        assert f["entities"] == ["A", "B"] and f["container"] == "polymarket:1"
        assert f["probability"] == 0.4 and f["movement_24h"] == 0.03
        assert f["movement_1h"] is None and f["movement_7d"] is None
        assert f["price_age_s"] == 900.0 and f["stale"] is False
        assert f["settled"] is False and f["blend_missing"] is False

    def test_generic_and_threshold_outcomes_are_not_entities(self):
        f = card_features(futures(5, names=("Yes", "No", "$175", "Marine Le Pen")), now=NOW)
        assert f["entities"] == ["Marine Le Pen"]

    def test_a_price_older_than_a_day_is_stale_and_unknown_age_is_not_a_pass(self):
        old = card_features(futures(1, observed="2026-11-05T11:00:00+00:00"), now=NOW)
        assert old["stale"] is True
        none = card_features(futures(1, observed=None), now=NOW)
        assert none["price_age_s"] is None and none["stale"] is None

    def test_settled_and_blend_missing(self):
        f = card_features(futures(2, prob=None, status="resolved"), now=NOW)
        assert f["settled"] is True and f["blend_missing"] is True and f["probability"] is None

    def test_event_features_spread_from_its_sources(self):
        f = card_features(event(), now=NOW)
        assert f["title"] == "Dallas Stars @ Columbus Blue Jackets"
        assert f["entities"] == ["Columbus Blue Jackets", "Dallas Stars"]
        assert f["sources"] == ["kalshi", "betting"] and f["source_count"] == 2.0
        assert f["source_spread"] == pytest.approx(0.015)
        assert f["price_age_s"] == 60.0 and f["settled"] is False

    def test_a_bundle_has_no_single_probability_so_its_flag_is_unknown(self):
        bundle = {
            "type": "bundle",
            "data": {"id": "theme:x", "title": "AI", "story_key": "story:ai", "items": [futures(3), futures(4)]},
        }
        f = card_features(bundle, now=NOW)
        assert f["category"] == "politics" and f["container"] == "story:ai"
        assert f["probability"] is None and f["blend_missing"] is None

    def test_concept_and_tournament_key_by_their_key(self):
        concept = {"type": "concept", "data": {"key": "event:ufc:1", "name": "UFC", "domain": "ufc", "status": "upcoming"}}
        assert card_features(concept, now=NOW)["category"] == "mma"
        tour = {"type": "tournament", "data": {"key": "t1", "name": "Open", "golfers": [{"name": "G", "probability": 0.2}], "champion": None}}
        f = card_features(tour, now=NOW)
        # No champion and no schedule status: settled is UNKNOWN, never False.
        assert f["item_key"] == "tournament:t1" and f["probability"] == 0.2 and f["settled"] is None
        assert f["settled_without_result"] is None
        running = card_features({**tour, "data": {**tour["data"], "schedule_status": "in-progress"}}, now=NOW)
        assert running["settled"] is False and running["settled_without_result"] is False
        won = card_features({**tour, "data": {**tour["data"], "champion": "G"}}, now=NOW)
        assert won["settled"] is True and won["shows_result"] is True and won["settled_without_result"] is False


class TestSettledWithoutResult:
    """Fable 3: a finished game shown WITH its result is a legitimate seat; only
    settled-without-result is a truth-gate failure."""

    def test_a_final_with_its_score_is_not_a_failure(self):
        final = event(status="completed")
        final["data"].update(home_score=3, away_score=2)
        f = card_features(final, now=NOW)
        assert f["settled"] is True and f["shows_result"] is True and f["settled_without_result"] is False

    def test_a_final_without_its_score_is(self):
        f = card_features(event(status="completed"), now=NOW)
        assert f["settled"] is True and f["shows_result"] is False and f["settled_without_result"] is True

    def test_a_settled_futures_card_with_its_winner_is_not_a_failure(self):
        won = futures(3, prob=1.0, status="resolved")
        assert card_features(won, now=NOW)["settled_without_result"] is False
        flagged = futures(4, prob=0.62, status="resolved")
        flagged["data"]["top_outcomes"][0]["is_winner"] = True
        assert card_features(flagged, now=NOW)["settled_without_result"] is False

    def test_a_settled_futures_card_still_showing_a_live_price_is(self):
        f = card_features(futures(5, prob=0.62, status="resolved"), now=NOW)
        assert f["settled"] is True and f["settled_without_result"] is True

    def test_an_open_card_is_never_settled_without_result(self):
        assert card_features(futures(6), now=NOW)["settled_without_result"] is False


class TestBuildSlate:
    def test_served_first_in_order_then_unserved_pool_deduped(self):
        order, cands = build_slate([futures(1), event(), futures(1)], [futures(1), futures(9)], now=NOW)
        # A card served twice keeps both seats (its second gets its own key).
        assert order == ["futures:1", "event:7", "futures:1#3"]
        assert [(c["item_key"], c["served_position"]) for c in cands] == [
            ("futures:1", 1), ("event:7", 2), ("futures:1#3", 3), ("futures:9", None),
        ]

    def test_an_unidentifiable_card_keeps_its_seat_and_every_later_position(self):
        nameless = {"type": "futures", "score": 50, "data": {"name": "No id"}}
        order, cands = build_slate([futures(1), futures(2), nameless, futures(4), futures(5)], [], now=NOW)
        assert order == ["futures:1", "futures:2", "unknown:2", "futures:4", "futures:5"]
        assert [c["served_position"] for c in cands] == [1, 2, 3, 4, 5]
        assert cands[2]["item_id"] is None and cands[2]["card"] == nameless
        assert cands[3]["item_key"] == "futures:4" and cands[3]["served_position"] == 4

    def test_the_opening_ten_keep_their_served_card(self):
        order, cands = build_slate([futures(i) for i in range(1, 13)], [futures(99)], now=NOW)
        assert [("card" in c) for c in cands] == [True] * 10 + [False] * 3
        assert cands[0]["card"] == futures(1)

    def test_never_more_than_the_cap(self):
        served = [futures(i) for i in range(1, 400)]
        pool = [futures(i) for i in range(1000, 1300)]
        order, cands = build_slate(served, pool, now=NOW)
        assert len(cands) == MAX_CANDIDATES and len(order) == 399
        assert cands[-1]["served_position"] is None


# ── the writer ──────────────────────────────────────────────────────────────


class FakeDB:
    def __init__(self):
        self.added, self.executed, self.commits = [], [], 0

    def add(self, row):
        self.added.append(row)

    async def execute(self, stmt):
        self.executed.append(stmt)

    async def commit(self):
        self.commits += 1


def _deck(items, edition="ae0bc760eb204e34", **extra):
    async def read(db):
        return {"items": items, "edition": edition, "total": len(items), "cache": {"status": "hit"}, **extra}
    return read


async def _pool(db, now):
    return [futures(50)]


async def _facts(db, ids):
    return {i: {"movement_24h": 0.02, "updated_at": None} for i in ids}


class TestSnapshotWriter:
    async def test_off_reads_nothing_and_writes_nothing(self):
        async def boom(*_a):
            raise AssertionError("read while off")
        db = FakeDB()
        out = await snapshot_ranking_slate(db, now=NOW, read_deck=boom, read_pool=boom, read_facts=boom, environ={})
        assert out == {"status": "disabled"} and db.added == [] and db.commits == 0

    async def test_one_row_with_the_edition_the_sha_and_retention(self):
        db = FakeDB()
        out = await snapshot_ranking_slate(
            db, now=NOW, read_deck=_deck([futures(1), event()]), read_pool=_pool, read_facts=_facts, environ=ON,
        )
        assert out["status"] == "ok" and out["slate_id"] == "ae0bc760eb204e34"
        (row,) = db.added
        assert isinstance(row, RankingSlateSnapshot)
        assert row.slate_id == "ae0bc760eb204e34" and row.ranker_version == "abcdef123456"
        assert row.surface == "discover" and row.captured_at == NOW
        assert row.served_order == ["futures:1", "event:7"]
        assert [c["item_key"] for c in row.candidates] == ["futures:1", "event:7", "futures:50"]
        assert row.candidates[0]["movement_24h"] == 0.02
        assert row.summary["served_count"] == 2 and row.summary["deck_cache_status"] == "hit"
        assert row.summary["not_stored"] == ["movement_1h", "movement_7d"]
        (delete,) = db.executed
        cutoff = delete.compile().params["captured_at_1"]
        assert cutoff == NOW - timedelta(days=90)
        assert db.commits == 1

    async def test_a_degraded_or_empty_deck_writes_nothing(self):
        for read in (_deck([futures(1)], build_quality="degraded"), _deck([], edition=None), _deck([futures(1)], edition=None)):
            db = FakeDB()
            out = await snapshot_ranking_slate(db, now=NOW, read_deck=read, read_pool=_pool, read_facts=_facts, environ=ON)
            assert out["status"] in ("degraded_deck", "empty_deck") and db.added == []

    async def test_a_failed_pool_read_still_stores_the_served_order(self):
        async def bad_pool(db, now):
            raise RuntimeError("pool down")
        db = FakeDB()
        out = await snapshot_ranking_slate(
            db, now=NOW, read_deck=_deck([futures(1)]), read_pool=bad_pool, read_facts=_facts, environ=ON,
        )
        # Stored, but never "ok": an error must not masquerade as an empty pool.
        assert out["status"] == "ok_partial" and out["pool_scored"] == 0
        assert out["pool_error"] == "pool down" and out["facts_error"] is None
        assert db.added[0].served_order == ["futures:1"]
        assert db.added[0].summary["pool_error"] == "pool down"

    async def test_a_failed_facts_read_is_ok_partial_too(self):
        async def bad_facts(db, ids):
            raise RuntimeError("facts down")
        out = await snapshot_ranking_slate(
            FakeDB(), now=NOW, read_deck=_deck([futures(1)]), read_pool=_pool, read_facts=bad_facts, environ=ON,
        )
        assert out["status"] == "ok_partial" and out["facts_error"] == "facts down"

    async def test_a_failed_deck_read_is_reported_not_raised(self):
        async def bad(db):
            raise RuntimeError("feed down")
        import logging

        with self._caplog.at_level(logging.ERROR, logger="app.utils.ranking_slate_capture"):
            out = await snapshot_ranking_slate(FakeDB(), now=NOW, read_deck=bad, environ=ON)
        assert out["status"] == "deck_read_failed"
        # Loud: a night with no slate is an ERROR line, not a quiet WARNING.
        assert any(r.levelno == logging.ERROR and "nothing captured" in r.getMessage() for r in self._caplog.records)

    @pytest.fixture(autouse=True)
    def _grab_caplog(self, caplog):
        self._caplog = caplog


def test_grading_sheet_is_the_opening_ten_with_empty_grades():
    order, cands = build_slate([futures(i) for i in range(1, 15)], [], now=NOW)
    sheet = grading_sheet({"slate_id": "s1", "surface": "discover", "served_order": order, "candidates": cands})
    assert [i["position"] for i in sheet["items"]] == list(range(1, 11))
    assert sheet["items"][0] == {
        "position": 1, "item_key": "futures:1", "title": "Market 1", "probability": 0.4, "grade": None, "note": "",
    }
    assert sheet["grades_allowed"] == ["shareable", "interesting", "neither"]


# ── event fields ────────────────────────────────────────────────────────────


class RecordingDB:
    def __init__(self):
        self.rows = []

    def add_all(self, rows):
        self.rows.extend(rows)

    async def commit(self):
        pass


def _request():
    return Request({"type": "http", "method": "POST", "path": "/api/feed/interactions", "headers": [], "query_string": b""})


async def _post(monkeypatch, env_on: bool):
    import app.routes.feed as feed

    async def no_config():
        return {}

    monkeypatch.setattr(feed, "_load_discover_runtime_config", no_config)
    if env_on:
        monkeypatch.setenv(RANKING_SNAPSHOTS_ENV, "1")
    else:
        monkeypatch.delenv(RANKING_SNAPSHOTS_ENV, raising=False)
    body = feed.DiscoverInteractionBatch(
        interactions=[
            {
                "action": "impression", "item_type": "futures", "item_id": "1", "rank": 3, "surface": "web",
                "slate_id": "  ae0bc760eb204e34  ", "ranker_version": "x" * 90,
            }
        ]
    )
    db = RecordingDB()
    await feed.record_discover_interactions(request=_request(), body=body, user=None, db=db)
    return db.rows[0]


class TestEventFields:
    async def test_off_the_handler_sets_no_slate_fields(self, monkeypatch):
        """Off, the handler never SETS the two fields (they read NULL). This is
        about the values, not the statement: the ORM's INSERT may still name the
        two new columns (as NULL), which is why the migration must run in the
        release phase before this code serves (it does: `alembic upgrade head`)."""
        row = await _post(monkeypatch, env_on=False)
        assert "slate_id" not in row.__dict__ and "ranker_version" not in row.__dict__
        assert row.slate_id is None and row.ranker_version is None

    async def test_on_they_are_stored_trimmed_and_clipped(self, monkeypatch):
        row = await _post(monkeypatch, env_on=True)
        assert row.slate_id == "ae0bc760eb204e34"
        assert row.ranker_version == "x" * 64
        assert row.rank == 3

    def test_an_oversize_value_is_never_a_422(self):
        import app.routes.feed as feed

        feed.DiscoverInteractionIn(action="impression", item_type="futures", item_id="1", slate_id="s" * 500)


class TestFeedEnvelope:
    def test_off_no_ranker_version_on_the_envelope(self, monkeypatch):
        import app.routes.feed as feed

        monkeypatch.delenv(RANKING_SNAPSHOTS_ENV, raising=False)
        page = feed._feed_page_payload([], [], total=0, limit=20, offset=0, edition_status=None)
        assert RANKER_VERSION_FIELD not in page

    def test_on_the_envelope_names_the_deploy(self, monkeypatch):
        import app.routes.feed as feed

        monkeypatch.setenv(RANKING_SNAPSHOTS_ENV, "1")
        monkeypatch.setenv("HEROKU_SLUG_COMMIT", "0123456789abcdef")
        page = feed._feed_page_payload([], [], total=0, limit=20, offset=0, edition_status=None)
        assert page[RANKER_VERSION_FIELD] == "0123456789ab"


# ── admin + migration ───────────────────────────────────────────────────────


async def test_admin_capture_is_refused_while_off(monkeypatch):
    from fastapi import HTTPException

    import app.routes.admin_ranking_eval as admin

    monkeypatch.setattr(admin, "_check_admin_secret", lambda *a, **k: True)
    monkeypatch.delenv(RANKING_SNAPSHOTS_ENV, raising=False)
    with pytest.raises(HTTPException) as exc:
        await admin.capture_ranking_slate(request=_request(), secret=None, db=FakeDB())
    assert exc.value.status_code == 409


def test_the_admin_router_is_mounted_in_both_places():
    main = (BACKEND / "app" / "main.py").read_text()
    init = (BACKEND / "app" / "routes" / "__init__.py").read_text()
    assert "app.include_router(admin_ranking_eval.router" in main
    assert "dependencies=ADMIN_ROUTER_DEPENDENCIES)" in main.split("admin_ranking_eval.router", 1)[1].split("\n", 1)[0]
    assert "admin_ranking_eval" in init


def test_the_migration_creates_only_what_it_says_and_no_foreign_key():
    src = (BACKEND / "alembic" / "versions" / "ranking_slates_12095.py").read_text()
    tree = ast.parse(src)
    calls = [
        (n.func.attr, n.args[0].value if n.args and isinstance(n.args[0], ast.Constant) else None)
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name) and n.func.value.id == "op"
    ]
    assert ("create_table", "ranking_slate_snapshots") in calls
    assert ("create_table", "ranking_grades") in calls
    assert ("add_column", "discover_interactions") in calls
    assert "ForeignKey" not in src and "execute" not in {c for c, _ in calls}
    assert len("ranking_slates_12095") <= 32


def test_the_deck_read_passes_exactly_the_routes_parameters():
    """Fable 10: signature drift in `get_feed` would make every night a
    `deck_read_failed`; the kwargs the capture passes must be its parameters."""
    import ast as _ast
    import inspect

    from app.routes.feed import get_feed

    tree = _ast.parse(inspect.getsource(capture_mod.read_served_discover_deck).lstrip())
    (call,) = [n for n in _ast.walk(tree) if isinstance(n, _ast.Call) and getattr(n.func, "id", "") == "get_feed"]
    assert {kw.arg for kw in call.keywords} == set(inspect.signature(get_feed).parameters)


def test_the_task_reads_the_switch_before_any_session(monkeypatch):
    """Fable 5: off means no session and no run record."""
    import app.tasks as tasks

    monkeypatch.delenv(RANKING_SNAPSHOTS_ENV, raising=False)
    monkeypatch.setattr(tasks, "_tracked_run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran while off")))
    assert tasks.snapshot_ranking_slate.run() == {"status": "disabled"}


def test_the_snapshot_reads_the_route_itself_anonymously():
    import inspect

    src = inspect.getsource(capture_mod.read_served_discover_deck)
    assert "get_feed(" in src and "user=None" in src and "edition=None" in src and "debug=False" in src
