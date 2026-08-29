"""THE PLAYOFF GRID — players x rounds, built from the register and nothing else.

UX-P139, Alex's AMENDMENT to ruling 3, which is the whole design brief:

    "Grid gaps are a dealbreaker" means FAILING A CRITICAL EVAL, not a
    rendering choice. ... Therefore: a blank cell, an improperly blended cell,
    or a cell populated from the WRONG future is a linkage defect — no excuse,
    no interpolation. The derived-value fallback is retired: a cell whose
    direct markets are not linked renders as an ALARM STATE naming the missing
    linkage, and the fix is linking the real markets — exactly like the league
    playoff grids, whose register+sentinel machinery this page reuses. The
    register carries per-player per-round market IDs from BOTH sources; the
    grid reads only the register; wrong-future placement (a reach-QF market
    feeding the SF cell) is a named eval failure, not a data quirk.

WHAT UX-P138 DID AND WHY IT WAS NOT ENOUGH.  The previous grid resolved cells
at RENDER time in the browser, from three unrelated shapes: the match list, the
curated props section, and the board.  It refused to compute — which was right
— but its coverage was whatever those three happened to contain, so the middle
of the grid was holes and the holes were the honest consequence of asking the
wrong three questions.  Alex read a player with a QF number, a title number and
a blank between them, and named it correctly: that is not sparsity, it is a
cell whose market was never linked.

WHAT CHANGED.  ``reaches`` in the register is now the single input.  Every
(player, round) the census touched has a row there — pinned to a market and an
outcome per source, or explicitly ``missing`` with an evidence timestamp saying
when we looked.  This module turns that into a grid and evaluates it.  It never
reads the match list, never reads the props, never multiplies anything.

═══ THE FIVE CELL STATES, AND WHY "BLANK" IS NOT ONE ═══

``live`` / ``stale`` / ``dark``
    A registered identity with a price, wearing the page's own freshness
    vocabulary (``tournament_board.price_state``).  Same three words the boards
    and the slate use — a fourth opinion about what old means is how two
    surfaces end up disagreeing about the same number.

``settled``
    The market resolved.  "Settled means settled": a result, never a
    probability beside it.

``no_market``
    Every source was censused for this cell and none of them carries a future
    for it.  This is a RESULT, not a gap, and it is the state the amendment's
    axiom did not anticipate — see the census note below.  It renders as
    "no market", carries the date we last looked, and is counted separately
    from every failure state so it can never be mistaken for one.

``unlinked`` and ``unregistered`` — THE ALARM STATES
    ``unlinked``: the register pins an identity for this cell and the database
    returned nothing for it.  The market exists, the link is broken.  **ANY
    registered leg that fails to load raises this**, including the case where
    the other leg loaded fine: a two-source cell missing one source is a broken
    two-source claim, not a one-source answer, and it publishes no number.
    ``unregistered``: the register carries no cell at all for a (player, round)
    the grid has a column for.  Nobody censused it.
    Both are OUR defect, both name the missing linkage in the cell itself, and
    both are counted into ``alarms`` so a grid with any of them cannot read as
    healthy.

═══ THE CENSUS, MEASURED 2026-08-26, AND THE ONE PLACE IT CONTRADICTS THE AXIOM ═══

The amendment's axiom is that both sources carry a future for every player and
every round.  Measured against both sources' own inventories rather than ours:

  * **Kalshi carries ZERO round-advancement futures for this tournament.**  Its
    entire US Open inventory is five markets: the two outright winner fields,
    two "will X play" markets and a ticket-price market.  There is no series to
    link.
  * **Polymarket carries exactly 336** — 8 events, ``To Reach {R16, QF, SF,
    Final}`` x {Men's, Women's} — covering **44 of 128 men and 40 of 128
    women**, and only those four rounds.  Verified against Gamma directly
    (``/events/910171`` returns 44 markets), so this is upstream inventory and
    not an ingest shortfall.
  * Within that population coverage is **total**: all 84 players carry all four
    rounds.  There is not one player with a QF price and a blank SF — the
    specific defect Alex named is eliminated outright for every row that has a
    ladder at all.
  * Twelve men's and sixteen women's board contenders have no ladder on either
    source, Sinner among them.

So the honest grid has ``no_market`` cells and the axiom is not met.  The
important part is that the amendment's actual demand IS met: no cell is blank,
no cell is interpolated, no cell is fed by another round's future, every cell
states which market answers it or that none does, and every failure is an alarm
rather than a shrug.

═══ THE TWO EVALS ═══

``column_sums``
    Alex's ruling 4.  P(reach round R) over the whole field must sum to the
    round's slot count: 16 for R16, 8 for QF, 4 for SF, 2 for the Final, 1 for
    the title.  Reported per column with its ratio and a verdict.  It is a
    DIAGNOSTIC, never a corrector: nothing here rescales a column to make it
    add up, because a rescaled price is a fabricated one.

``monotonicity``
    A player cannot be likelier to reach the final than the semis.  Checked
    across each row's own cells left to right, including the title column.
    Violations are named per player and per adjacent pair.

Pure logic.  Every input is a plain dict, so the whole grid is testable without
a database.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from app.utils.futures_source_merge import blend_with_verdict
from app.utils.market_liquidity import LIQUIDITY_UNKNOWN, thinnest_liquidity
from app.utils.tournament_board import (
    _age_hours,
    draw_label,
    freshest_observation,
    governing_age_hours,
    price_state,
)
from app.utils.tournament_register import TournamentRegister, ROUNDS, player_image

logger = logging.getLogger(__name__)

#: How many players a round admits — the denominator of Alex's sum check.
#: ``qualifying`` is absent on purpose: it has no fixed slot count (128 main
#: draw entrants arrive from three different routes), so a sum check on it
#: would be a number with no expectation to compare against.
ROUND_SLOTS: dict[str, int] = {
    "R128": 128,
    "R64": 64,
    "R32": 32,
    "R16": 16,
    "QF": 8,
    "SF": 4,
    "F": 2,
    "title": 1,
}

#: How far a column's sum may sit from its slot count and still pass.
#:
#: A RATIO band, not an absolute one, because the same 0.3 that is noise on a
#: 16-slot column is a 15% error on a 2-slot one.  ±10% is wide enough to
#: absorb the overround these binaries carry (measured pair sums: mean 0.99 to
#: 1.00 across all eight ladders) and narrow enough that the Final column's
#: measured 1.39x is reported as the failure it is.
COLUMN_SUM_TOLERANCE = 0.10

#: A monotonicity break smaller than this is arithmetic noise on a rounded
#: quote, not a market disagreement.  Half a point.
MONOTONICITY_EPSILON = 0.005

CELL_LIVE = "live"
CELL_STALE = "stale"
CELL_DARK = "dark"
CELL_SETTLED = "settled"
CELL_NO_MARKET = "no_market"
#: THE ALARM STATES. Registered but the price never loaded / never registered.
CELL_UNLINKED = "unlinked"
CELL_UNREGISTERED = "unregistered"

ALARM_STATES = (CELL_UNLINKED, CELL_UNREGISTERED)
PRICED_STATES = (CELL_LIVE, CELL_STALE, CELL_DARK)

#: Column headers.  Short for a 390px phone; the SENTENCE travels beside it
#: because UX-P137's ruling 2 was Alex unable to tell what a bare percentage
#: meant, and "SF" alone is the same failure in a header.
SHORT_LABELS: dict[str, str] = {
    "qualifying": "Qual",
    "R128": "R128",
    "R64": "R64",
    "R32": "R32",
    "R16": "R16",
    "QF": "QF",
    "SF": "SF",
    "F": "Final",
    "title": "Title",
}

LONG_LABELS: dict[str, str] = {
    "qualifying": "To come through qualifying",
    "R128": "To reach the first round",
    "R64": "To reach the round of 64",
    "R32": "To reach the round of 32",
    "R16": "To reach the round of 16",
    "QF": "To reach the quarter-finals",
    "SF": "To reach the semi-finals",
    "F": "To reach the final",
    #: A DIFFERENT QUESTION, and it gets a different word. "Reach the final" and
    #: "win the title" are two markets and one is strictly harder; a last column
    #: that silently switched verbs under a shared header would re-commit the
    #: exact defect ruling 2 was issued about.
    "title": "To win the title",
}


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _cell(
    state: str,
    *,
    probability: Optional[float] = None,
    sources: Optional[list[dict[str, Any]]] = None,
    observed_at: Optional[datetime] = None,
    age_hours: Optional[float] = None,
    note: Optional[str] = None,
    censused_at: Optional[str] = None,
    blend_rule: Optional[str] = None,
    divergent: bool = False,
    liquidity: str = LIQUIDITY_UNKNOWN,
    liquidity_reasons: Optional[list[str]] = None,
) -> dict[str, Any]:
    return {
        "state": state,
        "probability": round(probability, 6) if probability is not None else None,
        # The field a client cannot round past: only a `live` cell may wear the
        # confident type. Same contract as the boards'.
        "probability_is_live": state == CELL_LIVE and probability is not None,
        "sources": sources or [],
        "source_count": len(sources or []),
        "observed_at": observed_at.isoformat() if observed_at else None,
        "age_hours": round(age_hours, 2) if age_hours is not None else None,
        "blend_rule": blend_rule,
        "divergent": divergent,
        # WHAT IS WRONG, IN WORDS, ON THE CELL. An alarm the reader cannot read
        # is a muted number with no stated reason — the failure CERT-411 named
        # on the props cards, one surface over.
        "note": note,
        # When we last LOOKED. The difference between "no market exists" and
        # "nobody has checked", which is the difference between an honest empty
        # and a stale claim about the world.
        "censused_at": censused_at,
        "is_alarm": state in ALARM_STATES,
        # ── HOW THIN THE MARKET BEHIND THIS NUMBER IS (UX-P157, #2256/#2257).
        # Defaults to `unknown` on every non-priced state, which is the truth:
        # a settled cell, a no-market cell and an alarm have no live book to
        # grade. `unknown` draws nothing, so those cells are unchanged.
        #
        # THIS FIELD MAY NEVER DECIDE WHETHER A CELL RENDERS. Alex's ruling and
        # the grid charter both forbid deleting a thin cell; Q428 measured what
        # filtering on this signal would cost (416 priced cells -> ~120) and
        # refused it. It is a mark beside the number, and nothing else.
        "liquidity": liquidity,
        "liquidity_reasons": sorted(liquidity_reasons or []),
    }


def _price_cell(
    blocks: list[dict[str, Any]],
    prices: dict[int, dict[str, Any]],
    *,
    now: datetime,
    cell_label: str,
) -> dict[str, Any]:
    """One reach cell from its registered source blocks.

    THE BLEND, and why it is the same call the boards make.  Alex's ruling 3
    asks for both sources "blended elegantly"; elegance here is *not writing a
    second blender*.  ``blend_with_verdict`` already carries the divergence
    gate and the equal-weight midpoint rule that the championship board and the
    events hero use, and the standing ruling is that the blend is the product —
    one number per question.  A grid with its own averaging rule would be a
    second opinion about the same two prices, printed one tab away from the
    first.
    """
    censused = sorted(
        (
            str(b.get("evidence", {}).get("observed_at"))
            for b in blocks
            if isinstance(b.get("evidence"), dict) and b.get("evidence", {}).get("observed_at")
        ),
        reverse=True,
    )
    censused_at = censused[0] if censused else None

    live_blocks = [b for b in blocks if b.get("status") == "live"]
    settled_blocks = [b for b in blocks if b.get("status") == "settled"]
    missing_blocks = [b for b in blocks if b.get("status") == "missing"]

    if not live_blocks and settled_blocks:
        # Settled means settled. The terminal result IS the state and there is
        # no probability beside it.
        result = str(settled_blocks[0].get("terminal_result") or "settled")
        return _cell(
            CELL_SETTLED,
            note=result,
            censused_at=censused_at,
            sources=[{"source": b.get("source"), "state": "settled"} for b in settled_blocks],
        )

    if not live_blocks:
        if missing_blocks:
            # THE CENSUSED ABSENCE. Both sources were asked and neither carries
            # a future for this question. Named per source so the reader (and
            # the next population pass) knows which one to go and look at.
            names = ", ".join(sorted({str(b.get("source")) for b in missing_blocks}))
            return _cell(
                CELL_NO_MARKET,
                note=f"No {cell_label} market at {names}",
                censused_at=censused_at,
                sources=[
                    {"source": b.get("source"), "state": "missing"} for b in missing_blocks
                ],
            )
        # A cell whose source list held nothing usable. The register validator
        # rejects this shape (`REACH_NO_SOURCES`), so reaching it means a
        # register was loaded past validation — loud, and never a blank.
        return _cell(
            CELL_UNREGISTERED,
            # UX-P145: user-visible via the cell tooltip. Was "Cell registered
            # with no source blocks — census incomplete".
            note="We have not found a market for this question yet",
            censused_at=censused_at,
        )

    blend_rows: list[dict[str, Any]] = []
    source_views: list[dict[str, Any]] = []
    unlinked_views: list[dict[str, Any]] = []
    observed_times: list[Optional[datetime]] = []
    unlinked: list[str] = []
    # A blended cell is only as solid as its THINNEST book — the same rule
    # `governing_age_hours` applies to age, for the same reason: the reader sees
    # one number, so the number answers for everything inside it.
    leg_liquidity_levels: list[Optional[str]] = []
    leg_liquidity_reasons: set[str] = set()

    for block in live_blocks:
        loaded = prices.get(block.get("outcome_id")) or {}
        probability = _as_float(loaded.get("probability"))
        observed = loaded.get("observed_at")
        observed = observed if isinstance(observed, datetime) else None

        if probability is None:
            # ── THE ALARM. The register pins market_id/outcome_id for this
            # exact question and the load came back with nothing. The market is
            # real; the link between it and this cell is broken. Named with the
            # identity so the fix is a lookup, not an investigation.
            unlinked.append(
                f"{block.get('source')} {block.get('market_external_id') or block.get('market_id')}"
            )
            unlinked_views.append({
                "source": block.get("source"),
                "state": "unlinked",
                "market_external_id": block.get("market_external_id"),
            })
            continue

        blend_rows.append({"source": block.get("source"), "probability": probability})
        source_age = _age_hours(observed, now)
        leg_liquidity = (loaded.get("liquidity") or {}).get("level")
        source_views.append({
            "source": block.get("source"),
            "probability": round(probability, 6),
            "observed_at": observed.isoformat() if observed else None,
            "age_hours": round(source_age, 2) if source_age is not None else None,
            "price_state": price_state(source_age),
            "market_external_id": block.get("market_external_id"),
            "liquidity": leg_liquidity,
        })
        observed_times.append(observed)
        leg_liquidity_levels.append(leg_liquidity)
        leg_liquidity_reasons.update((loaded.get("liquidity") or {}).get("reasons") or [])

    if unlinked:
        # ── PARTIAL IS STILL BROKEN, AND IT IS THE HARDER CASE TO SEE.
        #
        # This used to be two paths: every leg missing was an alarm, and ONE leg
        # missing printed the survivor as a live single-source number with
        # `is_alarm=False`.  CERT C-UX-P139-GRID-REGISTER-1's P1 executed that
        # second path — a registered Polymarket+Kalshi SF cell with Kalshi
        # absent returned `state='live'`, `source_count=1`, `alarm_cells=0` —
        # and it is exactly the laundering the amendment forbids: the grid's own
        # eval read green while the page published a half-answered question
        # wearing the confident type.
        #
        # A registered two-source cell is a claim that TWO markets answer this
        # question.  If one of them does not load, the claim is broken, and a
        # broken claim is an alarm with a named fix (link the market) — not a
        # number with a footnote.  So the number is WITHHELD, not muted: a price
        # the reader can see is a price the reader will believe, and one leg of
        # a two-leg blend is not the number this cell promised.
        # UX-P145 — THIS STRING IS READ BY USERS, which is easy to miss from
        # here.  It rides `note` into `gridCellExplanation()` and comes out as
        # the cell's `title=` tooltip AND its screen-reader text
        # (`frontend/lib/playoffGrid.ts`).  It used to say "N of M registered
        # sources priced; unpriced: ..." — *registered* is the name of our JSON
        # file, *priced* is a trading verb, and *sources* is our word for Kalshi
        # and Polymarket.  Three pieces of pipeline vocabulary in a sentence
        # aimed at somebody who wanted to know why a cell is blank.
        #
        # The market ids STAY.  They are the diagnostic half and Alex's
        # amendment requires an alarm to name the market that did not resolve;
        # a name is not jargon.  Only the framing changed.
        priced_note = (
            f"We have a number from {len(source_views)} of {len(live_blocks)} markets; "
            f"still missing: {'; '.join(unlinked)}"
            if source_views
            else f"We could not read a number from: {'; '.join(unlinked)}"
        )
        cell = _cell(
            CELL_UNLINKED,
            note=priced_note,
            censused_at=censused_at,
            sources=source_views + unlinked_views,
        )
        # The specimen stays identifiable: a fully-dead cell and a half-dead one
        # are the same alarm to the reader and two different fixes to us.
        cell["partially_unlinked"] = bool(source_views)
        return cell

    blend, divergence, rule = blend_with_verdict(blend_rows)
    if blend is None:
        return _cell(
            CELL_UNLINKED,
            # UX-P145: user-visible via the cell tooltip. Was "Registered and
            # priced, but the blend refused both legs" — every noun in it ours.
            note="Both markets quoted a number, but we could not combine them into one",
            censused_at=censused_at,
            sources=source_views,
        )

    # THE AND, inherited from the boards: a cell is as fresh as its OLDEST
    # contributor, because both legs are inside the number the reader sees.
    age = governing_age_hours(observed_times, now)
    state = price_state(age)
    newest = freshest_observation(observed_times)

    cell = _cell(
        state if state in PRICED_STATES else CELL_DARK,
        probability=blend,
        sources=source_views,
        observed_at=min((t for t in observed_times if t is not None), default=None),
        age_hours=age,
        censused_at=censused_at,
        blend_rule=rule,
        divergent=divergence is not None,
        liquidity=thinnest_liquidity(leg_liquidity_levels),
        # The union over the legs, not the thinnest leg's own list: a cell built
        # from one untraded book and one impossibly-wide book has BOTH problems,
        # and the reveal should be able to name both.
        liquidity_reasons=sorted(leg_liquidity_reasons),
    )
    cell["freshest_observed_at"] = newest.isoformat() if newest else None
    # Every registered leg loaded, or this function returned an alarm above.
    cell["partially_unlinked"] = False
    return cell


def evaluate_column_sums(
    columns: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Alex's ruling-4 sum check, per column.

    "every column validates: reach-round probabilities sum to the round's slot
    count (8 for QF, 4 for SF, 2 for F, 1 for title) within tolerance — show
    the sum check."

    Two things this deliberately does NOT do.  It does not rescale — a column
    normalised to its slot count is a column of fabricated numbers, and this
    page's whole claim is that its numbers are prices somebody quoted.  And it
    does not treat an under-sum and an over-sum as the same failure: a column
    that sums LOW because the field is only partly covered is a coverage fact,
    while one that sums HIGH is the market disagreeing with arithmetic.  Both
    are reported with the coverage count beside them so the reader can tell
    which they are looking at.
    """
    out: list[dict[str, Any]] = []
    for column in columns:
        key = column["key"]
        expected = ROUND_SLOTS.get(key)
        priced = [
            row["cells"][key]
            for row in rows
            if row["cells"].get(key, {}).get("probability") is not None
        ]
        total = sum(cell["probability"] for cell in priced)
        ratio = (total / expected) if expected else None
        verdict = "unchecked"
        if expected is not None and priced:
            verdict = (
                "pass"
                if abs((ratio or 0.0) - 1.0) <= COLUMN_SUM_TOLERANCE
                else ("over" if (ratio or 0.0) > 1.0 else "under")
            )
        out.append({
            "key": key,
            "short_label": column["short_label"],
            "sum": round(total, 4),
            "expected": expected,
            "ratio": round(ratio, 4) if ratio is not None else None,
            "priced_rows": len(priced),
            "total_rows": len(rows),
            "verdict": verdict,
        })
    return out


def evaluate_monotonicity(
    columns: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A player cannot be likelier to reach the final than the semis.

    The bound Alex's original ruling 3 wanted derived values to respect, kept
    as an EVAL now that the derivation is retired.  It is the cheapest possible
    proof that the columns are answering the questions their headers claim: if
    a reach-QF market had been wired into the SF cell, this fires on every row
    where the two differ, which is most of them.

    Reported, not corrected.  Measured 2026-08-26, 21 of 84 ladder players
    violate it — all in the sub-5% tail, where a thin binary prices "reach the
    final" a point above "reach the semis".  That is the market's own
    incoherence and hiding it would be the page lying on the market's behalf.

    ═══ ONLY CELLS OBSERVED AT THE SAME TIME ARE COMPARABLE (Q428) ═══

    A cell the page has already marked ``dark`` or ``stale`` is not an opinion
    about now, so an ordering between it and a live cell is not a disagreement
    between two markets — it is a gap between two moments.  Measured on the
    2026-08-28 payload, 5 of 27 reported violations were exactly that, four of
    them comparing a price captured 75 hours ago against one captured ten
    minutes ago:

        Alex de Minaur     R16 -> QF   live(0.17h) / dark(75.05h)
        Casper Ruud        R16 -> QF   live(0.17h) / dark(75.05h)
        Valentin Vacherot  QF  -> SF   dark(75.05h) / live(0.17h)
        Darwin Blanch      R16 -> QF   dark(75.05h) / live(0.17h)
        Joao Fonseca       SF  -> F    dark(72.97h) / dark(75.05h)

    This needs no constant and invents no vocabulary: the freshness words are
    already on every cell and only a ``live`` one may wear
    ``probability_is_live``.  Using them here is consistency with the surface's
    own contract.  Nor does it hide anything — the cell still renders, still
    carries its age and its state, and still counts in ``counts``.  What stops
    is the page ASSERTING that two markets contradict each other when it has
    only observed them at different times.

    ``settled`` is deliberately NOT in the skip list.  It is a terminal fact
    rather than a freshness word, and a settled cell out of order with a live
    one is the worst version of this failure, not an exempt one.  A cell with
    no ``state`` at all is compared: pure-logic callers pass bare
    probabilities, and skipping a cell that never claimed to be stale would
    switch this eval off for them.
    """
    order = [column["key"] for column in columns]
    violations: list[dict[str, Any]] = []
    for row in rows:
        priced = [
            (key, row["cells"][key]["probability"])
            for key in order
            if row["cells"].get(key, {}).get("probability") is not None
            and row["cells"].get(key, {}).get("state") not in (CELL_DARK, CELL_STALE)
        ]
        for (earlier, before), (later, after) in zip(priced, priced[1:]):
            if before < after - MONOTONICITY_EPSILON:
                violations.append({
                    "entity_key": row["entity_key"],
                    "display_name": row["display_name"],
                    "earlier": earlier,
                    "later": later,
                    "earlier_probability": before,
                    "later_probability": after,
                })
    return violations


def build_playoff_grid(
    register: dict[str, Any],
    *,
    board_rows: list[dict[str, Any]],
    prices: dict[int, dict[str, Any]],
    draw: str,
    now: datetime,
) -> dict[str, Any]:
    """The grid for one draw.

    ``board_rows`` are the championship board's, already blended and ranked by
    ``build_boards``.  Two reasons the rows come from there rather than from
    ``reaches``:

    * **One ranking.**  The board's order is the title ranking and every other
      surface on this page already uses it.  Two rankings of one field is a
      divergence bug wearing a layout decision.
    * **One title number.**  The last column IS the board's number, read from
      the board, so the grid and the board cannot print different values for
      the same question.  The standing ruling — the blend is the product —
      makes that a correctness property rather than a tidiness one.

    A board contender with no reach cells still gets a row.  Dropping it would
    make the grid's coverage look better than the data is, which is the one
    thing an alarm-state design must not do.

    And a player the LADDER carries who is not on the board also gets a row,
    appended after the ranked ones.  Measured 2026-08-26, 32 of the 84 ladder
    players have no outright quote — Monfils, Nakashima, Humbert, Fernandez,
    Venus Williams — so a rows-from-the-board-only grid would drop 128 priced
    markets, 20 of the men's 44 rows among them.  Their title cell is an honest
    ``no_market``; their reach cells are real prices.
    """
    reg = TournamentRegister(register)
    cells_by_key = reg.reach_cells(draw)

    reach_rounds = reg.reach_rounds(draw)
    columns = [
        {
            "key": name,
            "short_label": SHORT_LABELS.get(name, name),
            "long_label": LONG_LABELS.get(name, name),
            "kind": "reach",
            "slots": ROUND_SLOTS.get(name),
        }
        for name in reach_rounds
    ] + [
        {
            "key": "title",
            "short_label": SHORT_LABELS["title"],
            "long_label": LONG_LABELS["title"],
            "kind": "title",
            "slots": 1,
        }
    ]

    # Board rows first, in the board's own rank order, then the ladder-only
    # players. The second group is sorted by their own deepest priced reach
    # cell rather than left in register order: an unranked block sorted by
    # entity key would put Darwin Blanch above Gael Monfils for no reason a
    # reader could see, and this grid's whole grammar is "further down the page
    # means further from winning".
    on_board = {row.get("entity_key") for row in board_rows}
    ladder_only = [
        player
        for player in reg.players
        if player.get("draw") == draw
        and player.get("entity_key") not in on_board
        and any(key[0] == player.get("entity_key") for key in cells_by_key)
    ]

    def _ladder_strength(player: dict[str, Any]) -> float:
        """Deepest-round price for ordering the unranked tail. Never rendered."""
        best = 0.0
        for name in reversed(reach_rounds):
            reach = cells_by_key.get((str(player.get("entity_key")), name))
            for block in (reach or {}).get("sources") or []:
                loaded = prices.get(block.get("outcome_id")) if isinstance(block, dict) else None
                value = _as_float((loaded or {}).get("probability"))
                if value is not None:
                    return value
        return best

    ladder_only.sort(key=lambda p: (-_ladder_strength(p), str(p.get("display_name"))))

    grid_inputs: list[dict[str, Any]] = [
        *board_rows,
        *(
            {
                "entity_key": player.get("entity_key"),
                "display_name": player.get("display_name"),
                "seed": player.get("seed"),
                "rank": None,
                # No outright quote exists for these players. `None` here makes
                # the title cell an honest `no_market`, which is exactly what it
                # is — and never a zero, which would read as "the market says
                # they cannot win".
                "probability": None,
                "state": "live",
                "on_board": False,
            }
            for player in ladder_only
        ),
    ]

    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for board_row in grid_inputs:
        entity_key = board_row.get("entity_key")
        cells: dict[str, Any] = {}

        for name in reach_rounds:
            reach = cells_by_key.get((str(entity_key), name))
            if reach is None:
                # ── THE SECOND ALARM. A column exists because some player in
                # this draw has a cell for it; this player does not. Nobody
                # censused the pair. Never blank, never inferred from the
                # neighbours, and counted so the page cannot look complete.
                cells[name] = _cell(
                    CELL_UNREGISTERED,
                    # UX-P145: user-visible via the cell tooltip. Was "No {X}
                    # cell registered for this player".
                    note=f"We have not found a {SHORT_LABELS.get(name, name)} market for this player",
                )
            else:
                blocks = [b for b in (reach.get("sources") or []) if isinstance(b, dict)]
                cells[name] = _price_cell(
                    blocks,
                    prices,
                    now=now,
                    cell_label=SHORT_LABELS.get(name, name),
                )
            counts[cells[name]["state"]] = counts.get(cells[name]["state"], 0) + 1

        # THE TITLE COLUMN IS THE BOARD'S OWN CELL, not a re-blend of it.
        title_probability = board_row.get("probability")
        if board_row.get("state") not in (None, "live"):
            cells["title"] = _cell(CELL_SETTLED, note=str(board_row.get("state")))
        elif title_probability is None:
            cells["title"] = _cell(
                CELL_NO_MARKET,
                # UX-P146: user-visible via the cell tooltip. Was "No title
                # price on either winner field" — Alex's product-wide ruling
                # bans *price* as a noun in copy; the word is PROBABILITY.
                note="Neither winner market has a number for this player yet",
            )
        else:
            title_state = board_row.get("price_state") or "dark"
            cells["title"] = _cell(
                title_state if title_state in PRICED_STATES else CELL_DARK,
                probability=float(title_probability),
                sources=board_row.get("sources") or [],
                age_hours=board_row.get("age_hours"),
                blend_rule=board_row.get("blend_rule"),
                divergent=bool(board_row.get("divergent")),
                # INHERITED, not re-derived. The title cell IS the board's cell
                # (see the comment above it); a second grading pass over the
                # same two books is exactly the "second opinion one tab away"
                # this column exists to avoid.
                liquidity=str(board_row.get("liquidity") or LIQUIDITY_UNKNOWN),
                liquidity_reasons=list(board_row.get("liquidity_reasons") or []),
            )
            cells["title"]["observed_at"] = board_row.get("observed_at")
        counts[cells["title"]["state"]] = counts.get(cells["title"]["state"], 0) + 1

        rows.append({
            "entity_key": entity_key,
            "display_name": board_row.get("display_name"),
            "seed": board_row.get("seed"),
            # Alex's ruling 8, on the surface with the most rows: the grid was
            # 84 lines of text. Read from the register like every other cell in
            # this file — `player_image` returns the two pinned URLs and
            # nothing else, so the grid still reads only the register.
            "image": player_image(reg.by_entity.get(str(entity_key)) or {}),
            "rank": board_row.get("rank"),
            # Whether this row is on the championship board. The UI uses it to
            # explain the empty title cell in a word rather than leaving the
            # reader to wonder why the last column stops half way down.
            "on_board": board_row.get("on_board", True),
            "cells": cells,
        })

    total_cells = len(rows) * len(columns)
    alarms = sum(counts.get(state, 0) for state in ALARM_STATES)
    priced = sum(counts.get(state, 0) for state in PRICED_STATES)

    return {
        "draw": draw,
        "label": draw_label(draw),
        "columns": columns,
        "rows": rows,
        # THE HONESTY COUNTERS. Every cell is in exactly one of these buckets
        # and they add to `total_cells`; a grid that cannot account for all of
        # its own cells is not one anybody should trust.
        "counts": dict(sorted(counts.items())),
        "total_cells": total_cells,
        "priced_cells": priced,
        "no_market_cells": counts.get(CELL_NO_MARKET, 0),
        # NON-ZERO IS RED. The amendment's whole point: these are defects with
        # a named fix (link the market), not a data quirk to be explained.
        "alarm_cells": alarms,
        "column_sums": evaluate_column_sums(columns, rows),
        "monotonicity_violations": evaluate_monotonicity(columns, rows),
    }


def build_grids(
    register: dict[str, Any],
    *,
    boards: list[dict[str, Any]],
    prices: dict[int, dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    """One grid per board, keyed by draw."""
    return {
        board["draw"]: build_playoff_grid(
            register,
            board_rows=board.get("rows") or [],
            prices=prices,
            draw=board["draw"],
            now=now,
        )
        for board in boards
    }


__all__ = [
    "ALARM_STATES",
    "CELL_DARK",
    "CELL_LIVE",
    "CELL_NO_MARKET",
    "CELL_SETTLED",
    "CELL_STALE",
    "CELL_UNLINKED",
    "CELL_UNREGISTERED",
    "COLUMN_SUM_TOLERANCE",
    "MONOTONICITY_EPSILON",
    "PRICED_STATES",
    "ROUNDS",
    "ROUND_SLOTS",
    "build_grids",
    "build_playoff_grid",
    "evaluate_column_sums",
    "evaluate_monotonicity",
]
