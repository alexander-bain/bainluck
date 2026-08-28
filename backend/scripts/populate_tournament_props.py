#!/usr/bin/env python3
"""Populate the register's curated props & futures section (UX-P132, Alex's item 5).

"Beyond the two winner markets and today's matches, surface a section of
interesting tournament props/futures.  Interestingness bar applies: curated,
not a dump."

The curation happens HERE, by an agent, and lands in the committed register —
which is what makes "curated, not a dump" structural rather than aspirational.
The page has no discovery path: a market this script does not write cannot
appear, however much volume it has.

**The bar.** A prop earns its place by being a question a person following this
tournament would actually ask — "can Sinner complete the calendar slam", "does
Alcaraz even play" — not by being liquid.  Volume is a tiebreaker between
interesting markets, never a reason to include a dull one.  The Day-1 census
found nine Kalshi US-Open-adjacent markets; the two outright fields are already
the championship boards, so the candidates are the remaining seven:

    KXATPCOMPETE-26USOALC    will Alcaraz compete
    KXATPCOMPETE-26USOSIN    will Sinner compete
    KXATPGRANDSLAM-26        men's calendar grand slam
    KXATPGRANDSLAMFIELD-26   men's calendar grand slam, field
    KXWTAGRANDSLAM-26        women's calendar grand slam
    KXGRANDSLAM-CALC26       Alcaraz calendar slam
    KXGRANDSLAM-JSIN26       Sinner calendar slam

Input is one `/api/admin/db-query` dump, in the shape that endpoint returns:

    SELECT fm.id   AS market_id,
           fm.external_id AS market_ext,
           fm.source,
           fm.name AS market_name,
           fm.status,
           fo.id   AS outcome_id,
           fo.name AS outcome_name,
           fo.current_probability
      FROM futures_markets fm
      JOIN futures_outcomes fo ON fo.market_id = fm.id
     WHERE fm.external_id IN ('KXATPCOMPETE-26USOALC','KXATPCOMPETE-26USOSIN',
                              'KXATPGRANDSLAM-26','KXATPGRANDSLAMFIELD-26',
                              'KXWTAGRANDSLAM-26','KXGRANDSLAM-CALC26',
                              'KXGRANDSLAM-JSIN26')
       AND fm.status = 'open'
     ORDER BY fm.external_id, fo.current_probability DESC NULLS LAST;

Usage:
    python3 scripts/populate_tournament_props.py \\
        --register data/tournament_registers/us-open-2026.json \\
        --dump /tmp/uso/props.json \\
        --version 3 --supersedes-version 2 \\
        --observed-at 2026-08-26T00:00:00+00:00

It refuses to write a register that does not validate, exactly as the main
generator does.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.prop_template_family import (  # noqa: E402
    detect_template_families,
    outcome_signature,
)
from app.utils.tournament_register import (  # noqa: E402
    classify,
    us_open_2026_contract,
    validate_register,
)

#: The curation, written down. Each entry says WHY the question is interesting,
#: in the words the page will print. A ticker absent from this map is not
#: curated and will not be written, even if the dump contains it — which is the
#: difference between a curated section and a filtered dump.
#: ``answer`` names the ONE outcome whose probability answers ``title``, by the
#: source's own outcome name. ``None`` means the question is a field with no
#: single answering outcome, and the page ranks instead of printing a headline.
#: The script REFUSES a curation whose named answer is absent from the dump —
#: silently producing an unanswered card is how a wrong number gets shipped.
CURATION: dict[str, dict] = {
    "KXATPCOMPETE-26USOSIN": {
        "key": "sinner-competes",
        "title": "Will Sinner actually play?",
        "hook": "A withdrawal reshapes the entire men's board.",
        "draw": "mens-singles",
        "answer": "Yes",
    },
}

#: ONE CARD PER TEMPLATE FAMILY — AND THE SYSTEM FINDS THE FAMILY (UX-P154).
#:
#: ═══ ALEX'S QUESTION, 2026-08-28, quoted (ruling 144) ═══
#:
#: On UX-P151's combined second-major card: *"clearly looks better"*, and then:
#: *"Was this a bespoke solution? I thought we'd built tools to identify groups
#: and surface them as groups. Why didn't any of them trigger?"*
#:
#: **It was bespoke.**  UX-P151 shipped a `COMBINED_CURATION` map in which a
#: human wrote down two market tickers, the outcome name to pull from each, and
#: the label each row should print.  Nothing in it was detected; the pass only
#: checked that what a human had typed still existed.  Add a third player and
#: the card would not have noticed him.
#:
#: Why nothing triggered is answered at length, with the measurements, in
#: `app/utils/prop_template_family.py`.  The short version is that the two
#: things that could have fired both could not: the props renderer's family rule
#: is a CAP whose only outputs are two cards or one card and a deletion, and it
#: had been keyed on the whole register key since UX-P147, making it
#: structurally unreachable; and the real grouper, `prop_families.py`, is not
#: wired to this pass and returns `None` for `"Carlos Alcaraz: Grand Slam wins
#: in 2026"` anyway.
#:
#: ═══ WHAT THIS MAP IS NOW ═══
#:
#: Keyed on the SKELETON the detector produces — the question with the subject
#: slot empty — and it carries only the things a machine cannot know: the
#: sentence a reader sees, why it is interesting, which draw it belongs to, and
#: which of the shared outcomes the card compares.
#:
#: Everything else is DERIVED: which markets are in the family, how many there
#: are, who each row is, and what each row is called.  A third `KXGRANDSLAM-*`
#: market with the same ladder joins this card with no edit here, which is the
#: only real test of "by the system".
#:
#: THE ROWS ARE THE SOURCE'S OWN WORDS.  UX-P151 renamed "2+ Grand Slam wins" to
#: a hand-written "Alcaraz"; the rows now read "Carlos Alcaraz" because that is
#: what the market's own title calls him.  Alex, item 4 of the same directive:
#: *"the market's own words are USED when they are the market's words."*  A
#: curated rename is a claim about a number that nothing downstream can check.
#:
#: WHY NO ``answer``.  A card with a single headline number needs one outcome
#: that answers its question, and a family has one per member by construction.
#: So it is a FIELD card: ``answer_entity_key`` is ``None``, the renderer ranks
#: instead of leading, and "which number goes in the big type" is never guessed.
#:
#: WHAT THE HOOK IS DOING.  The title Alex wrote reads as a race — *who* wins —
#: and these are INDEPENDENT binaries that can both resolve Yes: there are four
#: majors a year and each man needs two of them, not the same two.  Their
#: numbers do not sum to 100 and must never be normalised so they do (the same
#: rule the cycling GC field carries).  The title is his, verbatim; the hook is
#: what stops it being read as an exclusive race.
FAMILY_CURATION: dict[str, dict] = {
    "{} grand slam wins in 2026": {
        "key": "second-major",
        "title": "Who wins a second major this year?",
        "hook": (
            "Both already have one in 2026. These are two separate questions — "
            "they could both do it, or neither."
        ),
        "draw": "mens-singles",
        #: Matched EXACTLY against each member's own outcome names, never
        #: fuzzily. The detector has already proved every member offers the same
        #: set, so naming it once names it for all of them.
        "compare_outcome": "2+ Grand Slam wins",
    },
}

#: Curated OUT, with the reason, because a silent omission is indistinguishable
#: from an oversight and this section's whole claim is that the bar was applied.
#:
#: `KXATPGRANDSLAM-26` / `KXWTAGRANDSLAM-26` — "Who will win *a* Grand Slam in
#: 2026?", resolving 2027-01-07. Two defects, either one disqualifying. (1) It
#: is a SEASON question, not a US Open question: it stays open through the
#: Australian Open five months after this tournament ends. (2) Its leaders are
#: already-settled 99s — Sinner .99, Zverev .99, Alcaraz .97 on the men's side,
#: Rybakina .99 and Andreeva .99 on the women's — because those players have
#: already won a major this year. A "prop" whose top rows are decided facts is
#: a dull row wearing a probability. These were curated IN by UX-P132 under the
#: titles "Will anyone win the men's/women's calendar slam?", which the markets
#: do not ask; that misdescription is the third reason.
#:
#: `KXATPGRANDSLAMFIELD-26` — "any man other than Alcaraz and Sinner", Yes at
#: .99. Already happened. Never curated in; recorded so the next pass does not
#: rediscover it as a candidate.
DECLINED: dict[str, str] = {
    "KXATPGRANDSLAM-26": "season-long field resolving 2027-01-07; leaders already settled at .97-.99",
    "KXWTAGRANDSLAM-26": "season-long field resolving 2027-01-07; leaders already settled at .99",
    "KXATPGRANDSLAMFIELD-26": "already resolved in substance (Yes .99); not a US Open question",
    # CURATED OUT 2026-08-26 (UX-P135), having been curated IN by UX-P134.
    # "Will Alcaraz actually play?" was measured at Yes .905 and 808.7h old —
    # 33.7 days without a reading, the oldest thing in the section. The draw
    # ceremony is tomorrow, after which the question answers itself. Its twin
    # `KXATPCOMPETE-26USOSIN` is KEPT: at Yes .63 and 186.7h it is both the
    # freshest incumbent and genuinely undecided, which is the whole difference.
    "KXATPCOMPETE-26USOALC": "Yes .905 at 808.7h (33.7d); near-decided and the draw resolves it tomorrow",
}

#: Card keys this pass RETIRES, and where they went — merged into the register's
#: own ``props_declined`` on every run.
#:
#: `props_declined` used to be hand-maintained while `props` was generated, so
#: the two could disagree and only a test noticed.  That is the wrong way round:
#: the pass that removes a card is the thing that knows why, and
#: ``test_every_prop_removed_from_the_register_says_why_it_went`` exists because
#: a silent removal is indistinguishable from an oversight.  Merged, never
#: replaced — the eight UX-P139 grid-cell reasons are hand-written and stay.
RETIRED: dict[str, str] = {
    "alcaraz-second-major": (
        "retired INTO `second-major` (UX-P151, Alex 2026-08-28): Alcaraz is a leg of the "
        "combined card now, not a card of his own. The number did not go anywhere — it is "
        "the Alcaraz row"
    ),
    "sinner-second-major": (
        "retired INTO `second-major` (UX-P151, Alex 2026-08-28): Sinner is a leg of the "
        "combined card now, not a card of his own. The number did not go anywhere — it is "
        "the Sinner row"
    ),
}

# ---------------------------------------------------------------------------
# THE WOMEN'S SECTION (UX-P147, Alex's item 7) — RULED YES, AND BLOCKED
# ---------------------------------------------------------------------------
#
# Alex ruled YES on a women's props section and named the direction he wanted:
# **Sabalenka back-to-back, first-time major winner, all-American final**, plus
# the nationality props "once lane1/012's discovery fix lands (do not hand-enter
# what discovery should find)".
#
# The curation is written and the section is ready.  What is missing is the
# markets, and the census below is the whole reason this file still ships two
# men's cards and no women's ones.  Three sweeps, 2026-08-27/28:
#
# **1. Our database.**  Every open US-Open market at either source that is not
# an advance-to-round binary, a qualifying match, or a celebrity-attendance
# novelty: seventeen rows, and all seventeen are the two winner fields, the six
# Polymarket reach-ladders, the two Kalshi "to play" markets, or unrelated
# tickers that matched on the words ("RÜFÜS DU SOL Streams in 2026").  Nothing
# a woman's props section could print.
#
# **2. Polymarket upstream** (Gamma, `tag_slug=tennis`, 60 open events).  The
# two winner fields, the eight reach-ladders, "Who will attend the US Open
# Finals?", and a Chipotle promotion.  No non-advance women's question exists.
#
# **3. Kalshi upstream — the full open book.**  13,511 open events scanned by
# ticker and title.  Twelve US-Open-specific markets exist that WE DO NOT HOLD:
#
#     KXWTANATSTAGE-26QF     Women's Singles: Americans to Reach Quarterfinals
#     KXWTANATSTAGE-26SF     Women's Singles: Americans to Reach Semifinals
#     KXATPNATSTAGE-26QF     Men's Singles: Americans to Reach Quarterfinals
#     KXATPNATSTAGE-26SF     Men's Singles: Americans to Reach Semifinals
#     KXATPNATSTAGE-26FIN    Men's Singles: Americans to Reach Final
#     KXATPWTA-26USO         US Open Exacta (80 men-and-women pairings)
#     KXWTAADVANCE-26USO{QUAR,SEMI,FIN}   women's reach-fields
#     KXATPADVANCE-26USO{QUAR,SEMI,FIN}   men's reach-fields
#
# `SELECT ... WHERE external_id IN (...)` over those twelve returns **0 rows**.
# The `NATSTAGE` family IS the nationality prop Alex asked for, and
# `KXATPNATSTAGE-26FIN` is as close as any market gets to "all-American final".
# So his parenthetical governs: do not hand-enter them.  They are lane1/012's.
#
# ** AND THE PART THAT CHANGES THE DEPENDENCY. **  Discovery is necessary and
# NOT sufficient.  Measured on Kalshi's own API the same night, every one of the
# six NATSTAGE markets is::
#
#     last_price_dollars 0.0000   open_interest_fp 0.00   liquidity_dollars 0.0000
#     yes_bid 0.02  yes_ask 0.90                (KXWTANATSTAGE-26SF-1, "1+ Americans")
#
# Zero trades, zero open interest, an 88-cent spread.  Ingesting them tomorrow
# would put a question on the page with no number under it.  So the women's
# section is blocked on the market TRADING, not only on us fetching it, and the
# report says so rather than letting a discovery fix be mistaken for the unlock.
#
# **"Sabalenka back-to-back" and "first-time major winner" do not exist as
# markets anywhere.**  Not at Kalshi (all 13,511 open events), not at
# Polymarket.  The only thing that could print under either title is a slice of
# the women's winner field, which is the board directly above — one number
# answering two differently-worded questions is the divergence this register
# refuses, and it is the same defect UX-P134 fixed when it stopped a
# threshold-ladder maximum from answering a calendar-slam question.
#
# WHAT IS READY.  `curatedProps` takes a draw and does not care which; the
# renderer, the rotation, the honesty treatment and the empty-state sentence
# already work for `womens-singles`, and were re-verified this queue.  The day a
# NATSTAGE market lands with a price, it is an entry in `CURATION` and nothing
# else.
WOMENS_NON_ADVANCE_CENSUS: dict[str, str] = {
    "KXWTANATSTAGE-26QF": "not ingested (0 rows); and 0 trades / 0 OI / .02-.90 spread upstream",
    "KXWTANATSTAGE-26SF": "not ingested (0 rows); and 0 trades / 0 OI / .02-.90 spread upstream",
    "KXATPNATSTAGE-26FIN": "the closest market to 'all-American final'; not ingested, 0 OI",
    "KXATPWTA-26USO": "US Open Exacta, 80 pairings — genuinely fun, not ingested, unpriced",
    "sabalenka-back-to-back": "NO MARKET EXISTS at either source. Would have to be the winner field's Sabalenka row, which is the board above",
    "first-time-major-winner": "NO MARKET EXISTS at either source. Would have to be derived from the winner field, which the client never does (ruling 003)",
}

# ---------------------------------------------------------------------------
# THE ADVANCE LADDER (UX-P135, Day 5)
#
# Polymarket runs one binary per player per round — "Will <player> advance to
# the <round>?" — 336 of them across 84 US Open players. That population is a
# LADDER, which is exactly the shape the feed audit drives to zero: curating
# Alcaraz at R16 *and* QF *and* SF is three cards asking one question three
# times, and the reader learns nothing from the second and third.
#
# So the rule here is ONE QUESTION PER PLAYER, at the deepest round the market
# still calls close. Everything else about a player is dropped, and the drop is
# what makes this curation rather than an import. Selected on three grounds,
# all of which have to hold:
#
#   1. A name a casual fan recognises. This section competes with the boards
#      above it, which already print all 80 contenders in rank order.
#   2. Genuine uncertainty — roughly .25 to .75. A .95 is a fact wearing a
#      probability, and the section already lost two cards to that test.
#   3. A question the boards do not already answer. "Who wins?" is the board.
#      "Does the second week happen for this player?" is not, and for a
#      128-draw tournament it is the more askable one for eleven of them.
#
# BOTH DRAWS, deliberately. UX-P134 curated four props, all men's, so the
# women's tab shipped the honest-empty state. Four of the eight below are
# women's — the first cards that tab has ever had.
#
# ** THESE ARE NOT LIVE. ** Measured 2026-08-26: 23.2-25.3h, which is `stale`
# under the page's own thresholds, and the page will render them muted with
# their age. They are curated anyway because 23 hours is not 34 days, the
# questions are better than the ones they sit beside, and the honesty treatment
# exists precisely so that a good stale number can still be shown. What is NOT
# claimed is the thing the Day-4 mission expected: these ladders were 3.6-5.6h
# old when that mission measured them and they are not now. See the report.
#
# Keyed on `external_id` (the Polymarket condition hash), like the Kalshi half,
# because our own `market_id` is a local surrogate and a re-ingest can move it.
ADVANCE_CURATION: dict[str, dict] = {
    "0x0d62271aa9d9c4e2aa5aa6e4d7f044c7b0821bd93bb999dc06c51f150d1cf4e3": {
        "key": "alcaraz-semifinals",
        "title": "Does Alcaraz reach the semifinals?",
        "hook": "The men's favourite, and the market still calls it close to a coin flip.",
        "draw": "mens-singles",
        "answer": "Yes",
    },
    "0x234cfdf2f118eb7f349a9f9abfc23556c930eab2e05fa113962b0192488c8910": {
        "key": "djokovic-quarterfinals",
        "title": "Does Djokovic reach the quarterfinals?",
        "hook": "Twenty-four majors, and the second week is no longer a formality.",
        "draw": "mens-singles",
        "answer": "Yes",
    },
    "0x91ee5878ac149eab31e866607043b21bc9cc4ddce4d6970447d3250eb4751022": {
        "key": "zverev-semifinals",
        "title": "Does Zverev reach the semifinals?",
        "hook": "Perennially close to a first major. The market has him at even money.",
        "draw": "mens-singles",
        "answer": "Yes",
    },
    "0xdc42f3b0ded6249c92e3eea60572ca39d917786e1965ee1024e13a0796dd8720": {
        "key": "shelton-quarterfinals",
        "title": "Does Shelton reach the quarterfinals?",
        "hook": "The loudest home crowd in tennis, and a market split down the middle.",
        "draw": "mens-singles",
        "answer": "Yes",
    },
    "0x24fd9fa0a695ad98c2fc3ca7300a97353b8025bf9af231a223e5df1498aeefeb": {
        "key": "sabalenka-semifinals",
        "title": "Does Sabalenka reach the semifinals?",
        "hook": "The women's favourite. Even the market cannot separate it.",
        "draw": "womens-singles",
        "answer": "Yes",
    },
    "0xea5b210653d6791dfb36b4f7e800fd6a3ee7a7c356557cc0fe53e02c26c89883": {
        "key": "swiatek-semifinals",
        "title": "Does Swiatek reach the semifinals?",
        "hook": "Dominant almost everywhere else; New York has been the exception.",
        "draw": "womens-singles",
        "answer": "Yes",
    },
    "0xbd82f2526c64cfa634da82c90f3db653ef6d47925fa1edf9e16db95844fb9b5a": {
        "key": "gauff-semifinals",
        "title": "Does Gauff reach the semifinals?",
        "hook": "The home favourite, and the market is far less sure than the crowd.",
        "draw": "womens-singles",
        "answer": "Yes",
    },
    "0x1e045109e228f8b7381dcc21bf9ba320b5bd5d237cb02f038cabdaf96b2a1b0f": {
        "key": "osaka-round-of-16",
        "title": "Does Osaka reach the second week?",
        "hook": "Two US Open titles, and a first week the market rates a coin flip.",
        "draw": "womens-singles",
        "answer": "Yes",
    },
}


def read_query_dump(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    if payload.get("truncated"):
        raise RuntimeError(f"{path} is TRUNCATED — re-run with a higher limit.")
    return [dict(zip(payload["columns"], row)) for row in payload["rows"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", required=True)
    parser.add_argument("--dump", required=True)
    parser.add_argument(
        "--advance-dump",
        help="second dump, the Polymarket 'advance to the <round>' binaries "
        "(UX-P135). Optional so the Kalshi-only pass still runs unchanged.",
    )
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--supersedes-version", type=int, required=True)
    parser.add_argument("--out", help="defaults to --register (in place)")
    args = parser.parse_args()

    register = json.loads(Path(args.register).read_text())
    rows = read_query_dump(Path(args.dump))
    if args.advance_dump:
        rows = rows + read_query_dump(Path(args.advance_dump))

    # One curation table, assembled from two. Keeping them separate above is
    # editorial (the two populations were surveyed on different days, against
    # different bars); keeping them separate HERE would duplicate the refusal
    # logic, which is the part that must not diverge.
    curation = {**CURATION, **ADVANCE_CURATION}
    keys = [spec["key"] for spec in curation.values()] + [
        spec["key"] for spec in FAMILY_CURATION.values()
    ]
    if len(set(keys)) != len(keys):
        # Two curations writing one card key would silently drop one of them,
        # and the section would be short with nothing to point at.
        print(f"REFUSED: duplicate curation keys in {sorted(keys)}", file=sys.stderr)
        return 1

    by_market: dict[str, list[dict]] = {}
    for row in rows:
        by_market.setdefault(str(row["market_ext"]), []).append(row)

    # ── THE SYSTEM FINDS THE FAMILIES (UX-P154, Alex's item 1) ───────────────
    #
    # Detection runs over everything in the dump that has not been curated OUT,
    # and it runs BEFORE anything decides what a card is. Declined tickers are
    # excluded first: a market we have already refused on its merits must not be
    # able to drag a good one into a family, and it must not be able to raise a
    # refusal about a question nobody is going to write.
    candidates = [
        {
            "market_ext": market_ext,
            "market_name": market_rows[0]["market_name"],
            "source": market_rows[0]["source"],
            "outcomes": [str(r["outcome_name"]) for r in market_rows],
        }
        for market_ext, market_rows in sorted(by_market.items())
        if market_ext not in DECLINED
    ]
    families = detect_template_families(candidates)

    # EVERY DETECTED FAMILY NEEDS A QUESTION, or the pass stops.
    #
    # This is the refusal that makes the detector worth having. Without it a
    # newly-listed family would either ship as N repeated cards (the UX-P147
    # failure) or be silently dropped (the UX-P138 failure); with it, the pass
    # tells the curator that a family exists, what its skeleton is, and which
    # markets are in it — which is the whole of what they need to write one line.
    uncurated = [f for f in families if f.skeleton not in FAMILY_CURATION]
    if uncurated:
        for family in uncurated:
            print(
                f"REFUSED: template family {family.skeleton!r} is not curated. "
                f"Members: {list(family.market_exts)}. "
                f"Shared outcomes: {list(family.signature)}. "
                "These markets ask one question about different subjects and would "
                "otherwise ship as repeated cards. Add a FAMILY_CURATION entry keyed "
                "on that skeleton, or decline the markets.",
                file=sys.stderr,
            )
        return 1

    detected_skeletons = {f.skeleton for f in families}
    stale = sorted(set(FAMILY_CURATION) - detected_skeletons)
    if stale:
        # A curated family the detector no longer finds. Either a source renamed
        # a market out of the shape, or a member stopped being returned. Both are
        # "the card you curated is not the card that would ship", and both are a
        # decision to re-make rather than a shape to absorb.
        print(
            f"REFUSED: curated families {stale} are not present in this dump. "
            f"Detected: {sorted(detected_skeletons)}",
            file=sys.stderr,
        )
        return 1

    # A market in a family must NOT also produce a card of its own. Without this
    # the register would carry both the comparison and the single-subject cards
    # it replaced, which is the repetition Alex ruled out arriving by a different
    # door.
    family_markets = {ext for f in families for ext in f.market_exts}
    claimed_by_both = family_markets & set(curation)
    if claimed_by_both:
        print(
            f"REFUSED: {sorted(claimed_by_both)} is curated as its own card AND is a "
            "member of a detected template family. Pick one.",
            file=sys.stderr,
        )
        return 1

    props: list[dict] = []
    skipped: list[str] = []
    for market_ext, market_rows in sorted(by_market.items()):
        if market_ext in family_markets:
            # A member of a detected family, consumed by its combined card
            # below. Not skipped, and not below the bar.
            continue
        spec = curation.get(market_ext)
        if spec is None:
            # In the dump but not curated. Not an error — it is the bar working.
            skipped.append(market_ext)
            continue

        answer_name = spec.get("answer")
        names = [str(r["outcome_name"]) for r in market_rows]
        if answer_name is not None and answer_name not in names:
            # REFUSE, loudly. The alternative is a card with a question and no
            # answer, which the renderer would fall back to ranking — quietly
            # turning a curated question into a field list because a source
            # renamed an outcome. A curation that no longer matches its market
            # is a curation decision to re-make, not a shape to absorb.
            print(
                f"REFUSED {market_ext}: curated answer {answer_name!r} is not an "
                f"outcome of this market. Present: {names}",
                file=sys.stderr,
            )
            return 1

        props.append({
            "key": spec["key"],
            "title": spec["title"],
            "hook": spec["hook"],
            "draw": spec["draw"],
            "source": market_rows[0]["source"],
            "market_id": market_rows[0]["market_id"],
            "market_external_id": market_ext,
            "markets": [
                {"market_id": market_rows[0]["market_id"], "market_external_id": market_ext}
            ],
            "outcomes": [
                {
                    "entity_key": f"{spec['key']}:{str(r['outcome_name']).lower().replace(' ', '-')}",
                    "display_name": r["outcome_name"],
                    "outcome_id": r["outcome_id"],
                    "is_answer": str(r["outcome_name"]) == answer_name,
                    # PER-OUTCOME PROVENANCE, on every card and not only the
                    # combined ones. It is what makes "these two numbers come
                    # from two different markets" a readable property of the
                    # file rather than something a reader of it has to infer,
                    # and the committed-register guard asserts the answer rule
                    # off exactly this field.
                    "market_id": r["market_id"],
                    "market_external_id": market_ext,
                }
                for r in market_rows
            ],
            "evidence": {
                "kind": "prop-census",
                "observed_at": args.observed_at,
                "market_name": market_rows[0]["market_name"],
                "answer": answer_name,
            },
        })

    # ── One card per DETECTED family: one question, one row per member ───────
    #
    # UX-P151 built this loop from a hand-written list of legs; UX-P154 builds it
    # from `detect_template_families`. Nothing below names a ticker, a player or
    # a count — the family says who is in it, and the curation says what the
    # question is called.
    #
    # Every refusal here is loud and fatal, and that is the whole design. A
    # comparison card that quietly loses a member is WORSE than no card: it
    # prints one man's number under "who wins", which is the exact class of
    # defect UX-P134 fixed when it stopped a ladder maximum answering a slam
    # question.
    for family in sorted(families, key=lambda f: f.skeleton):
        spec = FAMILY_CURATION[family.skeleton]
        key = spec["key"]
        compare = spec["compare_outcome"]

        # THE COMPARISON MUST COME OUT OF THE SHARED SET. `family.signature` is
        # the INTERSECTION of the members' outcome names, so an outcome one
        # member does not offer cannot be named here — which is the check that
        # makes "one column, same question, every member" true by construction
        # rather than by the curator having looked.
        if outcome_signature([compare]) and outcome_signature([compare])[0] not in (
            family.signature
        ):
            print(
                f"REFUSED {key}: compared outcome {compare!r} is not offered by every member "
                f"of {family.skeleton!r}. Shared outcomes: {list(family.signature)}.",
                file=sys.stderr,
            )
            return 1

        outcomes: list[dict] = []
        legs_evidence: list[dict] = []
        for member in family.members:
            market_rows = by_market[member.market_ext]
            match = [r for r in market_rows if str(r["outcome_name"]) == compare]
            if len(match) != 1:
                names = [str(r["outcome_name"]) for r in market_rows]
                print(
                    f"REFUSED {key}: compared outcome {compare!r} matched {len(match)} rows "
                    f"in {member.market_ext}. Present: {names}",
                    file=sys.stderr,
                )
                return 1
            row = match[0]
            slug = member.display_name.lower().replace(" ", "-")
            outcomes.append({
                "entity_key": f"{key}:{slug}",
                # THE SOURCE'S OWN WORDS (Alex, item 4). Derived from the
                # market's own title, not curated — see `subject_display`.
                "display_name": member.display_name,
                "outcome_id": row["outcome_id"],
                # NO ANSWER, by construction — see FAMILY_CURATION's note. A
                # family has one candidate answer per member, so no single
                # outcome answers the question; the card is a field and the
                # renderer ranks it.
                "is_answer": False,
                "market_id": row["market_id"],
                "market_external_id": member.market_ext,
            })
            legs_evidence.append({
                "market_external_id": member.market_ext,
                "market_name": member.market_name,
                "source_outcome_name": compare,
                # The DERIVATION is what is recorded now, not a rename. Two
                # facts a reader of this file can check against the market
                # title: the subject the detector isolated, and the skeleton
                # every member shares.
                "subject": member.display_name,
            })

        # One `source` on the card, so it has to be true of every member. A
        # cross-source comparison is a real thing to want and this shape cannot
        # honestly describe it, so refuse rather than pick the first one.
        member_sources = {member.source for member in family.members}
        if len(member_sources) != 1:
            print(
                f"REFUSED {key}: members span {sorted(member_sources)} and the card carries "
                "one `source`. A cross-source card needs a shape that can say so.",
                file=sys.stderr,
            )
            return 1

        props.append({
            "key": key,
            "title": spec["title"],
            "hook": spec["hook"],
            "draw": spec["draw"],
            "source": member_sources.pop(),
            "markets": [
                {
                    "market_id": o["market_id"],
                    "market_external_id": o["market_external_id"],
                }
                for o in outcomes
            ],
            "outcomes": outcomes,
            "evidence": {
                "kind": "prop-census-family",
                "observed_at": args.observed_at,
                # THE DETECTION IS THE EVIDENCE. `skeleton` is the shared
                # question the detector found and `shared_outcomes` is the set
                # every member offers — the two facts that make this one card
                # rather than N. A reader of the register can check both against
                # the market titles without running anything.
                "skeleton": family.skeleton,
                "shared_outcomes": list(family.signature),
                "legs": legs_evidence,
                "answer": None,
            },
        })

    register["props"] = props
    # Merged, never replaced: the hand-written UX-P139 grid-cell reasons stay.
    register["props_declined"] = {**(register.get("props_declined") or {}), **RETIRED}
    register["version"] = args.version
    register["supersedes_version"] = args.supersedes_version

    # `generated_at` is DELIBERATELY not advanced (UX-P134). It means "when the
    # data in this register was observed", and a props-only pass observed only
    # props — the draw, the players and the matchups were not re-read. Stamping
    # the whole file with this run's clock claims otherwise.
    #
    # That is not a nicety. `test_committed_slate_carries_no_already_played_match`
    # derives its floor from `generated_at`, so bumping it silently moves the
    # staleness bar for 66 matchups that nobody re-observed, and a match that was
    # legitimately in the window at generation time starts failing. The first run
    # of this pass did exactly that and the guard caught it.
    #
    # Each prop carries its own `evidence.observed_at`, which is where a
    # props-pass timestamp belongs.
    register["props_observed_at"] = args.observed_at

    findings = validate_register(register, us_open_2026_contract())
    verdict = classify(findings)

    print(f"curated props: {len(props)}")
    for prop in props:
        tickers = ", ".join(m["market_external_id"] for m in prop["markets"])
        print(f"  {prop['key']}: {len(prop['outcomes'])} outcomes ({tickers})")
    print(f"in the dump but below the bar: {len(skipped)} {skipped}")
    missing = sorted(set(curation) - set(by_market))
    if missing:
        print(f"curated but ABSENT from the dump: {missing}")
    # NO SILENT DETECTION. What the detector found is printed on every run, with
    # the subjects it isolated, because a family that quietly gains or loses a
    # member changes what a card says and nothing else would report it.
    print(f"template families detected: {len(families)}")
    for family in families:
        subjects = ", ".join(m.display_name for m in family.members)
        print(
            f"  {family.skeleton!r} -> {FAMILY_CURATION[family.skeleton]['key']} "
            f"[{subjects}]"
        )
    print(f"retired into a combined card: {sorted(RETIRED)}")
    print(f"findings: {findings or 'none'}")
    print(f"verdict:  {verdict}")

    if verdict["classification"] == "invalid":
        print("REFUSING TO WRITE — register does not validate.", file=sys.stderr)
        return 1

    out = Path(args.out or args.register)
    out.write_text(json.dumps(register, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
