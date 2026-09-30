"""#9636 — a published NFL week / MLB postseason opens as familiar cards.

SHIP: NFL-week and MLB-playoff hubs show familiar complete cards, available
related questions and working destinations (#9636, paired #9652/#9653 under
#9217). Pillar: MATCHING / FORMATTING / TRUTH.

What is pinned here, against ``GET /api/containers/{slug}``:

* **only a published collection has members** — disabled, unavailable,
  unpublished (including an un-migrated database), withdrawn and empty are each
  an explicit state, and none of them hydrates or leaks a member or a path;
* **one read, one revision** — the members served are the members the ONE
  published read returned at the revision it returned; the route never reads
  ``event_edges`` a second time;
* **familiar cards** — games carry ``GET /api/events``' card and questions
  carry search's futures card, built by the real serializers;
* **bounded** — the statement count is the same for one member as for forty;
* **no invented card, no dead link** — a member whose row is gone is withheld
  with a reason and has no destination.

The session is a double that answers the published read, the header read and
the card reads; everything else is answered empty and recorded. The one-snapshot
property of the published read itself is a property of one SQL statement and is
graded on real Postgres in ``tests/integration/test_container_assembly_real_postgres.py``.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.routes import containers as route
from app.utils import container_presentation as presentation
from app.utils.container_graph import CLASS_UNCLASSIFIED

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "container_hub_9636"

#: Gotcha #44: the rows are anchored to the current hour (offset first, then
#: truncate — no branch on the clock), so a "live" game is always one that
#: started an hour ago and a scheduled one is always two days out. The fixture
#: shifts every timestamp from NOW_H onto FIXTURE_BASE so the file never rots.
NOW_H = (datetime.now(timezone.utc) + timedelta(0)).replace(minute=0, second=0, microsecond=0)
FIXTURE_BASE = datetime(2026, 10, 4, 17, 0, tzinfo=timezone.utc)
KICKOFF = NOW_H


# ---------------------------------------------------------------------------
# The session double
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self.rows)

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def first(self):
        return self.rows[0] if self.rows else None

    def scalar(self):
        return self.rows[0] if self.rows else None

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None

    def mappings(self):
        return self

    def __iter__(self):
        return iter(self.rows)


class _Hub:
    """One collection as the database would hold it."""

    def __init__(
        self,
        slug,
        *,
        container_id=70,
        publication="published",
        revision=4,
        edges=(),
        children=(),
        kind="season",
        name="NFL 2026 · Week 5",
    ):
        self.slug = slug
        self.id = container_id
        self.publication = publication
        self.revision = revision
        # (class, child_type, child_id, parent_id, source, confidence)
        self.edges = list(edges)
        # (id, kind, name, slug, status, publication_state)
        self.children = list(children)
        self.kind = kind
        self.name = name


class _Session:
    def __init__(self, hub=None, *, migrated=True, events=(), markets=()):
        self.hub = hub
        self.migrated = migrated
        self.events = list(events)
        self.markets = list(markets)
        self.statements = []

    async def execute(self, sql, params=None):
        text_ = str(sql)
        self.statements.append(text_)
        if "to_regclass('public.container_corrections')" in text_:
            return _Result([(self.migrated, self.migrated)])
        if text_.startswith("SELECT 1 FROM containers WHERE slug"):
            exists = self.hub is not None and params["slug"] == self.hub.slug
            return _Result([(1,)] if exists else [])
        if text_.startswith("WITH hub AS"):
            return _Result(self._published_rows(params["slug"]))
        if "FROM containers" in text_ and "publication_state <> 'withdrawn'" in text_:
            return _Result(self._header_rows(params["id"]))
        if text_.startswith("SELECT events.") and "WHERE events.id IN" in text_:
            return _Result(self.events)
        if text_.startswith("SELECT futures_markets.") and "WHERE futures_markets.id IN" in text_:
            return _Result(self.markets)
        return _Result()

    def _published_rows(self, slug):
        hub = self.hub
        if hub is None or slug != hub.slug:
            return []
        live_parts = {hub.id} | {
            c[0] for c in hub.children if c[5] != "withdrawn"
        }
        edges = sorted(
            (e for e in hub.edges if e[3] in live_parts),
            key=lambda e: (e[0] or "", e[2]),
        )
        if hub.publication != "published" or not edges:
            return [(hub.id, hub.publication, hub.revision) + (None,) * 6]
        return [(hub.id, hub.publication, hub.revision) + tuple(e) for e in edges]

    def _header_rows(self, container_id):
        hub = self.hub
        head = (
            hub.id, hub.kind, hub.name, hub.slug, "sports", "live",
            KICKOFF - timedelta(days=3), KICKOFF + timedelta(days=4), None, hub.publication,
        )
        kids = [
            (c[0], c[1], c[2], c[3], "sports", c[4], None, None, hub.id, c[5])
            for c in sorted(hub.children, key=lambda c: (c[2], c[0]))
            if c[5] != "withdrawn"
        ]
        return [head] + kids

    def edge_reads(self):
        return [s for s in self.statements if "event_edges" in s]


# ---------------------------------------------------------------------------
# Rows — representative, not production
# ---------------------------------------------------------------------------


def _sport(key="americanfootball_nfl", name="NFL"):
    from app.models import Sport

    sport = Sport(key=key, name=name, active=True)
    sport.id = 1
    return sport


def _event(event_id, home, away, *, hours=0, status="scheduled", sport=None, **extra):
    from app.models import Event

    event = Event(
        id=event_id,
        external_id=f"rep-{event_id}",
        home_team_name=home,
        away_team_name=away,
        commence_time=KICKOFF + timedelta(hours=hours),
        status=status,
        sport_id=1,
        **extra,
    )
    event.sport = sport or _sport()
    return event


def _market(market_id, name, *, event_id=None, legs=(("Yes", 0.6), ("No", 0.4)), sport=None):
    from app.models import FuturesMarket, FuturesOutcome

    market = FuturesMarket(
        id=market_id,
        source="kalshi",
        external_id=f"REP-{market_id}",
        name=name,
        category="sports",
        status="open",
        sport_id=1,
        event_id=event_id,
        market_tier=2,
    )
    market.sport = sport or _sport()
    market.outcomes = [
        FuturesOutcome(id=market_id * 10 + i, market_id=market_id, name=leg, current_probability=p)
        for i, (leg, p) in enumerate(legs)
    ]
    return market


def _nfl_week(publication="published", revision=4):
    """Week 5: two games, a question on each, one prop, one member whose row is gone."""
    events = [
        _event(501, "Buffalo Bills", "Kansas City Chiefs", hours=53),
        _event(502, "Philadelphia Eagles", "Dallas Cowboys", hours=-1, status="live",
               home_score=7, away_score=3),
    ]
    markets = [
        _market(9101, "Chiefs at Bills: winner", event_id=501,
                legs=(("Buffalo Bills", 0.55), ("Kansas City Chiefs", 0.45))),
        _market(9102, "Cowboys at Eagles: winner", event_id=502,
                legs=(("Philadelphia Eagles", 0.62), ("Dallas Cowboys", 0.38))),
        _market(9103, "Josh Allen: 2+ passing touchdowns?", event_id=501),
    ]
    edges = [
        ("match_winner", "event", 501, 70, "statpal", 1.0),
        ("match_winner", "event", 502, 70, "statpal", 1.0),
        ("match_winner", "market", 9101, 70, "register", 1.0),
        ("match_winner", "market", 9102, 70, "register", 1.0),
        ("prop", "market", 9103, 70, "register", 0.9),
        # The edge survives, the row does not (deleted twin, purged market).
        ("match_winner", "event", 599, 70, "statpal", 1.0),
    ]
    hub = _Hub("nfl-2026-week-5", publication=publication, revision=revision, edges=edges)
    return hub, events, markets


def _mlb_postseason():
    sport = _sport("baseball_mlb", "MLB")
    events = [
        _event(801, "New York Yankees", "Boston Red Sox", hours=-100, status="completed",
               home_score=2, away_score=5, completed_at=KICKOFF - timedelta(hours=97),
               sport=sport),
        _event(802, "Los Angeles Dodgers", "San Diego Padres", hours=50, sport=sport),
    ]
    markets = [
        _market(9201, "Padres at Dodgers: winner", event_id=802,
                legs=(("Los Angeles Dodgers", 0.58), ("San Diego Padres", 0.42)), sport=sport),
        _market(9202, "2026 World Series champion", event_id=None,
                legs=(("Los Angeles Dodgers", 0.21), ("New York Yankees", 0.12)), sport=sport),
    ]
    edges = [
        ("match_winner", "event", 801, 80, "espn", 1.0),
        ("match_winner", "event", 802, 80, "espn", 1.0),
        ("match_winner", "market", 9201, 80, "register", 1.0),
        ("title", "market", 9202, 80, "register", 1.0),
    ]
    hub = _Hub(
        "mlb-2026-postseason", container_id=80, edges=edges, revision=11,
        kind="season", name="MLB 2026 Postseason",
    )
    return hub, events, markets


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")


async def _get(session, slug, **kwargs):
    return await route.get_container(slug=slug, include_children=kwargs.get("include_children", True), db=session)


def _cards_hydrated(session):
    return [
        s for s in session.statements
        if s.startswith("SELECT events.") or s.startswith("SELECT futures_markets.")
    ]


# ---------------------------------------------------------------------------
# States: only `published` carries members
# ---------------------------------------------------------------------------


async def test_disabled_flag_is_a_404_and_reads_nothing(monkeypatch):
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "false")
    hub, events, markets = _nfl_week()
    session = _Session(hub, events=events, markets=markets)
    with pytest.raises(HTTPException) as err:
        await _get(session, hub.slug)
    assert err.value.status_code == 404
    assert session.statements == []


async def test_a_slug_with_no_collection_is_a_404_that_names_its_state():
    session = _Session(None)
    with pytest.raises(HTTPException) as err:
        await _get(session, "nfl-2026-week-9")
    assert err.value.status_code == 404
    assert err.value.detail == {"state": "unavailable", "slug": "nfl-2026-week-9"}
    assert _cards_hydrated(session) == []


async def test_an_unmigrated_database_serves_unpublished_with_no_member():
    """Before #9651's migration runs there is no publication state, so nothing
    is for readers — the pre-#9636 route would have served every edge."""
    hub, events, markets = _nfl_week()
    session = _Session(hub, migrated=False, events=events, markets=markets)
    payload = await _get(session, hub.slug)
    assert payload["state"] == "unpublished"
    assert payload["reason"] == "publication_schema_absent"
    assert payload["revision"] is None
    assert payload["sections"] == [] and payload["member_count"] == 0
    assert payload["children"] == [] and payload["container"] is None
    assert session.edge_reads() == []
    assert _cards_hydrated(session) == []


@pytest.mark.parametrize("publication", ["unpublished", "withdrawn", "some_future_state"])
async def test_a_collection_not_for_readers_leaks_no_member_and_no_path(publication):
    hub, events, markets = _nfl_week(publication=publication)
    hub.children = [(71, "season", "Early window", "nfl-2026-week-5-early", "live", "published")]
    session = _Session(hub, events=events, markets=markets)
    payload = await _get(session, hub.slug)

    expected = "withdrawn" if publication == "withdrawn" else "unpublished"
    assert payload["state"] == expected
    assert payload["revision"] == 4
    assert payload["sections"] == [] and payload["member_count"] == 0
    assert payload["withheld"] == [] and payload["children"] == []
    assert payload["container"] is None
    assert "destination" not in json.dumps(payload)
    assert _cards_hydrated(session) == []


async def test_a_published_collection_with_no_member_is_empty_not_missing():
    hub = _Hub("nfl-2026-week-6", edges=[])
    session = _Session(hub)
    payload = await _get(session, hub.slug)
    assert payload["state"] == "empty"
    assert payload["container"]["slug"] == "nfl-2026-week-6"
    assert payload["sections"] == [] and payload["member_count"] == 0
    assert payload["edition"] == {
        "kind": "nfl_week", "league": "nfl", "season": 2026,
        "stage": "Regular Season", "week": 6,
    }
    assert _cards_hydrated(session) == []


# ---------------------------------------------------------------------------
# Published: familiar cards, one revision, working destinations
# ---------------------------------------------------------------------------


async def test_an_nfl_week_serves_familiar_game_and_question_cards():
    hub, events, markets = _nfl_week()
    session = _Session(hub, events=events, markets=markets)
    payload = await _get(session, hub.slug)

    assert payload["state"] == "published"
    assert payload["revision"] == 4
    assert payload["edition"]["kind"] == "nfl_week" and payload["edition"]["week"] == 5
    assert [s["class"] for s in payload["sections"]] == ["match_winner", "prop"]

    winners = payload["sections"][0]["members"]
    # Games first, by kickoff (the game live now before the one two days out), then questions.
    assert [(m["type"], m["id"]) for m in winners] == [
        ("event", 502), ("event", 501), ("market", 9101), ("market", 9102),
    ]
    live = winners[0]
    # The events list's card, verbatim: its served state, teams and score.
    assert live["card"]["id"] == 502
    assert live["card"]["status"] == "live"
    assert live["card"]["home_score"] == 7
    assert live["card"]["home_team"] == "Philadelphia Eagles"
    assert live["destination"] == {
        "kind": "event", "id": 502, "web": "/events/502", "api": "/api/events/502",
    }
    # Related questions come from membership + event_id, never from a name.
    by_id = {m["id"]: m for s in payload["sections"] for m in s["members"]}
    assert by_id[501]["question_ids"] == [9101, 9103]
    assert by_id[502]["question_ids"] == [9102]
    question = by_id[9101]
    assert question["event_id"] == 501
    assert [o["name"] for o in question["card"]["top_outcomes"]] == [
        "Buffalo Bills", "Kansas City Chiefs",
    ]
    assert question["destination"]["web"] == "/futures/9101"

    # Pre-#9636 member fields are all still there for released readers.
    for member in by_id.values():
        assert {"type", "id", "container_id", "source", "confidence"} <= set(member)
    assert payload["assembled"] is True
    assert "known_classes" in payload


async def test_a_member_whose_row_is_gone_is_withheld_never_a_card_or_a_link():
    hub, events, markets = _nfl_week()
    session = _Session(hub, events=events, markets=markets)
    payload = await _get(session, hub.slug)

    served = {(m["type"], m["id"]) for s in payload["sections"] for m in s["members"]}
    assert ("event", 599) not in served
    assert payload["withheld"] == [{"type": "event", "id": 599, "reason": "row_missing"}]
    assert payload["withheld_count"] == 1
    # The count a reader sees is the cards a reader can open.
    assert payload["member_count"] == len(served) == 5
    assert all(m["card"] and m["destination"] for s in payload["sections"] for m in s["members"])


async def test_one_card_the_serializer_cannot_draw_does_not_take_the_hub_down(monkeypatch):
    hub, events, markets = _nfl_week()
    session = _Session(hub, events=events, markets=markets)
    from app.routes import events as events_route

    real = events_route._format_event_with_aggregated_odds

    def poisoned(event, *args, **kwargs):
        if event.id == 501:
            raise ValueError("unconvertible leg")
        return real(event, *args, **kwargs)

    monkeypatch.setattr(events_route, "_format_event_with_aggregated_odds", poisoned)
    payload = await _get(session, hub.slug)
    assert {"type": "event", "id": 501, "reason": "unserializable"} in payload["withheld"]
    served = {m["id"] for s in payload["sections"] for m in s["members"]}
    assert 502 in served and 9101 in served


async def test_the_mlb_postseason_serves_its_final_game_with_the_result():
    hub, events, markets = _mlb_postseason()
    session = _Session(hub, events=events, markets=markets)
    payload = await _get(session, hub.slug)

    assert payload["edition"] == {"kind": "mlb_postseason", "league": "mlb", "season": 2026}
    assert payload["revision"] == 11
    assert [s["class"] for s in payload["sections"]] == ["match_winner", "title"]
    by_id = {m["id"]: m for s in payload["sections"] for m in s["members"]}
    final = by_id[801]["card"]
    assert final["status"] == "completed"
    assert (final["home_score"], final["away_score"]) == (2, 5)
    assert by_id[802]["question_ids"] == [9201]
    # A season-long question has no game, and says so rather than guessing one.
    assert by_id[9202]["event_id"] is None
    assert by_id[9202]["destination"]["web"] == "/futures/9202"


async def test_revision_and_members_come_from_the_one_published_read():
    """The membership served is the published read's, at its revision. The
    route issues exactly one statement over ``event_edges`` — a second read is
    how a payload would pair revision N with revision N+1's members."""
    hub, events, markets = _nfl_week(revision=8)
    session = _Session(hub, events=events, markets=markets)
    first = await _get(session, hub.slug)
    assert len(session.edge_reads()) == 1
    assert first["revision"] == 8

    # Assembly withdraws the prop and bumps the revision; the next read sees both.
    hub.edges = [e for e in hub.edges if e[2] != 9103]
    hub.revision = 9
    session.statements.clear()
    second = await _get(session, hub.slug)
    assert len(session.edge_reads()) == 1
    assert second["revision"] == 9
    assert [s["class"] for s in second["sections"]] == ["match_winner"]
    by_id = {m["id"]: m for s in second["sections"] for m in s["members"]}
    assert by_id[501]["question_ids"] == [9101]


async def test_nested_collections_are_destinations_only_when_published():
    hub = _Hub(
        "nfl-2026", kind="season", name="NFL 2026",
        edges=[("match_winner", "event", 501, 71, "statpal", 1.0)],
        children=[
            (71, "season", "NFL 2026 · Week 5", "nfl-2026-week-5", "live", "published"),
            (72, "season", "NFL 2026 · Week 6", "nfl-2026-week-6", "scheduled", "unpublished"),
            (73, "season", "NFL 2026 · Week 4", "nfl-2026-week-4", "final", "withdrawn"),
        ],
    )
    session = _Session(hub, events=[_event(501, "Buffalo Bills", "Kansas City Chiefs")])
    payload = await _get(session, hub.slug)

    assert payload["edition"] == {"kind": "nfl_season", "league": "nfl", "season": 2026}
    kids = {c["slug"]: c for c in payload["children"]}
    assert set(kids) == {"nfl-2026-week-5", "nfl-2026-week-6"}  # withdrawn left out
    assert kids["nfl-2026-week-5"]["destination"]["api"] == "/api/containers/nfl-2026-week-5"
    assert kids["nfl-2026-week-5"]["destination"]["web"] == "/collections/nfl-2026-week-5"
    assert kids["nfl-2026-week-6"]["destination"] is None
    assert kids["nfl-2026-week-5"]["edition"]["week"] == 5
    # The draw's member reaches the season hub, as the published read includes draws.
    assert payload["member_count"] == 1

    session.statements.clear()
    own_only = await _get(session, hub.slug, include_children=False)
    assert own_only["member_count"] == 0 and own_only["state"] == "published"
    assert _cards_hydrated(session) == []


# ---------------------------------------------------------------------------
# Bounded: the statement count does not grow with the membership
# ---------------------------------------------------------------------------


def _wide_week(games):
    events, markets, edges = [], [], []
    for i in range(games):
        eid, mid = 1000 + i, 5000 + i
        events.append(_event(eid, f"Home {i}", f"Away {i}", hours=48 + i))
        markets.append(_market(mid, f"Away {i} at Home {i}: winner", event_id=eid))
        edges.append(("match_winner", "event", eid, 70, "statpal", 1.0))
        edges.append(("match_winner", "market", mid, 70, "register", 1.0))
    return _Hub("nfl-2026-week-7", edges=edges), events, markets


async def test_statement_count_is_the_same_for_one_game_and_forty():
    counts = {}
    for games in (1, 40):
        hub, events, markets = _wide_week(games)
        session = _Session(hub, events=events, markets=markets)
        payload = await _get(session, hub.slug)
        assert payload["member_count"] == 2 * games
        counts[games] = len(session.statements)
    assert counts[1] == counts[40], counts
    # probe + published read + header + event cards (5) + market cards (1..5)
    assert counts[1] <= 13, counts


# ---------------------------------------------------------------------------
# The pure half
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "slug, expected",
    [
        ("nfl-2026-week-5", {"kind": "nfl_week", "league": "nfl", "season": 2026,
                             "stage": "Regular Season", "week": 5}),
        ("nfl-2026-preseason-week-2", {"kind": "nfl_week", "league": "nfl", "season": 2026,
                                       "stage": "Pre Season", "week": 2}),
        ("nfl-2026-postseason-week-1", {"kind": "nfl_week", "league": "nfl", "season": 2026,
                                        "stage": "Post Season", "week": 1}),
        ("nfl-2026", {"kind": "nfl_season", "league": "nfl", "season": 2026}),
        ("mlb-2026-postseason", {"kind": "mlb_postseason", "league": "mlb", "season": 2026}),
        # Slugs the adapters would never write have no edition, not a nearest one.
        ("nfl-2026-week-05", None),
        ("nfl-2026-week-0", None),
        ("nfl-2026-wildcard-week-1", None),
        ("mlb-1850-postseason", None),
        ("us-open-2026", None),
        ("", None),
    ],
)
def test_edition_is_read_by_round_tripping_the_adapters_own_slug(slug, expected):
    assert presentation.edition_for_slug(slug) == expected


def test_the_edition_agrees_with_the_declared_collection_roots():
    from app.utils.container_tournaments import DECLARED_COLLECTIONS

    for declaration in DECLARED_COLLECTIONS:
        edition = presentation.edition_for_slug(declaration.root_slug)
        assert edition is not None, declaration.root_slug
        assert edition["season"] == declaration.season


def test_present_sections_withholds_an_unknown_member_type():
    sections, withheld = presentation.present_sections(
        [{"class": "prop", "type": "container", "id": 3, "container_id": 1}],
        event_cards={}, market_cards={}, market_event_ids={}, failed={},
        order_classes=route.order_classes, unclassified=CLASS_UNCLASSIFIED,
    )
    assert sections == []
    assert withheld == [{"type": "container", "id": 3, "reason": "unknown_member_type"}]


def test_a_member_held_by_a_draw_and_its_parent_is_served_once():
    members = [
        {"class": "match_winner", "type": "event", "id": 1, "container_id": 70},
        {"class": "match_winner", "type": "event", "id": 1, "container_id": 71},
    ]
    sections, withheld = presentation.present_sections(
        members, event_cards={1: {"id": 1}}, market_cards={}, market_event_ids={},
        failed={}, order_classes=route.order_classes, unclassified=CLASS_UNCLASSIFIED,
    )
    assert sections[0]["count"] == 1 and withheld == []


# ---------------------------------------------------------------------------
# The representative native-consumer fixture (#9652)
# ---------------------------------------------------------------------------

_VOLATILE = {"prices_updated_at", "updated_at"}


def _rebase(value):
    """An aware ISO timestamp, moved from NOW_H onto FIXTURE_BASE; else as is."""
    if not isinstance(value, str) or len(value) < 19 or value[4] != "-" or "T" not in value:
        return value
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if when.tzinfo is None:
        return value
    return (when - NOW_H + FIXTURE_BASE).isoformat()


def _scrub(value):
    """The fixture pins the SHAPE and the representative values. Timestamps are
    rebased so they stay valid ISO-8601 a decoder can read, and the two
    serializer stamps that read the wall clock are blanked."""
    if isinstance(value, dict):
        return {k: (None if k in _VOLATILE else _scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return _rebase(value)


@pytest.mark.parametrize(
    "name, build",
    [("representative_nfl_week.json", _nfl_week), ("representative_mlb_postseason.json", _mlb_postseason)],
)
async def test_the_native_consumer_fixture_is_what_the_route_serves(name, build):
    """#9652 decodes these files. They are REPRESENTATIVE — built from the rows
    in this module through the real serializers, not captured from production —
    and this test fails the moment the route's payload drifts from them.

    Regenerate: ``BL_WRITE_9636_FIXTURES=1 python3 -m pytest <this file> -k fixture``.
    """
    import os

    hub, events, markets = build()
    payload = _scrub(await _get(_Session(hub, events=events, markets=markets), hub.slug))
    envelope = {
        "_representative": (
            "REPRESENTATIVE FIXTURE for #9636/#9652 — built from test rows through the "
            "real card serializers; NOT production data. Regenerate with "
            "BL_WRITE_9636_FIXTURES=1 (see backend/tests/test_container_hydrated_reader_9636.py)."
        ),
        "request": f"GET /api/containers/{hub.slug}",
        "response": payload,
    }
    path = FIXTURE_DIR / name
    if os.environ.get("BL_WRITE_9636_FIXTURES") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(envelope, indent=2, sort_keys=True, default=str) + "\n")
    stored = json.loads(path.read_text())
    assert stored == json.loads(json.dumps(envelope, sort_keys=True, default=str))
