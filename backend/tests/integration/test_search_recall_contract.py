"""#1494 — the search RECALL contract, executed against a real Postgres.

Why this file exists
--------------------
LAT-P002 sped up ``/api/events/search`` and was reverted (``f98d8104``) after
3 of 8 sampled production queries came back with ZERO futures. Its own
acceptance criterion 3 — the frozen gold set, no regression from 21/25 — was
listed as **OWED and never run**.

It was never run because nothing in this repo could run it:

* ``tests/integration/test_route_search.py`` uses a mock EMPTY db session, so
  the WHERE clause never executes against data — it pins response *shape*.
* the other ``*_seeded.py`` suites hand ``MagicMock`` rows back through a mocked
  session; again, no SQL runs.
* ``scripts/evals/search_gold_eval.py`` is a *scorer* — it grades results you
  give it. It does not fetch them.

So a whole class of defect — "the predicate silently stopped matching real
rows" — had no guard anywhere, on the p1 search surface. This file is that
guard: real Postgres, real tables, real ``pg_trgm``, real SQL, seeded rows that
MUST come back.

Following the precedent of ``tests/test_calibration_canonical_pg.py``: opt-in on
an env var so it skips where no Postgres exists, and wired into a dedicated CI
job (``search-recall`` in ``.github/workflows/ci.yml``) that provides one. CI is
the environment that runs this — not a dev sandbox.

    SEARCH_TEST_DATABASE_URL=postgresql+asyncpg://postgres@localhost/bl_searchtest \
        python3 -m pytest tests/integration/test_search_recall_contract.py -v

What each case guards
---------------------
The three queries that actually broke in production, plus the recall arms the
re-land changes:

===========================  ==========================================
case                         arm it exercises
===========================  ==========================================
masters winner               multi-term AND over ``FuturesMarket.name``
us recession 2026            name arm with a numeric term
nba champion                 name arm under a LEAGUE token present
nfl mvp                      ``_build_league_ticker_match`` (#993 L2-43)
outcome-only                 ``_outcome_id_match`` subquery
nba (league only)            bare-league arm (``league_only_explicit``)
us recession (both arms)     the LAT-P006 ``UNION`` returns EVERY arm
us recession (control row)   a sub-3-char term still FILTERS
wimbledon                    concept provenance, POSITIVE — LAT-P053
swiatek                      concept provenance, NEGATIVE — LAT-P053
===========================  ==========================================

The last two are not recall cases and are labelled so deliberately. They are the
**behavioural** half of concept provenance (#1846, ruling 041), which lived only
as an ``inspect.getsource`` assertion until LAT-P053 seeded the corpus that lets
the market-derived concept loop produce a row. See ``_CONCEPT_FUTURES_SEEDS``.

``nfl mvp`` and the outcome-only case are the subtle ones: in both, the market
NAME does not contain the whole query, so a predicate change that looks
harmless on name matching alone silently drops them.

NOTE for the re-land (#1494): commit ``2c9f961f`` claims 1c drops the FTS arm
from the WHERE with "IDENTICAL recall on the frozen benchmark". **That claim has
never been tested.** These cases are what test it. (Result: it held — the
re-land preserved recall on 7 of 8 production queries where LAT-P002 lost 3.)

SCOPE LIMIT — read this before quoting a green run
--------------------------------------------------
**This gate proves PREDICATE recall, not production recall.** It seeds a handful
of rows, so every query here is fast and nothing ever hits the request budget.

That is not hypothetical. On the LAT-P005 re-land this gate reported
``SEARCH RECALL 5/5`` and CI went green, while production STILL returned zero
futures for ``us recession 2026`` — that query costs ~23.6s against the real
table and gets dropped at the 20s deadline. **Both results were correct.** The
predicate matches; the query is too slow to finish.

So a green n/n here rules out exactly one failure mode: "the WHERE clause stopped
matching rows it should match". It says nothing about:

* timeout-induced loss, which is a function of real data volume and load;
* ranking or ordering;
* anything about a table larger than the seed.

Catching the timeout class needs a cost bound on the query itself, not a recall
assertion. LAT-P006 delivered that bound as a SQL-SHAPE guard —
``TestFuturesRecallArmsAreUnionedNotOred`` in
``tests/test_search_latency_contract.py`` — rather than as a plan or wall-clock
assertion, precisely because neither is meaningful on a small seed. Do not let a
green run HERE stand in for that; they guard different failure modes.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres search recall "
            "contract (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]


#: Every seeded OUTCOME carries a price, and that is load-bearing (#6327).
#:
#: This file's subject is the recall ARMS — name AND-match, numeric term, league
#: ticker, the outcome-id subquery, trigram — and none of them reads a price, so
#: the seeds originally left `current_probability` NULL the same way they leave
#: `volume` and `image_url` NULL: not the subject. #6327 then made the search page
#: WITHDRAW a market whose every outcome is unpriced (it was drawing a ranked
#: ladder of dashes), and an unpriced corpus is not a model of the markets this
#: gate names — "Masters Tournament Winner 2026", "NBA Champion 2026", "Ballon
#: d'Or Winner 2026" are among the most heavily traded questions on the venue.
#: Without this the whole corpus is correctly suppressed and all 21 recall cases
#: report RECALL REGRESSION against a route that is behaving exactly as ruled.
#:
#: So: an artefact of the fixture's focus, corrected — NOT the gate relaxed. The
#: withdrawal rule itself is asserted at the route in
#: `tests/integration/test_route_search_withdraws_unpriced_card_6327.py`, both
#: directions, and at the predicate in
#: `tests/test_search_withdraws_wholly_unpriced_card_6327.py`.
#:
#: One value for every leg on purpose: the rerank sorts on VOLUME (#993's
#: real-interest signal), so a uniform price cannot buy any market an ordering it
#: had not already earned, and every ordering assertion below reads the same as it
#: did when the column was NULL.
_SEED_PRICE = 0.25


# --------------------------------------------------------------------------
# Schema + seed
# --------------------------------------------------------------------------
# `Base.metadata.create_all` rather than `alembic upgrade head`: this gate is
# about the PREDICATE's recall, and the migration chain has its own guard
# (`tests/test_alembic.py`). create_all is derived from the same models the
# route queries, so the columns are identical, and it keeps the CI job fast and
# free of Heroku-release-specific migration behaviour.
#
# `pg_trgm` IS required — the fuzzy fallback uses `similarity()`/`%`, which do
# not exist without the extension. Index presence deliberately is NOT required:
# an index changes plan and speed, never the result set, so recall is
# index-independent by construction.

_FUTURES_SEEDS = [
    # (external_id, name, [outcome names])
    ("kalshi-masters-2026", "Masters Tournament Winner 2026", ["Scottie Scheffler"]),
    ("kalshi-recession-2026", "US Recession in 2026?", ["Yes", "No"]),
    ("kalshi-nbachamp-2026", "NBA Champion 2026", ["Boston Celtics"]),
    # League-ticker recall: "nfl" appears ONLY in the ticker, never in the name.
    ("KXNFLMVP-26", "MVP Winner?", ["Patrick Mahomes"]),
    # Outcome-only recall: the market name contains neither query term.
    ("kalshi-outcome-only", "Award Winner 2026", ["Caitlin Clark"]),
    # LAT-P006: `us recession` must return BOTH arms' rows. This one is reachable
    # ONLY via the outcome arm (the NAME contains neither "us" nor "recession"),
    # while "US Recession in 2026?" above is reachable only via the name arm. One
    # query, two arms, two different markets — so a change that collapses the
    # UNION to a single arm, or to an intersection, fails loudly instead of
    # quietly halving recall.
    ("kalshi-us-gdp", "Q4 GDP print above 3%?", ["US recession averted"]),
    # LAT-P006 control: matches `%recession%` but NOT `%us%`, in name or outcome.
    # It must stay OUT of the `us recession` result. This is what makes the
    # 2-character term's ENFORCEMENT observable — LAT-P006 staged "drop sub-3-char
    # terms from the outcome arm" as a candidate fix, and that candidate would let
    # this row in. The chosen UNION fix does not, and this pins the difference.
    ("kalshi-euro-gdp", "Euro area growth 2026?", ["Recession likely"]),
    # LAT-P013: the apostrophe case. `d'or` is FOUR characters, so LAT-P010's
    # `len(term) < 3` gate admitted it, but pg_trgm splits the pattern on the
    # apostrophe and can extract no trigram from `d` or `or` — so `%d'or%`
    # seq-scanned 3 GB of `futures_outcomes`. Measured 19,171ms / 13,677ms against
    # a 615ms `dora` control of the SAME LENGTH.
    #
    # Reachable via the market NAME, which is the arm the gate KEEPS. This is the
    # row that proves the fix did not buy speed with recall.
    ("kalshi-ballondor-2026", "Ballon d'Or Winner 2026", ["Lamine Yamal"]),
    # LAT-P013: the stated cost. Its NAME contains no apostrophe form at all, so
    # it is reachable ONLY through the outcome arm — the arm the gate drops for a
    # single no-trigram term. Pinned below as a DELIBERATE trade, not an accident.
    # Two outcomes on purpose: the multi-term outcome arm requires EACH term to
    # match SOME outcome of the market, so `award d'or` needs one outcome carrying
    # "award" and one carrying "d'Or". With a single outcome the multi-term case
    # would fail for a reason that has nothing to do with what it is testing.
    ("kalshi-france-award", "France Football Award 2026",
     ["Winner of the d'Or", "Award vacated"]),
    # ---- #4572: an interior substring must not outrank a real prefix. --------
    #
    # `yank` reaches BOTH of these rows and reaches them the SAME way, which is
    # the whole point: neither passes the word test, because `Yankees` stems to
    # `yanke` and the query's lexeme is `yank`. So both are tier 2 with
    # `ts_rank_cd` 0.0 and — before the fix — the page is decided by
    # `market_tier`, `volume`, `updated_at` and finally `id`.
    #
    # 🔴 SEED ORDER IS LOAD-BEARING AND MUST NOT BE "TIDIED". The ITF row is
    # listed FIRST so it takes the LOWER id, and the pre-fix ORDER BY's last key
    # is `FuturesMarket.id ASC`. That is what makes the guard RED without the
    # ranking change instead of passing on a coin-flip: with these two rows the
    # wrong answer is the DETERMINISTIC one. Swap them and the test goes green
    # against a broken ranker.
    #
    # Volume is left unset on both on purpose. `_rerank_search_futures` classes
    # both as name-matches (its `_name_match` is a plain Python substring test,
    # so "Ma*yank*" counts) and sorts that bucket by volume — a stable sort, so
    # with equal volumes the SQL order is what survives to the payload. Give one
    # of them a volume and this stops testing the ORDER BY at all.
    #
    # Transcribed from the production reading in #4572 (2026-09-10 01:35Z), where
    # the ITF row held slot 0 and the Yankees' own game held slot 3.
    ("kalshi-itf-hurghada-m15", "M15 Hurghada: Mayank Sharma vs Luis Klaus",
     ["Mayank Sharma", "Luis Klaus"]),
    ("kalshi-rockies-yankees-f5", "Colorado Rockies vs. New York Yankees - First 5 Innings Winner",
     ["New York Yankees", "Colorado Rockies"]),
    # ---- #8689: a fragment term matches at the START of a word. -------------
    #
    # `us open` reaches all three through the name arm's substring ILIKE: the
    # real US Open, "Ven*us*" and "*Aus*tralian". `us` has no trigram, so it never
    # word-votes (LAT-P037), and it is a stopword, so `ts_rank_cd` ties every
    # name carrying "Open". Transcribed from production 2026-09-25 19:12Z, where
    # the Chengdu row held slot 2 and the Australian Open slot 3 of `us open`.
    # Outcomes carry neither "open" nor both terms, so only the NAME arm can
    # admit these rows — the arm the fix changes.
    ("kalshi-usopen-mens-2027", "2027 US Open Men's Singles Winner", ["Carlos Alcaraz"]),
    ("polymarket-chengdu-dbl-8689", "Chengdu Open (Doubles): Peers/Venus vs Johnson/Zielinski",
     ["Peers/Venus", "Johnson/Zielinski"]),
    ("kalshi-ausopen-mens-8689", "Australian Open Men's Singles Winner", ["Jannik Sinner"]),
]

# LAT-P053 Item 5 — the seeded futures corpus, carried FIVE times and ruled into
# CI by Alex on 2026-08-14: *"a corpus carried five times is either an instrument
# or clutter, and it just got called an instrument."*
#
# What it unlocks that `_FUTURES_SEEDS` cannot: the market-derived **event-concept
# loop** (`events.py:3483`). That loop only mints a row when the market's
# `llm_sport_category` is in `_EVENT_CONCEPT_DOMAINS` AND its name is a
# winner-field, and no row above satisfies either condition — so every assertion
# about concept provenance has, until now, been a source assertion.
#
# `TestEveryConceptCallSiteIsRouted` in `tests/test_search_scorer_wiring.py` says
# so in its own docstring: *"The behavioural version needs the market-derived
# concept loop to produce a row, which needs a seeded futures corpus with outcomes
# and sports; that belongs to the real-Postgres contract suite and is recorded as
# owed."* This is that corpus. The source guard stays — it catches a fourth
# unrouted call site, which behaviour cannot — but it is no longer the only
# instrument.
#
# One market is enough, because the property under test is a per-ROW decision and
# the two directions are two QUERIES against the same row:
#
#   "wimbledon" — the query names the concept  -> not derived -> ranks -> present
#   "swiatek"   — reaches the same market by its OUTCOME only, so the query does
#                 NOT name the concept -> derived -> UNRANKABLE -> absent, while
#                 the market itself still comes back
#
# Verified against the real predicates before being encoded (not assumed):
# `is_winner_market("2026 Wimbledon Winner")` is True, `clean_slug` gives
# `2026-wimbledon-winner`, the label strips to "2026 Wimbledon", and
# `_query_names_concept` returns True for "wimbledon" / False for "swiatek".
# Tennis deliberately, not awards: no `_detect_query_*` resolver fires on
# "wimbledon", so the upsert path cannot clear `_derived` behind the loop's back
# and make the positive case pass for the wrong reason. ("us open" would have —
# it is also a golf major.)
_CONCEPT_FUTURES_SEEDS = [
    # (external_id, name, llm_sport_category, [outcome names])
    ("kalshi-wimbledon-2026", "2026 Wimbledon Winner", "tennis", ["Iga Swiatek"]),
]


# --------------------------------------------------------------------------
# #4723 — the /typeahead POOL, which is a different thing from /search's page
# --------------------------------------------------------------------------
#
# These rows exist to make the POOL CUT decide the answer, because that is the
# only state in which the defect is reachable. `_TYPEAHEAD_FUTURES_POOL` is 20
# and `_rerank_search_futures` runs AFTER it, so with a handful of candidates
# the reranker decides everything and the ORDER BY under test is invisible. A
# seed of five markets would go green against the very code that shipped the
# defect. So the collision classes are seeded 22 deep, on purpose.
#
# Production, `GET /api/events/typeahead?q=nfl`, 2026-09-10 08:45Z: 18 of the 20
# pool slots were i-**nfl**-ation markets and the dropdown offered four of them,
# while 181 genuine NFL futures sat below the cut (open markets whose NAME
# whole-lexeme-matches `nfl`, counted on production the same morning).
#
# THE THREE CLASSES, and each one is load-bearing:
#
#   name                       word   prefix   tier  volume   what it proves
#   -----------------------------------------------------------------------
#   NFL Playoff Qualifiers…    yes    yes        5      900   the answer
#   NFLX closing value…        no     yes        1    100..   prefix ALONE is
#                                                             not enough
#   How high will inflation…   no     no         1  10000..   the filed defect
#
# The tier/volume shape is what makes the test DISCRIMINATE rather than merely
# pass. The answer is the WORST row by both priors — tier 5, and out-traded 11x
# — so it can only reach the pool on a query-relevance key:
#
#   tier, volume (live before #4723)  -> 20 inflation rows.       answer absent
#   prefix, tier, volume (#4723 as    -> 20 NFLX rows (tier 1).   answer absent
#     filed: one key)
#   word, prefix, tier, volume        -> answer at slot 0.        PASSES
#
# The middle line is the measurement that changed the fix. On production `fed`
# (73 log hits) the one-key form is WORSE THAN LIVE — `fed:*` prefixes `feder`,
# so slots 0-3 become "Next German federal election winner?" / "Brazil Federal
# District Governor winner?", the Con-fed-eration class `_expanded_tsquery`
# documents. NFLX is that class made reproducible: a genuine prefix that is not
# the answer.
#
# Names are checked against every other query this file asserts on, so the rows
# join no other candidate set: none contains `re`, `us`, `nba`, `mvp`, `fed`,
# `sun`, `yank`, `laker`, `celtic`, `masters`, `clark` or `d'or`.
_TYPEAHEAD_POOL_DEPTH = 22
_TYPEAHEAD_POOL_ANSWER = "NFL Playoff Qualifiers 2027"


def _typeahead_pool_seeds():
    """(external_id, name, market_tier, volume) for the #4723 pool cases."""
    rows = [
        ("kalshi-nfl-playoff-qual-2027", _TYPEAHEAD_POOL_ANSWER, 5, 900),
        # The RECALL control, copied from the production dropdown rather than
        # invented: `pats` reaches this row by interior substring only — no
        # whole-word arm and no prefix arm touches it — so it is exactly the
        # row that vanishes if the #4723 keys ever become a filter.
        ("kalshi-korpatsch-doubles", "Doubles: Huergo/Korpatsch vs Chan/Joint", 5, 3),
    ]
    for i in range(_TYPEAHEAD_POOL_DEPTH):
        rows.append(
            (f"kalshi-nflx-{i}", f"NFLX closing value above ${i}00?", 1, 100 + i)
        )
        rows.append(
            (
                f"kalshi-inflation-{i}",
                f"How high will inflation go by month {i}?",
                1,
                10000 + i,
            )
        )
    return rows


# #4728 — (external_id, name, llm_sport_category) for the team-nickname arm.
#
# Copied from production 2026-09-10, not invented. The pair is the whole point:
# both names carry the word "Patriots", and ONLY the sport category tells the New
# England Patriots apart from the Caribbean Premier League side. Of 53 open
# `%patriot%` markets that morning, 31 were New England's and 15 of the rest were
# St. Kitts and Nevis — so the cricket row is not a hypothetical, it is the
# majority of what an unscoped alias would serve a Patriots fan.
_NICKNAME_SEEDS = [
    ("kalshi-nickname-nfl-pats", "Jets vs. Patriots", "football"),
    (
        "kalshi-nickname-cpl-pats",
        "Caribbean Premier League: Barbados Tridents vs "
        "St. Kitts and Nevis Patriots",
        "cricket",
    ),
    ("kalshi-nickname-mls-revs", "Chicago Fire FC vs. New England Revolution", "soccer"),
]

#: Outcome names for the nickname seeds, chosen so the outcome arm stays mute.
#:
#: Every other seed in this file is priced (#6327); these were the last name-only
#: rows a /search test asserts on, and #3412's withdrawal made that shortcut fatal
#: to them. They cannot simply be named "Patriots"/"Revolution" — the outcome-name
#: arm would then answer `pats` and `revs`, the nickname arm under test would stop
#: being the only thing that can reach these rows, and
#: `test_the_nickname_arm_does_not_fan_out_across_sports` would be satisfied by a
#: route that had lost the alias entirely.
#:
#: "Home" and "Away" contain none of `pat`, `patriot`, `rev`, `nba champion`, nor
#: any token in the file-wide exclusion list. They are also the two words a real
#: two-sided fixture market actually uses, so the corpus got more realistic, not
#: less. One price for both legs, for the reason stated at `_SEED_PRICE`.
_NICKNAME_OUTCOMES = ("Home", "Away")


async def _seed(session):
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport, Team

    nba = Sport(key="basketball_nba", name="NBA")
    golf = Sport(key="golf_pga", name="PGA")
    session.add_all([nba, golf])
    await session.flush()

    # One NBA event so the league-only query has something to find.
    session.add(
        Event(
            sport_id=nba.id,
            home_team_name="Boston Celtics",
            away_team_name="Los Angeles Lakers",
            commence_time=datetime.now(timezone.utc) + timedelta(days=2),
            status="scheduled",
        )
    )

    # LAT-P034/#1732: the events bucket's word-boundary rule is a RECALL change
    # decided entirely by Postgres text semantics — `to_tsvector` tokenisation and
    # English stemming. Neither can be mocked, and until now this gate had exactly
    # ONE event assertion in the file (the bare-league query), so an event-recall
    # regression had nowhere to fail. These four rows are the smallest seed that
    # separates the classes the rule must tell apart:
    #
    #   Federico Coria  — the query `fed` is a word PREFIX. Must NOT match.
    #   Boston Celtics  — `celtics` is the whole word. Must match.
    #   LA Lakers       — `laker` matches only because English stemming folds
    #                     Lakers -> laker. If the config ever stops being
    #                     'english', the singular/plural class silently dies and
    #                     this is the only test that would notice.
    #   Sunrisers Leeds — `sun` is a prefix of Sunrisers. Must NOT match, and it
    #                     must not take Connecticut Sun down with it.
    # The did-you-mean fallback resolves its correction against `teams`, and this
    # file seeded no team at all — so the fallback could never fire here and the
    # POSITIVE direction of LAT-P034's guard ("a query that genuinely matches
    # nothing still gets its correction") had nothing to assert against.
    #
    # `similarity('Boston Celtics', 'celtcs')` = **0.294**, measured on production
    # rather than guessed, against the 0.25 threshold the route pins with
    # `SET LOCAL pg_trgm.similarity_threshold`. The margin is real but thin: if
    # this team's NAME changes, re-measure instead of assuming the test still
    # exercises the path.
    session.add(Team(sport_id=nba.id, name="Boston Celtics", abbreviation="BOS"))

    # LAT-P046 — the POOL specimen, transcribed from production 2026-08-13.
    #
    # `bruins` matches 9 team rows there, and the three that sort FIRST
    # alphabetically are three sport-variants of one school (Belmont), so the
    # `ORDER BY Team.name LIMIT 3` pool never fetched Boston Bruins and the
    # name-dedup then collapsed those three rows into ONE candidate. The scorer
    # cannot promote a row the query did not return, which is why this is a
    # recall test and not a ranking one — and why it lives in the only file that
    # runs the SQL.
    #
    # Four rows is the smallest seed that reproduces it: three non-prominent
    # duplicates that sort before the wanted row, and the wanted row.
    nhl = Sport(key="icehockey_nhl", name="NHL")
    ncaab = Sport(key="basketball_ncaab", name="NCAAB")
    wncaab = Sport(key="basketball_wncaab", name="WNCAAB")
    ncaa_bb = Sport(key="baseball_ncaa", name="NCAA Baseball")
    session.add_all([nhl, ncaab, wncaab, ncaa_bb])
    await session.flush()
    for _sport in (ncaab, wncaab, ncaa_bb):
        session.add(Team(sport_id=_sport.id, name="Belmont Bruins", abbreviation="BEL"))
    session.add(Team(sport_id=nhl.id, name="Boston Bruins", abbreviation="BOS"))

    for home, away in [
        ("Federico Coria", "Vitaliy Sachko"),
        ("Connecticut Sun", "Sunrisers Leeds"),
    ]:
        session.add(
            Event(
                sport_id=golf.id,
                home_team_name=home,
                away_team_name=away,
                commence_time=datetime.now(timezone.utc) + timedelta(days=2),
                status="scheduled",
            )
        )

    # #4809 — the GAME-CARD half of the nickname alias. Transcribed from
    # production 2026-09-10, the morning after #4728 went live, when `?q=pats`
    # answered with the right TEAM and the right MARKETS and **zero games**.
    #
    # Three rows, and each one is load-bearing:
    #
    #   New England Patriots  the recall target. `pats` must reach it.
    #   St Kitts & Nevis      a real Caribbean Premier League cricket side and a
    #     Patriots            genuine WHOLE-WORD match on the token `Patriots`.
    #                         `pats` must NOT reach it; the literal query
    #                         `patriots` still must, or the alias has become a
    #                         filter. On the EVENT rail this fan-out is sharper
    #                         than on the futures rail: event team names are the
    #                         same words the venue prints.
    #   UTEP Miners           the `niners` specimen. NO 49ers event is seeded on
    #                         purpose, so the nickname arm finds nothing and the
    #                         query falls to the trigram "did you mean" — which
    #                         in production corrected `niners` to `UTEP Miners`
    #                         and served two college football games inside a
    #                         response whose markets were all correctly the 49ers.
    nfl = Sport(key="americanfootball_nfl", name="NFL")
    cricket = Sport(key="cricket_cpl", name="Caribbean Premier League")
    ncaaf = Sport(key="americanfootball_ncaaf", name="NCAA Football")
    session.add_all([nfl, cricket, ncaaf])
    await session.flush()

    for sport_row, home, away in [
        (nfl, "New England Patriots", "New York Jets"),
        (cricket, "Barbados Tridents", "St Kitts & Nevis Patriots"),
        (ncaaf, "UTEP Miners", "Texas Southern Tigers"),
    ]:
        session.add(
            Event(
                sport_id=sport_row.id,
                home_team_name=home,
                away_team_name=away,
                commence_time=datetime.now(timezone.utc) + timedelta(days=2),
                status="scheduled",
            )
        )

    # The fallback resolves its correction against `teams`, so the Miners need a
    # team row for the `niners` path to be reachable at all — without it the
    # suppression test would pass vacuously. The fallback is proven ALIVE in this
    # fixture by `celtcs` -> Boston Celtics above (similarity 0.294, measured).
    session.add(Team(sport_id=ncaaf.id, name="UTEP Miners", abbreviation="UTEP"))

    # #8250 — the reported pair, verbatim names. For `red socks`, plain
    # `similarity` puts Red Star first (0.357 vs 0.316) and `word_similarity` puts
    # Boston Red Sox first (0.600 vs 0.500) — measured on local Postgres, same
    # numbers #8155 measured on production. Without both rows the twin-agreement
    # guard below cannot tell the two orderings apart.
    mlb = Sport(key="baseball_mlb", name="MLB")
    serbia = Sport(key="soccer_serbia_superliga", name="Serbian SuperLiga")
    session.add_all([mlb, serbia])
    await session.flush()
    session.add(Team(sport_id=mlb.id, name="Boston Red Sox", abbreviation="BOS"))
    session.add(Team(sport_id=serbia.id, name="Red Star", abbreviation="CZV"))

    for external_id, name, outcomes in _FUTURES_SEEDS:
        market = FuturesMarket(
            source="kalshi",
            external_id=external_id,
            name=name,
            status="open",
            # Must be in the future: the route filters
            # `resolution_date IS NULL OR resolution_date >= now()`.
            resolution_date=datetime.now(timezone.utc) + timedelta(days=90),
        )
        session.add(market)
        await session.flush()
        for outcome_name in outcomes:
            session.add(
                FuturesOutcome(
                    market_id=market.id,
                    external_id=f"{external_id}:{outcome_name}",
                    name=outcome_name,
                    current_probability=_SEED_PRICE,
                )
            )

    # LAT-P053 Item 5: the concept corpus. Same shape, plus the one column the
    # concept loop reads and the loop above never sets.
    for external_id, name, category, outcomes in _CONCEPT_FUTURES_SEEDS:
        market = FuturesMarket(
            source="kalshi",
            external_id=external_id,
            name=name,
            status="open",
            llm_sport_category=category,
            resolution_date=datetime.now(timezone.utc) + timedelta(days=90),
        )
        session.add(market)
        await session.flush()
        for outcome_name in outcomes:
            session.add(
                FuturesOutcome(
                    market_id=market.id,
                    external_id=f"{external_id}:{outcome_name}",
                    name=outcome_name,
                    current_probability=_SEED_PRICE,
                )
            )

    # #4723: the pool-cut corpus. No outcomes — these rows are reached by NAME,
    # and an outcome would put them in a second arm and blur what is being read.
    for external_id, name, market_tier, volume in _typeahead_pool_seeds():
        session.add(
            FuturesMarket(
                source="kalshi",
                external_id=external_id,
                name=name,
                status="open",
                market_tier=market_tier,
                volume=volume,
                resolution_date=datetime.now(timezone.utc) + timedelta(days=90),
            )
        )

    # #4728: the nickname corpus. PRICED, with deliberately inert outcome names
    # — the same correction #6327 made to the main corpus above, for the same
    # reason and with the confound answered rather than dodged (#3412).
    #
    # These rows were name-only because "an outcome would let a second arm
    # answer", which is a real hazard and is NOT what omitting the price
    # protected against: the hazard is the outcome NAME joining the candidate
    # set, not the price column existing. #3412 made /search withdraw a market
    # holding no outcome rows at all, so a name-only seed is no longer a model
    # of the markets this gate names — "Jets vs. Patriots" is an ordinary NFL
    # fixture, and without this every nickname case reports a RECALL REGRESSION
    # against a route behaving exactly as ruled.
    #
    # `_NICKNAME_OUTCOMES` is the confound's actual answer: two names that
    # appear in NO query this file asserts on (checked against `pats`,
    # `patriots`, `revs`, `nba champion` and the file-wide list at
    # `_typeahead_pool_seeds` — `re`, `us`, `nba`, `mvp`, `fed`, `sun`, `yank`,
    # `laker`, `celtic`, `masters`, `clark`, `d'or`). So the outcome-name arm
    # still cannot answer any of them and the nickname arm remains the only
    # thing that can reach these rows — which is the whole subject.
    #
    # The POOL seeds above stay name-only and unpriced: #3412 deliberately does
    # not filter the typeahead, so nothing suppresses them. See the note at
    # `typeahead_search`'s futures pool.
    for external_id, name, category in _NICKNAME_SEEDS:
        market = FuturesMarket(
            source="kalshi",
            external_id=external_id,
            name=name,
            status="open",
            llm_sport_category=category,
            resolution_date=datetime.now(timezone.utc) + timedelta(days=90),
        )
        session.add(market)
        await session.flush()
        for outcome_name in _NICKNAME_OUTCOMES:
            session.add(
                FuturesOutcome(
                    market_id=market.id,
                    external_id=f"{external_id}:{outcome_name}",
                    name=outcome_name,
                    current_probability=_SEED_PRICE,
                )
            )

    await session.commit()


@pytest.fixture
async def seeded_db():
    """A real Postgres with the real schema and the seed rows above.

    Function-scoped deliberately. ``pytest.ini`` leaves
    ``asyncio_default_fixture_loop_scope`` unset, so a module-scoped async
    fixture would outlive the function-scoped event loop that created its
    engine and fail on a closed loop. Re-seeding five markets per test is
    cheap, and it buys full isolation between cases.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401  — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await _seed(session)

    yield engine, maker

    await engine.dispose()


@pytest.fixture
async def search(seeded_db):
    """Call the REAL route through the app, against the REAL database."""
    from httpx import ASGITransport, AsyncClient

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    _engine, maker = seeded_db

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_db_rw] = _override
    app.dependency_overrides[get_optional_user] = lambda: None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def _do(q: str) -> dict:
            resp = await client.get("/api/events/search", params={"q": q})
            assert resp.status_code == 200, f"{q!r} -> HTTP {resp.status_code}"
            return resp.json()

        yield _do

    app.dependency_overrides.clear()


@pytest.fixture
async def typeahead(seeded_db):
    """LAT-P007: the same real-Postgres treatment for `/typeahead`.

    Nothing in this repo exercised typeahead recall against real rows, so its
    predicate could be changed freely and silently. It is the surface that fires
    on every keystroke, so it deserves the guard more than `/search` does, not
    less.

    Redis is patched out: `typeahead_search` reads a cache before touching the
    database, and a hit would make every assertion here test Redis instead of the
    predicate.
    """
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient

    from app.main import app
    from app.services.database import get_db, get_db_rw

    _engine, maker = seeded_db

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_db_rw] = _override

    with patch("app.tasks.redis_state.get_redis_client", side_effect=RuntimeError("no redis")):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def _do(q: str) -> dict:
                resp = await client.get("/api/events/typeahead", params={"q": q})
                assert resp.status_code == 200, f"{q!r} -> HTTP {resp.status_code}"
                return resp.json()

            yield _do

    app.dependency_overrides.clear()


def _typeahead_texts(payload) -> list[str]:
    items = payload.get("suggestions", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    return [str(i.get("text") or i.get("name") or "") for i in items if isinstance(i, dict)]


def _futures_names(payload: dict) -> list[str]:
    return [f.get("name") or f.get("market_name") for f in payload.get("futures", [])]


# --------------------------------------------------------------------------
# The contract
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "query,must_find",
    [
        # The three that actually returned ZERO futures in production.
        ("masters winner", "Masters Tournament Winner 2026"),
        ("us recession 2026", "US Recession in 2026?"),
        ("nba champion", "NBA Champion 2026"),
        # Name contains no "nfl" — reachable ONLY via the ticker prefix arm.
        ("nfl mvp", "MVP Winner?"),
        # LAT-P013: the multi-term apostrophe query, untouched by this queue's
        # gate (which is single-term only) and therefore a pure regression guard.
        ("ballon d'or", "Ballon d'Or Winner 2026"),
        # LAT-P013: the SINGLE-term no-trigram query — the one that measured
        # 19,171ms. The gate drops only its OUTCOME arm; the NAME arm must still
        # answer, or the fix has traded a slow answer for no answer.
        ("d'or", "Ballon d'Or Winner 2026"),
    ],
)
async def test_query_returns_its_market(search, query, must_find):
    names = _futures_names(await search(query))
    assert must_find in names, (
        f"RECALL REGRESSION: {query!r} returned {names!r}, missing {must_find!r}. "
        "A query that returns HTTP 200 with the right answer absent is worse "
        "than a slow one — this is the exact shape that reverted LAT-P002."
    )


async def test_outcome_only_recall(search):
    """The market NAME contains neither term; only an OUTCOME name matches.

    Guards `_outcome_id_match`. A predicate change that keeps name matching
    working drops this silently.
    """
    names = _futures_names(await search("caitlin clark"))
    assert "Award Winner 2026" in names, (
        f"outcome-only recall lost: got {names!r}"
    )


async def test_union_returns_rows_from_every_recall_arm(search):
    """LAT-P006: the recall arms are UNIONed, so one query returns BOTH arms.

    `us recession` reaches "US Recession in 2026?" only through the NAME arm and
    "Q4 GDP print above 3%?" only through the OUTCOME arm. Both must come back.

    This is the guard for the shape LAT-P006 shipped. Combining the arms with a
    top-level `OR` timed out in production (>10s; the live request measured
    23.57s and returned zero futures for a market that exists), so they are now
    combined with `UNION` — set-identical, 437ms. The failure mode a UNION
    introduces that an OR cannot is collapsing to ONE arm, or to an INTERSECT.
    Either halves recall while every single-arm test in this file still passes.
    """
    names = _futures_names(await search("us recession"))
    assert "US Recession in 2026?" in names, (
        f"NAME-arm row lost from the union: got {names!r}"
    )
    assert "Q4 GDP print above 3%?" in names, (
        f"OUTCOME-arm row lost from the union: got {names!r}. The arms are being "
        "intersected or one arm was dropped — a UNION must return both."
    )


async def test_short_term_is_still_enforced_in_the_outcome_arm(search):
    """A sub-3-character term still FILTERS; it was not dropped to buy speed.

    `%us%` is a 2-char infix pattern, unservable by a pg_trgm GIN, and it seq-scans
    3 GB of `futures_outcomes` in production (6,865ms for 64,200 rows — where the
    3-char control `%ing%` returns MORE rows in 1,171ms). The tempting fix is to
    drop such terms from the outcome arm. LAT-P006 measured that the term is not
    the driver — the top-level OR is — and fixed the OR instead, so the term keeps
    its meaning.

    "Euro area growth 2026?" matches `%recession%` (outcome "Recession likely")
    but nothing matches `%us%`. If it starts appearing for `us recession`, a short
    term has been silently dropped and the query now means something else.
    """
    names = _futures_names(await search("us recession"))
    assert "Euro area growth 2026?" not in names, (
        f"the 2-char term `us` stopped filtering: got {names!r}. Dropping "
        "sub-3-char terms widens the query — that is a precision regression, not "
        "an optimisation."
    )


async def test_the_outcome_arm_trade_for_a_no_trigram_single_term_is_deliberate(search):
    """LAT-P013's stated cost, pinned so it is a decision and not an accident.

    For a SINGLE term that yields no pg_trgm trigram (`d'or`, `u.s.`, `a.i.`), the
    outcome arm is dropped and only the market NAME arm runs. "France Football
    Award 2026" is reachable only through its outcome ("Winner of the d'Or"), so
    it does not come back for `d'or`.

    Why that is the right trade, in production numbers rather than in principle:
    the arm being dropped is what made this query cost 13.7-19.2s, and at that
    cost it does not reliably return anything at all. Of two production samples on
    2026-08-09, one came back `degraded: [futures, teams]` — HTTP 200 with ZERO
    futures, gotcha #53's shape. So the real before/after is not "outcome recall
    vs none", it is "an intermittently empty answer in 19s" vs "the name matches,
    every time, in well under a second".

    NOTE this is a WEAKER justification than LAT-P010 had for `re`/`la`, and it is
    recorded as weaker rather than borrowed. There, 0 of 10 visible futures came
    from the outcome arm because thousands of name matches outranked it. Here name
    matches are few, so an outcome-only row COULD have reached the page. If this
    trade ever needs undoing, the fix is a servable outcome predicate for
    punctuation-split terms, not widening the gate back.
    """
    names = _futures_names(await search("d'or"))
    assert "France Football Award 2026" not in names, (
        f"got {names!r} — the outcome arm is running for a no-trigram single "
        "term again, which is the 19s seq scan LAT-P013 removed"
    )


async def test_a_multi_term_query_keeps_its_no_trigram_outcome_arm(search):
    """The gate is single-term ONLY, and that scoping is measured, not assumed.

    `ballon or` — an explicit 2-char token inside a multi-term AND — measured 85ms
    in production against a 36ms control, because the ANDed arms let the selective
    term drive. The multi-term path has no defect to fix, and LAT-P006 pins that a
    short term must still FILTER there.

    So "France Football Award 2026", unreachable for the single term `d'or`, IS
    reachable for `award d'or`, where `award` seeds and `d'or` filters.
    """
    names = _futures_names(await search("award d'or"))
    assert "France Football Award 2026" in names, (
        f"got {names!r} — the single-term gate has leaked into the multi-term "
        "branch and is dropping outcome recall it must not touch"
    )


async def test_an_all_short_token_query_falls_back_rather_than_returning_nothing(search):
    """The edge case LAT-P013 required be decided explicitly rather than left open.

    A query whose every token is unservable has no term that can seed cheaply.
    THE CHOICE MADE: change nothing. Multi-term queries keep the existing
    behaviour, and a single unservable term keeps its NAME arm. Nothing silently
    returns empty — which was the stated unacceptable outcome.

    `d'or a.i.` is two tokens, neither yielding a trigram. It must still answer
    with the same shape any other query does, not a hard-coded empty.
    """
    payload = await search("d'or a.i.")
    assert isinstance(payload.get("futures"), list), (
        "an all-unservable query stopped returning a well-formed futures list"
    )
    assert "degraded" not in payload or "futures" not in (payload.get("degraded") or []), (
        f"an all-unservable query is shedding its futures stage: {payload.get('degraded')!r}"
    )


async def test_league_only_query_still_broad(search):
    """`league_only_explicit`: a bare league token keeps the wide arm.

    The re-land's 1b narrows the league arm by AND-ing the remaining terms.
    A league-ONLY query has no remaining terms and must not be narrowed to
    nothing.
    """
    payload = await search("nba")
    found = payload.get("results") or []
    assert found or _futures_names(payload), (
        "a bare league query returned nothing at all — 1b over-narrowed"
    )


async def test_recall_summary(search, capsys):
    """Emit the found-count the way criterion 3 asks for it.

    Printed so the CI job log carries the numbers, satisfying #1494's
    'RUN, with output quoted' — a gate whose result nobody can read is the
    same as a gate nobody ran.
    """
    cases = [
        ("masters winner", "Masters Tournament Winner 2026"),
        ("us recession 2026", "US Recession in 2026?"),
        ("nba champion", "NBA Champion 2026"),
        ("nfl mvp", "MVP Winner?"),
        ("caitlin clark", "Award Winner 2026"),
        # LAT-P013: the no-trigram cases. `d'or` is the single-term one that
        # measured 19,171ms; it must still answer off the NAME arm.
        ("ballon d'or", "Ballon d'Or Winner 2026"),
        ("d'or", "Ballon d'Or Winner 2026"),
    ]
    found, missing = 0, []
    for query, expected in cases:
        if expected in _futures_names(await search(query)):
            found += 1
        else:
            missing.append(query)

    with capsys.disabled():
        print(f"\nSEARCH RECALL: {found}/{len(cases)} found", flush=True)
        if missing:
            print(f"SEARCH RECALL MISSING: {missing}", flush=True)
        # Printed EVERY run, next to the number, because the number is the thing
        # people will quote. See SCOPE LIMIT in the module docstring: this gate
        # went 5/5 green on the LAT-P005 re-land while production still returned
        # zero futures for `us recession 2026`. Both were correct.
        print(
            "SEARCH RECALL SCOPE: predicate recall only, on a small seeded DB. "
            "This gate CANNOT detect timeout-induced recall loss (#1494) — a green "
            "n/n here does not mean production recall is intact.",
            flush=True,
        )

    assert found == len(cases), f"recall {found}/{len(cases)}, missing {missing}"


# --------------------------------------------------------------------------
# LAT-P007 — /typeahead recall, against real Postgres
# --------------------------------------------------------------------------
async def test_typeahead_still_finds_its_market(typeahead):
    """The 3-char+ path keeps working after the UNION + non-correlated rewrite.

    `/typeahead` measured 9,682ms -> 2,414ms on the same 990 production rows.
    Both changes are set-identical, so recall must be untouched.
    """
    texts = _typeahead_texts(await typeahead("recession"))
    assert any("Recession" in t for t in texts), (
        f"typeahead lost its market: got {texts!r}"
    )


async def test_typeahead_outcome_recall_survives_above_the_threshold(typeahead):
    """The outcome arm still runs at 3+ characters.

    "Award Winner 2026" is reachable ONLY through an outcome name
    ("Caitlin Clark"). The sub-3-char skip must not have disabled the arm
    outright — it is scoped to short queries, nothing else.
    """
    texts = _typeahead_texts(await typeahead("caitlin"))
    assert any("Award Winner" in t for t in texts), (
        f"typeahead outcome-name recall lost above the threshold: got {texts!r}"
    )


async def test_typeahead_team_pool_reaches_past_alphabetical_duplicates(typeahead):
    """LAT-P046 — the wanted team must be FETCHED, not merely rankable.

    Three "Belmont Bruins" rows sort before "Boston Bruins" alphabetically. With
    the pool query ordered by `Team.name` and capped at 3, all three slots went
    to Belmont, the name-dedup collapsed them to one, and Boston was never a
    candidate at any point in the request. Ordering the FETCH by sport
    prominence — the same signal `search_match_class.rank_key` uses to separate
    two equally-classed teams — puts it in the pool.

    This asserts recall, not order: Boston has to be REACHABLE. If a later
    change reorders the suggestions but keeps Boston in them, this still passes,
    which is correct — ranking is the scorer's job and it has its own tests.
    """
    texts = _typeahead_texts(await typeahead("bruins"))
    assert any("Boston Bruins" in t for t in texts), (
        "the pool never fetched the prominent team — alphabetical duplicates "
        f"took every slot again: got {texts!r}"
    )
    # And it did not win by evicting the others: recall is widened, not swapped.
    assert any("Belmont Bruins" in t for t in texts), (
        f"the duplicate school fell out of the pool entirely: got {texts!r}"
    )


async def test_typeahead_short_query_answers_without_the_outcome_scan(typeahead):
    """A 2-char query must still answer, and must not 500.

    At two characters the outcome arm is skipped: it measured 8,633ms against
    3 GB of `futures_outcomes` and returned 17 of 20 visible rows as substring
    accidents (Lamprecht, Baltimore, Guterres). The endpoint still has to
    RESPOND — `min_length=2`, so this is a legal query and the most common one
    a user fires.
    """
    payload = await typeahead("re")
    assert isinstance(_typeahead_texts(payload), list)


# --------------------------------------------------------------------------
# LAT-P010 — /search's single sub-3-char term (#1494 GAP 1)
# --------------------------------------------------------------------------
async def test_short_single_term_search_still_answers(search):
    """A 2-char query must still return its NAME matches.

    The outcome arm is dropped at 2 characters (it seq-scans 3 GB and, measured
    in production, contributed 0 of 10 visible rows because ts_rank_cd sorts
    outcome-only matches below every name match). The NAME arm must survive —
    "US Recession in 2026?" contains "re".
    """
    names = _futures_names(await search("re"))
    assert any("Recession" in (n or "") for n in names), (
        f"a 2-char query lost its name matches too: got {names!r}. Only the "
        "OUTCOME arm should be dropped below 3 characters."
    )


async def test_multi_term_short_token_still_filters_after_lat_p010(search):
    """LAT-P010 must not have leaked into the multi-term path.

    This is LAT-P006's guard restated at the boundary LAT-P010 introduced: in
    `us recession`, the 2-char `us` still FILTERS, so a market matching only
    `%recession%` stays out. If LAT-P010's gate were applied per-term instead of
    to the single-term path, this row would be admitted.
    """
    names = _futures_names(await search("us recession"))
    assert "Euro area growth 2026?" not in names, (
        f"the sub-3-char gate leaked into the multi-term AND: got {names!r}"
    )
    assert "US Recession in 2026?" in names, (
        f"multi-term recall broke: got {names!r}"
    )


async def test_a_fragment_term_matches_a_word_start_not_an_infix(search):
    """#8689: `us open` must answer with the US Open, not with "Venus" and "Aus".

    A no-trigram term keeps its substring ILIKE (LAT-P037: it cannot word-vote)
    but must now also start a word. `re` -> "Recession" above is the prefix case
    this has to keep; this is the infix case it exists to drop.
    """
    names = _futures_names(await search("us open"))
    assert "2027 US Open Men's Singles Winner" in names, (
        f"the fragment rule took the real US Open with the noise: got {names!r}"
    )
    for infix in (
        "Chengdu Open (Doubles): Peers/Venus vs Johnson/Zielinski",
        "Australian Open Men's Singles Winner",
    ):
        assert infix not in names, (
            f"`us` matched inside a word again ({infix!r}): got {names!r}"
        )


# --------------------------------------------------------------------------
# LAT-P034 / #1732 (events half) — word about-ness, on a REAL Postgres
# --------------------------------------------------------------------------
#
# Every other test in this file guards FUTURES recall. The events bucket had one
# assertion (the bare-league query) and no coverage at all of the predicate that
# decides which events a query returns — so LAT-P034 changed event recall with
# nothing in CI able to fail. These tests close that, and they belong HERE rather
# than in the mocked unit suite for a specific reason: the rule is `to_tsvector`
# tokenisation plus English stemming, which is Postgres behaviour. A mocked
# session compiles the SQL and never runs it, so it can prove the SHAPE is right
# and cannot prove the ANSWER is.


def _event_pairings(payload: dict) -> list[str]:
    return [
        f"{e.get('home_team')} vs {e.get('away_team')}"
        for e in (payload.get("results") or [])
    ]


async def test_a_word_prefix_is_not_a_match(search):
    """The payoff, stated as a test: `fed` must not return Federico Coria.

    This is #1732's events half. In production on 2026-08-11 the query returned
    25 rows and every one was a person whose name merely starts with those
    letters, tied at ts_rank_cd 0.0 and ordered by kickoff time.
    """
    payload = await search("fed")
    assert _event_pairings(payload) == [], (
        f"`fed` still returns events: {_event_pairings(payload)!r}. A word PREFIX "
        "is not what the query is about."
    )
    assert payload["pagination"]["total_results"] == 0, (
        "the rows are filtered out of the page but still counted, so the header "
        "advertises results the user cannot see"
    )


async def test_a_whole_word_still_matches(search):
    """The other direction, which is the half that makes the rule safe to ship.

    A cap that only ever removes rows is indistinguishable from a broken filter
    until someone searches for something real.
    """
    assert "Boston Celtics vs Los Angeles Lakers" in _event_pairings(
        await search("celtics")
    ), "whole-word event recall is gone — the rule is filtering everything"


async def test_english_stemming_keeps_the_singular_plural_class(search):
    """`laker` -> `Lakers` survives ONLY because the FTS config is 'english'.

    This is the load-bearing assumption behind accepting the rule's known
    truncation loss: the truncations people actually type are plurals, and the
    stemmer folds them for free. Switch the config to 'simple' and this dies
    silently while every shape assertion still passes.
    """
    assert "Boston Celtics vs Los Angeles Lakers" in _event_pairings(
        await search("laker")
    ), (
        "singular/plural recall is gone. If the FTS config is no longer "
        "'english', the word rule is far more destructive than it was measured "
        "to be and must be reconsidered, not patched."
    )


async def test_the_rule_does_not_take_the_real_team_with_the_noise(search):
    """`sun`: Sunrisers Leeds is a prefix collision, Connecticut Sun is the team.

    They are seeded on the SAME event on purpose. A rule that dropped the row
    would look correct on a noise-only fixture and would be wrong.
    """
    pairings = _event_pairings(await search("sun"))
    assert "Connecticut Sun vs Sunrisers Leeds" in pairings, (
        f"the whole-word team was dropped along with the prefix noise: {pairings!r}"
    )


_YANK_REAL = "Colorado Rockies vs. New York Yankees - First 5 Innings Winner"
_YANK_NOISE = "M15 Hurghada: Mayank Sharma vs Luis Klaus"


async def test_an_interior_substring_does_not_outrank_a_real_prefix(search):
    """#4572: `yank` must lead with the Yankees, not with "Ma*yank*".

    Measured on production 2026-09-10 01:35Z: slot 0 was a $15k ITF qualifier
    whose only connection to the query was four letters sitting in the MIDDLE of
    the first name "Mayank"; the Yankees' own game was slot 3.

    The cause is not the recall arm the issue first blamed. It is that the word
    test rejects the REAL answer too — `Yankees` stems to `yanke`, the query's
    lexeme is `yank` — so both rows land in tier 2 with `ts_rank_cd` **0.0** and
    the page falls through to `market_tier`/`volume`/`updated_at`/`id`, none of
    which is about the query. This is the pathology LAT-P111 named: when the
    relevance signal is structurally dead, whatever sorts next decides the page.

    The fix adds a prefix test as an ORDER BY key directly below the rank, and a
    prefix is a strictly stronger claim than the substring that admitted the row:

        to_tsvector('…New York Yankees…') @@ to_tsquery('yank:*')  ->  true
        to_tsvector('…Mayank Sharma…')    @@ to_tsquery('yank:*')  ->  false

    This test can only run here. `ts_rank_cd`, English stemming and the ORDER BY
    are Postgres semantics — a unit test that mocked them would be green on a
    ranker that shipped the ITF row first, which is exactly the state production
    was in when this was filed.
    """
    names = _futures_names(await search("yank"))
    assert _YANK_REAL in names, (
        f"the Yankees market is not even in the bucket: {names!r}. This is a "
        "RECALL failure, which the ranking fix was never supposed to cause — "
        "check the outcome arm before touching the ORDER BY."
    )
    assert names.index(_YANK_REAL) < names.index(_YANK_NOISE), (
        f"an interior substring still outranks a real prefix: {names!r}. "
        f"{_YANK_NOISE!r} matches `yank` only in the MIDDLE of 'Mayank'."
    )


async def test_the_prefix_key_did_not_buy_its_ordering_with_recall(search):
    """The other direction, and the reason #4572's fix is ORDERING-ONLY.

    The refusal in `_futures_name_match_term` (LAT-P037) is about RECALL: a
    prefix arm in the WHERE fetches rows that are not answers (`fed:*` ->
    `federico`, the 25 rows LAT-P033/LAT-P034 closed). #4572 adds its prefix
    score to the ORDER BY and nowhere else, so the candidate set must be
    IDENTICAL — including the noise row, which is still a legitimate substring
    match and is still reachable, just no longer first.

    A "fix" that filtered the ITF row out would satisfy the test above and would
    be a recall change wearing a ranking change's clothes. This is the control
    that tells them apart.
    """
    names = _futures_names(await search("yank"))
    assert _YANK_NOISE in names, (
        f"the substring match was REMOVED from the bucket, not just demoted: "
        f"{names!r}. #4572 is a ranking fix — recall must not move."
    )


# --------------------------------------------------------------------------
# #4723 — the same defect one surface over, where the POOL CUT is the mechanism
# --------------------------------------------------------------------------
async def test_the_typeahead_pool_is_chosen_by_the_query_not_by_volume(typeahead):
    """🔴 #4723: the dropdown must offer the NFL market, not i-**nfl**-ation.

    Measured on production 2026-09-10 08:45Z, `q=nfl` offered five futures and
    FOUR were inflation markets. The cause is not the reranker — it runs on the
    20 rows SQL already chose, and 18 of those 20 were imposters. Until #4723
    the typeahead futures ORDER BY was `market_tier, volume`: a market-QUALITY
    prior and a popularity prior, neither of which is about what was typed.

    The seed makes the answer the WORST row by both of those priors (tier 5,
    out-traded 11x by the collisions), so it can reach the pool only on a
    query-relevance key. See `_typeahead_pool_seeds` for the three classes and
    the three orderings they separate.

    This test can only run here: which 20 rows a LIMIT returns under an ORDER BY
    over `to_tsvector`/`to_tsquery` is Postgres semantics end to end.
    """
    texts = _typeahead_texts(await typeahead("nfl"))
    assert _TYPEAHEAD_POOL_ANSWER in texts, (
        f"the dropdown still cannot see the NFL market: {texts!r}. It is tier 5 "
        "and out-traded, so it reaches the 20-row pool only if the ORDER BY "
        "leads with a query-relevance key — check that the #4723 keys are still "
        "ahead of `market_tier`/`volume` in the typeahead futures query."
    )


async def test_a_genuine_prefix_that_is_not_the_answer_does_not_take_the_pool(
    typeahead,
):
    """🔴 WHY THE WORD KEY SITS ABOVE THE PREFIX KEY, and #4723's own proposal
    would have failed this.

    The issue proposed a single key: the #4572 prefix test. Measured on
    production it is not enough and on one real query it is worse than live —
    `fed:*` prefixes `feder`, handing `fed` (73 log hits) to "Next German
    federal election winner?" and "Brazil Federal District Governor winner?".

    `NFLX` is that class, reproducible: 22 rows that genuinely DO prefix-match
    `nfl`, sit at tier 1, and would fill all 20 pool slots under a prefix-only
    ordering — pushing the whole-word answer out exactly as inflation does
    today. A fix that ships the one key passes the test above only if it also
    fails this one.

    PRESENCE is the discriminator here, and deliberately so. Under a
    prefix-only ordering the 22 tier-1 NFLX rows fill all twenty pool slots and
    the answer never reaches `_rerank_search_futures` at all — verified against
    a real Postgres over these exact rows (`answer_in_pool`: tier/volume False,
    prefix/tier/volume False, word/prefix/tier/volume True). Asserting a
    POSITION instead would couple this to the suggestion scorer that runs after
    the reranker, which #4723 does not touch and must not be pinned by it.
    """
    texts = _typeahead_texts(await typeahead("nfl"))
    assert _TYPEAHEAD_POOL_ANSWER in texts, (
        f"the whole-word NFL market lost the pool to rows that merely PREFIX "
        f"the query: {texts!r}. A prefix key alone reproduces the defect with a "
        "better-looking cast — see the `fed` table in "
        "`tests/test_typeahead_futures_pool_ordering_4723.py`."
    )
    assert any(t.startswith("NFLX ") for t in texts), (
        f"the prefix-matching rows were REMOVED rather than outranked: "
        f"{texts!r}. They are legitimate substring recall; #4723 reorders."
    )


async def test_the_typeahead_pool_keys_did_not_buy_their_ordering_with_recall(
    typeahead,
):
    """🔴 THE CONTROL, and it is the important one.

    #4723 is ORDERING-ONLY: `ta_futures_where`, the UNION arms and
    `_ta_candidate_filter` are byte-identical, so a row that reached the
    dropdown before must still reach it. A change that filtered the collisions
    out would satisfy both tests above and would be the LAT-P002 revert shape —
    a recall change wearing a ranking change's clothes — against the refusal
    LAT-P037 states in capitals.

    `pats` is the case, and it is REAL rather than constructed: on production
    the dropdown offers five Huergo/Kor**patsch** doubles rows for a query that
    means the Patriots. #4723 cannot fix that, and this test does not pretend it
    can — measured 2026-09-10, 53 open Patriots futures exist and ZERO contain
    the substring `pats`, while `websearch_to_tsquery('pats')` is the lexeme
    `pat` and "Patriots" stems to `patriot`, so no whole-word arm reaches them
    either. They are not in the candidate set at all, which makes it a RECALL
    gap (its own issue) and not something an ORDER BY can reach.

    What this asserts is the half #4723 owns: the interior match is still
    SERVED. If it disappears, the keys became a filter.
    """
    texts = _typeahead_texts(await typeahead("pats"))
    assert any("Korpatsch" in t for t in texts), (
        f"the interior substring match was REMOVED, not merely reordered: "
        f"{texts!r}. #4723 adds ORDER BY keys and nothing else — recall must "
        "not move."
    )


async def test_a_filtered_bucket_does_not_trigger_a_did_you_mean(search):
    """A correction is for "matched nothing", not "matched things we filtered".

    Measured on production 2026-08-11, the corrections the newly-empty queries
    would draw: ipo -> IPK, yank -> Petr Yan, pats -> Paterno, sox -> Sora.
    Substituting one of those is worse than an empty bucket, because it is
    asserted to the user as the answer.
    """
    payload = await search("fed")
    assert not payload.get("did_you_mean"), (
        f"`fed` matched rows we filtered and then offered "
        f"{payload.get('did_you_mean')!r} as a correction anyway"
    )


async def test_a_genuinely_unmatched_query_still_gets_its_correction(search):
    """The guard must not disable did-you-mean wholesale.

    `celtcs` matches no event by substring at all, so the fallback SHOULD run —
    that is the case it was written for. Asserting only the suppression direction
    would let a change that kills the feature entirely pass.
    """
    payload = await search("celtcs")
    assert payload.get("did_you_mean") == "Boston Celtics", (
        f"expected a correction to 'Boston Celtics', got "
        f"{payload.get('did_you_mean')!r}. `%celtcs%` matches no event by "
        "substring, so the guard must let the fallback run — otherwise "
        "did-you-mean is dead for every query, not just the filtered ones."
    )


async def test_a_two_word_misspelling_gets_the_same_rescue_as_a_one_word_one(search):
    """#8155 — `Red socks` returned a blank page while `Yankes` returned 38 results.

    Both are misspellings of a currently-playing MLB club; the only difference was
    `len(terms) == 1` on the correction gate. A TestFlight tester reported the
    two-word one in an in-app shake: *"Red socks is actually a legit team and it
    says no results"*.

    Seeded analogue, so this runs on the contract fixture rather than production:
    `boston celtcs` is the two-word shape of the `celtcs` case directly above.
    Measured `word_similarity('boston celtcs', 'Boston Celtics')` = **0.786**,
    against **0.500** for the nearest decoy `Boston Bruins` — so this asserts the
    right club, not merely that something came back.
    """
    payload = await search("boston celtcs")
    assert payload.get("did_you_mean") == "Boston Celtics", (
        f"expected the two-word misspelling to be corrected to 'Boston Celtics', "
        f"got {payload.get('did_you_mean')!r} — the multi-term arm of the "
        "did-you-mean gate has regressed to single-term only (#8155)"
    )


async def test_the_multi_term_correction_refuses_a_near_miss_that_clears_the_prefilter(
    search,
):
    """The floor is load-bearing, and this fails if it is removed.

    NOT a vacuous negative. `celtics roster` **reaches** the correction: plain
    `similarity('Boston Celtics', 'celtics roster')` = **0.429**, comfortably over
    the 0.25 prefilter this path pins, so with the `word_similarity` floor deleted
    it WOULD be answered "did you mean Boston Celtics". It is refused only because
    `word_similarity` = **0.533** is below the 0.59 floor.

    That is the distinction the floor exists to draw, measured on the real
    population in #8155: a genuine misspelling of a club scores >= 0.600
    (`red socks` -> Boston Red Sox), while a real club name plus an ordinary extra
    word scores <= 0.583 (`france d'or` -> France, `queens club` -> Queens (NC)).
    Correcting the second class asserts a wrong answer to the reader, which the
    sibling `fed` guard above already rules is worse than an empty bucket.
    """
    payload = await search("celtics roster")
    assert not payload.get("did_you_mean"), (
        f"`celtics roster` drew the correction "
        f"{payload.get('did_you_mean')!r}. It clears the 0.25 similarity "
        "prefilter, so the only thing that may refuse it is the multi-term "
        "word_similarity floor — this is what a deleted or lowered floor looks "
        "like (#8155)."
    )


#: #8250 — the multi-term population both twins must answer identically. The
#: first two are the reported class, the third is #8155's own seeded analogue,
#: the fourth is a real club plus an ordinary word (the floor must refuse it),
#: and `celtcs` pins that the single-term arm did not move.
_TWIN_CORRECTION_CASES = (
    ("red socks", "Boston Red Sox"),
    ("boston red socks", "Boston Red Sox"),
    ("boston celtcs", "Boston Celtics"),
    ("celtics roster", None),
    ("celtcs", "Boston Celtics"),
)


@pytest.mark.parametrize(("q", "expected"), _TWIN_CORRECTION_CASES)
async def test_both_fuzzy_twins_give_the_same_correction(search, typeahead, q, expected):
    """#8250 — `/typeahead` and `/search` are twin "did you mean" fallbacks.

    #8155 moved `/search`'s multi-term arm onto `word_similarity` and left the
    dropdown on plain `similarity`, so for `red socks` the dropdown said "Showing
    results for Red Star" while the search page said Boston Red Sox. Asserted as
    AGREEMENT on each case and against the expected answer, so neither twin can
    drift alone and both cannot drift together.
    """
    search_dym = (await search(q)).get("did_you_mean")
    typeahead_dym = (await typeahead(q)).get("did_you_mean")
    assert (search_dym, typeahead_dym) == (expected, expected), (
        f"{q!r}: /search corrects to {search_dym!r}, /typeahead to "
        f"{typeahead_dym!r}, expected {expected!r} from both (#8250)"
    )


async def test_the_floor_withholds_the_correction_not_the_row(typeahead):
    """#8250 — the floor gates what the dropdown ASSERTS, not what it offers.

    `celtics roster` has no correction (word_similarity 0.533 < 0.59, as on
    `/search`), but the dropdown is a list of candidates: the Celtics row stays.
    Removing the row would be a recall loss nobody asked for.
    """
    payload = await typeahead("celtics roster")
    assert "Boston Celtics" in _typeahead_texts(payload), (
        f"`celtics roster` lost the Boston Celtics row: "
        f"{_typeahead_texts(payload)!r} — the #8250 floor must gate only "
        "did_you_mean, never the fuzzy team rows"
    )


# --------------------------------------------------------------------------
# LAT-P053 Item 5 — concept provenance, BEHAVIOURALLY (#1846, ruling 041)
# --------------------------------------------------------------------------
# The fifth carry, ruled into CI rather than restaged: Alex, 2026-08-14 —
# *"a corpus carried five times is either an instrument or clutter, and it just
# got called an instrument."*
#
# `TestEveryConceptCallSiteIsRouted` asserts these properties over
# `inspect.getsource(search_events)`. That guard is honest about being the weaker
# kind and names its own blind spot: *"What it CANNOT catch: a routed call site
# that passes the wrong concept."* These three cases run the SQL and read the
# wire, so they catch exactly that.
#
# Both directions, deliberately, per the standing rule that a cap's guard tests
# must assert the flood stays capped AND the adjacent surface stays populated
# (gotcha #43). A strip that deleted every concept row would pass a
# strip-only test.


def _concept_keys(payload: dict) -> list[str]:
    return [
        str(c.get("key") or "") for c in (payload.get("event_concepts") or [])
    ]


async def test_private_ranking_evidence_never_reaches_the_wire(search):
    """The behavioural twin of the `.pop("_derived", None)` source assertion.

    `_derived` and `_aliases` are ranking INPUTS. Typeahead learned this by
    nearly shipping 40 outcome strings per keystroke; on `/search` it is two
    keys, and the discipline is the same. A source assertion proves the `.pop`
    is written; this proves it runs on a row that actually exists.
    """
    payload = await search("wimbledon")
    concepts = payload.get("event_concepts") or []
    assert concepts, (
        "the concept corpus did not reach the loop — this test proves nothing "
        "about the strip if there is no row to strip. Check that "
        "`_CONCEPT_FUTURES_SEEDS` still sets `llm_sport_category='tennis'` and "
        "that the name is still a winner-field."
    )
    for row in concepts:
        assert "_derived" not in row, f"private ranking evidence on the wire: {row!r}"
        assert "_aliases" not in row, f"private ranking evidence on the wire: {row!r}"
    for row in payload.get("teams") or []:
        assert "_aliases" not in row, f"private ranking evidence on the wire: {row!r}"


async def test_a_concept_the_query_names_survives_the_scorer(search):
    """#1846's positive direction, on `/search`.

    Ruling 041 makes derived-only evidence UNRANKABLE — dropped, not demoted —
    so blanket-flagging every market-derived concept deletes concepts whose own
    name IS the query. That is the bug typeahead shipped and `/search` did not,
    and this is the assertion that keeps the divergence from being 'fixed' in
    the wrong direction by a later consistency edit.
    """
    keys = _concept_keys(await search("wimbledon"))
    assert any("wimbledon" in k.lower() for k in keys), (
        f"`wimbledon` names the concept its own market minted, so the concept "
        f"OWNS that evidence and must rank. Got {keys!r}. A blanket "
        "`_derived = True` on the market-derived loop is what this catches."
    )


async def test_a_concept_the_query_does_not_name_is_dropped(search):
    """The negative direction — and the one that makes the pair meaningful.

    `swiatek` reaches the SAME market through the outcome arm, so the loop mints
    the same concept. But the query names an outcome, not the ceremony, so the
    concept holds only derived evidence and ruling 041 drops it.

    The market itself must still come back. If both vanish, recall broke and the
    provenance rule is not what this test measured.
    """
    payload = await search("swiatek")
    assert "2026 Wimbledon Winner" in _futures_names(payload), (
        "the outcome arm stopped reaching the market — this case tests "
        "provenance, and it cannot do that if recall is what failed"
    )
    keys = _concept_keys(payload)
    assert not any("wimbledon" in k.lower() for k in keys), (
        f"`swiatek` does not name the Wimbledon concept, so that concept holds "
        f"derived-only evidence and is UNRANKABLE under ruling 041. Got {keys!r}."
    )


# --------------------------------------------------------------------------
# #4728 — the RECALL half: a fan types their team's nickname
# --------------------------------------------------------------------------
async def test_a_team_nickname_reaches_its_teams_markets(search):
    """🔴 #4728: `pats` must reach the Patriots' markets.

    Measured on production 2026-09-10: `?q=pats` returned ZERO of the 31 open
    New England Patriots markets, `?q=revs` zero of 15, `?q=niners` zero of 36,
    `?q=bucs` zero of 41. The nickname appears in no market name — venues write
    "Jets vs. Patriots" — and it stems to a different lexeme than the full name
    (`pats` -> `pat`, `patriots` -> `patriot`), so neither the substring arm nor
    the whole-word arm can reach the row. Only an alias can.

    The team ROW already resolves (`teams.alternate_names` carries these), which
    is exactly what made the gap easy to miss: the page shows the right team and
    none of its markets.
    """
    names = _futures_names(await search("pats"))
    assert "Jets vs. Patriots" in names, (
        f"`pats` did not reach the Patriots' own market: {names!r}. This is the "
        "#4728 recall hole — a fan typing the nickname their team is known by "
        "gets none of that team's markets."
    )


async def test_the_nickname_arm_does_not_fan_out_across_sports(search):
    """The guard that makes the alias safe to ship, and to extend.

    "Patriots" is not unique: 22 of the 53 open `%patriot%` markets on
    2026-09-10 were NOT New England's, and 15 of those were the Caribbean
    Premier League's St. Kitts and Nevis Patriots — a genuine whole-word match
    on a cricket side. An alias that expanded `pats` to `patriots` and stopped
    there would serve those 15 to a Patriots fan, which is the cross-league
    fan-out `CURATED_TEAM_ALIASES`'s (sport_key, name) key exists to prevent.

    This is the mutation-killing half of the pair: delete the
    `llm_sport_category` term from `_team_nickname_futures_arms` and the test
    above still passes while this one goes red.
    """
    names = _futures_names(await search("pats"))
    assert not any("St. Kitts" in (n or "") for n in names), (
        f"the nickname arm fanned out of the franchise's sport: {names!r}. "
        "`pats` is the NFL New England Patriots; Caribbean Premier League "
        "cricket is a different team that happens to share a word."
    )


async def test_the_literal_query_still_reaches_every_sport(search):
    """The ADDITIVE contract, and the control that makes the pair above honest.

    The sport scope belongs to the ALIAS arm, never to the futures query. A
    "fix" that scoped the whole query to the nickname's sport would satisfy both
    tests above and would be a filter wearing an alias's clothes — so the
    literal query has to keep reaching the sports the alias deliberately skips.

    `patriots` is not an alias, produces no nickname arm at all, and must return
    the Caribbean Premier League side exactly as it does today. That row is a
    legitimate whole-word answer to what the user literally typed; it is only
    wrong as an answer to `pats`.
    """
    names = _futures_names(await search("patriots"))
    assert any("St. Kitts" in (n or "") for n in names), (
        f"the literal query LOST the cricket side: {names!r}. #4728 adds a "
        "UNION arm — it must not narrow what `patriots` itself reaches."
    )
    assert "Jets vs. Patriots" in names, (
        f"the literal query lost the NFL row too: {names!r}"
    )


async def test_a_second_nickname_in_a_second_sport_also_resolves(search):
    """One green nickname could be a coincidence; the mechanism is the claim.

    `revs` -> "Revolution" scoped to soccer exercises a different row of
    `CURATED_TEAM_ALIASES`, a different sport category, and a different derived
    token — so it fails if the derivation is hard-coded to the football case.
    """
    names = _futures_names(await search("revs"))
    assert "Chicago Fire FC vs. New England Revolution" in names, (
        f"`revs` did not reach the Revolution's market: {names!r}"
    )


async def test_a_query_with_no_nickname_is_untouched(search):
    """The no-cost path: the overwhelming majority of queries.

    `_team_nickname_futures_arms` must return [] for them, so the SQL is
    byte-identical and no query pays for a feature it does not use. Asserted
    here on behaviour, and directly on the helper in
    `tests/test_search_team_nickname_aliases_4728.py`.
    """
    names = _futures_names(await search("nba champion"))
    assert "NBA Champion 2026" in names, (
        f"a query with no nickname in it changed: {names!r}"
    )


# --------------------------------------------------------------------------
# #4809 — the GAME-CARD half: a fan's nickname must reach their team's games
# --------------------------------------------------------------------------
async def test_a_team_nickname_reaches_its_teams_game_cards(search):
    """🔴 #4809: `pats` must reach the Patriots' GAMES, not just their markets.

    Measured on production 2026-09-10, with #4728 already live: `?q=pats`
    returned the right team row and 10 correct markets and **0 game cards**;
    `revs` 0; `niners` 2, both of them UTEP Miners.

    The cause is that the two rails match different columns. #4728's alias lives
    on `teams.alternate_names`, which the futures arm reaches through the team
    row — but the game rail matches the DENORMALISED `Event.home_team_name` /
    `away_team_name` text and never joins `teams`, so the alias is invisible to
    it. Only an event-side arm can close it.
    """
    pairings = _event_pairings(await search("pats"))
    assert any("New England Patriots" in p for p in pairings), (
        f"`pats` did not reach the Patriots' own game: {pairings!r}. This is the "
        "#4809 hole — the nickname reaches the team row and the markets, and the "
        "reader still sees no games."
    )


async def test_the_nickname_game_arm_does_not_fan_out_across_sports(search):
    """The guard that makes the event arm safe, and safe to extend.

    On the EVENT rail this matters MORE than on the futures rail: event team
    names are the same words the venue prints, so the bare token `Patriots`
    reaches `St Kitts & Nevis Patriots` — a Caribbean Premier League cricket
    side, a genuine whole-word match, and a wrong answer to `pats`.

    This is the mutation-killing half of the pair below: delete
    `Sport.key == sport_key` from `_team_nickname_event_arms` and the test above
    still passes while this one goes red.
    """
    pairings = _event_pairings(await search("pats"))
    assert not any("St Kitts" in p for p in pairings), (
        f"the nickname game arm fanned out of the franchise's sport: {pairings!r}. "
        "`pats` is the NFL New England Patriots; Caribbean Premier League cricket "
        "is a different team that happens to share a word."
    )


async def test_the_literal_query_still_reaches_every_sports_games(search):
    """The ADDITIVE contract for the game rail, and the honesty control.

    The sport scope belongs to the ALIAS arm, never to the event query. A "fix"
    that scoped the whole query to the nickname's sport would satisfy both tests
    above and be a filter wearing an alias's clothes — so the literal query has
    to keep reaching the sport the alias deliberately skips.

    `patriots` is not an alias, produces no nickname arm at all, and must return
    the Caribbean Premier League side exactly as it does today. That row is a
    legitimate whole-word answer to what the user literally typed; it is only
    wrong as an answer to `pats`.
    """
    pairings = _event_pairings(await search("patriots"))
    assert any("St Kitts" in p for p in pairings), (
        f"the literal query lost the cricket side: {pairings!r}. The alias arm is "
        "UNION-shaped and may only ADD rows; it must never narrow what the user "
        "actually typed."
    )
    assert any("New England Patriots" in p for p in pairings), (
        f"the literal query lost the NFL side: {pairings!r}"
    )


async def test_a_resolved_nickname_is_never_corrected_to_a_spelling_neighbour(search):
    """🔴 The `niners` -> UTEP Miners half, which recall alone does NOT fix.

    No 49ers event is seeded here on purpose, so the nickname arm finds nothing
    and `total_count` is 0 — exactly the state that sends a query to the trigram
    "did you mean" fallback. In production that fallback corrected `niners` to
    the nearest team NAME, `UTEP Miners`, and served two college football games
    inside a response whose 10 markets were all correctly San Francisco 49ers.

    With 49ers games in the window the recall arm alone would hide this, because
    the count is no longer 0 and the fallback never runs. That is why the seed
    withholds them: a bye week, an off-season or a narrow `days_back` reproduces
    this state in production at any time.

    We KNOW what `niners` names — the map is curated, franchise-anchored and
    sport-keyed — so an honest empty rail beats a guess, and the team and market
    rails still answer. The fallback itself is proven ALIVE in this fixture by
    the `celtcs` -> Boston Celtics correction (similarity 0.294, measured), so
    this assertion is not passing vacuously.
    """
    pairings = _event_pairings(await search("niners"))
    assert not any("UTEP" in p for p in pairings), (
        f"`niners` was 'corrected' to a spelling neighbour: {pairings!r}. A query "
        "that resolved a curated franchise nickname must never be answered with a "
        "different team that merely looks like it."
    )


@pytest.fixture
async def search_with_a_49ers_game(seeded_db, search):
    """`search`, plus the ONE row `_seed` deliberately withholds.

    The seed has no 49ers event ON PURPOSE — it is what keeps
    `test_a_resolved_nickname_is_never_corrected_to_a_spelling_neighbour` from
    passing vacuously, because with 49ers games in the window `total_count` is
    never 0 and the "did you mean" fallback never runs.

    The `9ers` test below needs the opposite state, so it gets its own row here
    rather than in `_seed`, where it would silently disarm that suppression test.
    `seeded_db` is function-scoped, so this row exists for this one test only.

    Seattle is the opponent because it shares no word with any other seeded row —
    a `Seahawks` collision would make a `9ers` hit ambiguous about which side of
    the fixture matched.
    """
    from app.models.models import Event, Sport
    from sqlalchemy import select

    _engine, maker = seeded_db
    async with maker() as session:
        nfl = (
            await session.execute(
                select(Sport).where(Sport.key == "americanfootball_nfl")
            )
        ).scalar_one()
        session.add(
            Event(
                sport_id=nfl.id,
                home_team_name="San Francisco 49ers",
                away_team_name="Seattle Seahawks",
                commence_time=datetime.now(timezone.utc) + timedelta(days=2),
                status="scheduled",
            )
        )
        await session.commit()

    return search


async def test_substring_nickname_9ers_reaches_49ers_game_cards(
    search_with_a_49ers_game,
):
    """🔴 CERT-2527's required repair, on a real Postgres.

    `9ers` is the one curated alias that is SPELLED INSIDE its own token, and the
    first cut of #4809 skipped it on the futures rail's reasoning: a substring
    needs no arm, because ILIKE will find it. True of `FuturesMarket.name`; false
    here, because the event matcher AND-s an FTS whole-word test onto the ILIKE::

        ILIKE '%9ers%'  vs 'San Francisco 49ers'  -> TRUE
        to_tsvector('San Francisco 49ers')        -> 'san' 'francisco' '49ers'
        plainto_tsquery('9ers')                   -> '9ers'                -> FALSE

    AND-ed that is FALSE, so the skip removed the only mechanism that could have
    matched and `?q=9ers` returned the team row, 10 correct 49ers markets and zero
    game cards — #4809's own symptom surviving inside #4809's fix.

    This runs against a real Postgres and not the unit suite deliberately: the
    defect lives in the disagreement between `ILIKE` and `to_tsvector`, and only
    the engine that owns both can be asked whether they agree. A mocked matcher
    would have reported this fix working while production returned nothing.
    """
    pairings = _event_pairings(await search_with_a_49ers_game("9ers"))
    assert any("San Francisco 49ers" in p for p in pairings), (
        f"`9ers` did not reach the 49ers' own game: {pairings!r}. The ILIKE arm "
        "matches the substring but the AND-ed FTS arm cannot word-match `9ers` "
        "against the lexeme `49ers`, so without an expansion arm the reader sees "
        "no games."
    )


async def test_the_9ers_arm_does_not_fan_out_across_sports(search_with_a_49ers_game):
    """The repair inherits the sport scope; it does not bypass it.

    The cheap version of this fix — dropping the substring skip AND the
    `Sport.key` guard together — would satisfy the test above. `9ers` expands to
    the bare token `49ers`, and nothing about that token is intrinsically NFL.
    """
    pairings = _event_pairings(await search_with_a_49ers_game("9ers"))
    assert not any("UTEP" in p or "St Kitts" in p for p in pairings), (
        f"the `9ers` arm reached outside the NFL: {pairings!r}"
    )


# --------------------------------------------------------------------------
# #7381 — /typeahead's TEAM arm matches a word START, not a substring
# --------------------------------------------------------------------------
# These belong in this file and nowhere else. The rule is one Postgres regex
# AND-ed onto an ILIKE, so the only instrument that can grade it is the engine
# that owns both operators — a mocked session returns whatever rows the fake was
# told to hold and would report this fix working while `?q=nba` still offered
# Tornado Pekanbaru. That is the same reasoning `test_substring_nickname_9ers…`
# gives for living here, and it is the reason this file exists at all.


@pytest.fixture
async def typeahead_with_infix_teams(seeded_db, typeahead):
    """`typeahead`, plus the four team rows #7381 was measured on.

    Three of these are transcribed from production 2026-09-19 rather than
    invented: `GET /api/events/typeahead?q=nba` offered "Tornado Pekanbaru"
    (soccer) and "Trinbago Knight Riders" (cricket) and nothing else in the team
    slots, because `nba` is spelled inside Peka(nba)ru and Tri(nba)go.

    They are NOT seeded alone. A rule that only ever removes rows looks perfect
    on a noise-only fixture and is indistinguishable from a broken predicate, so
    each noise row is paired with a row of the SAME shape that must survive:

        Tornado Pekanbaru        `nba` is an infix        -> must be dropped
        Trinbago Knight Riders   `nba` is an infix        -> must be dropped
        Charlotte Hornets        `nets` is an infix       -> must be dropped
        Brooklyn Nets            `nets` starts a word     -> must SURVIVE
        San Francisco 49ers      `9ers` is an infix of
                                 its own token, RESCUED
                                 by its alias row        -> must SURVIVE

    The 49ers row is the important one and it is transcribed, aliases and all,
    from production: ``alternate_names = ["9ers", "49ers", "niners"]``. It is the
    escape hatch this whole rule depends on. `9ers` is spelled INSIDE the token
    "49ers", so the boundary rule cannot match the name — and does not need to,
    because inside the JSON text the alias is preceded by a quote, which is a
    word start. Take the aliases away and `9ers` stops reaching the 49ers, which
    is #4809 / CERT-2527's defect returning through a different door.

    Soccer and cricket are deliberate: `_is_individual_sport` strips tennis, MMA,
    golf and boxing "teams" out of the pool before the predicate is ever graded,
    so a tennis specimen (Korpatsch, the production example in the sibling arm
    #5082) would pass this test for the wrong reason.

    `_TEAM_POOL_SIZE` is 3. The seed is kept small and spread across distinct
    query terms so that a positive assertion can never fail because the pool
    filled up — a crowded fixture turns a recall assertion into a ranking one.
    """
    from app.models.models import Sport, Team
    from sqlalchemy import select

    _engine, maker = seeded_db
    async with maker() as session:
        nba = (
            await session.execute(
                select(Sport).where(Sport.key == "basketball_nba")
            )
        ).scalar_one()
        nfl = (
            await session.execute(
                select(Sport).where(Sport.key == "americanfootball_nfl")
            )
        ).scalar_one()
        soccer = Sport(key="soccer_indonesia_liga_1", name="Liga 1")
        cricket = Sport(key="cricket_caribbean_premier_league", name="CPL")
        session.add_all([soccer, cricket])
        await session.flush()

        session.add_all([
            Team(sport_id=soccer.id, name="Tornado Pekanbaru", abbreviation="TPK"),
            Team(
                sport_id=cricket.id,
                name="Trinbago Knight Riders",
                abbreviation="TKR",
            ),
            Team(sport_id=nba.id, name="Charlotte Hornets", abbreviation="CHA"),
            Team(
                sport_id=nba.id,
                name="Brooklyn Nets",
                abbreviation="BKN",
                alternate_names=["Nets", "Brooklyn"],
            ),
            Team(
                sport_id=nfl.id,
                name="San Francisco 49ers",
                abbreviation="SF",
                alternate_names=["9ers", "49ers", "niners"],
            ),
        ])
        await session.commit()

    return typeahead


async def test_an_infix_inside_a_word_is_not_a_team_match(typeahead_with_infix_teams):
    """🔴 #7381's symptom, exactly as a reader met it on production.

    `nba` is the third most-searched query in `search_query_logs` and the two
    team rows it offered were an Indonesian soccer club and a Caribbean cricket
    franchise. Neither name contains the word "NBA"; both contain the letters.
    """
    texts = _typeahead_texts(await typeahead_with_infix_teams("nba"))
    offenders = [t for t in texts if "Pekanbaru" in t or "Trinbago" in t]
    assert offenders == [], (
        f"`nba` still offers a team matched on an interior substring: {offenders!r}. "
        "Peka(nba)ru and Tri(nba)go are spelling coincidences inside one word, "
        "not teams the reader asked for."
    )


async def test_the_word_start_rule_does_not_take_the_real_team_with_the_noise(
    typeahead_with_infix_teams,
):
    """The other direction, and the one that makes the rule safe to ship.

    `nets` is the production case where the noise and the answer sit in the same
    sport: Charlotte Ho(rnets) is an infix, Brooklyn **Nets** is the team. A
    filter that dropped both would satisfy the test above and be wrong.
    """
    texts = _typeahead_texts(await typeahead_with_infix_teams("nets"))
    assert any("Brooklyn Nets" in t for t in texts), (
        f"the real team went out with the noise: {texts!r}. The rule is a word "
        "BOUNDARY test, not a whole-word one — dropping Brooklyn Nets means the "
        "predicate is filtering everything, which no recall census would survive."
    )
    assert not any("Hornets" in t for t in texts), (
        f"`nets` still offers Charlotte Ho(rnets): {texts!r}"
    )


async def test_progressive_typing_still_matches_a_partial_word(
    typeahead_with_infix_teams,
):
    """The reason `/typeahead` was left on a substring ILIKE in the first place.

    `_event_name_match` records that `/search`'s whole-word (`to_tsvector`) rule
    cannot serve the dropdown, because `celt` is not a word of "Celtics" — and it
    is right. This test is the proof that #7381 took the weaker rule and not that
    one: every prefix a reader types on the way to a team still matches, at the
    start of the name AND at the start of a later word.

    If this goes red the fix has been "simplified" into `/search`'s rule and the
    dropdown has stopped answering keystrokes, which is a far larger regression
    than the one #7381 repairs.
    """
    for prefix, wanted in [
        ("brook", "Brooklyn Nets"),   # start of the name
        ("charl", "Charlotte Hornets"),  # start of the name, the noise row's own turn
        ("knight", "Trinbago Knight Riders"),  # start of the SECOND word
        ("riders", "Trinbago Knight Riders"),  # start of the THIRD word
    ]:
        texts = _typeahead_texts(await typeahead_with_infix_teams(prefix))
        assert any(wanted in t for t in texts), (
            f"`{prefix}` no longer reaches {wanted!r}: {texts!r}. A word-boundary "
            "rule must keep every partial word a reader can type."
        )


async def test_an_alternate_name_is_matched_on_its_own_word_start(
    typeahead_with_infix_teams,
):
    """The third column, which is a JSONB array cast to text.

    `alternate_names` reaches the predicate as `["Nets", "Brooklyn"]`, so every
    alias is preceded by `"` or `, ` — non-alphanumeric, hence a word start. The
    column is easy to forget precisely because it does not look like prose, and
    a fix applied to `name` and `abbreviation` alone would leave the widest of
    the three arms matching anywhere.
    """
    texts = _typeahead_texts(await typeahead_with_infix_teams("nets"))
    assert any("Brooklyn Nets" in t for t in texts), (
        f"the alias arm stopped matching at a word start inside the JSON text: "
        f"{texts!r}"
    )


async def test_a_nickname_spelled_inside_its_own_token_survives_on_its_alias(
    typeahead_with_infix_teams,
):
    """🔴 The rule's one real cost, and the mechanism that pays it.

    `9ers` is spelled INSIDE the token "49ers", so the boundary rule cannot match
    it against the NAME — by construction, and there is no lexical rule that
    could: "9ers" in "49ers" and "nets" in "Hornets" are the same shape, and one
    of them is the defect. `_event_name_match` reached the same wall on `/search`
    and named the answer: "separating them needs the team registry … the
    alias/identity layer, not a WHERE clause here."

    On production the 49ers row carries `["9ers", "49ers", "niners"]`, and inside
    the JSON text every alias is preceded by a quote — a word start. So the alias
    arm matches and the reader still gets their team. This test is that
    dependency, made explicit: it is the only thing standing between #7381 and a
    regression of #4809 / CERT-2527.

    MEASURED over the 250 most-searched verbatim queries of the last 90 days:
    exactly four team NAMES are lost to this class, and every one of them is a
    row with no aliases at all — Saskatchewan Roughriders (`riders`), Creighton
    Bluejays (`blue jays`), Purdue Boilermakers (`oil`), Charlotte 49ers
    (`9ers`). Each is reachable by its own name, and the repair for all four is
    an alias row, not a looser predicate. Filed as the follow-up in #7381.
    """
    texts = _typeahead_texts(await typeahead_with_infix_teams("9ers"))
    assert any("San Francisco 49ers" in t for t in texts), (
        f"`9ers` no longer reaches the 49ers: {texts!r}. The boundary rule cannot "
        "match `9ers` against the token '49ers', so this row survives ONLY on its "
        "alias arm — if that arm stopped being searched, or stopped being tested "
        "at a word start inside the JSON text, #4809's defect is back."
    )


async def test_the_multi_word_branch_carries_the_same_rule(
    typeahead_with_infix_teams,
):
    """`is_multi_word` is a SECOND copy of the team filter, and it is the one
    `nba champion` — a head query — actually lands in.

    This file's own history is the argument for asserting both: the route's
    comments record `/search` and `/typeahead` drifting for three cycles by
    keeping two copies of one rule. Fixing the single-word branch alone would go
    green on every other test here.
    """
    matched = _typeahead_texts(await typeahead_with_infix_teams("knight nba"))
    assert not any("Trinbago" in t for t in matched), (
        f"the multi-word branch still matches `nba` inside Tri(nba)go: {matched!r}. "
        "`knight` word-starts and `nba` does not, so the AND must fail."
    )
    # ...and the same two-term query with both terms at word starts still lands.
    kept = _typeahead_texts(await typeahead_with_infix_teams("knight riders"))
    assert any("Trinbago Knight Riders" in t for t in kept), (
        f"the multi-word branch stopped matching a genuine two-word query: {kept!r}"
    )


async def test_the_seeded_teams_that_never_collided_are_untouched(
    typeahead_with_infix_teams,
):
    """The census said 40 of 47 head terms are identical row for row. This is
    that claim, on the rows this file already had before #7381 existed.

    `bruins` and `celtics` are the file's own pre-existing team specimens, and
    neither is an infix of anything seeded. If the boundary rule reaches them,
    the escape or the anchor is wrong — for instance an unescaped term, or an
    anchor that requires the match to start the WHOLE string rather than a word.
    """
    assert any(
        "Boston Bruins" in t
        for t in _typeahead_texts(await typeahead_with_infix_teams("bruins"))
    ), "the pool specimen from LAT-P046 stopped matching"
    assert any(
        "Boston Celtics" in t
        for t in _typeahead_texts(await typeahead_with_infix_teams("celtics"))
    ), "a plain whole-word team match stopped matching"


# --------------------------------------------------------------------------
# #5773 — the outcome arm speaks for the club the registry resolved
# --------------------------------------------------------------------------
# Here because the rule is ILIKE and POSIX `~*` word boundaries over real
# outcome text, and the resolution that switches it on is the teams query the
# route runs first; neither half means anything against a mocked session.

_YANK_OUTCOME_JUNK = (
    "Who will become Prime Minister of India after next general election?",
    "WBC Flyweight Title on January 1, 2027",
    "Latin Grammy Awards: Best Urban Song",
)
_PHIL_WHOLE_WORD = "Colorado Governor winner?"
_PHIL_PREFIX_ONLY = "2027 FIFA Women's World Cup Champion"
_LEBRO_CONTROL = "Will LeBron James retire before next NBA season? (5773 control)"


@pytest.fixture
async def search_with_resolved_clubs(seeded_db, search):
    """`search`, plus the rows #5773's futures half was reported on.

    `?q=yank` on production 2026-09-25 04:5xZ resolved New York Yankees on the
    teams rail and still listed three markets reached only through an outcome
    spelling the four letters: `Priyanka Gandhi Vadra`, `Yankiel Rivera`,
    `Daddy Yankee`. `phil` carries the whole-word case (`Phil Weiser`, which must
    survive) beside a prefix-only one (`Philippines`, which the rule drops while
    `phil` resolves the Phillies). The LeBron row is the control: `lebro`
    resolves no club, so its arm must be the bare substring it always was.

    Its own fixture, not `_seed`: adding the Yankees to the shared seed would make
    `yank` resolve a club for every test in this file, and
    `test_an_interior_substring_does_not_outrank_a_real_prefix` asserts the
    Mayank row is still IN the bucket.
    """
    from sqlalchemy import select

    from app.models.models import FuturesMarket, FuturesOutcome, Sport, Team

    _engine, maker = seeded_db
    async with maker() as session:
        mlb = (
            await session.execute(select(Sport).where(Sport.key == "baseball_mlb"))
        ).scalar_one()
        session.add_all(
            [
                Team(sport_id=mlb.id, name="New York Yankees", abbreviation="NYY"),
                Team(sport_id=mlb.id, name="Philadelphia Phillies", abbreviation="PHI"),
            ]
        )
        for external_id, name, outcomes in (
            ("KXINDIAPM-5773", _YANK_OUTCOME_JUNK[0], ["Priyanka Gandhi Vadra", "Rahul Gandhi"]),
            ("KXWBCFLY-5773", _YANK_OUTCOME_JUNK[1], ["Yankiel Rivera", "Kenshiro Teraji"]),
            ("KXLATINGRAMMY-5773", _YANK_OUTCOME_JUNK[2],
             ["Daddy Yankee: Bzrp Music Sessions, Vol. 0/66", "Karol G: Si Antes Te Hubiera Conocido"]),
            ("KXCOGOV-5773", _PHIL_WHOLE_WORD, ["Phil Weiser", "Michael Bennet"]),
            ("KXWWC-5773", _PHIL_PREFIX_ONLY, ["Philippines", "Spain"]),
            ("KXLEBRON-5773", _LEBRO_CONTROL, ["Yes", "No", "LeBron James"]),
        ):
            market = FuturesMarket(
                source="kalshi",
                external_id=external_id,
                name=name,
                status="open",
                resolution_date=datetime.now(timezone.utc) + timedelta(days=90),
            )
            session.add(market)
            await session.flush()
            for outcome_name in outcomes:
                session.add(
                    FuturesOutcome(
                        market_id=market.id,
                        external_id=f"{external_id}:{outcome_name}",
                        name=outcome_name,
                        current_probability=_SEED_PRICE,
                    )
                )
        await session.commit()

    return search


async def test_a_resolved_club_keeps_its_own_market_and_sheds_the_spelling_junk(
    search_with_resolved_clubs,
):
    """#5773's specimen. The Yankees market is reached through its outcome
    `New York Yankees` and stays; every market reached only by `yank` sitting
    inside another name goes — including `Mayank`, the #4572 row the ranking fix
    could only sink."""
    payload = await search_with_resolved_clubs("yank")
    assert "New York Yankees" in [t.get("name") for t in payload.get("teams", [])], (
        "the fixture is dead: `yank` did not resolve the Yankees, so the rule under "
        "test never switched on"
    )
    names = _futures_names(payload)
    assert _YANK_REAL in names, f"the club's own market was lost: {names!r}"
    leaked = [n for n in (*_YANK_OUTCOME_JUNK, _YANK_NOISE) if n in names]
    assert not leaked, (
        f"`yank` resolved the Yankees and still served {leaked!r} through an "
        "outcome that only spells the four letters (#5773)"
    )


async def test_a_whole_word_outcome_survives_the_club_rule(search_with_resolved_clubs):
    """`phil` resolves the Phillies, and `Phil Weiser` is still a Phil. The rule
    narrows partial-word matches only; a whole word is what the reader typed."""
    names = _futures_names(await search_with_resolved_clubs("phil"))
    assert _PHIL_WHOLE_WORD in names, f"a whole-word outcome was lost: {names!r}"
    assert _PHIL_PREFIX_ONLY not in names, (
        f"`Philippines` survived while `phil` resolved a club: {names!r}. That is "
        "the named cost of the rule; if it is back, the rule did not switch on"
    )


async def test_a_query_that_resolves_no_club_keeps_the_bare_substring(
    search_with_resolved_clubs,
):
    """The control, and the reason the earlier word test was descoped: `lebro`
    is four letters into a PERSON, no registry row answers for it, and the arm
    must still reach every market that lists him."""
    payload = await search_with_resolved_clubs("lebro")
    assert not payload.get("teams"), f"`lebro` resolved a team: {payload.get('teams')!r}"
    names = _futures_names(payload)
    assert _LEBRO_CONTROL in names, (
        f"`lebro` lost the market that lists LeBron James: {names!r}. A query that "
        "resolves no club must compile the outcome arm exactly as before"
    )


# --------------------------------------------------------------------------
# #8523 — a rostered player's full name reaches his club
# --------------------------------------------------------------------------
# Here and not in a unit suite for the reason the #7381 block gives: the lookup
# is Postgres JSON (`jsonb_array_elements`, `->>`, `#>>`) over the roster column,
# and only the engine that owns those operators can say what they match.


@pytest.fixture
async def search_with_a_rostered_player(seeded_db, search):
    """`search`, plus the rows #8523 was reported on (production 2026-09-25).

    `?q=patrick mahomes` served teams 0, games 0 and futures led by novelty
    markets listing him as an outcome (Madden cover, SNL host), with his award
    markets below them. Transcribed shape, trimmed to one of each class:

        Kansas City Chiefs   NFL, roster holds him (object form) and Travis
                             Kelce (the older bare-string form — 992 of the
                             10,268 production roster entries are strings)
        Chiefs at Dolphins   scheduled, in the window
        Offensive Player of  `football`, market_tier 3 — the one that belongs
        the Year Winner?     first
        Who will host SNL    `entertainment`, market_tier 2 — why it led: tier
        Season 51?           2 sorts above tier 3 and nothing about the query
                             separates two outcome-only matches

    Its own fixture, not `_seed`, so no roster exists for any other test in this
    file to trip over.
    """
    from sqlalchemy import select

    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport, Team

    _engine, maker = seeded_db
    async with maker() as session:
        nfl = (
            await session.execute(
                select(Sport).where(Sport.key == "americanfootball_nfl")
            )
        ).scalar_one()
        session.add(
            Team(
                sport_id=nfl.id,
                name="Kansas City Chiefs",
                abbreviation="KC",
                roster_players=[
                    {"name": "Patrick Mahomes", "espn_id": "3139477"},
                    "Travis Kelce",
                ],
            )
        )
        session.add(
            Event(
                sport_id=nfl.id,
                home_team_name="Miami Dolphins",
                away_team_name="Kansas City Chiefs",
                commence_time=datetime.now(timezone.utc) + timedelta(days=3),
                status="scheduled",
            )
        )
        for external_id, name, category, tier, volume in (
            ("KXNFLOPOY-8523", "Offensive Player of the Year Winner?",
             "football", 3, 1_409_544),
            ("KXSNLHOST-8523", "Who will host Saturday Night Live Season 51?",
             "entertainment", 2, 1_641_127),
        ):
            market = FuturesMarket(
                source="kalshi",
                external_id=external_id,
                name=name,
                status="open",
                llm_sport_category=category,
                market_tier=tier,
                volume=volume,
                resolution_date=datetime.now(timezone.utc) + timedelta(days=90),
            )
            session.add(market)
            await session.flush()
            for outcome_name in ("Patrick Mahomes", "Travis Kelce"):
                session.add(
                    FuturesOutcome(
                        market_id=market.id,
                        external_id=f"{external_id}:{outcome_name}",
                        name=outcome_name,
                        current_probability=_SEED_PRICE,
                    )
                )
        await session.commit()

    return search


def _team_names(payload: dict) -> list[str]:
    return [t.get("name") for t in payload.get("teams") or []]


@pytest.mark.parametrize(
    "q", ["patrick mahomes", "Patrick Mahomes", "  patrick   MAHOMES "]
)
async def test_a_rostered_players_name_reaches_his_team_and_its_game(
    search_with_a_rostered_player, q
):
    """#8523 — the reported query, in the cases a reader types it."""
    payload = await search_with_a_rostered_player(q)
    assert "Kansas City Chiefs" in _team_names(payload), (
        f"{q!r} served teams {_team_names(payload)!r} — the roster says he is a "
        "Kansas City Chief and the page did not ask it (#8523)"
    )
    pairings = _event_pairings(payload)
    assert "Miami Dolphins vs Kansas City Chiefs" in pairings, (
        f"{q!r} served games {pairings!r} — his team resolved but its next game "
        "is missing (#8523)"
    )
    assert payload.get("did_you_mean") is None, (
        f"{q!r} was 'corrected' to {payload.get('did_you_mean')!r} — a resolved "
        "player is never a spelling to guess at"
    )


async def test_his_award_market_ranks_above_the_novelty_that_lists_him(
    search_with_a_rostered_player,
):
    """#8523 — the ranking half, and it is not a separate mechanism.

    The Chiefs' games make the sport facet NFL, and `_demote_wrong_sport` (#7259)
    sinks the `entertainment` row beneath the `football` one. Before the roster
    arm there were no games, no facet, no resolved sport, and market_tier 2 put
    SNL first.
    """
    names = _futures_names(await search_with_a_rostered_player("patrick mahomes"))
    opoy = "Offensive Player of the Year Winner?"
    snl = "Who will host Saturday Night Live Season 51?"
    assert opoy in names and snl in names, f"recall moved: {names!r}"
    assert names.index(opoy) < names.index(snl), (
        f"futures order {names!r}: the novelty still leads his award market (#8523)"
    )


async def test_the_older_bare_string_roster_form_is_read_too(
    search_with_a_rostered_player,
):
    """992 production roster entries are plain strings, not `{name: ...}`."""
    payload = await search_with_a_rostered_player("travis kelce")
    assert "Kansas City Chiefs" in _team_names(payload), (
        f"`travis kelce` served teams {_team_names(payload)!r} — a string-form "
        "roster entry was not read"
    )


@pytest.mark.parametrize(
    "q",
    [
        # A surname is not the full name (and one word is never looked up).
        "mahomes",
        # A prefix of the name is not the name.
        "patrick maho",
        # Two words that are no rostered player's name.
        "patrick kelce",
    ],
)
async def test_only_a_complete_rostered_name_resolves_a_team(
    search_with_a_rostered_player, q
):
    """#8523's controls. Each still reaches the markets through their outcome
    text, so the fixture is live — only the team must not appear."""
    payload = await search_with_a_rostered_player(q)
    assert _futures_names(payload), f"{q!r} reached no markets — the control is dead"
    assert "Kansas City Chiefs" not in _team_names(payload), (
        f"{q!r} resolved the Chiefs from a roster without naming a player in full"
    )


# --------------------------------------------------------------------------
# #8523, dropdown half — the same player, typed into /typeahead
# --------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# #8697 — a resolved team's games lead; a namesake from a teamless sport sinks
# ---------------------------------------------------------------------------


@pytest.fixture
async def search_with_a_namesake_rugby_club(seeded_db, search):
    """`?q=chiefs` on production 2026-09-25, trimmed to one of each class.

        Kansas City Chiefs          NFL team — the TEAMS card resolves it
        Exeter Chiefs v Gloucester  rugby_other, TOMORROW — led the games list
        Miami Dolphins v KC Chiefs  NFL, in 3 days — sat second
        Bath v Exeter Chiefs        rugby_other, in 5 days

    No rugby club named Chiefs is in the teams table, which is the evidence.
    """
    from sqlalchemy import select

    from app.models.models import Event, Sport, Team

    _engine, maker = seeded_db
    now = datetime.now(timezone.utc)
    async with maker() as session:
        nfl = (
            await session.execute(
                select(Sport).where(Sport.key == "americanfootball_nfl")
            )
        ).scalar_one()
        rugby = Sport(key="rugby_other", name="rugby_other")
        session.add(rugby)
        await session.flush()
        session.add(Team(sport_id=nfl.id, name="Kansas City Chiefs", abbreviation="KC"))
        for sport_id, home, away, days in (
            (rugby.id, "Exeter Chiefs", "Gloucester", 1),
            (nfl.id, "Miami Dolphins", "Kansas City Chiefs", 3),
            (rugby.id, "Bath", "Exeter Chiefs", 5),
        ):
            session.add(
                Event(
                    sport_id=sport_id,
                    home_team_name=home,
                    away_team_name=away,
                    commence_time=now + timedelta(days=days),
                    status="scheduled",
                )
            )
        await session.commit()
    return search


def _game_pairs(payload: dict) -> list[str]:
    return [
        f"{r.get('home_team') or r.get('home_team_name')} v "
        f"{r.get('away_team') or r.get('away_team_name')}"
        for r in payload.get("results") or []
    ]


async def test_the_resolved_teams_game_leads_a_namesakes_rugby_match(
    search_with_a_namesake_rugby_club,
):
    payload = await search_with_a_namesake_rugby_club("chiefs")
    assert [t.get("name") for t in payload.get("teams") or []] == ["Kansas City Chiefs"]
    games = _game_pairs(payload)
    assert games[0] == "Miami Dolphins v Kansas City Chiefs", games
    # Sunk, never dropped — and still in kickoff order among themselves.
    assert games[1:] == ["Exeter Chiefs v Gloucester", "Bath v Exeter Chiefs"], games


async def test_without_the_key_the_namesake_leads_again(
    search_with_a_namesake_rugby_club, monkeypatch,
):
    """Strawman: remove the key and tomorrow's rugby match is first again —
    the fixture reproduces the defect, so the test above testifies."""
    from app.routes import events as events_module

    monkeypatch.setattr(
        events_module, "_event_teamless_sport_order_key", lambda *_: None
    )
    games = _game_pairs(await search_with_a_namesake_rugby_club("chiefs"))
    assert games[0] == "Exeter Chiefs v Gloucester", games


async def test_a_query_that_resolves_no_team_keeps_kickoff_order(
    search_with_a_namesake_rugby_club,
):
    """`exeter` matches no team row, so the evidence is disarmed."""
    games = _game_pairs(await search_with_a_namesake_rugby_club("exeter"))
    assert games == ["Exeter Chiefs v Gloucester", "Bath v Exeter Chiefs"], games


@pytest.fixture
async def typeahead_with_a_rostered_player(search_with_a_rostered_player, typeahead):
    """`typeahead` over the same seed as `search_with_a_rostered_player`.

    The roster index is PROCESS state (`_roster_player_team_ids`), and every
    test here gets a fresh database, so it is expired on the way in and out: an
    index built over another test's rows would answer with that test's ids.
    """
    from app.routes import events as events_route

    events_route._roster_index_expires_at = 0.0
    yield typeahead
    events_route._roster_index_expires_at = 0.0


def _typeahead_rows(payload) -> list[tuple[str, str]]:
    items = payload.get("suggestions", []) if isinstance(payload, dict) else payload
    return [(i.get("type"), i.get("text")) for i in items if isinstance(i, dict)]


async def test_the_dropdown_offers_a_rostered_players_team_and_its_game(
    typeahead_with_a_rostered_player,
):
    """#8523 — `patrick mahomes` in the search box: his club, then its game.

    Production before (2026-09-25 04:1xZ): five novelty markets, no team, no
    game. The club must also LEAD the novelty that lists him — it carries his
    name as scorer evidence, so a club row sitting under the SNL market would
    mean the evidence never reached the scorer.
    """
    rows = _typeahead_rows(await typeahead_with_a_rostered_player("patrick mahomes"))
    texts = [t for _, t in rows]
    assert ("team", "Kansas City Chiefs") in rows, (
        f"no Chiefs row in the dropdown: {rows!r} (#8523)"
    )
    assert any(k == "event" and "Kansas City Chiefs" in t for k, t in rows), (
        f"the Chiefs resolved but their next game is missing: {rows!r} (#8523)"
    )
    snl = "Who will host Saturday Night Live Season 51?"
    if snl in texts:
        assert texts.index("Kansas City Chiefs") < texts.index(snl), (
            f"the club ranks below a novelty that merely lists him: {rows!r}"
        )


async def test_the_dropdown_ranks_his_teams_game_above_the_novelties(
    typeahead_with_a_rostered_player,
):
    """#8523 — the GAME leads the novelties too, not only the club.

    The test above let the game sit anywhere, and production served it LAST
    (2026-09-25 05:5xZ): club, then Madden / SNL / wedding / two Google-search
    markets, then "Kansas City Chiefs at Miami Dolphins". The game's own name
    holds no word of the query, so without the player's alias it scores the
    fragment class, under every market that lists him as an outcome.
    """
    rows = _typeahead_rows(await typeahead_with_a_rostered_player("patrick mahomes"))
    kinds = [k for k, _ in rows]
    assert "event" in kinds and "futures" in kinds, f"recall moved: {rows!r}"
    game_at = kinds.index("event")
    first_market_at = kinds.index("futures")
    assert game_at < first_market_at, (
        f"the Chiefs' game ranks under a market that merely lists him: {rows!r} (#8523)"
    )
    assert rows[game_at - 1] == ("team", "Kansas City Chiefs"), (
        f"the game is not directly under its club: {rows!r} (#8523)"
    )


async def test_the_dropdown_reads_the_bare_string_roster_form(
    typeahead_with_a_rostered_player,
):
    rows = _typeahead_rows(await typeahead_with_a_rostered_player("travis kelce"))
    assert ("team", "Kansas City Chiefs") in rows, rows


@pytest.mark.parametrize("q", ["mahomes", "patrick maho", "patrick kelce"])
async def test_the_dropdown_resolves_a_team_only_from_a_complete_rostered_name(
    typeahead_with_a_rostered_player, q
):
    """No liveness assert, unlike `/search`'s controls: the dropdown ANDs every
    word, so `patrick kelce` legitimately reaches nothing. The control is live
    anyway, because the roster rescue is gated on an EMPTY TEAM POOL only, which
    every one of these queries has."""
    rows = _typeahead_rows(await typeahead_with_a_rostered_player(q))
    assert ("team", "Kansas City Chiefs") not in rows, (
        f"{q!r} resolved the Chiefs from a roster without naming a player in full"
    )


# --------------------------------------------------------------------------
# #4615 — a resolved team's own game sits directly under the team, above its props
# --------------------------------------------------------------------------


@pytest.fixture
async def typeahead_with_a_team_and_its_inning_markets(seeded_db, typeahead):
    """The `dodg` rows from production 2026-09-25 07:30Z (`6e2f96cb`).

    Dodgers card, then the game's own parent market and four "Nth Inning Winner"
    markets, then tonight's game LAST: the fixture was already in the pool, so
    the lead-team arm never marked it, and `query_names_participant` refuses the
    prefix `dodg` (and the fold `dodger`), so it stayed a plain `event` under
    `futures`. Its own fixture, not `_seed`, so no other test sees a Dodgers row.
    """
    from sqlalchemy import select

    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport, Team

    _engine, maker = seeded_db
    async with maker() as session:
        mlb = (
            await session.execute(select(Sport).where(Sport.key == "baseball_mlb"))
        ).scalar_one()
        dodgers = Team(
            sport_id=mlb.id,
            name="Los Angeles Dodgers",
            abbreviation="LAD",
            alternate_names=["Los Angeles", "Dodgers", "LAD"],
        )
        session.add(dodgers)
        await session.flush()
        session.add(
            Event(
                sport_id=mlb.id,
                home_team_name="San Francisco Giants",
                away_team_name="Los Angeles Dodgers",
                away_team_id=dodgers.id,
                commence_time=datetime.now(timezone.utc) + timedelta(hours=6),
                status="scheduled",
            )
        )
        parent = "Los Angeles Dodgers vs. San Francisco Giants"
        for suffix in ("", " - 1st Inning Winner", " - 3rd Inning Winner",
                       " - 4th Inning Winner", " - 5th Inning Winner"):
            external_id = f"KXMLBGAME-4615{suffix.replace(' ', '')}"
            market = FuturesMarket(
                source="kalshi",
                external_id=external_id,
                name=f"{parent}{suffix}",
                status="open",
                llm_sport_category="baseball",
                market_tier=3,
                volume=50_000,
                resolution_date=datetime.now(timezone.utc) + timedelta(days=1),
            )
            session.add(market)
            await session.flush()
            for outcome_name in ("Los Angeles Dodgers", "San Francisco Giants"):
                session.add(
                    FuturesOutcome(
                        market_id=market.id,
                        external_id=f"{external_id}:{outcome_name}",
                        name=outcome_name,
                        current_probability=_SEED_PRICE,
                    )
                )
        await session.commit()

    return typeahead


_DODGERS_GAME = ("event", "Los Angeles Dodgers at San Francisco Giants")


@pytest.mark.parametrize("q", ["dodg", "dodger"])
async def test_a_resolved_teams_game_sits_directly_under_it(
    typeahead_with_a_team_and_its_inning_markets, q
):
    """🔴 THE SHIP. `dodg` is the production specimen (MC1B, the unfinished alias);
    `dodger` is the `yankee` shape (the whole alias through the plural fold)."""
    rows = _typeahead_rows(await typeahead_with_a_team_and_its_inning_markets(q))
    kinds = [k for k, _ in rows]
    assert "futures" in kinds, f"{q!r}: recall moved, no inning markets: {rows!r}"
    assert rows[:2] == [("team", "Los Angeles Dodgers"), _DODGERS_GAME], (
        f"{q!r}: the Dodgers' game is not directly under the Dodgers: {rows!r} (#4615)"
    )


async def test_a_team_the_query_only_lands_on_keeps_market_before_game(
    typeahead_with_a_team_and_its_inning_markets,
):
    """The control arm: the same team leads, the gate stays SHUT. `angel` lands on
    the Dodgers only as a prefix of the token "Angeles" (MC2) — not a whole owned
    name, not the unfinished form of one — so their game keeps ruling 041's
    market > event, exactly as before #4615.

    Not `angeles`: that is a whole word of "Los Angeles Dodgers", so #4411's
    `query_names_participant` already promotes every Los Angeles game for it,
    and a control there would pass or fail for a reason the gate never touched.
    """
    rows = _typeahead_rows(await typeahead_with_a_team_and_its_inning_markets("angel"))
    kinds = [k for k, _ in rows]
    # The Dodgers are still the route's lead team here (the only club `angel`
    # reaches) even though their MC2 card falls under the page cut: forcing the
    # gate open turns this test red, which is what proves it testifies.
    assert _DODGERS_GAME in rows and "futures" in kinds, (
        f"the control is dead — `angel` reached no game or no market: {rows!r}"
    )
    assert kinds.index("futures") < rows.index(_DODGERS_GAME), (
        f"`angel` promoted the game over the market: {rows!r} (#4615 gate leaked)"
    )


# ---------------------------------------------------------------------------
# #8704 — the collapse refill reads the rows the window's statement already has
# ---------------------------------------------------------------------------

#: 25 copies of one question rank first (tier 1, top volume), so the 20-row
#: window dedups to ONE answer row and the collapse refill fires; 45 distinct
#: questions follow. Tier<=1 therefore holds 70 rows — more than rank 60 — so
#: the window statement's own spare rows ARE the refill (`skipped` + full page).
_REFILL_WORDS = (
    "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima "
    "mike november oscar papa quebec romeo sierra tango uniform victor whiskey "
    "xray yankee zulu amber cobalt denim ember fern garnet harbor ivory jade "
    "kelp lotus maple nectar onyx pearl quartz raven slate topaz"
).split()


@pytest.fixture
async def search_with_a_collapsing_window(seeded_db):
    """`/api/events/search?debug_timing=1` over a corpus whose window collapses."""
    from httpx import ASGITransport, AsyncClient

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.services.database import get_db, get_db_rw

    _engine, maker = seeded_db
    names = [("Qzunited Cup Winner?", 1, 10_000_000 - i) for i in range(25)]
    names += [
        (f"Qzunited {word.title()} Trophy Winner?", 2, 1_000_000 - i)
        for i, word in enumerate(_REFILL_WORDS[:45])
    ]
    async with maker() as session:
        for i, (name, tier, volume) in enumerate(names):
            market = FuturesMarket(
                source="kalshi",
                external_id=f"KXQZUNITED-8704-{i}",
                name=name,
                status="open",
                market_tier=tier,
                volume=volume,
                resolution_date=datetime.now(timezone.utc) + timedelta(days=90),
            )
            session.add(market)
            await session.flush()
            session.add(
                FuturesOutcome(
                    market_id=market.id,
                    external_id=f"KXQZUNITED-8704-{i}:yes",
                    name="Yes",
                    current_probability=_SEED_PRICE,
                )
            )
        await session.commit()

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_db_rw] = _override
    app.dependency_overrides[get_optional_user] = lambda: None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def _do(q: str) -> dict:
            resp = await client.get(
                "/api/events/search", params={"q": q, "debug_timing": 1}
            )
            assert resp.status_code == 200, f"{q!r} -> HTTP {resp.status_code}"
            return resp.json()

        yield _do
    app.dependency_overrides.clear()


def _futures_names(payload: dict) -> list[str]:
    return [f.get("name") or f.get("question") for f in payload.get("futures") or []]


async def test_a_collapsed_window_refills_from_rows_already_fetched(
    search_with_a_collapsing_window,
):
    payload = await search_with_a_collapsing_window("qzunited")
    timing = payload.get("debug_timing") or {}
    assert timing.get("futures_outcome_arm") == "skipped", timing
    assert timing.get("futures_refill_source") == "window", timing
    names = _futures_names(payload)
    assert names[0] == "Qzunited Cup Winner?", names
    assert names.count("Qzunited Cup Winner?") == 1, names
    assert len(names) >= 10, f"the refill did not fill the page: {names!r}"


async def test_the_refill_from_the_window_serves_what_the_refill_query_served(
    search_with_a_collapsing_window, monkeypatch,
):
    """Strawman control: force today's query path and compare the served page."""
    from app.routes import events as events_module

    fast = await search_with_a_collapsing_window("qzunited")
    monkeypatch.setattr(events_module, "_futures_refill_in_hand", lambda *_: None)
    slow = await search_with_a_collapsing_window("qzunited")
    assert (slow.get("debug_timing") or {}).get("futures_refill_source") == "query"
    assert _futures_names(fast) == _futures_names(slow)
    assert [f.get("id") for f in fast["futures"]] == [
        f.get("id") for f in slow["futures"]
    ]


# ---------------------------------------------------------------------------
# #8756 — `eagles` shows the Philadelphia Eagles on the teams card
# ---------------------------------------------------------------------------

#: Six college rows that say "Eagles" THREE times across name + aliases — they
#: score 4.5 on `ts_rank_cd`, above Philadelphia's 3.0 (name + one alias).
_EAGLES_REPEATERS = (
    ("American Eagles", ["Eagles", "American", "American University Eagles"]),
    ("Coppin St Eagles", ["Eagles", "Coppin St", "Coppin State Eagles"]),
    ("Morehead St Eagles", ["Morehead State Eagles", "Eagles", "Morehead St"]),
    ("Georgia Southern Eagles", ["Eagles", "GA Southern", "Georgia Southern Eagles"]),
    ("Eastern Washington Eagles", ["Eagles", "E Washington", "Eastern Washington Eagles"]),
    ("Boston College Eagles", ["Eagles", "Boston College", "Boston College Eagles"]),
)
#: Twenty rows tied with Philadelphia at 3.0 whose names sort BEFORE it — so the
#: old `rank, name` window put Philadelphia at row 27 of 25 (production: 26).
_EAGLES_TIES = tuple(
    (f"{school} Eagles", ["Eagles", school])
    for school in (
        "Abilene", "Akron", "Albany", "Alcorn", "Auburn", "Ball", "Baylor",
        "Belmont", "Brown", "Butler", "Campbell", "Canisius", "Cornell",
        "Dayton", "Drake", "Elon", "Furman", "Hofstra", "Idaho", "Lamar",
    )
)


@pytest.fixture
async def search_with_many_eagles(seeded_db, search):
    """`?q=eagles` on production 2026-09-26, reduced to its shape (#8756)."""
    from sqlalchemy import select

    from app.models.models import Sport, Team

    _engine, maker = seeded_db
    async with maker() as session:
        # Both sports are in the base seed.
        sports = {
            s.key: s
            for s in (
                await session.execute(
                    select(Sport).where(
                        Sport.key.in_(("americanfootball_nfl", "basketball_ncaab"))
                    )
                )
            ).scalars()
        }
        nfl, ncaab = sports["americanfootball_nfl"], sports["basketball_ncaab"]
        session.add(
            Team(
                sport_id=nfl.id, name="Philadelphia Eagles",
                abbreviation="PHI", alternate_names=["Eagles"],
            )
        )
        for name, aliases in _EAGLES_REPEATERS + _EAGLES_TIES:
            session.add(Team(sport_id=ncaab.id, name=name, alternate_names=aliases))
        await session.commit()
    return search


def _team_names(payload: dict) -> list[str]:
    return [t.get("name") for t in payload.get("teams") or []]


async def test_eagles_leads_the_teams_card_with_the_philadelphia_eagles(
    search_with_many_eagles,
):
    teams = _team_names(await search_with_many_eagles("eagles"))
    assert teams[0] == "Philadelphia Eagles", teams
    assert len(teams) == 5, teams


async def test_without_the_marquee_tiebreak_philadelphia_is_never_fetched(
    search_with_many_eagles, monkeypatch,
):
    """Strawman: the old `rank, name` window. Philadelphia sorts past row 25, so
    no ranking below can reach it — the fixture reproduces the defect."""
    from sqlalchemy import literal

    from app.routes import events as events_module

    monkeypatch.setattr(events_module, "_team_marquee_order", lambda: literal(0))
    teams = _team_names(await search_with_many_eagles("eagles"))
    assert "Philadelphia Eagles" not in teams, teams


async def test_a_query_naming_a_college_keeps_the_college_first(
    search_with_many_eagles,
):
    """Control: the scorer still ranks text first — `american eagles` is not
    handed to the NFL club because it is marquee."""
    teams = _team_names(await search_with_many_eagles("american eagles"))
    assert teams[0] == "American Eagles", teams
