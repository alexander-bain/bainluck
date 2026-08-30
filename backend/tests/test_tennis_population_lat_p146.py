"""LAT-P146 — the tennis event page stops rebuilding the whole tennis universe.

`GET /api/event/event:tennis:...` measured 21.0 s on production `944c466e`, and
30.3 s (Heroku H12 — the reader got an error page) on one of the US Open's alias
slugs. The cause was a 23,101-market / 50,842-outcome ORM load, in ~47 queries,
to render 1,307 children and one winner field.

These guards pin the two halves of the fix and, more importantly, the properties
that make them SAFE:

* the shared resolved arm is a **strict superset** — the caller's exact window is
  re-applied on every read, so a stale cache can only ever be missing a row that
  resolved minutes ago and can never serve one that has aged out;
* it carries **identity only** — no price and no grade is ever read from it;
* `winner_candidate_ids` is a **provable superset** of every market
  `select_winner_field` can ask an outcome count about, and the proof here drives
  the real resolver and records what it actually asks for rather than asserting
  a list someone wrote down.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils import tennis_population as tp

UTC = timezone.utc
NOW = datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


class FakeRedis:
    """Just enough Redis, with a switch for every failure the module handles."""

    def __init__(self, *, fail_get=False, fail_set=False):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}
        self.fail_get = fail_get
        self.fail_set = fail_set
        self.gets: list[str] = []

    def get(self, key):
        self.gets.append(key)
        if self.fail_get:
            raise RuntimeError("redis down")
        return self.store.get(key)

    def setex(self, key, ttl, value):
        if self.fail_set:
            raise RuntimeError("redis down")
        self.store[key] = value
        self.ttls[key] = ttl


class FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class FakeDb:
    """Returns queued results in order and records the statements it was given."""

    def __init__(self, results):
        self._results = list(results)
        self.statements: list[object] = []

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        if not self._results:
            return FakeResult([])
        return FakeResult(self._results.pop(0))


def market_row(
    market_id,
    name,
    *,
    status="open",
    resolution=None,
    group_id=None,
    source="polymarket",
    volume=0.0,
):
    """A selected row, shaped the way SQLAlchemy hands one back: named columns."""
    return SimpleNamespace(
        id=market_id,
        name=name,
        status=status,
        resolution_date=resolution,
        group_id=group_id,
        source=source,
        volume_24h=volume,
    )


def outcome_row(market_id, name, probability=0.5, is_winner=False):
    return SimpleNamespace(
        market_id=market_id,
        name=name,
        current_probability=probability,
        is_winner=is_winner,
    )


# ---------------------------------------------------------------------------
# 1. Row encoding — the cache's wire shape
# ---------------------------------------------------------------------------


class TestRowCodec:
    def test_round_trip_preserves_every_field(self):
        when = datetime(2026, 8, 12, 3, 4, 5, tzinfo=UTC)
        row = tp.MarketRow(7, "US Open Winner", "resolved", when, "pm:1", "kalshi", 12.5)
        back = tp._decode_row(tp._encode_row(row))
        assert back is not None
        assert (back.id, back.name, back.status) == (7, "US Open Winner", "resolved")
        assert back.resolution_date == when
        assert (back.group_id, back.source, back.volume_24h) == ("pm:1", "kalshi", 12.5)

    def test_round_trip_survives_a_null_resolution_date(self):
        row = tp.MarketRow(7, "n", "open", None, None, None, None)
        back = tp._decode_row(tp._encode_row(row))
        assert back is not None and back.resolution_date is None

    def test_a_naive_cached_datetime_is_read_as_utc(self):
        raw = [1, "n", "resolved", "2026-08-12T03:04:05", None, None, None]
        back = tp._decode_row(raw)
        assert back is not None
        assert back.resolution_date == datetime(2026, 8, 12, 3, 4, 5, tzinfo=UTC)

    @pytest.mark.parametrize(
        "raw",
        [
            [1, "n", "open"],                                   # short
            "not-a-row",                                        # not a sequence of 7
            ["one", "n", "open", None, None, None, None],       # id is not an int
            [1, "n", "open", "not-a-date", None, None, None],   # undecodable date
        ],
    )
    def test_a_malformed_row_decodes_to_none_rather_than_raising(self, raw):
        assert tp._decode_row(raw) is None

    def test_the_cache_generation_is_in_both_keys(self):
        assert tp.CACHE_GENERATION in tp.PRIMARY_KEY
        assert tp.CACHE_GENERATION in tp.MIRROR_KEY
        assert tp.PRIMARY_KEY != tp.MIRROR_KEY


# ---------------------------------------------------------------------------
# 2. Reading and writing the shared arm
# ---------------------------------------------------------------------------


class TestCacheSlots:
    def test_a_hit_decodes_every_row(self):
        rc = FakeRedis()
        rows = [tp.MarketRow(i, f"m{i}", "resolved", NOW, None, "kalshi", 1.0) for i in range(3)]
        tp._write_cached(rc, rows)
        got = tp._read_cached(rc, tp.PRIMARY_KEY)
        assert [r.id for r in got] == [0, 1, 2]

    def test_an_empty_population_is_never_stored(self):
        """gotcha #53 — a zero-row read is either an empty month of tennis or a
        broken query, and freezing the second into a 24 h mirror blanks the page
        for a day."""
        rc = FakeRedis()
        tp._write_cached(rc, [])
        assert rc.store == {}

    def test_both_slots_are_written_with_their_own_ttls(self):
        rc = FakeRedis()
        tp._write_cached(rc, [tp.MarketRow(1, "m", "resolved", NOW, None, "k", 1.0)])
        assert rc.ttls[tp.PRIMARY_KEY] == tp.RESOLVED_TTL_SECONDS
        assert rc.ttls[tp.MIRROR_KEY] == tp.RESOLVED_MIRROR_TTL_SECONDS

    def test_a_write_failure_is_swallowed(self):
        tp._write_cached(
            FakeRedis(fail_set=True),
            [tp.MarketRow(1, "m", "resolved", NOW, None, "k", 1.0)],
        )  # must not raise

    def test_no_client_is_a_miss_not_a_crash(self):
        assert tp._read_cached(None, tp.PRIMARY_KEY) is None
        tp._write_cached(None, [tp.MarketRow(1, "m", "resolved", NOW, None, "k", 1.0)])

    def test_a_read_failure_is_a_miss(self):
        assert tp._read_cached(FakeRedis(fail_get=True), tp.PRIMARY_KEY) is None

    def test_an_empty_list_payload_reads_as_empty_not_as_absent(self):
        """`[]` and `None` are different answers and stay different (gotcha #53)."""
        rc = FakeRedis()
        rc.store[tp.PRIMARY_KEY] = tp._dumps([])
        assert tp._read_cached(rc, tp.PRIMARY_KEY) == []

    def test_an_oversized_payload_is_refused_without_decoding(self, caplog):
        rc = FakeRedis()
        rc.store[tp.PRIMARY_KEY] = b"x" * (tp.MAX_PAYLOAD_BYTES + 1)
        with caplog.at_level(logging.WARNING):
            assert tp._read_cached(rc, tp.PRIMARY_KEY) is None
        assert "refusing" in caplog.text

    def test_an_undecodable_payload_is_a_miss(self):
        rc = FakeRedis()
        rc.store[tp.PRIMARY_KEY] = b"{not json"
        assert tp._read_cached(rc, tp.PRIMARY_KEY) is None

    def test_a_payload_that_is_not_a_list_is_a_miss(self):
        rc = FakeRedis()
        rc.store[tp.PRIMARY_KEY] = tp._dumps({"rows": []})
        assert tp._read_cached(rc, tp.PRIMARY_KEY) is None

    def test_one_malformed_row_does_not_empty_the_population(self, caplog):
        """gotcha #42 — the healthy siblings survive, and the drop is logged."""
        rc = FakeRedis()
        good = tp._encode_row(tp.MarketRow(9, "m", "resolved", NOW, None, "k", 1.0))
        rc.store[tp.PRIMARY_KEY] = tp._dumps([good, [1, 2], good])
        with caplog.at_level(logging.WARNING):
            rows = tp._read_cached(rc, tp.PRIMARY_KEY)
        assert [r.id for r in rows] == [9, 9]
        assert "malformed" in caplog.text


# ---------------------------------------------------------------------------
# 3. THE SUPERSET PROPERTY — the reason a shared arm is allowed at all
# ---------------------------------------------------------------------------


class TestSupersetWindow:
    def test_the_widening_outlives_the_mirror(self):
        """If the cached query did not reach further back than the mirror lives,
        a payload served from the mirror could be MISSING rows the caller's own
        cutoff still admits — the one direction the superset forbids."""
        assert tp.CUTOFF_SLACK_SECONDS > tp.RESOLVED_MIRROR_TTL_SECONDS

    def test_within_drops_rows_outside_the_exact_window(self):
        cutoff = NOW - timedelta(days=30)
        inside = tp.MarketRow(1, "in", "resolved", cutoff + timedelta(hours=1), None, "k", 0)
        edge = tp.MarketRow(2, "edge", "resolved", cutoff, None, "k", 0)
        outside = tp.MarketRow(3, "out", "resolved", cutoff - timedelta(hours=1), None, "k", 0)
        assert [r.id for r in tp._within([inside, edge, outside], cutoff)] == [1, 2]

    def test_within_drops_a_row_with_no_resolution_date(self):
        cutoff = NOW - timedelta(days=30)
        assert tp._within([tp.MarketRow(1, "n", "resolved", None, None, "k", 0)], cutoff) == []

    async def test_a_cached_row_that_has_aged_out_is_not_served(self):
        """The load-bearing case. The cache holds a wider window than any caller
        asks for; the caller's exact cutoff is what decides."""
        cutoff = NOW - timedelta(days=30)
        rc = FakeRedis()
        tp._write_cached(
            rc,
            [
                tp.MarketRow(1, "fresh", "resolved", NOW - timedelta(days=2), None, "k", 0),
                tp.MarketRow(2, "ancient", "resolved", NOW - timedelta(days=200), None, "k", 0),
            ],
        )
        db = FakeDb([])
        rows = await tp.resolved_arm(db, cutoff, rc=rc)
        assert [r.id for r in rows] == [1]
        assert db.statements == []  # a hit never touches the database

    async def test_a_miss_queries_the_WIDENED_cutoff(self):
        cutoff = NOW - timedelta(days=30)
        rc = FakeRedis()
        db = FakeDb([[]])
        captured = {}

        async def _fetch(_db, when):
            captured["cutoff"] = when
            return []

        original = tp.fetch_resolved_arm
        tp.fetch_resolved_arm = _fetch
        try:
            await tp.resolved_arm(db, cutoff, rc=rc)
        finally:
            tp.fetch_resolved_arm = original

        assert captured["cutoff"] < cutoff
        assert cutoff - captured["cutoff"] == timedelta(seconds=tp.CUTOFF_SLACK_SECONDS)

    async def test_a_miss_fills_the_cache_and_still_applies_the_exact_window(self):
        cutoff = NOW - timedelta(days=30)
        rc = FakeRedis()
        db = FakeDb(
            [
                [
                    market_row(1, "fresh", status="resolved", resolution=NOW - timedelta(days=1)),
                    market_row(2, "old", status="resolved", resolution=NOW - timedelta(days=90)),
                ]
            ]
        )
        rows = await tp.resolved_arm(db, cutoff, rc=rc)
        assert [r.id for r in rows] == [1]
        # BOTH were cached — the cache is the wider set, the filter is the narrow one.
        assert [r.id for r in tp._read_cached(rc, tp.PRIMARY_KEY)] == [1, 2]

    async def test_a_failed_scan_serves_the_mirror(self, caplog):
        cutoff = NOW - timedelta(days=30)
        rc = FakeRedis()
        tp._write_cached(
            rc, [tp.MarketRow(5, "m", "resolved", NOW - timedelta(days=1), None, "k", 0)]
        )
        rc.store.pop(tp.PRIMARY_KEY)  # primary expired, mirror survives

        class Boom(FakeDb):
            async def execute(self, *a, **k):
                raise RuntimeError("scan failed")

        with caplog.at_level(logging.WARNING):
            rows = await tp.resolved_arm(Boom([]), cutoff, rc=rc)
        assert [r.id for r in rows] == [5]
        assert "serving the mirror" in caplog.text

    async def test_a_failed_scan_with_no_mirror_raises(self):
        class Boom(FakeDb):
            async def execute(self, *a, **k):
                raise RuntimeError("scan failed")

        with pytest.raises(RuntimeError):
            await tp.resolved_arm(Boom([]), NOW - timedelta(days=30), rc=FakeRedis())


# ---------------------------------------------------------------------------
# 4. Identity only — no price and no grade comes out of the shared arm
# ---------------------------------------------------------------------------


class TestSharedArmCarriesIdentityOnly:
    def test_the_encoded_row_has_no_price_and_no_grade(self):
        row = tp.MarketRow(1, "m", "resolved", NOW, "g", "kalshi", 3.0)
        row.outcomes = [tp.OutcomeRow("Alcaraz", 0.9, True)]
        encoded = tp._encode_row(row)
        assert len(encoded) == 7
        flat = repr(encoded)
        assert "Alcaraz" not in flat and "0.9" not in flat

    def test_a_decoded_row_starts_with_no_outcomes(self):
        row = tp._decode_row(tp._encode_row(tp.MarketRow(1, "m", "resolved", NOW, None, "k", 0)))
        assert row.outcomes == []

    def test_a_selected_row_keeps_outcomes_it_already_carries(self):
        """Fill what is missing, never empty what is there. The production
        projection selects no outcomes, so this is empty on both arms — but a
        reader that DESTROYS what its caller handed it turns a market with
        prices into a child with none, silently."""
        seeded = SimpleNamespace(
            id=1,
            name="m",
            status="open",
            resolution_date=None,
            group_id=None,
            source="k",
            volume_24h=0,
            outcomes=[SimpleNamespace(name="Alcaraz", current_probability=0.5)],
        )
        assert [o.name for o in tp._row_to_market(seeded).outcomes] == ["Alcaraz"]

    def test_a_selected_row_without_outcomes_starts_empty(self):
        assert tp._row_to_market(market_row(1, "m")).outcomes == []


# ---------------------------------------------------------------------------
# 5. winner_candidate_ids — proved against the real resolver
# ---------------------------------------------------------------------------


def _corpus():
    """A corpus with every shape `select_winner_field` distinguishes."""
    from app.utils.tennis_population import MarketRow

    def m(mid, name, vol=1.0):
        row = MarketRow(mid, name, "open", None, None, "polymarket", vol)
        return row

    rows = [
        m(1, "US Open Men's Singles Winner"),
        m(2, "2026 Men's US Open Winner (Tennis)"),
        m(3, "US Open Women's Singles Winner"),
        m(4, "Cincinnati Open Winner"),
        m(5, "Serena Williams to Win a Tournament in 2026"),
        m(6, "Alcaraz vs Sinner"),
        m(7, "2026 Wimbledon Winner"),
        m(8, "US Open Men's Singles: Total Aces"),
        # A name made ENTIRELY of stopwords. `canonical_tokens` is empty, so the
        # subset arm can never reach it and only the exact-slug arm can — and
        # search really does emit `event:tennis:{clean_slug(name)}` for any
        # winner market, so a reader really can land on this key.
        m(9, "Men's Singles Winner"),
    ]
    for row in rows:
        row.outcomes = [
            tp.OutcomeRow("Carlos Alcaraz", 0.4),
            tp.OutcomeRow("Jannik Sinner", 0.35),
            tp.OutcomeRow("Other", 0.25),
        ]
    rows[4].outcomes = [tp.OutcomeRow("Serena Williams", 0.02)]  # the novelty prop
    return rows


@pytest.mark.parametrize(
    "slug",
    [
        "us-open-men-s-singles-winner",
        "us-open-women-s-singles-winner",
        "2026-men-s-us-open-winner-tennis",
        "cincinnati-open-winner",
        "wimbledon-2026",
        "a-tournament-that-does-not-exist",
        "",
    ],
)
def test_the_prefetch_covers_every_id_the_resolver_asks_about(slug):
    """THE PROOF, and it is a recording, not an assertion about a list.

    `select_winner_field` is driven for real; every id it asks a real-outcome
    count about is recorded, and the recorded set must be inside the prefetch.
    If the resolver's pre-count filter ever widens, this fails — which is the
    only way a two-phase load can go silently wrong.
    """
    from app.utils.event_tennis import select_winner_field
    from app.utils.outcome_display import is_field_outcome, is_placeholder_outcome_name

    corpus = _corpus()
    asked: set[int] = set()

    def _count(market):
        asked.add(market.id)
        return sum(
            1
            for o in (market.outcomes or [])
            if o.name
            and not is_field_outcome(o.name)
            and not is_placeholder_outcome_name(o.name)
        )

    select_winner_field(corpus, slug, _count)
    prefetch = set(tp.winner_candidate_ids(corpus, slug))
    assert asked <= prefetch, f"resolver asked about {sorted(asked - prefetch)}"


def test_the_prefetch_admits_an_exact_slug_match_that_is_not_a_field():
    """#1793's "a direct request is not an inference" case: the novelty prop is
    reachable by its own exact slug, so its count must be prefetchable."""
    corpus = _corpus()
    ids = tp.winner_candidate_ids(corpus, "serena-williams-to-win-a-tournament-in-2026")
    assert 5 in ids


def test_the_prefetch_reaches_a_market_only_the_exact_slug_can_reach():
    """The exact-slug arm is load-bearing on its own, and this is the case that
    proves it: `canonical_tokens("Men's Singles Winner")` is EMPTY, so the subset
    arm cannot reach that market at any slug. Drop the exact arm and the resolver
    still asks for its count while the prefetch no longer holds it — a market
    that answers by name would silently resolve on zero competitors.

    Added because mutation M19 SURVIVED the battery's first run: every other
    exact-slug market in the corpus was also reachable by subset, so removing the
    arm changed nothing any assertion could see.
    """
    corpus = _corpus()
    ids = tp.winner_candidate_ids(corpus, "men-s-singles-winner")
    assert 9 in ids


def test_the_prefetch_excludes_markets_that_are_not_winner_markets():
    corpus = _corpus()
    ids = tp.winner_candidate_ids(corpus, "us-open-men-s-singles-winner")
    assert 6 not in ids  # a matchup
    assert 8 not in ids  # a prop


def test_the_prefetch_is_far_smaller_than_the_population():
    corpus = _corpus()
    ids = tp.winner_candidate_ids(corpus, "us-open-men-s-singles-winner")
    assert len(ids) < len(corpus)


# ---------------------------------------------------------------------------
# 6. Outcome loading
# ---------------------------------------------------------------------------


class TestLoadOutcomes:
    async def test_no_ids_means_no_query(self):
        db = FakeDb([[outcome_row(1, "x")]])
        assert await tp.load_outcomes(db, []) == {}
        assert db.statements == []

    async def test_rows_are_bucketed_by_market(self):
        db = FakeDb([[outcome_row(1, "A", 0.6), outcome_row(2, "B", 0.4), outcome_row(1, "C")]])
        loaded = await tp.load_outcomes(db, [1, 2])
        assert [o.name for o in loaded[1]] == ["A", "C"]
        assert [o.name for o in loaded[2]] == ["B"]

    async def test_a_market_with_no_outcomes_gets_an_empty_list_not_a_missing_key(self):
        db = FakeDb([[]])
        loaded = await tp.load_outcomes(db, [3])
        assert loaded == {3: []}

    async def test_ids_are_deduped(self):
        db = FakeDb([[]])
        loaded = await tp.load_outcomes(db, [4, 4, 4])
        assert list(loaded) == [4]

    async def test_an_unattributable_row_is_loud(self, caplog):
        db = FakeDb([[SimpleNamespace(name="orphan")]])
        with caplog.at_level(logging.WARNING):
            await tp.load_outcomes(db, [1])
        assert "no requested market_id" in caplog.text

    async def test_is_winner_is_carried_through_as_a_bool(self):
        db = FakeDb([[outcome_row(1, "A", 1.0, is_winner=True)]])
        loaded = await tp.load_outcomes(db, [1])
        assert loaded[1][0].is_winner is True


class TestAttachOutcomes:
    def test_it_fills_what_is_empty(self):
        market = tp.MarketRow(1, "m", "open", None, None, "k", 0)
        tp.attach_outcomes([market], {1: [tp.OutcomeRow("A", 0.5)]})
        assert [o.name for o in market.outcomes] == ["A"]

    def test_it_never_empties_a_market_that_already_has_outcomes(self):
        """"Loaded nothing" and "was not asked for" are different facts."""
        market = tp.MarketRow(1, "m", "open", None, None, "k", 0)
        market.outcomes = [tp.OutcomeRow("Seeded", 0.5)]
        tp.attach_outcomes([market], {1: []})
        assert [o.name for o in market.outcomes] == ["Seeded"]

    def test_a_market_absent_from_the_load_is_left_alone(self):
        market = tp.MarketRow(9, "m", "open", None, None, "k", 0)
        tp.attach_outcomes([market], {1: [tp.OutcomeRow("A", 0.5)]})
        assert market.outcomes == []


# ---------------------------------------------------------------------------
# 7. The population itself
# ---------------------------------------------------------------------------


class TestLoadPopulation:
    async def test_the_open_arm_is_read_fresh_even_on_a_cache_hit(self):
        """The live half is never cached — a new match and a changed status have
        to appear immediately, and that is the whole reason the arms are split."""
        rc = FakeRedis()
        tp._write_cached(
            rc, [tp.MarketRow(2, "old", "resolved", NOW - timedelta(days=1), None, "k", 0)]
        )
        db = FakeDb([[market_row(1, "live")]])
        rows = await tp.load_population(db, now=NOW, window_days=30, rc=rc)
        assert [r.id for r in rows] == [1, 2]
        assert len(db.statements) == 1  # the open arm, and nothing else

    async def test_a_row_in_both_arms_appears_once(self):
        rc = FakeRedis()
        tp._write_cached(
            rc, [tp.MarketRow(1, "same", "resolved", NOW - timedelta(days=1), None, "k", 0)]
        )
        db = FakeDb([[market_row(1, "same")]])
        rows = await tp.load_population(db, now=NOW, window_days=30, rc=rc)
        assert [r.id for r in rows] == [1]

    async def test_the_population_is_ordered_by_id(self):
        rc = FakeRedis()
        tp._write_cached(
            rc,
            [
                tp.MarketRow(50, "b", "resolved", NOW - timedelta(days=1), None, "k", 0),
                tp.MarketRow(10, "a", "resolved", NOW - timedelta(days=1), None, "k", 0),
            ],
        )
        db = FakeDb([[market_row(30, "mid")]])
        rows = await tp.load_population(db, now=NOW, window_days=30, rc=rc)
        assert [r.id for r in rows] == [10, 30, 50]

    async def test_the_window_is_derived_from_the_caller_s_clock(self):
        rc = FakeRedis()
        tp._write_cached(
            rc,
            [
                tp.MarketRow(1, "in", "resolved", NOW - timedelta(days=29), None, "k", 0),
                tp.MarketRow(2, "out", "resolved", NOW - timedelta(days=31), None, "k", 0),
            ],
        )
        db = FakeDb([[]])
        rows = await tp.load_population(db, now=NOW, window_days=30, rc=rc)
        assert [r.id for r in rows] == [1]


# ---------------------------------------------------------------------------
# 8. Query shapes — the arms are what they claim to be
# ---------------------------------------------------------------------------


class TestQueryShapes:
    async def test_the_open_arm_selects_only_open_tennis_and_no_outcomes(self):
        db = FakeDb([[]])
        await tp.fetch_open_arm(db)
        sql = str(db.statements[0])
        assert "futures_markets" in sql
        assert "futures_outcomes" not in sql  # no selectinload, no join
        assert "llm_sport_category" in sql and "status" in sql
        assert " OR " not in sql.upper().replace("\n", " ")

    async def test_the_resolved_arm_carries_the_three_statuses_and_the_bound(self):
        db = FakeDb([[]])
        await tp.fetch_resolved_arm(db, NOW - timedelta(days=30))
        sql = str(db.statements[0])
        assert "resolution_date" in sql
        assert "futures_outcomes" not in sql
        assert tp.RESOLVED_STATUSES == ("resolved", "closed", "settled")

    async def test_neither_arm_selects_a_price_column(self):
        db = FakeDb([[], []])
        await tp.fetch_open_arm(db)
        await tp.fetch_resolved_arm(db, NOW)
        for statement in db.statements:
            sql = str(statement)
            assert "current_probability" not in sql
            assert "is_winner" not in sql


# ---------------------------------------------------------------------------
# 9. The adapter, end to end: the same page, built out of a fraction of the rows
# ---------------------------------------------------------------------------


def _adapter_corpus():
    """One winner field, one matchup in the draw, one token prop, one stranger."""
    return [
        market_row(100, "2026 Wimbledon Winner", group_id="pm:1"),
        market_row(101, "Coco Gauff vs Aryna Sabalenka"),
        market_row(102, "Wimbledon Total Aces"),
        market_row(103, "Bertran vs Soto"),  # a Challenger — neither is in the draw
    ]


def _adapter_outcomes():
    return {
        100: [
            outcome_row(100, "Coco Gauff", 0.45),
            outcome_row(100, "Aryna Sabalenka", 0.40),
            outcome_row(100, "Other", 0.10),
        ],
        101: [outcome_row(101, "Coco Gauff", 0.6), outcome_row(101, "Aryna Sabalenka", 0.4)],
        102: [outcome_row(102, "Over 200.5", 0.5)],
        103: [outcome_row(103, "Bertran", 0.5)],
    }


class _AdapterDb:
    """Serves the population once, then answers each outcome load by id."""

    def __init__(self, population, outcomes):
        self.population = population
        self.outcomes = outcomes
        self.outcome_requests: list[list[int]] = []
        self._served_population = 0

    async def execute(self, statement, *args, **kwargs):
        sql = str(statement)
        if "futures_outcomes" in sql:
            # The market ids are bound parameters of the expanding IN — which
            # SQLAlchemy renders as ONE parameter holding the whole list.
            params = statement.compile().params
            ids = set()
            for value in params.values():
                if isinstance(value, int):
                    ids.add(value)
                elif isinstance(value, (list, tuple)):
                    ids.update(v for v in value if isinstance(v, int))
            ids = sorted(ids)
            self.outcome_requests.append(ids)
            rows = []
            for market_id in ids:
                rows.extend(self.outcomes.get(market_id, []))
            return FakeResult(rows)
        self._served_population += 1
        if self._served_population == 1:
            return FakeResult(self.population)
        return FakeResult([])  # the resolved arm is empty in this fixture


class TestAdapterTwoPhaseLoad:
    async def test_the_page_is_built_and_the_stranger_is_excluded(self, monkeypatch):
        from app.utils.event_tennis import TennisEventAdapter

        monkeypatch.setattr(tp, "_get_client", lambda: None)
        db = _AdapterDb(_adapter_corpus(), _adapter_outcomes())
        envelope = await TennisEventAdapter().build_event("2026-wimbledon-winner", db)

        assert envelope is not None
        assert envelope["event"]["name"] == "2026 Wimbledon Winner"
        names = [c["name"] for c in envelope["primary"]["competitors"]]
        assert names == ["Coco Gauff", "Aryna Sabalenka"]  # "Other" dropped
        child_ids = [c["market_id"] for c in envelope["children"]]
        assert 101 in child_ids and 102 in child_ids
        assert 103 not in child_ids  # the concurrent-tournament guard still holds

        # A child without its outcomes is a row with no probability — the exact
        # thing a two-phase load can silently produce by loading the wrong phase.
        matchup = next(c for c in envelope["children"] if c["market_id"] == 101)
        assert matchup["probability"] is not None
        assert [o["name"] for o in matchup["outcomes"]] == ["Coco Gauff", "Aryna Sabalenka"]

    async def test_outcomes_are_loaded_for_candidates_and_children_only(self, monkeypatch):
        """The ship, asserted as a count: the stranger's outcomes are never read."""
        from app.utils.event_tennis import TennisEventAdapter

        monkeypatch.setattr(tp, "_get_client", lambda: None)
        db = _AdapterDb(_adapter_corpus(), _adapter_outcomes())
        await TennisEventAdapter().build_event("2026-wimbledon-winner", db)

        requested = {i for batch in db.outcome_requests for i in batch}
        assert 100 in requested          # the winner field
        assert {101, 102} <= requested   # the children
        assert 103 not in requested      # never associated, never loaded

    async def test_children_are_ordered_by_market_id(self, monkeypatch):
        from app.utils.event_tennis import TennisEventAdapter

        monkeypatch.setattr(tp, "_get_client", lambda: None)
        db = _AdapterDb(list(reversed(_adapter_corpus())), _adapter_outcomes())
        envelope = await TennisEventAdapter().build_event("2026-wimbledon-winner", db)
        ids = [c["market_id"] for c in envelope["children"]]
        assert ids == sorted(ids)

    async def test_an_empty_population_still_404s(self, monkeypatch):
        from app.utils.event_tennis import TennisEventAdapter

        monkeypatch.setattr(tp, "_get_client", lambda: None)
        db = _AdapterDb([], {})
        assert await TennisEventAdapter().build_event("2026-wimbledon-winner", db) is None
