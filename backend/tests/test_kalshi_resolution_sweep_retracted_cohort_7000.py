"""#7000 — the sweep reaches the families no grading band can ever ask about.

A Kalshi family whose EVERY leg carries `ungradeable_result` is invisible to all
three bands in `backfill_winners`: band 1 excludes retracted legs by name, band 2
requires `status = 'resolved'`, and band 3 requires at least one leg carrying an
AUTHORITATIVE source — which this cohort by definition has none of. So when the
venue finalises one, nothing in the product finds out, and the reader keeps
seeing a live price on a decided question.

WHAT A READER SAW (production, 2026-09-18). `/entertainment` served "How many
Emmys will 'The Pitt' win?" as `Exactly 6 · 98%`, captioned **Resolves Dec 31,
2026**, three days after Kalshi finalised all 25 legs with `Exactly 6 = yes`.
Our row: `status='open'`, `resolution_date = expiration_time = 2026-12-31`,
25 legs, 0 winners, all 25 `ungradeable_result`, `updated_at` frozen at
2026-09-11 — four days BEFORE the venue closed it (gotcha #33: the open-market
poll stops seeing a market the moment the venue stops listing it).

This sweep is the only rail that can reach it, and it already could: the
specimen satisfies every clause of `SELECT_SQL`. It was simply ranked by the
inherited `updated_at ASC`, i.e. by the poller's coverage, near the back of a
~7,000-row queue drained 500 a night.

THE MEASUREMENT THAT SIZED IT, and the one that rejected the first idea:

  * the cohort is 3,464 open families (2,902 of them tier 1-3);
  * 25 drawn pseudo-randomly and probed at Kalshi itself: 3 finalised with a
    full set of per-leg results, the rest genuinely `active` — ~12% yield,
    against the beat's own measured base-order yield of 0.8%;
  * a STALENESS gate ("retracted AND not price-polled for a day") was tried and
    REJECTED — the head of that cohort probed as `KXSWEDENPARLI-26` and eight
    2027 `KXNFLSEED` tickers, every one active. Membership is the retraction
    ALONE. See `RETRACTED_COHORT_RANK_SQL` for the full note.

So these guards are about RANK and about MEMBERSHIP, and the load-bearing pair
is `test_a_legless_market_is_not_in_the_cohort` (the `NOT EXISTS` half is
vacuously true for a market with no legs at all) and
`test_a_partly_graded_family_is_not_in_the_cohort` (those ARE reachable by the
other bands, so promoting them would spend the batch's head on rows that already
have a rail).

Clocks are literals (gotcha #44).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tasks import kalshi_resolution_sweep as sweep  # noqa: E402
from app.utils.kalshi_fabricated_loss import RETRACTION_SOURCE  # noqa: E402
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS  # noqa: E402

#: The instant the cohort was measured on production. A literal, never `now()`.
NOW = datetime(2026, 9, 18, 21, 0, tzinfo=timezone.utc)
PURGE_FLOOR = NOW - timedelta(days=PROVABLY_PURGED_AGE_DAYS)

CREATE_MARKETS = """
    CREATE TABLE futures_markets (
        id INTEGER PRIMARY KEY,
        external_id TEXT,
        source TEXT,
        status TEXT,
        market_tier INTEGER,
        commence_time TEXT,
        resolution_date TEXT,
        expiration_time TEXT,
        updated_at TEXT
    )
"""

CREATE_OUTCOMES = """
    CREATE TABLE futures_outcomes (
        id INTEGER PRIMARY KEY,
        market_id INTEGER,
        resolution_source TEXT
    )
"""

INSERT_MARKET = """
    INSERT INTO futures_markets
        (id, external_id, source, status, market_tier, commence_time,
         resolution_date, expiration_time, updated_at)
    VALUES (:id, :external_id, 'kalshi', 'open', 5, :commence_time,
            :resolution_date, NULL, :updated_at)
"""

INSERT_LEG = """
    INSERT INTO futures_outcomes (market_id, resolution_source)
    VALUES (:market_id, :resolution_source)
"""


def _seed(markets):
    """`markets` is a list of `(id, external_id, updated_at, [leg sources])`.

    A leg source of `None` is a leg nobody has graded, which is the ordinary
    ungraded state and NOT a retraction.
    """
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(CREATE_MARKETS))
        conn.execute(text(CREATE_OUTCOMES))
        for mid, ext, updated_at, legs in markets:
            conn.execute(
                text(INSERT_MARKET),
                {
                    "id": mid,
                    "external_id": ext,
                    "commence_time": (NOW - timedelta(days=1)).isoformat(),
                    "resolution_date": (NOW + timedelta(days=30)).isoformat(),
                    "updated_at": updated_at.isoformat(),
                },
            )
            for src in legs:
                conn.execute(
                    text(INSERT_LEG), {"market_id": mid, "resolution_source": src}
                )
    return engine


def _select(engine, *, limit=100, offset=0, now=NOW):
    tokens = sweep.past_event_band_tokens(now)
    sql = sweep.banded_select_sql(len(tokens))
    with engine.begin() as conn:
        rows = conn.execute(
            text(sql),
            {
                "purge_floor": PURGE_FLOOR.isoformat(),
                "limit": limit,
                "offset": offset,
                **sweep.band_bind_params(tokens),
            },
        ).all()
    return [r[1] for r in rows]


#: A ticker with no `YYMONDD` segment, so the played-game band cannot rank it and
#: the cohort rank is the only thing that can. This is the real specimen's shape.
RETRACTED = [RETRACTION_SOURCE] * 3
FRESH = NOW - timedelta(minutes=5)
STALE = NOW - timedelta(days=40)


# --- membership --------------------------------------------------------------


class TestWhatIsInTheCohort:
    def test_a_fully_retracted_family_outranks_a_fresher_row(self):
        """The whole ship: the specimen's shape beats the inherited ordering.

        `updated_at ASC` would put the never-touched row first. The retracted
        family is the one the venue may have answered, so it leads.
        """
        engine = _seed(
            [
                (1, "KXOTHER-26ALPHA", STALE, [None, None]),
                (2, "KXEMMYCOUNT-26PIT", FRESH, RETRACTED),
            ]
        )

        assert _select(engine) == ["KXEMMYCOUNT-26PIT", "KXOTHER-26ALPHA"]

    def test_a_partly_graded_family_is_not_in_the_cohort(self):
        """One non-retracted leg and another band can already see it.

        This is the discriminator, not a detail: band 1 selects on "a leg that is
        neither authoritative nor `ungradeable_result`" and band 3 on "at least
        one AUTHORITATIVE leg". A family with a mixed leg set has a rail. Only a
        family where every leg is retracted has none, and promoting the mixed
        ones would spend the batch's head on rows that are already covered.
        """
        # THE STAMPS OPPOSE THE EXPECTED ANSWER ON PURPOSE. The mixed rows are
        # the STALE ones, so the inherited `updated_at ASC` would put them
        # first: the only thing that can lift the pure family to the head is the
        # cohort rank. Seeded the other way round the assertion passes whether
        # or not the rank exists, which is the flaw the mutation run found.
        engine = _seed(
            [
                (1, "KXMIXED-26BETA", STALE, [RETRACTION_SOURCE, None]),
                (2, "KXMIXED-26GAMMA", STALE, [RETRACTION_SOURCE, "api_settlement"]),
                (3, "KXPURE-26DELTA", FRESH, RETRACTED),
            ]
        )

        assert _select(engine)[0] == "KXPURE-26DELTA"

    def test_a_legless_market_is_not_in_the_cohort(self):
        """THE VACUITY TRAP, and the reason the rank is an EXISTS *pair*.

        "Every leg is retracted" spelled as `NOT EXISTS (a non-retracted leg)`
        alone is VACUOUSLY TRUE for a market with no legs at all — and a market
        with no legs is the one thing the venue certainly cannot grade. Without
        the paired `EXISTS (a retracted leg)` the sweep would promote exactly the
        rows with nothing to find, ahead of the ones with something.

        The legless row is the STALE one, so `updated_at ASC` would lead with it
        and only the paired `EXISTS` can demote it. Seeded the other way round
        this guard passes against the vacuous predicate — measured, not assumed:
        it did, until the mutation run caught it.
        """
        engine = _seed(
            [
                (1, "KXLEGLESS-26EPSILON", STALE, []),
                (2, "KXRETRACTED-26ZETA", FRESH, RETRACTED),
            ]
        )

        assert _select(engine) == ["KXRETRACTED-26ZETA", "KXLEGLESS-26EPSILON"]

    def test_an_ordinary_ungraded_family_is_not_in_the_cohort(self):
        """`NULL` legs are the ordinary ungraded state, not a retraction.

        Band 1 exists for these. If they ranked with the cohort the promotion
        would be most of the population and would rank nothing.

        Stamps oppose the expected answer, as in the two guards above: the
        ungraded family is STALE, so only the rank can put the retracted one
        first.
        """
        engine = _seed(
            [
                (1, "KXUNGRADED-26ETA", STALE, [None, None, None]),
                (2, "KXRETRACTED-26THETA", FRESH, RETRACTED),
            ]
        )

        assert _select(engine) == ["KXRETRACTED-26THETA", "KXUNGRADED-26ETA"]


# --- rank position -----------------------------------------------------------


class TestWhereTheCohortSits:
    def test_the_played_game_band_still_leads(self):
        """Second, not first, and the two yields are why.

        The played-game band probed at ~67% and this cohort at ~12%. Promoting
        the weaker signal above the stronger one would spend the head of a
        500-row batch on it. A guard rather than a comment because the order of
        two sort terms is exactly the kind of thing a later edit reverses by
        accident.
        """
        played = f"KXNCAAF1H-{NOW.year % 100:02d}SEP17UTEPOKLA"
        engine = _seed(
            [
                (1, "KXRETRACTED-26IOTA", FRESH, RETRACTED),
                (2, played, FRESH, [None]),
            ]
        )

        assert _select(engine) == [played, "KXRETRACTED-26IOTA"]

    def test_within_the_cohort_the_inherited_ordering_still_decides(self):
        """The new term ranks the cohort, it does not re-order inside it.

        `updated_at ASC` still decides among promoted rows, so the sweep keeps
        preferring the row it has looked at least recently.
        """
        engine = _seed(
            [
                (1, "KXRETRACTED-26KAPPA", FRESH, RETRACTED),
                (2, "KXRETRACTED-26LAMBDA", STALE, RETRACTED),
            ]
        )

        assert _select(engine) == ["KXRETRACTED-26LAMBDA", "KXRETRACTED-26KAPPA"]


# --- it is an order, never a filter ------------------------------------------


class TestItIsAnOrderAndNotAFilter:
    def test_no_row_is_lost_to_the_new_term(self):
        """#3284's rule, restated for the second term.

        A filter would strand every non-retracted row; a sort merely ranks them
        later and they are still reached. The population must be identical with
        and without the promotion.
        """
        markets = [
            (1, "KXRETRACTED-26MU", FRESH, RETRACTED),
            (2, "KXUNGRADED-26NU", FRESH, [None]),
            (3, "KXLEGLESS-26XI", FRESH, []),
            (4, "KXMIXED-26OMICRON", FRESH, [RETRACTION_SOURCE, "api_settlement"]),
        ]

        assert sorted(_select(_seed(markets))) == sorted(m[1] for m in markets)

    def test_the_predicate_is_byte_identical_to_the_unbanded_select(self):
        """The new term may only touch the ORDER BY.

        `banded_select_sql` is surgery on `SELECT_SQL`'s own text; if the head
        ever differs, the sweep is selecting a different population than every
        CERT-766 / CAL-P992 guard validated.
        """
        banded = sweep.banded_select_sql(len(sweep.past_event_band_tokens(NOW)))

        assert (
            banded.partition("ORDER BY")[0]
            == sweep.SELECT_SQL.partition("ORDER BY")[0]
        )

    def test_the_cohort_rank_survives_an_empty_played_game_band(self):
        """`band_rank_sql(0)` is the literal `NULL`, and the second term must
        still rank behind it.

        The zero-token case is the one #3284 says fails in production rather
        than in a guard, so the second term is exercised there too.
        """
        engine = _seed(
            [
                (1, "KXUNGRADED-26PI", STALE, [None]),
                (2, "KXRETRACTED-26RHO", FRESH, RETRACTED),
            ]
        )
        sql = sweep.banded_select_sql(0)

        with engine.begin() as conn:
            rows = conn.execute(
                text(sql),
                {"purge_floor": PURGE_FLOOR.isoformat(), "limit": 100, "offset": 0},
            ).all()

        assert [r[1] for r in rows] == ["KXRETRACTED-26RHO", "KXUNGRADED-26PI"]


# --- the cursor and the report -----------------------------------------------


class TestTheRunCanBeAudited:
    def test_the_cursor_was_re_versioned_for_the_new_order(self):
        """An offset is a position in an ORDER, and the order changed.

        Resuming a `:v2` offset under this ordering would skip an arbitrary
        slice on the first run after deploy and nothing would report it.
        """
        assert sweep.SWEEP_CURSOR_KEY.endswith(":v3")

    def test_the_population_count_selects_the_cohort(self):
        """`fully_retracted_total` is the number that says the promotion works.

        It is appended to `COUNT_SQL`, so this also pins that the four columns
        the reader already depends on keep their positions.
        """
        engine = _seed(
            [
                (1, "KXRETRACTED-26SIGMA", FRESH, RETRACTED),
                (2, "KXRETRACTED-26TAU", FRESH, RETRACTED),
                (3, "KXUNGRADED-26UPSILON", FRESH, [None]),
                (4, "KXLEGLESS-26PHI", FRESH, []),
            ]
        )

        with engine.begin() as conn:
            totals = conn.execute(
                text(sweep.COUNT_SQL), {"purge_floor": PURGE_FLOOR.isoformat()}
            ).first()

        assert totals[0] == 4  # eligible_total, position unchanged
        assert totals[4] == 2  # the two fully-retracted families, and only those
