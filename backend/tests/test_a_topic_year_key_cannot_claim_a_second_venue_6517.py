"""#6517 — a card stops being scored for corroboration from a venue that never
listed its question.

## The defect

`Which party will win the U.S. House?` (market 108621, Kalshi `CONTROLH-2026`)
was served on Discover page one carrying `source_count: 2`,
`sources: ['kalshi', 'polymarket']`, `qa_signals: ['multi_source_consistency_check']`
and `interestingness_reasons: ['multi_source', ...]`.

No Polymarket market about the U.S. House was consulted. The whole basis was the
card's `canonical_market_key`, `politics::championship:2027` — a bucket holding
1,422 rows on 2026-09-16 (1,419 Kalshi, 3 Polymarket), whose three Polymarket
rows were all `resolved`:

    114260   resolved   Any EU nation's debt downgraded before 2027?
    114330   resolved   Odds Trump acquires Greenland before 2027 hit __ by March 31?
    8414985  resolved   Russia x Ukraine ceasefire by end of 2027?

`multi_source_signal` returns 0.7 at `source_count == 2`, weighted 10.0, so each
of **1,942 open markets** across **23** such buckets carried +7.0 interestingness
it had not earned, displacing cards two venues really do carry.

## The seam this gate pins

The predicate now in `app/utils/canonical_market_key.py` already existed, in
`routes/feed.py`, as `_canonical_key_safe_for_dedupe`. It refused
`politics::championship:2027` correctly and had exactly ONE call site: feed
dedupe. The source-count path read the same key with no guard — so the key that
was too weak to decide *"are these the same question?"* was trusted with the
strictly stronger *"are these the same question, at two venues?"*.

## Why this file tests TWO writers

Fixing `routes/feed.py` alone would have been INERT. `/api/feed` reads the
interestingness score from Redis, and that score is written by
`tasks/precompute_interestingness.py`, which derives `source_counts` from the
same key with its own query. The task is the writer that owns the ranking
number; the route owns the payload's `sources`/`source_count` and the admin
trace. Both are asserted here, so removing either filter reddens this file.
"""

import json
from datetime import datetime, timezone

import pytest

import app.routes.feed as feed_module
from app.utils.canonical_market_key import canonical_key_identifies_one_question

from tests.test_interestingness_chunking import (
    FakeMarket,
    FakeOutcome,
    FakeRedis,
    FakeSession,
    _CountRows,
    _KeyRows,
    _ScalarRows,
    _patch,
)


#: The live specimen, and its bucket-mates from the census on the issue.
HOUSE_KEY = "politics::championship:2027"

#: Every topic-and-year bucket that carried >=2 sources on production
#: 2026-09-16, with its open-market count. All 23 share one shape: empty league
#: segment, generic category. None of them can denote a single question.
MEASURED_UNSAFE_KEYS = {
    "politics::championship:2027": 1225,
    "entertainment::championship:2026": 212,
    "economics::championship:2026": 158,
    "entertainment::championship:2027": 148,
    "politics::championship:2026": 83,
    "other::championship:2026": 34,
    "tech::championship:2027": 22,
    "weather::championship:2026": 19,
    "geopolitics::championship:2027": 10,
    "geopolitics::championship:2026": 9,
}

#: Keys that DO denote a question and must keep their cross-source credit — the
#: other branch, so this gate cannot be satisfied by refusing everything.
MEASURED_SAFE_KEYS = [
    "politics:US:championship:2027",  # the Senate card: differs only by league
    "soccer::championship:2026",  # sports-like topic carries its own structure
    "tech:NASDAQ:earnings:2026",  # a real league AND a specific category
    "economics::cpi:2026",  # non-generic category
    "politics:US:senate-ga:2026",
]


# ---------------------------------------------------------------------------
# 1. the predicate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(MEASURED_UNSAFE_KEYS))
def test_a_topic_year_bucket_does_not_denote_one_question(key):
    assert canonical_key_identifies_one_question(key) is False, (
        f"{key!r} held a whole topic for a whole year on production "
        f"({MEASURED_UNSAFE_KEYS[key]} open markets). Two rows sharing it are "
        "not two views of one question."
    )


@pytest.mark.parametrize("key", MEASURED_SAFE_KEYS)
def test_a_question_key_keeps_its_cross_source_credit(key):
    assert canonical_key_identifies_one_question(key) is True, (
        f"{key!r} names a question; refusing it would delete real two-venue "
        "corroboration, which is the opposite defect"
    )


def test_the_house_key_and_the_senate_key_differ_only_by_league():
    """The one-character difference that decides it, pinned so a future
    normalisation of the league segment cannot quietly re-admit the bucket."""
    assert canonical_key_identifies_one_question("politics:US:championship:2027")
    assert not canonical_key_identifies_one_question("politics::championship:2027")


def test_a_short_key_is_left_alone():
    """Fewer than four segments is not one of the generated topic-year keys."""
    assert canonical_key_identifies_one_question("nba:finals") is True


def test_an_absent_key_claims_nothing():
    assert canonical_key_identifies_one_question(None) is False
    assert canonical_key_identifies_one_question("") is False


# ---------------------------------------------------------------------------
# 2. WRITER ONE — the precompute task, which owns the ranking number
# ---------------------------------------------------------------------------


def _reasons_by_market(redis: FakeRedis) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for key, _ttl, value in redis.written:
        if not isinstance(key, str) or not key.startswith("interestingness:"):
            continue
        out[int(key.split(":")[1])] = json.loads(value)["reasons"]
    return out


def _scores_by_market(redis: FakeRedis) -> dict[int, float]:
    out: dict[int, float] = {}
    for key, _ttl, value in redis.written:
        if not isinstance(key, str) or not key.startswith("interestingness:"):
            continue
        out[int(key.split(":")[1])] = json.loads(value)["score"]
    return out


@pytest.mark.asyncio
async def test_the_cached_score_carries_no_multi_source_for_a_topic_year_key(
    monkeypatch,
):
    """THE regression. Both markets have two distinct sources behind their key;
    only the one whose key names a question may be scored for it."""
    redis = FakeRedis()
    house = FakeMarket(108621, outcomes=[FakeOutcome(0.855, 2.0)], key=HOUSE_KEY)
    senate = FakeMarket(
        108622, outcomes=[FakeOutcome(0.855, 2.0)], key="politics:US:championship:2027"
    )
    session = FakeSession(
        [
            _KeyRows([HOUSE_KEY, "politics:US:championship:2027"]),
            _CountRows([(HOUSE_KEY, 2), ("politics:US:championship:2027", 2)]),
            _ScalarRows([house, senate]),
            _ScalarRows([]),
        ]
    )
    _patch(monkeypatch, session, redis)

    from app.tasks.precompute_interestingness import _precompute_interestingness

    result = await _precompute_interestingness()
    assert result["status"] == "ok"

    reasons = _reasons_by_market(redis)
    assert "multi_source" not in reasons[108621], (
        "the House card was scored for a second venue on the strength of "
        f"{HOUSE_KEY!r}, whose only Polymarket rows are settled markets about "
        "EU debt, Greenland and a Ukraine ceasefire"
    )
    assert "multi_source" in reasons[108622], (
        "a key that names a question must keep its cross-source credit — "
        "refusing every key is the opposite defect, not the fix"
    )


@pytest.mark.asyncio
async def test_the_refusal_is_worth_the_measured_points(monkeypatch):
    """Not just a missing label: the two cards must actually score apart, or the
    displacement this ship is about has not been undone."""
    redis = FakeRedis()
    house = FakeMarket(108621, outcomes=[FakeOutcome(0.855, 2.0)], key=HOUSE_KEY)
    senate = FakeMarket(
        108622, outcomes=[FakeOutcome(0.855, 2.0)], key="politics:US:championship:2027"
    )
    session = FakeSession(
        [
            _KeyRows([HOUSE_KEY, "politics:US:championship:2027"]),
            _CountRows([(HOUSE_KEY, 2), ("politics:US:championship:2027", 2)]),
            _ScalarRows([house, senate]),
            _ScalarRows([]),
        ]
    )
    _patch(monkeypatch, session, redis)

    from app.tasks.precompute_interestingness import _precompute_interestingness

    await _precompute_interestingness()

    scores = _scores_by_market(redis)
    assert scores[108622] > scores[108621], (
        "two otherwise identical markets scored the same, so the topic-year "
        "key is still buying a multi-source bonus"
    )


# ---------------------------------------------------------------------------
# 3. WRITER TWO — the route, which owns `sources` / `source_count` and the trace
# ---------------------------------------------------------------------------


class _Row:
    def __init__(self, key, source=None, source_count=None, sources=None):
        self.canonical_market_key = key
        self.source = source
        self.source_count = source_count
        self.sources = sources


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    """Records the statements it was asked to run."""

    def __init__(self, rows):
        self._rows = rows
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self._rows)


@pytest.mark.asyncio
async def test_the_keyed_branch_never_asks_about_a_topic_year_key():
    """Dropped BEFORE the query: the coarse buckets are the expensive ones
    (1,419 rows behind the House key alone), so refusing them must not cost a
    scan to discover."""
    db = _Session([_Row("politics:US:championship:2027", "kalshi")])

    counts, names = await feed_module._query_canonical_source_counts(
        db, {HOUSE_KEY, "politics:US:championship:2027"}
    )

    assert db.statements, "the keyed branch issued no statement at all"
    rendered = str(
        db.statements[-1].compile(compile_kwargs={"literal_binds": True})
    )
    assert HOUSE_KEY not in rendered, (
        "the topic-year key reached the database — it must be dropped before "
        "the query, not after"
    )
    assert "politics:US:championship:2027" in rendered
    assert HOUSE_KEY not in counts and HOUSE_KEY not in names


@pytest.mark.asyncio
async def test_a_candidate_set_of_only_topic_year_keys_asks_nothing():
    """Filtering to empty must short-circuit, never fall through to the unkeyed
    group-by over every keyed row in the table."""
    db = _Session([])

    counts, names = await feed_module._query_canonical_source_counts(
        db, set(MEASURED_UNSAFE_KEYS)
    )

    assert counts == {} and names == {}
    assert db.statements == [], (
        "a fully-refused candidate set fell through and grouped the whole table"
    )


@pytest.mark.asyncio
async def test_the_admin_trace_agrees_with_the_feed():
    """The unkeyed branch feeds `/api/admin/discover-quality/trace`. A trace that
    reported the pre-fix count would send the next reader hunting a defect the
    feed no longer has (notice 37)."""
    db = _Session(
        [
            _Row(HOUSE_KEY, source_count=2, sources=["kalshi", "polymarket"]),
            _Row(
                "politics:US:championship:2027",
                source_count=2,
                sources=["kalshi", "polymarket"],
            ),
        ]
    )

    counts, names = await feed_module._query_canonical_source_counts(db, None)

    assert HOUSE_KEY not in counts, (
        "the admin trace still reports 2 sources for the House card while the "
        "feed scores it as 1"
    )
    assert HOUSE_KEY not in names
    assert counts["politics:US:championship:2027"] == 2


@pytest.mark.asyncio
async def test_a_refused_key_falls_back_to_the_markets_own_source():
    """The call sites read `.get(key, 1)` and `.get(key, [market.source])`, so
    dropping the key IS the fix — this pins that the fallback is reached rather
    than a `0` or an empty source list being served."""
    db = _Session([])

    counts, names = await feed_module._query_canonical_source_counts(db, {HOUSE_KEY})

    assert counts.get(HOUSE_KEY, 1) == 1
    assert names.get(HOUSE_KEY, ["kalshi"]) == ["kalshi"]


# ---------------------------------------------------------------------------
# 4. one predicate, not two copies
# ---------------------------------------------------------------------------


def test_both_writers_read_the_same_predicate():
    """The defect was one guarded caller and one unguarded one. A second copy of
    the rule is how that comes back."""
    import app.tasks.precompute_interestingness as task_module

    assert (
        feed_module.canonical_key_identifies_one_question
        is canonical_key_identifies_one_question
    )
    assert (
        task_module.canonical_key_identifies_one_question
        is canonical_key_identifies_one_question
    )
    assert (
        feed_module._canonical_key_identifies_one_question
        is canonical_key_identifies_one_question
    ), "the feed's dedupe path must read the shared predicate, not a local copy"


def test_the_utility_module_imports_nothing_from_the_app():
    """`sport_keys.py` idiom: both a route and a task read this, so it must not
    be able to close an import cycle."""
    from pathlib import Path

    import app.utils.canonical_market_key as mod

    source = Path(mod.__file__).read_text()
    offenders = [
        line
        for line in source.splitlines()
        if line.startswith(("import app", "from app"))
    ]
    assert offenders == [], f"canonical_market_key.py imports app code: {offenders}"


def test_the_dedupe_path_still_refuses_what_it_always_refused():
    """The rename must not have changed dedupe behaviour — the bucket it has
    always refused is still refused."""
    assert not feed_module._canonical_key_identifies_one_question(HOUSE_KEY)
    assert feed_module._canonical_key_identifies_one_question("nba:NBA:championship:2026")
