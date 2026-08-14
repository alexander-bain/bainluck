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
            "split_counts": {
                "test": len(GOLD_ROWS),
                "canary": len(OUTCOME_EVIDENCE_ROWS),
            },
            "split_note": (
                "`test` is the historical cohort the §5 ledger of docs/search-scoring-spec.md is "
                "written against — 46 probes graded 44-wide — and it MUST NOT grow without "
                "restating every prior read. The outcome-evidence discrimination class "
                "(ruling 056, #1861) is therefore in `canary`."
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
