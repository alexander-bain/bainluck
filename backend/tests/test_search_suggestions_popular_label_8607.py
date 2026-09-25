"""#8607 — the search row stops calling a Senate race "Championship odds".

WHAT A USER SAW (production, phone-width LOOK of `/search`, 2026-09-25 11:19Z):

    Maine Senate winner?     Championship odds
    Texas Senate winner?     Championship odds

Section 5 of `_build_search_suggestions` ranks tier-1 open markets by
`volume_24h` and gave every one of them the same label. On production that
minute about half its top 40 were `category='politics'` (Senate, House and
Governor races, the 2028 presidency, the Nobel Peace Prize) and some were
`entertainment` (Dancing with the Stars, Best Picture). The label now says why
the market is on the row: a `championship` market keeps "Championship odds",
every other market is there because it is popular.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.routes import events as events_routes
from app.routes.events import _popular_market_label


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _QueuedDB:
    """Answers the build's statements in order: sections 1-4 empty, then section 5."""

    def __init__(self, results):
        self._results = list(results)

    async def execute(self, stmt):
        if not self._results:
            raise AssertionError("the build issued more statements than were queued")
        return self._results.pop(0)


@pytest.fixture
def no_redis(monkeypatch):
    import app.tasks.redis_state as redis_state

    monkeypatch.setattr(redis_state, "get_redis_client", lambda: None)


#: The production rows, by id and stored category, top of section 5's ordering.
_PRODUCTION_SECTION_5 = [
    (40533, "2027 Pro Football Champion", "championship"),
    (61461681, "FedEx Open de France Winner", "championship"),
    (275, "Pro Baseball Champion", "championship"),
    (109082, "Maine Senate winner?", "politics"),
    (109065, "Texas Senate winner?", "politics"),
    (56775566, "Pro Football Championship Game Matchup", "championship"),
    (112897, "Presidential Election Winner 2028", "politics"),
    (60481087, "Dancing with the Stars Season 35 · Winner", "entertainment"),
]


def _market(mid, name, category):
    return SimpleNamespace(
        id=mid, name=name, category=category, status="open", market_tier=1
    )


async def test_the_row_labels_each_market_by_what_it_is(no_redis):
    """One run of the real build over the production section-5 rows."""
    db = _QueuedDB(
        [
            _Rows([]),
            _Rows([]),
            _Rows([]),
            _Rows([]),
            _Rows([_market(*row) for row in _PRODUCTION_SECTION_5]),
        ]
    )

    chips = (await events_routes._build_search_suggestions(db))["suggestions"]
    labels = {c["query"]: c["label"] for c in chips}

    # Positive control first: the fixture reached section 5 and filled the row,
    # so an absent "Championship odds" below cannot be an empty row.
    assert list(labels) == [name for _, name, _ in _PRODUCTION_SECTION_5]

    assert labels["Maine Senate winner?"] == "Popular market"
    assert labels["Texas Senate winner?"] == "Popular market"
    assert labels["Presidential Election Winner 2028"] == "Popular market"
    assert labels["Dancing with the Stars Season 35 · Winner"] == "Popular market"
    assert labels["2027 Pro Football Champion"] == "Championship odds"
    assert labels["Pro Baseball Champion"] == "Championship odds"


@pytest.mark.parametrize(
    "category,expected",
    [
        ("championship", "Championship odds"),
        ("politics", "Popular market"),
        ("entertainment", "Popular market"),
        ("economics", "Popular market"),
        (None, "Popular market"),
    ],
)
def test_only_a_championship_is_called_one(category, expected):
    """A missing category is not evidence of a championship — it falls to the
    label that is true of every market on this section."""
    assert _popular_market_label(_market(1, "m", category)) == expected
