"""UX-P259 / #2579 — the tournament a player can win is reachable by typing their name.

THE DEFECT, measured in production 2026-09-01.

`GET /api/events/search?q=Alcaraz` returned 10 futures during the US Open and
**none of them was a US Open winner market** — the one where Alcaraz is the 36.5%
favourite, which is simultaneously the headline board on `/tournaments/us-open`,
a `/sports` Top Market, and on the Discover home page. Same for Sabalenka, Gauff,
Swiatek, Zverev, Djokovic, Fritz. The more famous the player, the worse it got.

WHY, and it is entirely mechanical (`routes/events.py`, the futures ORDER BY):

    _futures_name_tier.asc()      # 0 = name match, 1 = ticker/alias, 2 = outcome-only
    futures_search_rank.desc()    # ts_rank_cd over the NAME vector only
    FuturesMarket.market_tier.asc()
    ...
    .limit(_SEARCH_FUTURES_WINDOW)          # 20

`market_tier` — the site's own market-QUALITY prior — sorts THIRD, behind a
relevance tier that is absolute. So every name match outranks every outcome-only
match no matter how good the market is, and the 20-row window is filled before
an outcome-only row is ever considered. Measured open-market counts:

    term        name matches   outcome-only matches   winner market on page?
    Alcaraz         41                 19                    NO
    Sabalenka       16                 14                    NO
    Mahomes          4                 33                    yes

Mahomes is the control that proves the mechanism: he has only 4 name matches, so
6 window slots are left over and his outcome-only markets DO surface. Nothing is
special about tennis — it is arithmetic on the window.

`_fetch_futures_window` makes it exact: it fetches the tier<=1 arms first and
**skips the outcome arm entirely** when they already fill 20 rows. For `Alcaraz`
the outcome arm never runs at all.

This was predicted. `routes/events.py` (LAT-P032, #1732) says of this ORDER BY:

    "outcome-only matches already score ~0 on the name vector, so the real defect
     may be that tier separation is not enforced at the page boundary — a RANKING
     fix, not a recall one. Verify that before deleting anything."

Verified above, and this module is that fix, shipped on its own gate as #1732 asked.

THE RULE — a "headline contender" market, and every clause was chosen by replaying
candidate rules over the live corpus rather than by reasoning about them:

  1. `market_tier == 1`. NOT `<= 2`. Tier 2 admits exactly the junk #993 was
     written to keep out: replaying `<= 2` promoted "Jimmy Fallon: Guests in 2026",
     "Vogue (US) 2026: Cover Models", "Call Her Daddy: Guests this year",
     "#1 Searched Person on Google" and "Who will attend Taylor Swift and Travis
     Kelce's wedding?" — the last one twice, for Patrick AND Brittany Mahomes.
  2. A WHOLE-WORD outcome match, not a substring. This is the clause that keeps
     the documented `fed` collision out: `fed` is not a word in "Russian
     Federation", "Confederation" or "Julie Fedorchak", so none of them can reach
     this lane. (#1732 measured those as 7 of 20 rows — 35% of the page.)
  3. `current_probability >= MIN_CONTENDER_PROBABILITY`. The entity must be a real
     contender in the market, not a listed joke. This is #993's distinction made
     numeric: "LeBron James" appears as an outcome of presidential-run markets,
     and a market where you are a 1% longshot is not a market about you.
  4. `volume >= MIN_CONTENDER_VOLUME`. Measured separation on the live corpus:

         term        best headline-contender market            volume
         Gauff       2026 Women's US Open Winner (Tennis)    5,819,053
         Sabalenka   2026 Women's US Open Winner (Tennis)    5,819,053
         Alcaraz     2026 Men's US Open Winner (Tennis)      4,108,808
         Alcaraz     US Open Men's Singles Winner              470,270
         Sabalenka   WTA Toronto Winner                         61,326
         ---------------------------------------------------- floor ---
         Jordan      NASCAR Winn-Dixie 250 Team Winner           2,534
         Jordan      MO-04 House winner?                         2,273
         Trump       Snooker China Open 2026: Winner               140
         Djokovic    Cincinnati Open: Winner                      NULL

     Two orders of magnitude of daylight. The floor is what makes it safe to put
     these rows at the TOP of the page: `Trump` (Judd Trump, snooker) and
     `Jordan` (five unrelated people named Jordan) produce **no** rows at all and
     their pages stay byte-identical. It also drops "Cincinnati Open: Winner",
     a volume-NULL, resolution_date-NULL stale market that would otherwise have
     outranked the US Open during the US Open (that staleness is #2510/#2513,
     not this queue).

REPLAYED, not argued. Over the live corpus the rule returns ZERO rows for every
term the route's history says must not move — `fed`, `LeBron`, `Mahomes`,
`president`, `recession`, `Trump`, `Jordan` — and returns the tournament winner
market for every term in the bug report. A term that yields nothing costs the
page nothing: the merge below is a no-op on an empty reserved list.

This module is PURE — no ORM, no I/O, no imports from `app`. The SQL that finds
the candidate rows lives at the one call site in `routes/events.py`; everything
that DECIDES lives here, so it can be replayed over fixtures.
"""

from __future__ import annotations

import re

# A market must be tier 1 to earn a reserved slot. See clause 1 above — tier 2 was
# measured and rejected, it is not an untried tightening.
HEADLINE_MARKET_TIER = 1

# The typed entity must be a real contender in the market, not a listed longshot.
MIN_CONTENDER_PROBABILITY = 0.05

# #6430 — THE SAME FLOOR, WHEN THE OUTCOME IS ANCHORED TO A TEAM WE HOLD.
#
# Clause 3 above asks "is this market about you?" and answers it with a price,
# because price was the only signal to hand. Price is field-size-blind, and in a
# large field it answers wrongly. Measured on production 2026-09-19,
# `MLB World Series Champion 2026` (114584, tier 1, volume 40,784,846):
#
#     field 31 outcomes, mean 3.49%, only 7 of 31 at or above 0.05
#     Dodgers 0.3050  -> promoted    (q=dodgers serves the market at row 1)
#     Yankees 0.1050  -> promoted    (q=yankees  serves the market at row 1)
#     Boston Red Sox 0.0455 -> REFUSED, and it is the only failing clause
#
# So 24 of 31 MLB clubs cannot reach their own championship market by typing
# their name, including clubs ABOVE the field mean — the Red Sox are 9th of 31
# and 1.3x the average. A Dodgers fan gets the World Series card; a Red Sox fan
# gets ten tier-5 "1st Inning Winner" rows and no championship question at all.
#
# THE REPAIR IS NOT A FIELD-RELATIVE FLOOR, AND THE CORPUS IS WHY. Replaying
# `min(0.05, 1/field)` over the live tier-1 volume>=10k corpus admits:
#
#     112897   Presidential Election Winner 2028          128 outcomes, 5 priced >= 0.05
#     56775566 Pro Football Championship Game Matchup     256 outcomes, top price 0.035
#
# — which is clause 3's own LeBron case, reintroduced wholesale. Field size does
# not separate a 31-club championship from a 128-name presidential field.
#
# IDENTITY DOES. `futures_outcomes.team_id` is an anchored correspondence to a
# club row we hold, not a string that happens to match. Measured the same minute:
#
#     114584   MLB World Series Champion 2026        31 outcomes, 30 with team_id
#     112897   Presidential Election Winner 2028    128 outcomes,  0 with team_id
#     56775566 Pro Football Championship Matchup    256 outcomes,  0 with team_id
#
# The two markets that would have poisoned a price-relative floor are excluded
# BY CONSTRUCTION, and the 25 markets the anchor does admit are the league
# championships a fan means: College Football National Championship, Pro
# Football 2027 Champion, the World Series, the conference titles, Champions
# League, F1 Constructors. So for an anchored outcome the identity IS the
# contender evidence, and the price clause relaxes to a priced-at-all floor.
#
# THERE IS NO ANCHORED PRICE FLOOR, AND CERT-3125 IS WHY.
#
# The first version of this arm kept a sub-floor of 0.005, chosen off the price
# histogram (a 144-row mode at the venues' 1c tick over a thin dust tail). That
# floor was measured against the wrong question. It admits 14 of the World
# Series market's 30 anchored clubs, so the ship this arm exists to deliver —
# "a correctly anchored club reaches its championship market by typing its
# name" — still fails for sixteen clubs, the Diamondbacks among them at 0.0015
# against a real two-sided book (bid 0.0010 / ask 0.0020). A floor that answers
# "is this club likely to win" cannot answer "is this market about this club",
# and the second is the only question this lane asks.
#
# PRICE IS NOT THE DISCRIMINATOR. IDENTITY AGREEMENT IS. Dropping the floor with
# nothing in its place is not safe either, and the corpus says so by name:
# `Coach of the Year Winner` (416, tier 1, volume 12,179,061) carries the
# outcome "Mike Brown" anchored to team 11 NEW ENGLAND PATRIOTS and "Will Hardy"
# anchored to team 6 NORTH CAROLINA TAR HEELS, both at 0.000000. A bare
# `team_id IS NOT NULL` makes a coach's name a headline contender on a mis-anchor
# — clause 3's poison arriving through the anchor instead of through the string.
#
# So an anchored outcome qualifies when the anchor CORRESPONDS: the outcome's own
# name agrees with the name of the team it is anchored to. Two independent
# signals that must say the same thing, which is ruling 048's shape (an
# id-anchored correspondence, never an id-less claim). Measured on production
# 2026-09-19, market 114584: 28 of 30 anchored outcomes agree; the 2 that do not
# are "New York Mets" anchored to NEW YORK YANKEES and "Los Angeles Angels"
# anchored to LOS ANGELES DODGERS — the same team-identity poison #7188 is
# repairing, which this rule correctly REFUSES rather than papers over. When
# #7188 lands those two become 30 of 30 here with no change to this file.
#
# 🔴 SAY THE COST OUT LOUD (CERT-3128). "Correctly refused" is still a reader
# losing something: a fan typing "mets" gets no championship card at row 1 and
# "angels" gets none at all, measured the same minute. This ship's reach is
# therefore EVERY CORRECTLY ANCHORED CLUB — 28 of 30 here — and not the whole
# field; an earlier draft claimed the whole field and CERT-3128 blocked it for
# the difference. The gap is carried on **#7233**, its fix is #7188's ordered
# data repair (lane1's by D39), and the fix is NOT to loosen this rule: dropping
# the correspondence term to rescue those two re-admits "Mike Brown" below.
#
# THE WHOLE CORPUS REPLAY, tier 1 + volume >= 10,000, newly-admitted outcomes:
#
#     400     La Liga Winner                       17
#     114584  MLB World Series Champion 2026       14
#     399     English Premier League Winner?       12
#     129037  Pro Football: 2027 Champion           8
#     392     Champions League Winner               7
#                                                  --
#                                          5 markets, 58 outcomes
#
# Five markets, every one a league championship a fan means. `Coach of the Year`
# is excluded by the correspondence term; `Presidential Election Winner 2028`
# (0 anchored) and `Pro Football Championship Game Matchup` (0 anchored) remain
# excluded by construction, as they were.
#
# PRICED AT ALL IS STILL REQUIRED — `current_probability IS NOT NULL`. A row with
# no number is not a quote and has nothing to render; a row at 0.000000 is the
# market saying this club cannot win, which is a true answer to "is this market
# about you" and is shown as part of the field, never as a number about the club.
#
# NAME-ONLY OUTCOMES ARE UNTOUCHED: every clause above still governs them, so
# `fed`, `LeBron`, `president`, `Trump` and `Jordan` cannot reach this lane by
# any new route. This arm can only ever ADD a market that lists a real club.

# The market must be one people actually trade. `volume` is not a new signal here:
# it is already an ORDER BY key in the futures window and `_rerank_search_futures`
# calls it "the real-interest signal". See the measured table above for the floor.
MIN_CONTENDER_VOLUME = 10_000

# ONE reserved row. #993's "name-match beats outcome-only-match" still governs
# every other slot on the page.
#
# One and not two, and this is a correctness bound rather than caution. The
# route's `_normalize_futures_dedup_key` does NOT merge the two-source pair —
# measured on the live rows:
#
#     114159   "2026 Men's US Open Winner (Tennis)"  ->  name:men s us open champion tennis:1
#     34277822 "US Open Men's Singles Winner"        ->  name:us open men s singles champion:1
#
# Two keys, one question. At cap 2 those are exactly the top two rows `Alcaraz`
# returns, so the page would open with the same market twice at 35.5% and 36.5%
# — Alex's standing ruling ("the blend is the product; one number per question,
# source divergence is a data bug to fix, not a feature to show") violated by
# the very fix meant to answer the question. The cross-source merge is #2163's
# canonical-key work; until it lands, one row is the honest number.
#
# `promote_headline_contenders` takes `dedup_key` and honours it, so raising
# this is a one-line change the day that merge exists — but raise it THEN, and
# re-measure the pair first.
MAX_HEADLINE_SLOTS = 1

# Cost guard, mirroring `_has_extractable_trigram` in `routes/events.py`: a term
# with no 3-character alphanumeric run is unservable by a pg_trgm GIN and would
# seq-scan `futures_outcomes` (3.9M rows / 3 GB). Such a term is refused outright
# rather than made cheap-ish — this lane is a bonus, never a cost centre.
MIN_TERM_ALNUM_RUN = 3


def contender_word_pattern(term: str) -> str | None:
    """The POSIX whole-word regex for `term`, or None if it must not be searched.

    `\\m` / `\\M` are Postgres's start/end-of-word assertions. The term is reduced
    to alphanumeric runs joined by `\\s+`, which makes the output injection-proof
    by construction (no regex metacharacter can survive) and lets "Carlos Alcaraz"
    match an outcome stored with any whitespace between the words.

    Returns None for a term with no 3+ character alphanumeric run, so `fed`-length
    fragments and punctuation-only terms never reach the corpus.
    """
    if not term:
        return None
    words = [w for w in re.split(r"[^0-9A-Za-z]+", term) if w]
    if not words:
        return None
    if max(len(w) for w in words) < MIN_TERM_ALNUM_RUN:
        return None
    return r"\m" + r"\s+".join(words) + r"\M"


def contender_patterns(
    expanded: list[tuple[str, str | None]],
) -> list[str] | None:
    """One whole-word pattern per query term, or None if the query is ineligible.

    ANDed by the caller: "carlos alcaraz" must find an outcome matching BOTH words,
    the same all-terms-must-match semantics the route's other recall arms use. A
    query is ineligible the moment ANY of its terms is — a single unservable term
    would otherwise widen the lane back to the substring behaviour clause 2 exists
    to prevent.

    The EXPANSION is deliberately ignored. Synonym expansion ("champion" ->
    "winner") is a market-NAME device; an outcome is a competitor's name, and
    expanding it can only add collisions to a lane whose whole value is precision.
    """
    if not expanded:
        return None
    patterns = []
    for term, _expansion in expanded:
        pattern = contender_word_pattern(term)
        if pattern is None:
            return None
        patterns.append(pattern)
    return patterns


def is_contender_outcome(probability, volume, *, team_anchored: bool = False) -> bool:
    """The numeric half of the rule — clauses 3 and 4, on one outcome row.

    Kept here rather than only in SQL so a guard can assert the boundary values
    without a database, and so the two halves of the rule cannot drift apart.
    A probability of exactly 1.0 is admitted: `WTA Cincinnati Winner` carries a
    live 0.99 and there is no principled line between that and 1.0 — the volume
    floor is what excludes the degenerate rows, and it does so on merit.

    `team_anchored` — the outcome carries a `team_id` AND its own name agrees
    with that team's name, i.e. it IS a club we hold rather than a string that
    matched one or a mis-anchored row that merely carries an id (#6430 /
    CERT-3125, reasoning at the constants above). Such a row faces NO price
    floor: identity is the whole contender evidence, and the caller is
    responsible for establishing the correspondence — this function is told the
    answer, it does not guess it from `team_id` alone.

    It is keyword-only and defaults False so every existing caller and every
    replay corpus row keeps its exact previous verdict: this arm is strictly
    additive and can only widen, never refuse what it admitted before.

    The volume floor is NOT relaxed — identity answers "is this market about
    you", not "does anyone trade it". A price of None is still refused for both
    arms: a row with no number is not a quote.
    """
    if probability is None or volume is None:
        return False
    try:
        probability = float(probability)
        volume = float(volume)
    except (TypeError, ValueError):
        return False
    if volume < MIN_CONTENDER_VOLUME:
        return False
    if team_anchored:
        return True
    return probability >= MIN_CONTENDER_PROBABILITY


def promote_headline_contenders(
    page: list,
    contenders: list,
    *,
    cap: int = MAX_HEADLINE_SLOTS,
    dedup_key=None,
) -> tuple[list, int]:
    """Put up to `cap` headline-contender markets at the FRONT of `page`.

    Returns `(rows, promoted_count)`. Length is `max(len(page), promoted)` and
    therefore never exceeds the page size the caller already sliced to (`cap` is
    far below it): a full page is reordered and substituted, never grown. The
    only case that grows is a page shorter than `cap`, where there were free
    slots to begin with.

    At the front, not appended, and the volume floor is what earns that: every
    row that reaches here is a tier-1 market with real money on it where the
    person typed is a genuine contender. For `Alcaraz` mid-US-Open that is the
    US Open winner market, and burying the answer at rank 10 under
    "Roman Safiullin vs Carlos Alcaraz: Total Games" would be the same defect
    with a smaller number attached to it.

    A contender ALREADY ON THE PAGE is HOISTED to the front, not skipped, and
    still counts as promoted. UX-P272/#2668 is what that sentence is for. The
    older rule skipped it, on the reasoning that a row the page already holds
    needs no promotion — which is true only when `page` is what the caller
    SHIPS. `/search` slices to its shipped ten before calling here
    (`events.py`, `futures_markets = deduped_futures[:_SEARCH_FUTURES_PAGE]`),
    so for that caller the two readings agree. The typeahead passes its whole
    20-row window and ships the first five of it, so "already on the page"
    silently meant "already in a list the user may never see". Measured live
    2026-09-02: for `Alcaraz` the US Open winner market is row 1 of the raw
    window, `_rerank_search_futures` sinks it below nine name-matching props,
    the lane fired (27 ms stage mark), the promoter skipped it as already
    present, and the dropdown shipped five props and no answer.

    Hoisting rather than inserting is what keeps the no-duplicate guarantee
    exact: the row is RELOCATED, never added, so the returned length is
    unchanged and no question can appear twice. The guarantee the old comment
    claimed ("a promoted row can never restate something the page already
    holds") is therefore still true, and now the function's first sentence —
    contenders end up at the FRONT — is true as well.

    This is inert for `/search` BY CONSTRUCTION rather than by measurement: its
    lane only fires when every row of the shipped page is a name match, and a
    contender is outcome-only by the caller's own filter, so a contender that
    is already on that page makes the gate false and the lane never runs. The
    hoist branch is therefore unreachable from `/search`.

    Rows already on the page are reconciled by identity and, when `dedup_key`
    is given, a DIFFERENT market sharing the page's dedup key is still skipped
    — so a promoted row can never restate something the page already holds.
    Note that today's key does NOT merge the Kalshi/Polymarket pair for one
    tournament (see MAX_HEADLINE_SLOTS); the cap, not the key, is what keeps
    that question off the page twice. A key twin buried below the caller's
    visible cut is the one case this fix does NOT reach: it stays a skip,
    because hoisting a twin would change WHICH market's price the user reads,
    and no live specimen exists (the pair above normalizes to two keys).
    """
    if not contenders or cap <= 0:
        return page, 0

    seen_ids = {getattr(m, "id", None) for m in page}
    # Hoist the PAGE's own row, not the contender query's copy of it: the two
    # are separate result sets, and shipping the page's object keeps the
    # serialized row byte-identical to what the window would have produced.
    page_by_id: dict = {}
    for m in page:
        mid = getattr(m, "id", None)
        if mid is not None:
            page_by_id.setdefault(mid, m)
    seen_keys = set()
    if dedup_key is not None:
        seen_keys = {dedup_key(m) for m in page}

    promoted = []
    hoisted_ids: set = set()
    for market in contenders:
        if len(promoted) >= cap:
            break
        market_id = getattr(market, "id", None)
        if market_id in seen_ids:
            page_row = page_by_id.get(market_id)
            if page_row is None:
                # An id-less contender meeting an id-less page row: there is
                # nothing to reconcile the two by, so keep the conservative skip.
                continue
            hoisted_ids.add(market_id)
            promoted.append(page_row)
            continue
        if dedup_key is not None:
            key = dedup_key(market)
            if key in seen_keys:
                continue
            seen_keys.add(key)
        seen_ids.add(market_id)
        promoted.append(market)

    if not promoted:
        return page, 0

    # A hoisted row leaves the body of the page so it cannot appear twice; a
    # newly inserted one costs the page its weakest tail row. Both paths return
    # `len(page)`, which is why hoisting cannot grow the caller's page.
    rest = [m for m in page if getattr(m, "id", None) not in hoisted_ids]
    # Truncate from the TAIL: the rows that lose their slot are the weakest
    # name matches the window had, never the strongest.
    keep = len(page) - len(promoted)
    return promoted + rest[: max(keep, 0)], len(promoted)


def reserve_headline_slot(
    ranked: list,
    headline_market_ids,
    *,
    cap: int = MAX_HEADLINE_SLOTS,
    floor: int = 0,
) -> list:
    """Move up to `cap` already-earned headline markets to the FRONT of `ranked`.

    WHY A SECOND STEP EXISTS AT ALL (CERT-718, round one of this ship was blocked
    on exactly this). `promote_headline_contenders` puts the winner market first
    in the typeahead's *futures* list — and then `typeahead_search` sends every
    pool through `search_match_class.rank`, whose FIRST and inviolable sort key is
    the match class. The US Open winner market holds "Alcaraz" only as an OUTCOME,
    so it is MC4; every "… vs Carlos Alcaraz: Total Games" prop holds him in its
    own NAME, so each is MC1. The global scorer therefore undid the promotion in
    full. Measured on the real shape:

        after promote_headline_contenders   [winner, prop0, prop1, prop2, prop3]
        after search_match_class.rank       [prop0, prop1, prop2, prop3, winner]

    So the answer went to the BOTTOM of the dropdown — #2579's own defect with a
    smaller number attached, which is the thing `promote_headline_contenders`'
    docstring says must not happen.

    THE SHAPE OF THE FIX, and why it is a reservation rather than a scorer change.
    The tempting repair is to teach `search_match_class` that owned-contender
    evidence beats a name match. That would be wrong: MC1-before-MC4 is the rule
    that keeps `Chess Candidates 2026: Winner` off the page for `fed`, and it is
    load-bearing for every query, not just this one. #993 exists because that
    ordering was once absent. Weakening a universal rule to serve one lane trades
    a bounded bug for an unbounded one.

    Instead the scorer keeps its rule untouched and runs to completion, and ONE
    slot — `MAX_HEADLINE_SLOTS`, the same cap the page promotion honours — is
    reserved after it. The reservation is not a new judgement about relevance: the
    market has already passed tier 1, the whole-word outcome match, the
    probability floor and the volume floor before an id can reach here. This
    function only stops the scorer from discarding a decision that was already
    made on stricter evidence than the scorer has.

    APPLIED BEFORE THE `[:7]` SLICE, deliberately. The winner does not merely rank
    low — with five futures and two events all matching "Sabalenka" it lands in
    the seventh slot and the next candidate pushes it off the dropdown entirely.
    Reserving after truncation would rescue the visible case and lose the invisible
    one, and the invisible one is the reported bug.

    `floor` — THE RESERVATION RUNS INSIDE THE ORDERING POLICY, NOT OVER IT
    (#4614, #5059's decision B: "a later headline promotion can never override
    entity/game ordering"). The reservation's whole justification is that the
    scorer discards a decision made on STRICTER evidence than the scorer has —
    tier 1, a whole-word outcome match, a probability floor and a volume floor.
    That argument holds against a name match. It does NOT hold against a row the
    query RESOLVED, and shipping it as an unconditional hoist made it say the
    opposite of what it was for. Measured on production 2026-09-11:

        q=yankees   [MLB World Series Champion 2026, New York Yankees, game, …]
                     ^ MC4, the WORST class on the page, above an MC0 team card

    `red sox` had the same shape. The reservation had taken slot 0 from the team
    card whose name the user had typed in full — #4614 exactly, and the mirror of
    the defect this function was built to fix.

    So the caller passes the length of the leading entity block
    (`search_match_class.entity_prefix_len`) and the reservation inserts AFTER
    it: the resolved entity and its games keep the slots the scorer gave them,
    and the contender is reserved out of what remains — still ahead of every
    prop, which is the origin case (CERT-718: `Sabalenka` ships props first and
    no entity block, so the floor is 0 and the hoist is unchanged).

    A floor of 0 — the default, and what every caller that does not rank by class
    passes — restores the previous behaviour byte for byte.

    Pure and total: unknown ids, an empty list, a `cap` of zero and payloads of
    any shape are all no-ops that return `ranked` unchanged. Relative order among
    everything else is preserved, so the scorer's result still governs slots 2..n.
    """
    if cap <= 0 or not ranked or not headline_market_ids:
        return ranked
    wanted = {mid for mid in headline_market_ids if mid is not None}
    if not wanted:
        return ranked

    floor = max(0, min(int(floor), len(ranked)))

    # Indices, not membership: a page can hold two rows that compare equal, and
    # rebuilding `rest` by value would drop the wrong one.
    front_idx: list[int] = []
    for i, item in enumerate(ranked):
        # `i >= floor` — a contender that is ALREADY inside the protected block
        # is where the scorer put it. Moving it would be a no-op at best and a
        # reorder of the entity block at worst, so it is left alone.
        if (
            len(front_idx) < cap
            and i >= floor
            and isinstance(item, dict)
            and item.get("type") == "futures"
            and item.get("market_id") in wanted
        ):
            front_idx.append(i)

    if not front_idx:
        return ranked

    taken = set(front_idx)
    front = [ranked[i] for i in front_idx]
    rest = [item for i, item in enumerate(ranked) if i not in taken]
    # No contender was drawn from `rest[:floor]` (the `i >= floor` guard), so
    # this slice is still exactly the entity block the caller measured.
    return rest[:floor] + front + rest[floor:]
