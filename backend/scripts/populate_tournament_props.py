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

#: ONE CARD, TWO MARKETS — the shape a comparison question needs (UX-P151).
#:
#: ═══ ALEX'S RULING, 2026-08-28 ~10:45am PT, quoted ═══
#:
#: *"ONE COMBINED CARD — 'Who wins a second major this year?' — showing BOTH
#: players' probabilities (Alcaraz 2+ majors, Sinner 2+ majors, each from its
#: own real Kalshi market: KXGRANDSLAM-CALC26-family and KXGRANDSLAM-JSIN26)."*
#:
#: It resolves a tension the file had carried, unresolved, through three
#: queues.  UX-P138's note said the two ``*-second-major`` cards were *"one
#: templated question with the name swapped"*, and the fix that shipped for it
#: DELETED Alcaraz.  UX-P147 read Alex's *"I'd love to"* see both, restored
#: Alcaraz, and rekeyed the template cap so it could never collapse across
#: players — two cards, and the repetition Alex had objected to was back.
#:
#: Both readings were partial because both assumed the unit was a CARD PER
#: MARKET.  Drop that assumption and the two constraints stop fighting: one
#: card carrying both men's numbers has both players present and no template
#: repeated, which is the whole of what he asked for in each of the two notes.
#:
#: WHAT A LEG IS.  ``market_ext`` is the market the number comes from,
#: ``outcome`` is that market's own name for the leg (matched exactly, never
#: fuzzily), and ``display_name`` is what the row prints.  The rename is the
#: point: three rows reading "2+ Grand Slam wins" would be a threshold ladder,
#: and what the reader is comparing is two MEN.  Renaming a row is a curation
#: decision made once against the evidence — the same doctrine as the matchup
#: sides mapping — never a request-time guess.
#:
#: WHY NO ``answer``.  A card with a single headline number needs one outcome
#: that answers its question, and this one has two by construction.  So it is a
#: FIELD card: ``answer_entity_key`` is ``None``, the renderer ranks instead of
#: leading, and the "which number goes in the big type" question never has to
#: be guessed.  ``validate_prop`` has supported that shape since UX-P134; this
#: is the first curated card that uses it.
#:
#: WHAT THE HOOK IS DOING.  The title Alex wrote reads as a race — *who* wins —
#: and these are two INDEPENDENT binaries that can both resolve Yes: there are
#: four majors a year and each man needs two of them, not the same two.  Their
#: numbers do not sum to 100 and must never be normalised so they do (the same
#: rule the cycling GC field carries).  The title is his, verbatim; the hook is
#: what stops it being read as an exclusive race.
COMBINED_CURATION: dict[str, dict] = {
    "second-major": {
        "title": "Who wins a second major this year?",
        "hook": (
            "Both already have one in 2026. These are two separate questions — "
            "they could both do it, or neither."
        ),
        "draw": "mens-singles",
        "legs": [
            {
                "market_ext": "KXGRANDSLAM-CALC26",
                "outcome": "2+ Grand Slam wins",
                "display_name": "Alcaraz",
            },
            {
                "market_ext": "KXGRANDSLAM-JSIN26",
                "outcome": "2+ Grand Slam wins",
                "display_name": "Sinner",
            },
        ],
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
    keys = [spec["key"] for spec in curation.values()] + list(COMBINED_CURATION)
    if len(set(keys)) != len(keys):
        # Two curations writing one card key would silently drop one of them,
        # and the section would be short with nothing to point at.
        print(f"REFUSED: duplicate curation keys in {sorted(keys)}", file=sys.stderr)
        return 1

    # A market a combined card consumes must NOT also produce a card of its own.
    # Without this the register would carry both the comparison and the two
    # single-player cards it replaced, which is the repetition Alex ruled out
    # arriving by a different door.
    combined_markets = {
        leg["market_ext"] for spec in COMBINED_CURATION.values() for leg in spec["legs"]
    }
    claimed_by_both = combined_markets & set(curation)
    if claimed_by_both:
        print(
            f"REFUSED: {sorted(claimed_by_both)} is curated as its own card AND as a leg "
            "of a combined card. Pick one.",
            file=sys.stderr,
        )
        return 1

    by_market: dict[str, list[dict]] = {}
    for row in rows:
        by_market.setdefault(str(row["market_ext"]), []).append(row)

    props: list[dict] = []
    skipped: list[str] = []
    for market_ext, market_rows in sorted(by_market.items()):
        if market_ext in combined_markets:
            # Consumed by a combined card below. Not skipped, not below the bar.
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

    # ── The combined cards: one question, one leg per market (UX-P151) ───────
    #
    # Every refusal here is loud and fatal, and that is the whole design. A
    # comparison card that quietly loses a leg is WORSE than no card: it prints
    # one man's number under "who wins", which is the exact class of defect
    # UX-P134 fixed when it stopped a ladder maximum answering a slam question.
    for key, spec in sorted(COMBINED_CURATION.items()):
        outcomes: list[dict] = []
        legs_evidence: list[dict] = []
        for leg in spec["legs"]:
            market_rows = by_market.get(leg["market_ext"])
            if not market_rows:
                print(
                    f"REFUSED {key}: leg market {leg['market_ext']} is absent from the dump. "
                    "A comparison card missing a side is not a smaller card, it is a wrong one.",
                    file=sys.stderr,
                )
                return 1
            match = [r for r in market_rows if str(r["outcome_name"]) == leg["outcome"]]
            if len(match) != 1:
                names = [str(r["outcome_name"]) for r in market_rows]
                print(
                    f"REFUSED {key}: leg outcome {leg['outcome']!r} matched {len(match)} rows "
                    f"in {leg['market_ext']}. Present: {names}",
                    file=sys.stderr,
                )
                return 1
            row = match[0]
            outcomes.append({
                "entity_key": f"{key}:{leg['display_name'].lower().replace(' ', '-')}",
                "display_name": leg["display_name"],
                "outcome_id": row["outcome_id"],
                # NO ANSWER, by construction — see COMBINED_CURATION's note.
                # Two legs means no single outcome answers the question, so the
                # card is a field and the renderer ranks it.
                "is_answer": False,
                "market_id": row["market_id"],
                "market_external_id": leg["market_ext"],
            })
            legs_evidence.append({
                "market_external_id": leg["market_ext"],
                "market_name": row["market_name"],
                "source_outcome_name": leg["outcome"],
                "renamed_to": leg["display_name"],
            })

        # One `source` on the card, so it has to be true of every leg. A
        # cross-source comparison is a real thing to want and this shape cannot
        # honestly describe it, so refuse rather than pick the first one.
        leg_sources = {
            str(by_market[leg["market_ext"]][0]["source"]) for leg in spec["legs"]
        }
        if len(leg_sources) != 1:
            print(
                f"REFUSED {key}: legs span {sorted(leg_sources)} and the card carries one "
                "`source`. A cross-source card needs a shape that can say so.",
                file=sys.stderr,
            )
            return 1

        props.append({
            "key": key,
            "title": spec["title"],
            "hook": spec["hook"],
            "draw": spec["draw"],
            "source": leg_sources.pop(),
            "markets": [
                {
                    "market_id": o["market_id"],
                    "market_external_id": o["market_external_id"],
                }
                for o in outcomes
            ],
            "outcomes": outcomes,
            "evidence": {
                "kind": "prop-census-combined",
                "observed_at": args.observed_at,
                # The rename is recorded leg by leg. A curated display name that
                # nobody can trace back to the source's own outcome name is an
                # unfalsifiable claim about what a number means.
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
