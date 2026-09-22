"""Build the gold-query Search probe registry from Alex's approved gold set.

Queue 313. The gold set (`.claude/handoff/gold_queries_draft.md`, approved-with-
edits by Alex 2026-07-22) is 74 raw / **71 unique** queries: a COVERAGE half of
aspirational drafts and a REAL half of Alex's own logged searches. This module
turns the decidable ones into `search_entity` probes that
`scripts/evals/search_gold_eval.py` can score, and emits
`scripts/evals/search_gold_probes.json`.

WHY A GENERATOR AND NOT 44 HAND-WRITTEN JSON BLOCKS
---------------------------------------------------
Each probe needs a full `evidence{}` block whose `fixture_hash` must be a real
sha256 of the canonical presentation. Hand-authoring that is unreproducible and
one typo away from a silently-wrong hash. Here the convention is executable:

    hash_scope = "presentation/v1"
    fixture_hash = sha256(json.dumps(presentation, sort_keys, separators=(",",":")))

which is the same convention the committed `search_entity_probes.json` uses, and
which `validate_registry` itself re-checks (EVIDENCE_HASH_MISMATCH). The hash is
therefore machine-enforced rather than merely documented.

THE EXPECTED-ENTITY RULE (the integrity crux of this whole file)
----------------------------------------------------------------
`expected_entity_id` is **what the right answer is**, decided per query, and only
then matched to the identifier the product uses for that thing. It is NOT "what
production returned today" — that would make the baseline 100% by construction
and measure nothing.

Concretely, three rules were applied and each is visible in the table below:

* Where the referent is unambiguous and the product HAS the entity, the id is
  adopted even when Search ranks it below rank 1 (`british open` expects The Open
  Championship concept, which currently ranks 2nd behind a football club called
  "Brito"). Those probes are *supposed* to fail today.
* Where two answers are both genuinely acceptable, the extra ones go in
  `allowed_entity_ids` — `oracle.answer.allowed_entity_ids`, per P3, NOT `xfail`.
  `xfail` is reserved for known-broken-and-unambiguous, because the scorer exits
  1 on `xpass`, so an `xfail` on an ambiguity would turn "Search improved" into a
  red build.
* Where naming the right answer would require **inventing** an id for an entity
  the product does not have (there is no person surface; no MLB hub; Duke has no
  team slug), the query is NOT migrated. It is listed in `MC_CANDIDATES` as a
  question for Alex. Inventing an id to satisfy the validator is the one failure
  mode that would quietly corrupt the baseline (P8).

Run:  python scripts/evals/build_search_gold_registry.py --out scripts/evals/search_gold_probes.json
Check: python scripts/evals/build_search_gold_registry.py --check
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .probe_registry import SCHEMA_VERSION, fixture_sha256, validate_registry
except ImportError:  # Direct script use.
    from probe_registry import SCHEMA_VERSION, fixture_sha256, validate_registry

DEFAULT_OUT = Path(__file__).resolve().parent / "search_gold_probes.json"

GOLD_SET_SOURCE = ".claude/handoff/gold_queries_draft.md (gold query set v1, Alex approved-with-edits 2026-07-22)"
CAPTURED_AT = "2026-08-11T00:00:00Z"
EVIDENCE_SURFACE = "GET /api/events/typeahead on api.bainluck.com"

# Probes whose query did NOT come from Alex's gold draft, but from a MEASURED
# production defect. query -> (evidence source, issue).
#
# LAT-P033: these are tracked explicitly rather than just appended, for two
# reasons. First, PROVENANCE — stamping the gold-draft source onto a row Alex
# never wrote would be a lie in the one field whose whole job is saying where the
# expectation came from. Second, ACCOUNTING — the
# `migrated + deferred == GOLD_SET_UNIQUE_QUERIES` invariant is a statement about
# the DRAFT ("no query Alex approved was silently dropped"), so it must keep
# measuring the draft. Bumping the 71 to absorb a defect-derived probe would
# quietly redefine that constant as "however many rows exist", which is exactly
# the check the invariant is there to make impossible.
NON_DRAFT_SOURCES: dict[str, tuple[str, str]] = {
    "fed": (
        "GitHub #1732 — measured on production by LAT-P032, 2026-08-11 (v3770 cd84f690)",
        "#1732",
    ),
    "ai": (
        "GitHub #1758 — the revert of LAT-P035 (e22576db); measured on production "
        "by LAT-P037, 2026-08-11 (v3777 e22576db)",
        "#1758",
    ),
}

# Entity kind -> (surface, item_type). Mirrors search_results_producer.TYPE_MAP.
KIND_SHAPE = {
    "team": ("team", "team"),
    "concept": ("concept", "concept"),
    "market": ("market", "futures"),
    "hub": ("hub", "hub"),
    # `event` joined the shapes with the MC2 class (#1867): the MC1B LIMIT probe
    # `red so` is answered by a TEAM, but its rivals are games, and an expected
    # id the producer can mint (`event:<event_id>`, TYPE_MAP) must have a shape
    # here or a future event-answered probe would read as an unmapped kind.
    "event": ("event", "event"),
}

# (query, half, query_class, group_key, expected_entity_id, allowed_entity_ids,
#  known_failure_status, note)
#
# query_class vocabulary: the COVERAGE half keeps the draft's own family headings;
# the REAL half uses REAL_CLASSES from search_gold_eval.py (P7 — reuse, do not
# invent). Both are recorded verbatim so the two halves stay distinguishable (P10).
GOLD_ROWS: list[tuple[str, str, str, str, str, list[str], str, str]] = [
    # ---- coverage: teams -------------------------------------------------
    ("red sox", "coverage", "teams", "team:boston-red-sox", "team:boston-red-sox-mlb",
     ["team:boston-red-sox"], "pass",
     "LAT-P035 adjudication (#1754): `teams` holds TWO rows for this one club — id 853 "
     "`boston-red-sox` (sport baseball_mlb_preseason) and id 10709 `boston-red-sox-mlb` "
     "(baseball_mlb), with IDENTICAL name, abbreviation, espn_id and alternate_names "
     "(verified in production 2026-08-11). The response can only carry one: search_events "
     "dedupes the teams bucket by `row.name`, so whichever row sorts first wins and the other "
     "is dropped silently. LAT-P034 saw the winner ALTERNATE between runs, which made this "
     "probe — and therefore the lane's headline recall number — flap by +/-1 with no change "
     "to Search. Both ids denote the same real club, so per P3 this is an AMBIGUITY and is "
     "recorded with an alternative rather than left to a coin flip. This adjudicates the "
     "MEASUREMENT only; the duplicate rows remain a real defect and stay open as #1754."),
    ("pats", "coverage", "teams", "team:new-england-patriots", "team:new-england-patriots", [], "pass",
     "nickname for the same club as 'patriots' — shares its group key"),
    ("patriots", "coverage", "teams", "team:new-england-patriots", "team:new-england-patriots", [], "pass",
     "currently ranks California Baptist first; the NE Patriots team row is absent"),
    ("celtics", "coverage", "teams", "team:boston-celtics", "team:boston-celtics", [], "pass",
     "typeahead returns this team WITHOUT team_slug; /search resolves it to boston-celtics"),
    ("bruins", "coverage", "teams", "team:boston-bruins", "team:boston-bruins", [], "pass",
     "currently ranks Belmont Bruins first"),
    ("revs", "coverage", "teams", "team:new-england-revolution", "team:new-england-revolution", [], "pass",
     "sole suggestion returned"),
    ("yankees", "coverage", "teams", "team:new-york-yankees-mlb", "team:new-york-yankees-mlb", [], "pass",
     "canonical slug confirmed via /search"),
    # ---- coverage: events ------------------------------------------------
    ("the open", "coverage", "events", "competition:the-open-championship",
     "concept:event:golf:the-open-championship", [], "pass", "golf major concept hub"),
    ("british open", "coverage", "events", "competition:the-open-championship",
     "concept:event:golf:the-open-championship", [], "pass",
     "alias of the same competition; currently ranks a football club 'Brito' first"),
    ("world cup", "coverage", "events", "competition:fifa-world-cup-2026",
     "concept:event:soccer:world-cup-2026", [], "pass", "concept hub exists and ranks first"),
    ("super bowl", "coverage", "events", "competition:nfl-super-bowl", "market:86832", [], "pass",
     "no Super Bowl concept hub exists; the NFL Super Bowl Winner market is the best true answer"),
    ("march madness", "coverage", "events", "competition:ncaa-mens-basketball", "market:3",
     ["market:9459614"], "pass",
     "returns ZERO suggestions today; either college-basketball championship market is acceptable"),
    ("masters", "coverage", "events", "competition:the-masters",
     "concept:event:golf:the-masters", [], "pass", "golf major concept hub"),
    ("world series", "coverage", "events", "competition:mlb-world-series", "market:114584", [], "pass",
     "no World Series concept hub; currently ranks The Emmys first"),
    ("nba finals", "coverage", "events", "competition:nba-championship", "market:350", [], "pass",
     "no NBA Finals concept hub; currently ranks The Emmys first"),
    # ---- coverage: politics/econ ----------------------------------------
    ("election", "coverage", "politics_econ", "politics:us-elections", "market:112897", [], "pass",
     "the draft annotates politics/econ as 'category/market', so the market is the expected kind; "
     "the 2026 Midterms CONCEPT is an equally acceptable answer that the scorer cannot express "
     "(a cross-kind alternative always trips its single expected_item_type)"),
    ("president", "coverage", "politics_econ", "politics:us-elections", "market:112897", [], "pass",
     "currently ranks a baseball game (Uni-President Lions) first; the midterms concept is a "
     "cross-kind alternative the scorer cannot hold, so it is noted here rather than recorded"),
    ("rate cut", "coverage", "politics_econ", "economics:fed-rate-cuts", "market:113032",
     ["market:109534"], "pass", "two equivalent rate-cut-count markets"),
    ("fed", "coverage", "politics_econ", "economics:federal-reserve", "market:2656292",
     [], "xfail",
     "LAT-P033/#1732 gate. Measured on production 2026-08-11 (v3770 cd84f690): `fed` returns "
     "EIGHT futures, FOUR of them substring collisions inside proper nouns - 2026 Nobel Physics "
     "winner, ATP 1000 Montreal, Titled Tuesday and Grand Chess Tour (both Vladimir Fedoseev) - "
     "while 'Who will be confirmed as Fed Chair?' (58.9M volume, the expected id here) and 'How "
     "many Fed rate cuts in 2026?' (44.5M) do not appear AT ALL. Deliberately pinned to a market "
     "BELOW today's cut so that it CAN fail: pinning it to 'Will Trump end the Federal Reserve?' "
     "(live at #2) would have gated nothing. Single id with no alternatives, per this registry's "
     "own rule that an xfail carrying alternatives is an ambiguity wearing the wrong marker - the "
     "two rival Fed markets are therefore named here in prose, not encoded as allowed ids. xfail "
     "until LAT-P033 deploys; NOTE `--mode bucket_recall` does not consult known_failure_status "
     "(only the top1 mode does), so until then it reads as a straight fail and it is the "
     "DENOMINATOR that moved, not the numerator."),
    ("recession", "coverage", "politics_econ", "economics:recession", "market:108622",
     ["market:113012"], "pass", "two equivalent US recession markets"),
    ("inflation", "coverage", "politics_econ", "economics:inflation", "market:113386",
     ["market:2952604"], "pass", "headline inflation market; dated CPI prints acceptable"),
    # ---- coverage: entertainment ----------------------------------------
    ("oscars", "coverage", "entertainment", "ceremony:oscars",
     "concept:event:awards:oscars", [], "pass", "ceremony concept hub"),
    ("grammys", "coverage", "entertainment", "ceremony:grammys",
     "concept:event:awards:grammys", [], "pass", "ceremony concept hub"),
    ("best picture", "coverage", "entertainment", "ceremony:oscars", "market:6173044",
     ["market:57313556"], "pass",
     "a specific award was named, so the Best Picture market is the precise answer; today the "
     "generic Oscars ceremony concept ranks first, which is a near-miss rather than nonsense"),
    ("stranger things", "coverage", "entertainment", "series:stranger-things", "market:114237",
     ["market:109324"], "pass", "currently ranks The Emmys first"),
    # ---- coverage: weather/misc -----------------------------------------
    ("hurricane", "coverage", "weather_misc", "weather:hurricanes", "market:114086",
     ["market:56775660"], "pass",
     "the draft annotates weather/misc as 'weather page/markets', so a hurricane market is the "
     "expected kind; the NHL club is a legitimate rival reading but is a different kind, which "
     "the scorer cannot hold alongside a market"),
    # ---- coverage: tech --------------------------------------------------
    ("openai", "coverage", "tech", "company:openai", "market:113184",
     ["market:113004", "market:115379"], "pass", "any OpenAI IPO market is acceptable"),
    ("iphone", "coverage", "tech", "company:apple", "market:109349",
     ["market:113785", "market:113776"], "pass", "any iPhone-release market is acceptable"),
    ("spacex", "coverage", "tech", "company:spacex", "market:113758",
     ["market:108556", "market:113792"], "pass", "any SpaceX IPO market is acceptable"),
    ("IPO", "coverage", "tech", "finance:ipos", "market:113319", ["market:113758"], "pass",
     "currently ranks a Greek football club (Asteras Tripolis) first"),
    ("apple", "coverage", "tech", "company:apple", "market:109349",
     ["market:113419", "market:113774"], "pass", "any Apple company market is acceptable"),
    ("ai", "coverage", "tech", "tech:ai-models", "market:109596",
     ["market:113435"], "pass",
     "LAT-P037/#1758: THE GOLD SET'S FIRST SUB-3-CHARACTER PROBE, and it is here because its "
     "absence is what let LAT-P035 ship and be reverted. That queue measured 49 pairs, named its "
     "two losses honestly, and was green — while emptying the futures NAME arm at two characters, "
     "because not one of the 49 probes was shorter than three characters. A blind spot in a gold "
     "set does not announce itself; it reports a good number. "
     "WHAT THIS PROBE CAN AND CANNOT CATCH, stated so nobody over-reads it. It catches the "
     "SHAPE of that failure — if the 2-char name arm empties again, `ai`'s futures bucket goes "
     "empty and both this probe and the producer's empty-expected-bucket check fire. It would "
     "NOT have caught LAT-P035 itself: `to_tsvector('Best AI at the end of 2026?')` contains the "
     "lexeme `ai`, so the word test passed this market and only shrank the bucket around it. The "
     "probe that WOULD have caught it is `re` -> \"US Recession in 2026?\", and it is deliberately "
     "NOT added: measured on production 2026-08-11 (v3777), `re` returns 10 futures led by "
     "Presidential Election Winner 2028 and nine Ukraine 're-enter' markets, and 108622 is not "
     "among them. `re` has no correct referent — it is a prefix of a word the user has not "
     "finished typing — so encoding one would be inventing an expectation to satisfy a gate, "
     "which is the single failure mode this registry's own rules forbid. The deterministic guard "
     "for that boundary is a compiled-SQL oracle instead "
     "(test_search_latency_contract.TestTheWordTestDoesNotVoteOnAFragment), which needs no "
     "Postgres and therefore runs where the lane actually works. "
     "Referent: 'Best AI at the end of 2026?' (109596), rank 1 on production; 'AI bubble burst "
     "by...?' (113435) is an equally acceptable read of a bare `ai`."),
    # ---- coverage: family-specific --------------------------------------
    ("wwe", "coverage", "family_specific", "promotion:wwe", "market:12434043",
     ["market:56775492"], "pass", "currently ranks The Emmys first"),
    ("dancing with the stars", "coverage", "family_specific", "series:dancing-with-the-stars",
     "market:12764689", ["market:186450", "market:12764701"], "pass", "any DWTS S35 market is acceptable"),
    ("Survivor", "coverage", "family_specific", "series:survivor", "market:109525", [], "pass",
     "the season-50 winner market ranks first"),
    # ---- real half (Alex's logged queries) -------------------------------
    ("Golf", "real", "category_as_query", "hub:golf", "hub:golf", [], "pass",
     "one of only five hubs that exist (boxing, esports, golf, mma, tennis)"),
    ("tush push", "real", "concept_rule", "rule:tush-push", "market:113466", [], "pass",
     "the cultural-rule market resolves exactly"),
    ("fable", "real", "self_reference", "product:fable", "market:52755874",
     ["market:55268501"], "pass", "either Fable-access market is acceptable"),
    ("us open", "real", "ambiguity", "competition:us-open",
     "concept:event:tennis:2026-women-s-us-open-winner-tennis",
     ["concept:event:tennis:2026-men-s-us-open-winner-tennis"], "pass",
     "P3's ambiguity case handled with allowed_alternatives, NOT xfail: the men's and "
     "women's US Open concepts are both correct readings of a bare 'us open'"),
    ("Taylor Swift Madison", "real", "qualified_entity", "person:taylor-swift", "market:33283003", [], "pass",
     "qualifier narrows correctly to the Madison Square Garden market"),
    ("Where will Taylor Swift and Travis Kelce's Wedding occur?", "real", "full_question",
     "person:taylor-swift", "market:108271", [], "xfail",
     "KNOWN BROKEN, entity unambiguous: 57 chars exceeds typeahead's max_length=50 so the call "
     "422s, and /search returns an empty 200. The market exists and is reachable from 'taylor swift'."),
    ("2026 NBA Champion", "real", "real_history", "competition:nba-championship", "market:350", [], "pass",
     "ranks first"),
    ("The Open Championship Winner", "real", "real_history", "competition:the-open-championship",
     "concept:event:golf:the-open-championship", [], "pass", "ranks first"),
    ("2026 FIFA World Cup", "real", "real_history", "competition:fifa-world-cup-2026",
     "concept:event:soccer:world-cup-2026", [], "pass", "ranks first"),
    ("NBA: LeBron James Next Team", "real", "real_history", "person:lebron-james", "market:10054167", [], "pass",
     "exact market-title query resolves to its market"),
    ("Taylor Swift pregnant by...?", "real", "real_history", "person:taylor-swift", "market:112868",
     ["market:112976"], "pass", "exact market-title query resolves to its market"),
]

# Queries deliberately NOT migrated, because naming the right answer would mean
# inventing an entity id. Each is a real question for Alex, not a TODO.
MC_CANDIDATES: list[tuple[list[str], str]] = [
    (["taylor swift", "travis kelce", "john cena", "caitlin clark", "ohtani", "drake maye",
      "scheffler", "pogacar", "messi", "lebron"],
     "THERE IS NO PERSON SURFACE. All ten person queries resolve to assorted markets "
     "(and 'scheffler', 'messi' and 'lebron' currently rank the 2026 Midterm Elections concept "
     "first). What should a bare person query return — a person page we do not have, the "
     "highest-volume market naming them, or their team? Until that is decided, any "
     "expected_entity_id here would be invented."),
    (["MLB"],
     "Only five hubs exist (boxing, esports, golf, mma, tennis), so 'Golf' lands on a hub and "
     "'MLB' has nothing to land on — it returns individual games. The real half's "
     "CATEGORY-AS-QUERY lesson says bare league names must hit a league surface top-1. "
     "Should league hubs exist for the ball sports, or should 'MLB' resolve to the league page?"),
    (["duke"],
     "Duke Blue Devils has team_slug=None in /search (and is filed under americanfootball_ncaaf). "
     "It is unnavigable, so there is no id to expect. Is a slug owed for NCAA teams?"),
    (["wimbledon", "tour de france", "stanley cup", "olympics", "ryder cup", "wrestlemania",
      "little league world series", "Royal Rumble", "gymnastics"],
     "No entity of any kind exists for these competitions — 'wrestlemania' and 'little league "
     "world series' return ZERO suggestions; the others return same-named football clubs "
     "(Accrington Stanley, Royal Antwerp, Gimnastic, AFC Wimbledon) or a country ('France'). "
     "Is this a coverage gap to fill, or are these out of scope?"),
    (["trump"],
     "Ranks the 2026 Midterms concept first, which is not about Trump. Should a political-figure "
     "query return the figure's most-traded market, or the election concept they feature in?"),
    (["box office", "bachelor"],
     "'box office' returns one film's opening-weekend market and a US-ranking market with no "
     "obvious canonical answer; 'bachelor' returns Bachelorette markets — a different show. "
     "Which is the intended answer?"),
    (["heat wave", "snow boston"],
     "Both are weather-intent queries that return sports teams (Miami Heat; Boston Red Sox). "
     "No heat-wave or Boston-snow market surfaced at all. Do these markets exist to be found?"),
    (["nba finals games"],
     "Returns zero suggestions. Ambiguous between the NBA championship market and a "
     "'number of games in the series' market. Which did Alex mean?"),
]


# ---------------------------------------------------------------------------
# THE OUTCOME-EVIDENCE PROBE CLASS (ruling 056, #1861) — LAT-P052
# ---------------------------------------------------------------------------
#
# WHY THIS CLASS EXISTS. `-44` (#1843) deployed alone as v3807, carried a real
# ranking change, and moved ZERO of the 46 gold probes — with byte-identical
# per-probe dispositions against v3806. Ruling 056 forbids reading that as
# "ineffective": it says the INSTRUMENT could not see it, and it requires the
# gap be closed with a probe class rather than a caveat.
#
# #1843 widened the ranking evidence a futures market carries from its THREE
# DISPLAY outcomes to EVERY outcome it owns. So the class this set was missing
# is: **a query whose correct answer is a market that owns it on an outcome
# OUTSIDE the top-3 display cut.** Not one of the 46 probes had that shape.
#
# ---- SPLIT: `canary`, and that is a measurement decision, not a filing one --
#
# These probes are deliberately NOT in the `test` split. The entire §5 ledger of
# `docs/search-scoring-spec.md` is written against a 46-probe registry graded
# 44-wide; adding rows to `test` would silently move the denominator and make
# every prior read incomparable — a measurement defect committed in the name of
# fixing one. `--split canary` grades this class; `--split test` is untouched
# and still reads 46/44.
#
# ---- WHAT THESE PROBES CAN AND CANNOT GRADE (measured, not assumed) ---------
#
# LAT-P052 ran the REAL scorer (`app.utils.search_match_class.rank`) over REAL
# production evidence — 7 Oscar markets, 155 outcomes pulled from the production
# DB — under two regimes: `outcomes` = every owned outcome (post-#1843) versus
# `outcomes` = the top 3 only (pre-#1843). The answer is NOT uniform across the
# class, and the split is the real content of #1861:
#
#   * **4 of 5 specimens: the class moves, top-1 does not.** Every candidate owns
#     the queried outcome BELOW its own display cut, so all of them go MC5 -> MC4
#     together. `entity_top_1` reads relative order only, so a uniform lift is
#     invisible to it. **This is why 46 probes returned byte-identical
#     dispositions on v3807.**
#   * **`club kid`: top-1 MOVES.** "Oscars 2027: Best Original Screenplay Winner"
#     displays "Club Kid" at outcome rank 3 of 17 — INSIDE its cut — so it
#     already scored MC4 and did not move while the others did. An unequal lift
#     changes order. This specimen was found by building the discrimination test,
#     not by predicting it, and it is the existence proof that an
#     outcome-evidence change CAN be graded top-1.
#
# The general rule that falls out: top-1 moves only when the pre-change winner
# is a market that did NOT gain the class — one that already had it, or one that
# never owns the outcome at all (a substring accident, which is #1843's own
# stated specimen: "a market that owns the answer was losing to unrelated
# substring accidents").
#
# So these probes are (a) a REGRESSION GUARD on the outcome-evidence path — re-cap
# `_search_owned_outcome_names` and they drop MC4 -> MC5 — (b) the only probes in
# the set that turn on a non-top-3 outcome at all, and (c) in ONE case, a genuine
# top-1 discriminator. `tests/test_search_outcome_evidence_discrimination.py`
# asserts all three, INCLUDING the limit, so no future reader has to rediscover
# which is which.
#
# (query, expected_entity_id, allowed_entity_ids, outcome_rank, note)
OUTCOME_EVIDENCE_ROWS: list[tuple[str, str, list[str], int, str]] = [
    ("werwulf", "market:6173044", ["market:5165726", "market:57313556"], 17,
     "'Werwulf' is a Best Picture nominee sitting at outcome rank 17 of 38 — far outside the "
     "three rows the dropdown displays. The market's NAME ('Oscar winner: Best Picture') contains "
     "no query token, so the only evidence that can rank it is the owned outcome. Verified on "
     "production v3808 (2026-08-14): market 6173044 returns at rank 1."),
    ("elsinore", "market:6173044", ["market:5165726", "market:57313556"], 35,
     "Outcome rank 35 of 38 — the deepest specimen in the class, and the strongest demonstration "
     "that the evidence is genuinely unbounded rather than merely wider. Verified rank 1 on "
     "production v3808 (2026-08-14)."),
    ("behemoth", "market:6173044", ["market:5165726", "market:57313556"], 9,
     "Outcome rank 9 of 38. Verified rank 1 on production v3808 (2026-08-14)."),
    ("minotaur", "market:6173044", ["market:5165726", "market:57313556"], 31,
     "Outcome rank 31 of 38. Verified rank 1 on production v3808 (2026-08-14)."),
    ("club kid", "market:6173044", ["market:5165726", "market:57313556", "market:58492236"], 37,
     "THE DISCRIMINATING SPECIMEN, and the most valuable probe in this class. Outcome rank 37 of "
     "38 here, but rank 3 of 17 — INSIDE the display cut — in 'Oscars 2027: Best Original "
     "Screenplay Winner' (58492236). That rival therefore already scored MC4 before #1843 and did "
     "not move while every other candidate went MC5 -> MC4, so the lift is UNEQUAL and top-1 "
     "genuinely changes. It is the existence proof that an outcome-evidence change can be graded "
     "top-1 at all; the other four specimens cannot show that, because their lift is uniform. "
     "58492236 is recorded as an ALLOWED answer rather than a rival precisely because it owns the "
     "film too. Also the only MULTI-TOKEN query in the class, which exercises MC4's multi-token "
     "PATH — but NOT its conjunction: every candidate owning 'kid' here also owns 'club', so "
     "flipping MC4's `all()` to `any()` survives this specimen untouched. That was found by the "
     "mutation gate (M5) and the conjunction is now asserted separately, on a synthetic partial "
     "owner, in test_mc4_requires_every_query_token_not_merely_one. Recorded because the earlier "
     "version of this note claimed the specimen covered it. Verified rank 1 on production v3808 "
     "(2026-08-14)."),
]

# The films above are nominees in a live awards market, so this class has a
# SHELF LIFE the coverage half does not: when the 2027 Oscars settle, these
# markets resolve and the probes go stale. That is recorded here rather than
# discovered as a mystery failure — `valid_at` carries the capture date, and the
# class should be re-specimened against a live market when it next reads red.
OUTCOME_EVIDENCE_CAPTURED_AT = "2026-08-14T00:00:00Z"


# ---------------------------------------------------------------------------
# THE DIACRITIC-FOLDING PROBE CLASS (#1881) — LAT-P058
# ---------------------------------------------------------------------------
#
# WHY THIS CLASS EXISTS. #1881 is filed as a Search defect and had no probe, so
# nothing in the set could grade a fix for it — #1861's lesson, applied before
# the fix rather than after it. The Fable directive for LAT-P058 asked for gold
# probes on both of the issue's named specimens *so the gate can grade it*.
#
# ---- WHAT WAS MEASURED FIRST, AND WHAT IT CHANGED --------------------------
#
# #1881 reads as a RANKING bug. It is not one. `search_match_class.tokens()` has
# folded accents since ruling 041, so both spellings of both specimens already
# reach MC1 — the best non-exact class — against the entity the issue says is
# missing (asserted in `test_p11b_the_scorer_was_never_the_1881_defect`):
#
#     tokens('köln') == tokens('koln') == ('koln',)
#     match_class('vuelta a españa', Evidence('Vuelta a Espana 2026: Winner')) == MC1
#
# The defect is upstream, in RETRIEVAL. Production v3820, 2026-08-14 17:5x PDT:
#
#     vuelta a espana  -> 1 suggestion   market 58675941 'Vuelta a Espana 2026: Winner'
#     vuelta a españa  -> 0 suggestions  NOTHING AT ALL
#     koln             -> 1 suggestion   team fortuna-koln-ii   (the only ASCII-named club)
#     köln             -> 7 suggestions  all Köln-named, none of them the ASCII row
#
# A scorer cannot rank a candidate the SQL never handed it. `unaccent` is not
# installed; `pg_trgm` is doing the matching and trigrams over `ö` and `o` are
# simply different trigrams. So these probes grade an INDEX change, not a
# scorer change — and the one scorer-side fold this window did ship
# (`fragment_credit`, which was still comparing unfolded text at MC5) cannot
# move them, which is exactly why they belong here as `xfail` rather than as a
# claim that anything is fixed.
#
# ---- THE TWO DIRECTIONS, ONE PROBE EACH ------------------------------------
#
# The defect is not symmetric and neither is its fix, so the class is built to
# tell a half-fix from a whole one:
#
#   * `vuelta a españa` — ACCENTED query, ASCII-named entity. A query-side fold
#     alone (strip diacritics before matching) fixes this direction. The issue
#     calls that the "cheapest interim".
#   * `koln` — ASCII query, ACCENTED-named entity. A query-side fold does
#     NOTHING here; only an `unaccent` expression index over the COLUMN reaches
#     it.
#
# If a future window reports #1881 fixed and only the vuelta probe has flipped,
# half the defect is still shipping. That distinction is the point of the class.
#
# ---- SPLIT: `canary`, per ruling 060 ---------------------------------------
#
# Not negotiable and not a filing convenience: the §5 ledger of
# `docs/search-scoring-spec.md` is written against a 46-probe `test` cohort
# graded 44-wide, and growing it in place voids every read ever taken against
# it. Same reasoning as the outcome-evidence class above.
#
# ---- SPECIMEN DURABILITY ---------------------------------------------------
#
# This program has lost three specimens to expiry (`tour de france` died between
# `-45` shipping and its deploy check). So the anchors here were chosen for
# lifespan, and the choice is recorded rather than left implicit:
#
#   * The Köln probe anchors on TEAM rows. Teams do not resolve; `1. FC Köln`
#     will exist for as long as the club does.
#   * The Vuelta probe anchors on a market, which DOES expire (the 2026 Vuelta
#     settles around September 2026). It is used anyway because it is the only
#     specimen where the ASCII twin passes and the accented twin returns
#     literally nothing — the cleanest possible isolation of the fold. When it
#     reads red for expiry rather than for folding, re-specimen it against the
#     next edition; `valid_at` carries the capture date.
#
# (query, expected_entity_id, allowed_entity_ids, direction, status, note)
DIACRITIC_ROWS: list[tuple[str, str, list[str], str, str, str]] = [
    ("vuelta a espana", "market:58675941", [], "control", "pass",
     "THE CONTROL, and the reason this pair is decisive. The ASCII spelling returns this market "
     "at rank 1 on production v3820 (2026-08-14). Its accented twin below differs by exactly one "
     "character and returns nothing, so no explanation other than the fold survives — not "
     "coverage, not ranking, not the entity's existence."),
    ("vuelta a españa", "market:58675941", [], "accented_query_ascii_entity", "xfail",
     "THE DEFECT, accented-query direction. ZERO suggestions on production v3820 — not a wrong "
     "answer, no answer. The market's own name is ASCII ('Vuelta a Espana 2026: Winner') and the "
     "scorer already scores this query MC1 against it, so retrieval never offered it. This is the "
     "direction a query-side fold alone would fix."),
    ("koln", "team:1-fc-kln-bundesliga",
     ["team:1-fc-kln", "team:fc-viktoria-kln-1904"],
     "ascii_query_accented_entity", "xfail",
     "THE DEFECT, ASCII-query direction — the half a query-side fold CANNOT reach. On production "
     "v3820 `koln` returns exactly one suggestion, `team:fortuna-koln-ii`, which is the only club "
     "in the corpus whose stored name happens to be spelled without the umlaut; every real Köln "
     "entity is invisible to the ASCII spelling. Anyone typing on a keyboard without an umlaut "
     "key — or reading a URL — is looking at a search that cannot find a Bundesliga club. "
     "`1. FC Köln` is the expected referent; the duplicate row `team:1-fc-kln` and the other "
     "senior Köln club are allowed, because which of them ranks first is a ranking question and "
     "this probe grades retrieval. Closing it needs an `unaccent` expression index over the "
     "column, with the sequencing caveat #1881 records: unaccented duplicates roughly double "
     "579 MB of trigram index against a 1 GiB shared_buffers."),
]

DIACRITIC_CAPTURED_AT = "2026-08-14T00:00:00Z"


# ---------------------------------------------------------------------------
# THE MC3 (PARTIAL-TOKEN) AND MC2 (LAST-TOKEN PREFIX) CLASSES (#1867) — LAT-P061
# ---------------------------------------------------------------------------
#
# WHY THESE CLASSES EXIST. §7 of `docs/search-scoring-spec.md` recorded two
# blind spots and a table cell reading "NO" is not a queue, so #1867 made them
# one. MC3 was the larger: `PARTIAL_MIN_COVERAGE` could be retuned in EITHER
# direction and every number in §5 would be unchanged — a live ranking knob
# whose whole range was invisible to the instrument. MC2 was graded only as a
# side effect of probes aimed elsewhere, which catches a catastrophic break and
# cannot grade a change. Under ruling 056 a null read on either class indicts
# the INSTRUMENT, so neither could be tuned and read.
#
# ---- HOW THE SPECIMENS WERE FOUND, AND THE TWO INSTRUMENT FACTS IT COST -----
#
# Found, not predicted (#1861's `club kid` rule). Method: fetch the typeahead's
# own `debug_evidence` echo per query, rebuild `Evidence` through the module's
# OWN `evidence_from_wire`, and replay the REAL scorer, sweeping the knob across
# 0.05..1.00 in twenty steps. Two facts fell out that a predicted set would have
# encoded wrongly, and both are the reason the first candidate set was discarded:
#
#   1. **The route does not score the query. It scores `_q_identity`** —
#      `parse_intent(q).subject`. Replaying the RAW query reproduces a DIFFERENT
#      computation from production's. Measured: `who wins the us open` replayed
#      raw looks like a beautiful two-sided discriminator (the Honey Deuce
#      novelty market taking rank 1 off the tournament at the live default). On
#      the SUBJECT `who us open` both candidates sit at coverage 0.667, the knob
#      moves nothing, and production's own served order agrees with the subject
#      replay. That probe would have asserted a defect production does not have.
#      Every row below therefore carries the SUBJECT beside the query, and every
#      one was accepted only after the subject replay reproduced production's
#      served rank 1 exactly.
#   2. **`new ya` is MC2, not MC1B** — measured against the real Yankees
#      evidence, and live: 6 of 7 candidates score MC2. The MC1B boundary is
#      real but it is narrower than it looks, because `_query_prefixes_an_owned_name`
#      folds the whole string: `newya` is not a prefix of `newyorkyankees`. It is
#      still the wrong MC2 probe, for a reason that has nothing to do with its
#      class: muting MC2 does not move its top-1 (the whole set collapses
#      together), so it grades nothing. Recorded because an earlier draft
#      reached the right choice through the wrong reason.
#
# ---- WHAT MOVES TOP-1, STATED AS THE SHAPE A FUTURE PROBE MUST HAVE ---------
#
# A uniform lift is invisible to `entity_top_1` — the lesson #1861 paid for, and
# it applies unchanged here: if every candidate crosses the threshold together,
# the class moves and the ANSWER does not. So an MC3 probe needs the candidate
# set to hold an INVERSION — some candidate with a BETTER `KIND_ORDER` rank at a
# LOWER coverage than a rival — or a pair that ties on kind inside MC3 (ordered
# by `within_tier`) and separates inside MC5 (ordered by `fragment_credit`).
# Measured rarity: of ~45 real reader queries swept from `search_query_logs`,
# two produced a knob-moving top-1.
#
# For MC2 there is no coverage knob — the class fires or it does not — so the
# discrimination test is the class itself: raise `PREFIX_MIN_LEN` above the
# specimen's last token and MC2 cannot fire, which is what a regression in that
# branch looks like. A probe whose top-1 survives that grades nothing.
#
# ---- SPLIT: `canary`, per ruling 060 ---------------------------------------
#
# Same reasoning as the two classes above, and it is the issue's first
# non-negotiable: the §5 ledger is written against 46 probes graded 44-wide.
# `--split test` still reads 46/44 with this class in the file.
#
# ---- SHELF LIFE, CHOSEN AND RECORDED ---------------------------------------
#
# Six probes across THREE real-world groups (Masters / Oscars / Red Sox) so one
# market's resolution cannot take the class with it. The Red Sox MC3 row is the
# short-lived one — an ALCS-2026 market — and it is used anyway because it is
# the only specimen found whose edge sits ABOVE the default at 0.75; when it
# reads red for expiry rather than for tuning, re-specimen it. `valid_at`
# carries the capture date, as the diacritic class does.
#
# (query, subject, expected_entity_id, allowed_entity_ids, edges, note)
#
# `edges` are the measured knob values at which top-1 CHANGES, as
# (below, above) pairs of the sweep steps that bracket the change. An EMPTY
# tuple is a LIMIT row and is load-bearing, not a gap: it records a shape the
# knob provably cannot move, which is the issue's third non-negotiable.
MC3_ROWS: list[tuple[str, str, str, list[str], tuple[tuple[float, float], ...], str]] = [
    ("2027 the masters champion odds", "masters champion odds",
     "market:61056094", ["concept:event:golf:the-masters", "market:4"],
     ((0.30, 0.35), (0.65, 0.70)),
     "THE DISCRIMINATING SPECIMEN, and the only one found that brackets the live default from "
     "BOTH sides — which is what makes the knob gradeable rather than merely observable. On the "
     "subject `masters champion odds` the market owns 2 of 3 tokens (0.667) and the concept `The "
     "Masters` owns 1 (0.333). At the shipped 0.5 the market is MC3, the concept is MC5, and the "
     "market leads — which is what production serves. Tune DOWN past 0.333 and the concept is "
     "admitted to MC3, where `KIND_ORDER` puts event_concept (0) above futures (4), so THE ANSWER "
     "CHANGES to the tournament. Tune UP past 0.667 and the market itself falls to MC5, where the "
     "concept leads on kind again. A retune in either direction moves this probe; that sentence "
     "is exactly what #1867 says nothing in the set could say. Verified on production 2026-09-22: "
     "market 61056094 returns at rank 1, and the subject replay reproduces that rank 1."),
    ("2027 champions league winner odds", "champions league winner odds",
     "market:392",
     ["market:31834253", "market:399", "market:60607783", "market:8641791"],
     ((0.75, 0.80),),
     "THE SECOND MECHANISM, which is why it earns a row rather than duplicating the one above. "
     "There is no kind inversion here at all — all five candidates are futures (4), two at "
     "coverage 0.75 and three at 0.5. Inside MC3 the tie is broken by `within_tier`, so market "
     "392 leads. Tune past 0.75 and the whole cohort drops to MC5, where the key picks up "
     "`fragment_credit` — and the answer becomes `Champions League Winner` (31834253). So an MC3 "
     "change can move top-1 WITHOUT any candidate changing its class RELATIVE to another, purely "
     "by changing which tiebreak is in force. A probe set holding only the row above would read "
     "that whole mechanism as a null. Verified on production 2026-09-22."),
    ("masters winner", "masters winner",
     "market:4", ["concept:event:golf:the-masters", "market:61056094"],
     (),
     "THE LIMIT, and the issue's third non-negotiable: a probe set must encode what it CANNOT "
     "separate. `Masters Tournament Winner` owns every token of this query, so it is MC1 — and "
     "class comes first and is inviolable, so no value of `PARTIAL_MIN_COVERAGE` anywhere in "
     "0.05..1.00 can lift an MC3 or MC5 candidate over it. Swept all twenty steps: top-1 is "
     "market 4 at every one of them. This is the shape most real reader queries have (`masters "
     "winner` is the 2nd most-typed multi-word query in `search_query_logs` at 191 hits), and it "
     "is the measured reason MC3 coverage cannot be had by adding popular queries: the more "
     "exactly the reader names the thing, the less the partial-token knob can reach them. A null "
     "read on THIS probe after an MC3 retune is correct behaviour, not a blind instrument — which "
     "is the distinction ruling 056 exists to let a reader draw. Verified 2026-09-22."),
]

# (query, subject, expected_entity_id, allowed_entity_ids, muted_top1, note)
#
# `muted_top1` is what rank 1 BECOMES when MC2 is prevented from firing
# (`PREFIX_MIN_LEN` raised above the last token). `None` is a LIMIT row: MC2 is
# present in the candidate set and decides nothing.
MC2_ROWS: list[tuple[str, str, str, list[str], str | None, str]] = [
    ("masters champ", "masters champ", "market:61056094",
     ["concept:event:golf:the-masters", "market:4"],
     "concept:event:golf:the-masters",
     "THE DISCRIMINATING SPECIMEN for typeahead's defining behaviour — the user is still typing. "
     "`masters` is a complete token and `champ` is a live prefix of `Champion`, while `masterschamp` "
     "is not a prefix of any whole owned name, so MC1B (checked first) declines and this is "
     "genuinely MC2. Mute the class and the answer changes from `2027 The Masters Champion` to the "
     "`The Masters` concept, because the market drops to MC3 where event_concept outranks futures "
     "on `KIND_ORDER`. That is a reader-visible difference: mid-word, the half-typed query stops "
     "resolving to the market that answers it. Verified on production 2026-09-22: market 61056094 "
     "at rank 1, subject replay agrees."),
    ("oscar pictu", "oscar pictu", "market:6173044",
     ["market:5165726", "market:57313556", "market:27988771", "market:109551",
      "concept:event:awards:oscars"],
     "concept:event:awards:oscars",
     "THE SECOND SPECIMEN, and deliberately a WIDE one: five of six candidates score MC2 here "
     "against one in the row above, so the two together separate 'MC2 decided between rivals' "
     "from 'MC2 admitted a cohort'. Muting the class hands rank 1 to the `The Oscars` concept — "
     "every Best Picture market falls to MC3 at once and loses on kind. LINEAGE NOTE, recorded "
     "rather than left to be discovered: market 6173044 is also the outcome-evidence class's "
     "expected answer (#1861), so these two classes share a real-world group and the 2027 Oscars "
     "settling will age BOTH. That is why the other two MC2 rows anchor elsewhere. Verified on "
     "production 2026-09-22."),
    ("manchester unite", "manchester unite", "market:59164813",
     ["market:61717598", "team:manchester-united", "event:15311086", "market:63014",
      "market:60607626", "market:59693539"],
     None,
     "THE LIMIT, and the specific answer to #1867's Gap 2 — the reason MC2's incidental coverage "
     "is NOT sufficient, stated as a probe instead of an argument. FOUR of the seven candidates "
     "here ARE MC2, so a coverage table counting 'probes in whose candidate set MC2 appears' "
     "would score this query as solid MC2 coverage. It is not: `manchesterunite` IS a prefix of "
     "`manchesterunited`, MC1B is checked before MC2, and the top three rows are all MC1B — so "
     "muting MC2 entirely leaves rank 1 exactly where it was. This is precisely the shape #1867 "
     "means by 'graded only by accident': MC2 present in quantity, MC2 deciding nothing. It is "
     "also the measured reason the two rows above had to be FOUND rather than counted — the "
     "obvious mid-word queries are the ones MC1B has already claimed. Verified 2026-09-22."),
]

MC3_MC2_CAPTURED_AT = "2026-09-22T00:00:00Z"

#: Real-world group per #1867 probe. Written as ONE map over both classes
#: rather than per-row, because the property it encodes is cross-class: four
#: groups over six probes is the durability claim, and a row added to either
#: list without a decision here fails the lookup instead of silently minting a
#: fifth group nobody chose.
#:
#: THESE KEYS WERE CHOSEN AGAINST A GUARD, AND THE GUARD WAS RIGHT. The first
#: draft of this class keyed the Masters rows `concept:the-masters` and two
#: rows `team:boston-red-sox`; `validate_registry` refused it with
#: GROUP_SPLIT_LEAKAGE, because `team:boston-red-sox` is a `test` group and a
#: subject shared across splits is a contaminated read. Two different fixes
#: followed, and the distinction between them is the point:
#:
#:   * The Red Sox MC2 row was DROPPED, not renamed. Its expected answer was
#:     `team:boston-red-sox-mlb` — the identical entity the `test` probe
#:     `red sox` expects. That is one subject in two splits however it is
#:     labelled, and a new key would have been an evasion. `manchester unite`
#:     replaced it: same MC1B-limit shape, a group `test` does not hold.
#:   * The Masters rows KEPT their specimens under a narrower key, because the
#:     referents genuinely differ — `test`'s `masters` probe expects the
#:     tournament CONCEPT, these expect its WINNER MARKETS — and because the
#:     contamination the guard protects against was MEASURED ABSENT rather than
#:     argued away: `masters`, `oscars`, `best picture`, `red sox` and `us open`
#:     were each swept across all twenty values of `PARTIAL_MIN_COVERAGE` on
#:     production evidence and top-1 does not move at any of them. Single-token
#:     and fully-owned queries are MC0/MC1, and class order is inviolable, so
#:     the knob these canary probes grade cannot reach them. If a future MC3
#:     change ever DOES move one of those five, this note is falsified and the
#:     keys must merge — that is the check to run, not a re-reading of this
#:     paragraph.
MC_GROUP_KEYS: dict[str, str] = {
    "2027 the masters champion odds": "market:the-masters-winner",
    "2027 champions league winner odds": "competition:uefa-champions-league",
    "masters winner": "market:the-masters-winner",
    "masters champ": "market:the-masters-winner",
    "oscar pictu": "market:oscars-best-picture",
    "manchester unite": "team:manchester-united",
}


def _slug(query: str) -> str:
    out = "".join(char if char.isalnum() else "-" for char in query.lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:48]


def build_probes() -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    for query, half, query_class, group, expected, allowed, status, note in GOLD_ROWS:
        kind = expected.split(":", 1)[0]
        surface, item_type = KIND_SHAPE[kind]
        presentation = {"query": query}
        non_draft = NON_DRAFT_SOURCES.get(query)
        probes.append({
            "identity": {
                "probe_key": f"search-gold-{_slug(query)}-001",
                "probe_version": 1,
                "schema_version": SCHEMA_VERSION,
                "surface": "search_typeahead",
                "task_type": "search_entity",
                "item_type": item_type,
                "entity_ids": [expected, *allowed],
                "gold_half": half,
                "gold_family": query_class,
            },
            "evidence": {
                "fixture_hash": fixture_sha256(presentation),
                "hash_scope": "presentation/v1",
                "source": non_draft[0] if non_draft else GOLD_SET_SOURCE,
                "provenance": (
                    f"defect-derived probe, not from the gold draft; expected entity resolved "
                    f"against {EVIDENCE_SURFACE}"
                    if non_draft
                    else f"{half} half of the gold set; expected entity resolved against {EVIDENCE_SURFACE}"
                ),
                "captured_at": CAPTURED_AT,
                "valid_at": CAPTURED_AT,
                "license_usage_note": "internal product query set; queries name public figures and public events only",
                "pii_redacted": True,
            },
            "oracle": {
                "oracle_kind": "known_answer",
                "label_schema": "search_entity/v1",
                "label_schema_version": 1,
                "authority": "product judgment of the correct referent, matched to the identifier the product uses for it",
                "evidence": note,
                "adjudication_history": [],
                "answer": {
                    "expected_entity_id": expected,
                    "allowed_entity_ids": list(allowed),
                    "expected_surfaces": [surface],
                    "expected_item_type": item_type,
                    "query_class": query_class,
                },
            },
            "lifecycle": {
                "state": "active",
                "owner": "search-evals",
                "difficulty": "baseline",
                "failure_family": "search-entity-top-1",
                "issue_gotcha": (
                    non_draft[1] if non_draft else ("#993" if status == "xfail" else None)
                ),
                "known_failure_status": status,
            },
            "audience_safety": {
                "reviewer_audience": "engineer",
                "kid_facing": False,
                "guardian_safety_authority": None,
                "privacy_sensitivity": "none",
            },
            "isolation": {
                "split": "test",
                "real_world_group_key": group,
                "contamination_lineage": [f"lineage:gold-v1:{group}"],
                "prompt_version": None,
                "model_version": None,
                "scorer_version": "search-entity/v1",
            },
            "presentation": presentation,
        })
    probes.extend(build_outcome_evidence_probes())
    probes.extend(build_diacritic_probes())
    probes.extend(build_mc3_probes())
    probes.extend(build_mc2_probes())
    return probes


def build_diacritic_probes() -> list[dict[str, Any]]:
    """The DIACRITIC-FOLDING class (#1881) — `canary` split.

    See the block comment on ``DIACRITIC_ROWS`` for what was measured, why the
    class grades an index rather than the scorer, and why the two directions of
    the defect get one probe each.
    """

    probes: list[dict[str, Any]] = []
    for query, expected, allowed, direction, status, note in DIACRITIC_ROWS:
        kind = expected.split(":", 1)[0]
        surface, item_type = KIND_SHAPE[kind]
        presentation = {"query": query}
        probes.append({
            "identity": {
                "probe_key": f"search-diacritic-{_slug(query)}-001",
                "probe_version": 1,
                "schema_version": SCHEMA_VERSION,
                "surface": "search_typeahead",
                "task_type": "search_entity",
                "item_type": item_type,
                "entity_ids": [expected, *allowed],
                "gold_half": "diacritic_folding",
                "gold_family": "diacritic_folding",
            },
            "evidence": {
                "fixture_hash": fixture_sha256(presentation),
                "hash_scope": "presentation/v1",
                "source": (
                    "LAT-P058 (#1881, ruling 060): diacritic-folding class, specimened from the "
                    "two pairs named in the issue and re-measured on production v3820"
                ),
                "provenance": (
                    f"diacritic-folding half, {direction} direction; measured against "
                    f"{EVIDENCE_SURFACE}"
                ),
                "captured_at": DIACRITIC_CAPTURED_AT,
                "valid_at": DIACRITIC_CAPTURED_AT,
                "license_usage_note": (
                    "internal product query set; queries name public sports clubs and a public "
                    "sporting event only"
                ),
                "pii_redacted": True,
            },
            "oracle": {
                "oracle_kind": "known_answer",
                "label_schema": "search_entity/v1",
                "label_schema_version": 1,
                "authority": (
                    "product judgment: a diacritic is a spelling of the same entity, not a "
                    "different entity, so both spellings must reach the same referent"
                ),
                "evidence": note,
                "adjudication_history": [],
                "answer": {
                    "expected_entity_id": expected,
                    "allowed_entity_ids": list(allowed),
                    "expected_surfaces": [surface],
                    "expected_item_type": item_type,
                    "query_class": "diacritic_folding",
                },
            },
            "lifecycle": {
                "state": "active",
                "owner": "search-evals",
                "difficulty": "discrimination",
                "failure_family": "search-entity-top-1",
                "issue_gotcha": "#1881",
                "known_failure_status": status,
            },
            "audience_safety": {
                "reviewer_audience": "engineer",
                "kid_facing": False,
                "guardian_safety_authority": None,
                "privacy_sensitivity": "none",
            },
            "isolation": {
                "split": "canary",
                "real_world_group_key": f"diacritic:{direction}",
                "contamination_lineage": [f"lineage:diacritic-v1:{direction}"],
                "prompt_version": None,
                "model_version": None,
                "scorer_version": "search-entity/v1",
            },
            "presentation": presentation,
        })
    return probes


def build_outcome_evidence_probes() -> list[dict[str, Any]]:
    """The OUTCOME-EVIDENCE class (ruling 056, #1861) — `canary` split.

    Same schema as the gold probes, three deliberate differences:

    * ``isolation.split`` is ``canary``, so the historical ``test`` cohort keeps
      its denominator (see the block comment on ``OUTCOME_EVIDENCE_ROWS``).
    * ``gold_half`` is ``outcome_evidence`` — these are NOT from Alex's draft and
      must never be counted as coverage of it (P10: keep the halves
      distinguishable).
    * ``lifecycle.difficulty`` is ``discrimination``: the class exists to tell
      changes APART, which is a different job from covering the query space, and
      the set had never been assembled for it.
    """

    probes: list[dict[str, Any]] = []
    for query, expected, allowed, outcome_rank, note in OUTCOME_EVIDENCE_ROWS:
        kind = expected.split(":", 1)[0]
        surface, item_type = KIND_SHAPE[kind]
        presentation = {"query": query}
        probes.append({
            "identity": {
                "probe_key": f"search-outcome-evidence-{_slug(query)}-001",
                "probe_version": 1,
                "schema_version": SCHEMA_VERSION,
                "surface": "search_typeahead",
                "task_type": "search_entity",
                "item_type": item_type,
                "entity_ids": [expected, *allowed],
                "gold_half": "outcome_evidence",
                "gold_family": "outcome_evidence",
            },
            "evidence": {
                "fixture_hash": fixture_sha256(presentation),
                "hash_scope": "presentation/v1",
                "source": (
                    "LAT-P052 (#1861, ruling 056): outcome-evidence discrimination class, "
                    "specimened from the production futures_outcomes table"
                ),
                "provenance": (
                    f"outcome-evidence half; the expected market owns this query at outcome rank "
                    f"{outcome_rank}, outside the top-3 display cut, and matches on NO name token. "
                    f"Verified against {EVIDENCE_SURFACE}"
                ),
                "captured_at": OUTCOME_EVIDENCE_CAPTURED_AT,
                "valid_at": OUTCOME_EVIDENCE_CAPTURED_AT,
                "license_usage_note": "internal product query set; queries name public film titles only",
                "pii_redacted": True,
            },
            "oracle": {
                "oracle_kind": "known_answer",
                "label_schema": "search_entity/v1",
                "label_schema_version": 1,
                "authority": (
                    "product judgment: the product's ONLY representation of this film is as an "
                    "outcome of the Best Picture markets, so a market that owns it is the correct "
                    "referent — there is no rival surface to prefer"
                ),
                "evidence": note,
                "adjudication_history": [],
                "answer": {
                    "expected_entity_id": expected,
                    "allowed_entity_ids": list(allowed),
                    "expected_surfaces": [surface],
                    "expected_item_type": item_type,
                    "query_class": "outcome_evidence",
                },
            },
            "lifecycle": {
                "state": "active",
                "owner": "search-evals",
                "difficulty": "discrimination",
                "failure_family": "search-entity-top-1",
                "issue_gotcha": "#1861",
                "known_failure_status": "pass",
            },
            "audience_safety": {
                "reviewer_audience": "engineer",
                "kid_facing": False,
                "guardian_safety_authority": None,
                "privacy_sensitivity": "none",
            },
            "isolation": {
                "split": "canary",
                "real_world_group_key": "market:oscars-best-picture",
                "contamination_lineage": ["lineage:outcome-evidence-v1:market:oscars-best-picture"],
                "prompt_version": None,
                "model_version": None,
                "scorer_version": "search-entity/v1",
            },
            "presentation": presentation,
        })
    return probes


def _mc_probe(
    *,
    family: str,
    query: str,
    subject: str,
    expected: str,
    allowed: list[str],
    note: str,
    authority: str,
    provenance: str,
    group_key: str,
    issue: str,
) -> dict[str, Any]:
    """One MC3/MC2 probe (#1867). Shared because the two classes differ only in
    their family, their discrimination field and their prose — and a second
    copy of this dict is a second place for the schema to drift."""

    kind = expected.split(":", 1)[0]
    surface, item_type = KIND_SHAPE[kind]
    presentation = {"query": query}
    return {
        "identity": {
            "probe_key": f"search-{family.replace('_', '-')}-{_slug(query)}-001",
            "probe_version": 1,
            "schema_version": SCHEMA_VERSION,
            "surface": "search_typeahead",
            "task_type": "search_entity",
            "item_type": item_type,
            "entity_ids": [expected, *allowed],
            "gold_half": family,
            "gold_family": family,
        },
        "evidence": {
            "fixture_hash": fixture_sha256(presentation),
            "hash_scope": "presentation/v1",
            "source": (
                f"LAT-P061 (#1867, rulings 056/060): {family} discrimination class, specimened "
                "from the typeahead's own debug_evidence echo replayed through the real scorer"
            ),
            "provenance": (
                f"{provenance} The ROUTE scores `parse_intent(q).subject` = {subject!r}, not the "
                f"raw query, and this probe was accepted only after the subject replay reproduced "
                f"production's own served rank 1. Verified against {EVIDENCE_SURFACE}"
            ),
            "captured_at": MC3_MC2_CAPTURED_AT,
            "valid_at": MC3_MC2_CAPTURED_AT,
            "license_usage_note": "internal product query set; queries name public competitions only",
            "pii_redacted": True,
        },
        "oracle": {
            "oracle_kind": "known_answer",
            "label_schema": "search_entity/v1",
            "label_schema_version": 1,
            "authority": authority,
            "evidence": note,
            "adjudication_history": [],
            "answer": {
                "expected_entity_id": expected,
                "allowed_entity_ids": list(allowed),
                "expected_surfaces": [surface],
                "expected_item_type": item_type,
                "query_class": family,
            },
        },
        "lifecycle": {
            "state": "active",
            "owner": "search-evals",
            "difficulty": "discrimination",
            "failure_family": "search-entity-top-1",
            "issue_gotcha": issue,
            "known_failure_status": "pass",
        },
        "audience_safety": {
            "reviewer_audience": "engineer",
            "kid_facing": False,
            "guardian_safety_authority": None,
            "privacy_sensitivity": "none",
        },
        "isolation": {
            "split": "canary",
            "real_world_group_key": group_key,
            "contamination_lineage": [f"lineage:{family.replace('_', '-')}-v1:{group_key}"],
            "prompt_version": None,
            "model_version": None,
            "scorer_version": "search-entity/v1",
        },
        "presentation": presentation,
    }


def build_mc3_probes() -> list[dict[str, Any]]:
    """The MC3 (PARTIAL-TOKEN) class (#1867) — `canary` split.

    The class this set was missing is: **a query whose answer changes when
    `PARTIAL_MIN_COVERAGE` moves.** Two rows do that by two different
    mechanisms, and the third records the shape that provably cannot — see the
    block comment on ``MC3_ROWS`` for how each was measured.
    """

    probes: list[dict[str, Any]] = []
    for query, subject, expected, allowed, edges, note in MC3_ROWS:
        if edges:
            where = ", ".join(f"between {lo} and {hi}" for lo, hi in edges)
            provenance = (
                f"MC3 partial-token half; top-1 CHANGES as PARTIAL_MIN_COVERAGE crosses {where} "
                f"(swept 0.05..1.00 in twenty steps against the shipped 0.5)."
            )
        else:
            provenance = (
                "MC3 partial-token half, LIMIT row; top-1 is unchanged at every one of the twenty "
                "swept values of PARTIAL_MIN_COVERAGE, because an MC1 candidate owns the query "
                "and class order is inviolable."
            )
        probes.append(_mc_probe(
            family="mc3_partial",
            query=query,
            subject=subject,
            expected=expected,
            allowed=allowed,
            note=note,
            authority=(
                "product judgment: the reader named a competition and a market that answers it "
                "exists, so the row that answers the question is the correct referent. Which of "
                "the tournament's own surfaces ranks first is the ranking question this probe "
                "grades, which is why the rivals are ALLOWED rather than wrong"
            ),
            provenance=provenance,
            group_key=MC_GROUP_KEYS[query],
            issue="#1867",
        ))
    return probes


def build_mc2_probes() -> list[dict[str, Any]]:
    """The MC2 (LAST-TOKEN PREFIX) class (#1867) — `canary` split.

    MC2 has no knob, so the discrimination test is the class itself: mute it
    (raise ``PREFIX_MIN_LEN`` above the specimen's last token) and see whether
    the served answer moves. Two rows move; the third is the measured statement
    that MC2's incidental coverage is NOT sufficient — #1867's Gap 2.
    """

    probes: list[dict[str, Any]] = []
    for query, subject, expected, allowed, muted, note in MC2_ROWS:
        if muted is not None:
            provenance = (
                f"MC2 last-token-prefix half; muting MC2 (PREFIX_MIN_LEN above the last token) "
                f"moves top-1 to {muted}, so this probe grades the class rather than merely "
                f"exercising it."
            )
        else:
            provenance = (
                "MC2 last-token-prefix half, LIMIT row; MC2 IS present in the candidate set and "
                "top-1 does not move when it is muted, because MC1B is checked first and owns the "
                "answer. This is the 'graded only by accident' shape #1867 names."
            )
        probes.append(_mc_probe(
            family="mc2_prefix",
            query=query,
            subject=subject,
            expected=expected,
            allowed=allowed,
            note=note,
            authority=(
                "product judgment: the reader is mid-word and the endpoint is called typeahead — "
                "the correct answer is the row the finished query would resolve to, not a row "
                "that merely shares a fragment"
            ),
            provenance=provenance,
            group_key=MC_GROUP_KEYS[query],
            issue="#1867",
        ))
    return probes


def build_registry() -> dict[str, Any]:
    probes = build_probes()
    return {
        "metadata": {
            "schema_version": SCHEMA_VERSION,
            "description": (
                "Gold-query Search probes (queue 313). Generated by "
                "scripts/evals/build_search_gold_registry.py — edit the table there, not this file."
            ),
            "gold_set_source": GOLD_SET_SOURCE,
            "gold_set_unique_queries": 71,
            # `migrated` counts ONLY probes migrated FROM Alex's gold draft, and
            # it is derived from GOLD_ROWS rather than from len(probes) for that
            # reason. The outcome-evidence class (ruling 056) is not from the
            # draft, so folding it in here would have quietly restated 46 as 51
            # and overclaimed coverage of a set that did not grow.
            "migrated": len(GOLD_ROWS),
            "outcome_evidence_probes": len(OUTCOME_EVIDENCE_ROWS),
            "diacritic_probes": len(DIACRITIC_ROWS),
            "mc3_probes": len(MC3_ROWS),
            "mc2_probes": len(MC2_ROWS),
            "split_counts": {
                "test": len(GOLD_ROWS),
                "canary": (
                    len(OUTCOME_EVIDENCE_ROWS) + len(DIACRITIC_ROWS)
                    + len(MC3_ROWS) + len(MC2_ROWS)
                ),
            },
            "split_note": (
                "`test` is the historical cohort the §5 ledger of docs/search-scoring-spec.md is "
                "written against — 46 probes graded 44-wide — and it MUST NOT grow without "
                "restating every prior read. The outcome-evidence discrimination class "
                "(ruling 056, #1861), the diacritic-folding class (#1881, LAT-P058) and the "
                "MC3/MC2 discrimination classes (#1867, LAT-P061) are therefore all in `canary`."
            ),
            "mc_candidates": sum(len(queries) for queries, _ in MC_CANDIDATES),
            "results_producer": "scripts/evals/search_results_producer.py",
            "fixture_hash_convention": (
                "sha256 over the canonical JSON of presentation{} (hash_scope presentation/v1); "
                "validate_registry re-derives and enforces it"
            ),
        },
        "probes": probes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--check", action="store_true", help="verify the committed file matches this generator")
    args = parser.parse_args()

    registry = build_registry()
    errors = validate_registry(registry["probes"])
    if errors:
        print(json.dumps(errors, indent=2))
        return 2
    rendered = json.dumps(registry, indent=2, ensure_ascii=False) + "\n"

    out = Path(args.out)
    if args.check:
        if not out.exists() or out.read_text(encoding="utf-8") != rendered:
            print(f"STALE: {out} does not match the generator; re-run without --check")
            return 1
        print(f"OK: {out} matches the generator ({len(registry['probes'])} probes)")
        return 0

    out.write_text(rendered, encoding="utf-8")
    print(json.dumps(registry["metadata"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
