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
            "migrated": len(probes),
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
