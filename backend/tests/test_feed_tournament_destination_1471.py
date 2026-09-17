"""#1471 — a golf tournament card's destination is `/api/golf/tournaments/{slug}`.

WHAT A PERSON SAW. Alex, physical phone, 2026-09-16: the Discover golf card opened the
generic Golf page; the tournament row on that page opened **"Couldn't load Biltmore
Championship Asheville"**, and *Try Again* failed again. native/198 traced the request
and found it went to `GET /api/tournaments/biltmore-championship-asheville`, which
returns a permanent, correct 404 — `routes/tournaments.py`'s `REGISTERED_TOURNAMENTS`
is a hand-committed register holding exactly one key (`us-open`), and its module header
says in so many words that an unregistered slug is a 404 and never a nearest guess.

THE BACKEND WAS SOUND; THE CLIENT WAS ASKING THE WRONG ROUTE. Measured on production
2026-09-17 01:0xZ, every golf slug the feed and the golf listing carry:

    slug                                          /api/golf/tournaments  /api/tournaments
    biltmore-championship-asheville                                 200               404
    nationwide-children-s-hospital-championship                     200               404

`GET /api/golf/tournaments/biltmore-championship-asheville` served the tournament,
132 golfers, venue and dates. So the repair is a client-side destination change, and
this file exists to keep the two facts that change makes the client depend on true.

THE FIRST FACT: `type == "tournament"` MEANS GOLF. The client has to decide a
destination from the feed item alone, and the item carries no route hint. It is safe to
read the type that way today because `routes/feed.py` emits `"type": "tournament"` from
exactly one place — `_score_golf_tournaments`. A second emitter elsewhere (a tennis hub
item, say) would silently send a registered-hub row to the golf route, or the reverse,
with no test failing. `test_the_feed_emits_a_tournament_item_from_exactly_one_place`
is that alarm.

THE SECOND FACT: THE SLUG THE FEED PUBLISHES IS THE SLUG THE ROUTE MATCHES.
`_score_golf_tournaments` passes `t["slug"]` straight through, and
`get_golf_tournament` resolves `t.get("slug") or clean_slug(t["name"])` over the same
listing. They agree by construction and by nothing else — two different builders
(`get_golf_base` for the feed, `get_golf` for the route) reading one dict.
`test_the_slug_the_feed_publishes_is_the_slug_the_golf_route_resolves` drives both
expressions over one tournament and compares them.

WHAT THIS FILE DELIBERATELY DOES NOT ASSERT. The route's matcher has a second arm —
a tournament with no `slug` key still resolves via `clean_slug(name)` — that the feed
does not mirror: it would publish `slug: None`, and the client draws a row with no
destination at all. That arm is unreachable today (`_enrich_with_schedule` sets `slug`
unconditionally for every tournament in `get_golf`'s output, before its own
`if sched:` guard), so there is no specimen and no defect to assert; it is recorded on
#1471 as a latent hole for whoever owns `routes/feed.py` rather than fixed from here.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.routes import feed as feed_module
from app.utils.name_normalization import clean_slug


FEED_SOURCE = Path(inspect.getsourcefile(feed_module))


def _tournament_item_emitters() -> list[tuple[int, str]]:
    """Every `{"type": "tournament", ...}` literal in `routes/feed.py`.

    Returns `(lineno, enclosing_function_name)` per emitter. Parsed rather than
    grepped: a grep for the string also matches comments, docstrings and the
    `item["type"] == "tournament"` reads, which are not emitters.
    """
    tree = ast.parse(FEED_SOURCE.read_text())

    # Map every node to its nearest enclosing function by walking function bodies.
    enclosing: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                enclosing.setdefault(id(child), node.name)

    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if (
                isinstance(key, ast.Constant)
                and key.value == "type"
                and isinstance(value, ast.Constant)
                and value.value == "tournament"
            ):
                found.append((node.lineno, enclosing.get(id(node), "<module>")))
    return found


def test_the_feed_emits_a_tournament_item_from_exactly_one_place():
    """`type == "tournament"` is a golf tournament, so the client may route on it.

    If this fails because a NEW emitter was added, the client's destination rule is
    now wrong for that emitter's rows — either give the item a route hint the client
    can read, or keep the new family off this type. Do not widen the allowlist to
    make the red go away.
    """
    emitters = _tournament_item_emitters()

    assert emitters, (
        "No `{'type': 'tournament'}` literal found in routes/feed.py. Either the "
        "golf tournament card stopped being emitted, or it moved and this scan "
        "is now vacuous — read the file before editing the scan."
    )
    assert [fn for _, fn in emitters] == ["_score_golf_tournaments"], (
        "routes/feed.py emits a tournament feed item from more than one place: "
        f"{emitters}. The iOS client picks `/api/golf/tournaments/{{slug}}` from the "
        "item TYPE alone (#1471), so a non-golf emitter sends its rows to the golf "
        "route and 404s the reader."
    )


class _FakeGolfBase:
    """Stands in for `get_golf_base` so the scoring runs with no DB and no Redis."""

    def __init__(self, tournaments: list[dict]):
        self.tournaments = tournaments

    async def __call__(self, db, now, stages=None):
        return list(self.tournaments), "fresh"


#: The shape `get_golf` hands the feed, trimmed to the keys the scorer reads. Names
#: and slug are the live Biltmore row measured on production 2026-09-17.
BILTMORE = {
    "key": "biltmore_championship_asheville",
    "name": "Biltmore Championship Asheville",
    "slug": "biltmore-championship-asheville",
    "tour": "pga",
    "tour_label": "PGA Tour",
    "is_major": False,
    "is_tour_event": True,
    "venue": "The Cliffs at Walnut Cove",
    "location": "Arden, NC",
    "start_date": "2026-09-17T00:00:00+00:00",
    "end_date": "2026-09-20T00:00:00+00:00",
    "schedule_status": "upcoming",
    "commence_time": "2026-09-12T16:01:00+00:00",
    "resolution_date": "2026-09-20T00:00:00+00:00",
    "golfers": [
        {"name": "Jackson Koivun", "probability": 0.061, "rank": 1, "movement_24h": None},
        {"name": "Jacob Bridgeman", "probability": 0.042, "rank": 2, "movement_24h": None},
    ],
    "market_ids": [59863406],
    "market_names": ["Biltmore Championship Asheville Winner"],
    "market_sources": ["datagolf"],
}


def _score(monkeypatch, tournament: dict) -> list[dict]:
    import app.utils.golf_base as golf_base

    monkeypatch.setattr(golf_base, "get_golf_base", _FakeGolfBase([tournament]))
    # Anchored inside the tournament's own window so the scorer's clock branches are
    # not the subject here (gotcha #44: the anchor never branches on the real clock).
    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
    return asyncio.run(
        feed_module._score_golf_tournaments(db=None, now=now, sport_filter=None, ctx=None)
    )


def test_the_slug_the_feed_publishes_is_the_slug_the_golf_route_resolves(monkeypatch):
    """One tournament dict, two readers: the feed's card and the route's matcher.

    `routes/golf.py:get_golf_tournament` selects with
    `t.get("slug") or clean_slug(t["name"])`; the feed publishes `t["slug"]`. This
    drives both over the same row so a change to either side that breaks the
    round-trip is a red test rather than a 404 on a reader's phone.
    """
    items = _score(monkeypatch, BILTMORE)

    assert len(items) == 1, f"expected one golf tournament item, got {items!r}"
    published = items[0]["data"]["slug"]
    resolved_by_route = BILTMORE.get("slug") or clean_slug(BILTMORE["name"])

    assert published == resolved_by_route, (
        f"the feed card carries slug {published!r} but `get_golf_tournament` matches "
        f"on {resolved_by_route!r}; a tap on this card 404s."
    )
    assert published == "biltmore-championship-asheville"


def test_the_feed_card_is_not_routable_to_the_registered_tournament_hub():
    """The golf slug is not a `REGISTERED_TOURNAMENTS` key, and must not become one.

    This is the fact that made Alex's tap fail. Stated as a test so that "just
    register the golf tournaments" — the fix native/198 offered as option (a) — is a
    deliberate, visible change to the register charter rather than a quiet one.
    """
    from app.routes.tournaments import REGISTERED_TOURNAMENTS

    assert "biltmore-championship-asheville" not in REGISTERED_TOURNAMENTS
    assert set(REGISTERED_TOURNAMENTS) == {"us-open"}, (
        "REGISTERED_TOURNAMENTS grew. If a golf tournament was added, the client's "
        "#1471 destination rule (tournament item -> /api/golf/tournaments/{slug}) "
        "needs re-reading; if a tennis one was, nothing here changes but say so."
    )


@pytest.mark.parametrize("bad_type", ["event", "futures", "concept", "bundle"])
def test_the_scan_would_notice_a_second_emitter(bad_type):
    """Red-first control: the scan reads dict literals, not a substring.

    Proves `_tournament_item_emitters` keys on the `type` VALUE rather than on the
    word appearing anywhere — a scan that matched `"tournament"` in prose would
    report emitters for these types too, and the guard above would be vacuous.
    """
    tree = ast.parse(f'x = {{"type": "{bad_type}", "data": {{"slug": "tournament"}}}}')
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "type"
                    and isinstance(value, ast.Constant)
                    and value.value == "tournament"
                ):
                    found.append(node.lineno)
    assert found == [], f"{bad_type!r} literal misread as a tournament emitter"
