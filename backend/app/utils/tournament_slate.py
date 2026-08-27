"""Build the daily slate — "the script vs the divergence" (UX-P132, charter layer 2).

The boards answer *who wins the tournament*.  The slate answers *what is on
today*, and it is the half of the page that actually has live prices: the
outright fields have been dark for 8-32 days (#2199) while the match markets
were captured minutes ago.

**The script vs the divergence.**  The SCRIPT is the opening price — what the
market expected when the match was first quoted.  The DIVERGENCE is where it
has moved since.  A row is only interesting because those two differ, so both
travel together and the move is computed from the same normalized basis as the
number displayed beside it.  Computing the delta on raw prices and displaying
normalized ones would produce a row whose "+4.2" does not equal the difference
between its own two numbers.

Three things this module refuses to do:

1. **Print ``Yes``/``No``.**  Every side is looked up through the register's
   ``sides`` map, ``entity_key -> outcome_id``, pinned offline from the source's
   own ordered labels.  There is no name parsing here and no positional
   assumption; an unmapped side yields no row rather than a guess.

2. **Present an incoherent pair as a clean split.**  Two-outcome match quotes
   are independent binaries (gotcha #23): they are *quotes*, not a probability
   distribution, and nothing makes them sum to 1.  Measured 2026-08-25, all 162
   US Open qualification pairs summed to exactly 1.000 — but that is an
   observation about one moment, not a property, and the Cincinnati sample in
   the Day-1 census summed to 1.01.  So the sum is checked every time,
   normalized when it is close enough to be an overround, and REFUSED when it
   is not.  A 30-point disagreement normalized into a tidy 60/40 is a fabricated
   number wearing two players' names.

3. **Show a finished match as today's.**  Registration already excludes closed
   matches, but the register is a committed file and the clock keeps moving, so
   the same start-time bound is re-applied at serve time.  A register written
   this morning must not still be presenting this morning's matches at
   midnight.

4. **Call a row live off its freshest side.**  A slate row publishes a
   *normalized pair*, so both sides are inside the number the reader sees: an
   0.72 that was normalized against a side quoted twenty days ago is a
   twenty-day-old 0.72.  Freshness is therefore the AND over the sides, using
   the same ``governing_age_hours`` the boards use, and for the same reason
   (UX-P135, cert ``C-USOPEN-DAY3-TIER2``).  ``normalize_pair`` already refuses
   the *loud* version of this failure — one side stale at 0.9 against 0.6 — but
   a mixed-age pair that happens to still sum to 1.00 slips straight through
   the coherence gate, which is exactly what a coherence gate is for and
   exactly why it is not a freshness gate.

Pure logic — every input is a plain dict, so the whole slate is testable
without a database.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from app.utils.tournament_board import (
    DARK_PRICE_HOURS,
    draw_label,
    freshest_observation,
    governing_age_hours,
    price_state,
)
from app.utils.tournament_register import TournamentRegister, player_image

logger = logging.getLogger(__name__)

#: How far a two-sided quote may sum from 1.0 and still be treated as one
#: question with an overround.  Beyond this the two sides are not describing the
#: same match closely enough for a split to mean anything.
#:
#: 12 points is wide enough to absorb every overround this class produces (the
#: measured worst case across the Day-1 census was 1 point) and narrow enough
#: that a genuinely broken pair — one side stale at 0.9 while the other moved to
#: 0.6 — is refused rather than laundered.
MAX_PAIR_DEVIATION = 0.12

#: A slate row disappears this long after its scheduled start.  Matches the
#: generator's exclusion window so the file and the serving path agree; if they
#: drifted, a match would be registered and then not shown, or shown after it
#: was meant to be dropped, with no single place to look.
MATCH_STALE_AFTER_HOURS = 6.0

#: A move smaller than this is noise, not a story. Same dead band as the board's
#: trend direction, so "moved" means one thing across the whole page.
MOVE_DEAD_BAND = 0.003


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:  # NaN
        return None
    return result


def normalize_pair(
    a: Optional[float], b: Optional[float]
) -> tuple[Optional[float], Optional[float], Optional[float], bool]:
    """Two independent binary quotes -> one coherent pair.

    Returns ``(a_norm, b_norm, raw_sum, coherent)``.  When the pair cannot be
    made coherent both probabilities come back ``None`` — the caller must not
    fall back to the raw values, and there is nothing to fall back to.

    Not collapsed into "just renormalize": the *decision* is whether these two
    numbers are one question at all.  ``0.54 + 0.47`` is one question with a
    1-point overround.  ``0.90 + 0.60`` is two stale readings, and dividing them
    by 1.5 yields 60/40 — a number with no referent that looks exactly like a
    real one.
    """
    if a is None or b is None:
        return None, None, None, False
    if a < 0 or b < 0:
        return None, None, round(a + b, 6), False

    total = a + b
    if total <= 0:
        return None, None, round(total, 6), False
    if abs(total - 1.0) > MAX_PAIR_DEVIATION:
        return None, None, round(total, 6), False
    return round(a / total, 6), round(b / total, 6), round(total, 6), True


def _side_view(
    entity_key: str,
    player: dict[str, Any],
    loaded: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    observed = loaded.get("observed_at")
    age = (
        (now - observed).total_seconds() / 3600.0
        if isinstance(observed, datetime)
        else None
    )
    return {
        "entity_key": entity_key,
        "display_name": player.get("display_name") or entity_key,
        "seed": player.get("seed"),
        "country": player.get("country"),
        "image": player_image(player),
        "role": player.get("role", "contender"),
        "probability": None,
        "opening_probability": None,
        "move": None,
        "raw_probability": _as_float(loaded.get("probability")),
        "raw_opening_probability": _as_float(loaded.get("opening_probability")),
        "observed_at": observed,
        # Each side answers for its own freshness (UX-P135). The row's verdict
        # is the AND of these two, so the UI can name the old side instead of
        # muting the pair with no reason given.
        "age_hours": round(age, 2) if age is not None else None,
        "price_state": price_state(age),
    }


def build_slate(
    register: dict[str, Any],
    *,
    prices: dict[int, dict[str, Any]],
    now: datetime,
    max_stale_hours: float = MATCH_STALE_AFTER_HOURS,
) -> dict[str, Any]:
    """Assemble the daily slate payload.

    ``prices`` is keyed by ``outcome_id`` and carries ``{"probability",
    "opening_probability", "observed_at"}``.  Keying on the outcome id the
    register pins — rather than on anything derived from a name at request time
    — is what makes the sides mapping load-bearing instead of decorative.
    """
    reg = TournamentRegister(register)
    cutoff = now - timedelta(hours=max_stale_hours)

    rows: list[dict[str, Any]] = []
    dropped: dict[str, int] = {}

    def drop(reason: str) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    for matchup in reg.matchups:
        players = matchup.get("players")
        if not isinstance(players, list) or len(players) != 2:
            drop("NOT_A_PAIR")
            continue

        scheduled = matchup.get("scheduled_date")
        started: Optional[datetime] = None
        if isinstance(scheduled, str) and scheduled:
            try:
                started = datetime.fromisoformat(scheduled.replace("Z", "+00:00"))
            except ValueError:
                started = None
        if started is None:
            drop("NO_SCHEDULED_START")
            continue
        if started < cutoff:
            # Registered when it was upcoming; it is not upcoming now. The
            # register is a file and the clock is not.
            drop("ALREADY_PLAYED")
            continue

        block = next(
            (
                b for b in (matchup.get("sources") or [])
                if isinstance(b, dict) and b.get("status") == "live"
            ),
            None,
        )
        # A REGISTERED FIXTURE NOBODY PRICES IS STILL A FIXTURE (UX-P142).
        #
        # This used to `drop("NO_LIVE_SOURCE")`, and on ceremony day that one
        # line was the reason the page showed none of the released draw. The
        # main draw is 96 registered fixtures four days out and NOT ONE of them
        # has a match market at either source yet — nobody quotes a first round
        # before qualifying finishes — so every one of them was dropped by a
        # price rule and the reader was shown an empty list.
        #
        # A price is a fact ABOUT a fixture. Its absence is not evidence the
        # fixture does not exist, and the page's own standing rule is that no
        # state renders blank. So the row is built with no numbers on it and
        # `priced: False` saying why, exactly as the grid's `no_market` cell
        # does one tab over. `probability` stays None on both sides, which is
        # the same None every downstream honesty gate already handles.
        #
        # `SIDES_UNMAPPED` keeps its drop: that is a live quote we cannot
        # attribute to a player, which is a linkage DEFECT and not an absence,
        # and rendering it unpriced would hide it.
        sides_map: dict[str, Any] = {}
        if block is not None:
            candidate = block.get("sides")
            if not isinstance(candidate, dict) or set(candidate) != set(players):
                drop("SIDES_UNMAPPED")
                continue
            sides_map = candidate

        views: list[dict[str, Any]] = []
        # Both sides' own times, kept as a list. The verdict needs the oldest
        # and the display needs the newest; a running max destroys one of them.
        side_times: list[Optional[datetime]] = []
        for entity_key in players:
            player = reg.by_entity.get(entity_key)
            if player is None:
                break
            side = sides_map.get(entity_key) or {}
            outcome_id = side.get("outcome_id")
            loaded = prices.get(outcome_id) if isinstance(outcome_id, int) else None
            view = _side_view(entity_key, player, loaded or {}, now)
            observed = (loaded or {}).get("observed_at")
            side_times.append(observed if isinstance(observed, datetime) else None)
            views.append(view)
        if len(views) != 2:
            drop("PLAYER_NOT_REGISTERED")
            continue

        a_norm, b_norm, raw_sum, coherent = normalize_pair(
            views[0]["raw_probability"], views[1]["raw_probability"]
        )
        # The script is normalized on its OWN sum, not the current one — an
        # opening pair has its own overround, and mixing bases would make the
        # move an artifact of the two sums differing rather than of the market
        # moving.
        a_open, b_open, open_sum, open_coherent = normalize_pair(
            views[0]["raw_opening_probability"], views[1]["raw_opening_probability"]
        )

        if coherent:
            views[0]["probability"] = a_norm
            views[1]["probability"] = b_norm
        if open_coherent:
            views[0]["opening_probability"] = a_open
            views[1]["opening_probability"] = b_open
        if coherent and open_coherent:
            for view in views:
                view["move"] = round(
                    view["probability"] - view["opening_probability"], 6
                )

        # THE AND (UX-P135): the pair is as old as its older side.
        age = governing_age_hours(side_times, now)
        state = price_state(age)
        newest = freshest_observation(side_times)
        freshest_age = (now - newest).total_seconds() / 3600.0 if newest else None
        stale_sides = [
            v["entity_key"] for v in views if v["price_state"] != "live"
        ]

        favourite = None
        if coherent:
            favourite = (
                views[0]["entity_key"]
                if (views[0]["probability"] or 0) >= (views[1]["probability"] or 0)
                else views[1]["entity_key"]
            )

        moves = [v["move"] for v in views if v["move"] is not None]
        rows.append({
            "priced": block is not None,
            "matchup_key": matchup.get("matchup_key"),
            # OUR `events.id` for this fixture, when the register carries one
            # (UX-P139, Alex's item 7). Register-owned so a click-through is an
            # identity decision made once against the evidence, never a
            # request-time name match across two systems that disagree about
            # `Auger-Aliassime`. `None` on every US Open matchup today: the
            # qualifying draw has no `events` rows at all.
            "event_id": matchup.get("event_id"),
            "draw": matchup.get("draw"),
            "draw_label": draw_label(str(matchup.get("draw") or "")),
            "round": matchup.get("round"),
            "scheduled_date": started.isoformat(),
            "sides": views,
            # The honesty fields. A client that ignores every one of them still
            # cannot render a confident number, because `probability` is None
            # whenever the pair is incoherent.
            "coherent": coherent,
            "raw_sum": raw_sum,
            "opening_raw_sum": open_sum,
            "probability_is_live": state == "live" and coherent,
            # `unpriced` is its own word, distinct from `dark`. Dark means a
            # price we HAVE gone stale; unpriced means no market was ever
            # pinned. Collapsing them would make "the market stopped quoting
            # this" and "no market exists" the same sentence to a reader, and
            # only one of those is our problem to fix.
            "price_state": "unpriced" if block is None else state,
            # GOVERNING, not newest — see doctrine 4 in the module docstring.
            "observed_at": (
                min(t for t in side_times if t is not None).isoformat()
                if age is not None
                else None
            ),
            "age_hours": round(age, 2) if age is not None else None,
            "freshest_observed_at": newest.isoformat() if newest else None,
            "freshest_age_hours": (
                round(freshest_age, 2) if freshest_age is not None else None
            ),
            "stale_sides": stale_sides,
            "mixed_freshness": 0 < len(stale_sides) < len(views),
            "favourite": favourite,
            "has_moved": any(abs(m) > MOVE_DEAD_BAND for m in moves),
            "source_count": 1,
        })

    rows.sort(key=lambda r: (r["scheduled_date"], r["matchup_key"] or ""))

    # Slate-level, like the board's: the newest thing anyone has seen. Reads
    # `freshest_observed_at` because `observed_at` is now the governing side's.
    observed_times = [
        datetime.fromisoformat(r["freshest_observed_at"])
        for r in rows
        if r.get("freshest_observed_at")
    ]
    newest_overall = max(observed_times) if observed_times else None
    slate_age = (
        (now - newest_overall).total_seconds() / 3600.0 if newest_overall else None
    )

    if dropped:
        # Never a silent truncation. A short slate must be explainable.
        logger.info(
            "tournament slate for %s-%s dropped %s matchups: %s",
            reg.tournament, reg.season, sum(dropped.values()), dropped,
        )

    return {
        "matches": rows,
        "count": len(rows),
        "incoherent": sum(1 for r in rows if not r["coherent"]),
        "dropped": dict(sorted(dropped.items())),
        "price_state": price_state(slate_age),
        "newest_observed_at": newest_overall.isoformat() if newest_overall else None,
        "age_hours": round(slate_age, 2) if slate_age is not None else None,
        "dark_after_hours": DARK_PRICE_HOURS,
    }


def build_results(
    register: dict[str, Any],
    *,
    results: dict[str, Any],
) -> dict[str, Any]:
    """Decided matches, with the score (UX-P139, Alex's item 9).

    "Decided-match scores come from the ESPN API we already use for other
    scores — wire it; 'no data behind it' is not accepted."

    UX-P138 declared ``winner_entity_key`` and ``score``, rendered them when
    filled, and had nothing to fill them with.  This is the fill.  ``results``
    is ``app.services.espn_tennis.parse_results``' output: per draw, an
    unordered normalized name pair -> ``{score, winner_normalized, ...}``.

    WHY THIS IS A SEPARATE BUILDER AND NOT A FIELD ON THE SLATE.  ``build_slate``
    drops a matchup the moment it starts (``ALREADY_PLAYED``) — deliberately,
    because the register is a committed file and the clock keeps moving, and a
    slate still showing this morning's matches at midnight is the defect that
    rule exists to prevent.  A decided match is therefore not a slate row and
    never was, which is the real reason UX-P138's seam rendered nothing: it was
    attached to a list that structurally cannot contain a finished match.

    THE JOIN IS THE PLAYER PAIR, and NOT the matchup.  That is a correction of
    this function's first draft, and the reason is the same rule stated above:
    ``build_slate`` drops a matchup the moment it starts, so by the time a
    match has a result the register no longer carries it.  Joining results to
    matchups produced, measured, **0 results against 199 finished ESPN
    competitions** — a section that was structurally guaranteed to be empty.

    So a result is attached when BOTH of its players are registered in the same
    draw.  Player identity is the anchor everything else on this page already
    uses, it survives a matchup being retired, and it is strict in the way that
    matters: both names, in one draw, or the result is counted and dropped.  A
    result whose winner does not normalize to one of the two is dropped
    separately — a score under the wrong names is exactly the class of defect
    the register exists to make impossible, and it would look plausible.
    """
    reg = TournamentRegister(register)
    by_draw = (results or {}).get("draws") or {}

    from app.services.espn_tennis import normalize_name

    # (draw, normalized name) -> player. Built once; the join is a lookup.
    by_name: dict[tuple[str, str], dict[str, Any]] = {}
    for player in reg.players:
        key = (str(player.get("draw") or ""), normalize_name(player.get("display_name")))
        by_name.setdefault(key, player)

    rows: list[dict[str, Any]] = []
    unregistered_pair = 0
    winner_mismatch = 0

    # A matchup key when we still hold one, so a result and its former slate row
    # agree on identity. Absent, the ESPN competition id is the stable key.
    matchup_by_pair: dict[tuple, str] = {}
    for matchup in reg.matchups:
        players = matchup.get("players")
        if isinstance(players, list) and len(players) == 2:
            matchup_by_pair[
                (str(matchup.get("draw")), tuple(sorted(players)))
            ] = str(matchup.get("matchup_key"))

    for draw, found_by_pair in sorted(by_draw.items()):
        for found in found_by_pair.values():
            entries = [
                by_name.get((draw, normalize_name(name)))
                for name in (found.get("players") or [])
            ]
            if len(entries) != 2 or any(entry is None for entry in entries):
                unregistered_pair += 1
                continue

            keys = [str(entry.get("entity_key")) for entry in entries]
            winner_key: Optional[str] = None
            for key, entry in zip(keys, entries):
                if normalize_name(entry.get("display_name")) == found.get("winner_normalized"):
                    winner_key = key
                    break
            if winner_key is None:
                winner_mismatch += 1
                continue

            rows.append({
                "matchup_key": matchup_by_pair.get(
                    (draw, tuple(sorted(keys))),
                    f"espn:{found.get('espn_competition_id')}",
                ),
                "draw": draw,
                "draw_label": draw_label(draw),
                # OUR round when the register still holds the matchup, ESPN's
                # otherwise — and `source_round` carries ESPN's either way,
                # because it is finer than ours (three qualifying rounds where
                # the register has one bucket).
                "round": found.get("espn_round") or "",
                "players": [
                    {"entity_key": key, "display_name": entry.get("display_name"),
                     "seed": entry.get("seed"), "is_winner": key == winner_key}
                    for key, entry in zip(keys, entries)
                ],
                "winner_entity_key": winner_key,
                # Winner's games first, set by set. `None` for a retirement or a
                # partial read — see `format_score`, which refuses rather than
                # printing half a result as a whole one.
                "score": found.get("score"),
                "completed_at": found.get("completed_at"),
                "source_round": found.get("espn_round"),
                "source": "espn",
            })

    rows.sort(key=lambda r: (str(r.get("completed_at") or ""), r["matchup_key"] or ""))

    return {
        "matches": rows,
        "count": len(rows),
        # NEVER SILENT. A results list shorter than the day's play is either a
        # coverage fact or a join problem, and those need different people.
        # `unregistered_pairs` is the coverage one: a finished match at this
        # tournament whose two players the register does not both carry — most
        # of the qualifying draw, by design.
        "unregistered_pairs": unregistered_pair,
        "winner_not_registered": winner_mismatch,
        "source_competitions": (results or {}).get("stats", {}).get("final", 0),
        "source_scored": (results or {}).get("stats", {}).get("scored", 0),
        "source_errors": (results or {}).get("errors") or [],
    }


def build_props(
    register: dict[str, Any],
    *,
    prices: dict[int, dict[str, Any]],
    now: datetime,
) -> list[dict[str, Any]]:
    """The curated props & futures section (UX-P132, Alex's item 5).

    Reads only what the register curated.  There is no discovery step and no
    "everything else about this tournament" query, which is what keeps
    "curated, not a dump" true as the tournament grows — the interestingness
    bar is applied once, by the agent, when the register is written.

    A prop whose outcomes are all unpriced still renders: knowing the question
    is being asked is worth something, and an empty probability is honest where
    an invented one is not.
    """
    out: list[dict[str, Any]] = []
    for prop in TournamentRegister(register).props:
        views: list[dict[str, Any]] = []
        priced_times: list[Optional[datetime]] = []

        for outcome in prop.get("outcomes") or []:
            if not isinstance(outcome, dict):
                continue
            loaded = prices.get(outcome.get("outcome_id")) or {}
            probability = _as_float(loaded.get("probability"))
            observed = loaded.get("observed_at")
            observed = observed if isinstance(observed, datetime) else None
            outcome_age = (
                (now - observed).total_seconds() / 3600.0 if observed else None
            )
            outcome_state = price_state(outcome_age)
            if probability is not None:
                # Only a PRICED outcome contributes to the card's freshness. An
                # unpriced one has no reading to be stale, and counting it as
                # dark would paint every partially-quoted card dark.
                priced_times.append(observed)
            views.append({
                "entity_key": outcome.get("entity_key"),
                "display_name": outcome.get("display_name"),
                "probability": round(probability, 6) if probability is not None else None,
                # ITS OWN freshness, not the section's newest (UX-P135). The
                # old rule let one outcome refreshed an hour ago mark a
                # twenty-day-old answer live: the section max is exactly the
                # `C-USOPEN-DAY3-TIER2` shape applied to a card instead of a
                # blend. These flags cannot contradict the card's banner
                # because the banner is now derived FROM them.
                "probability_is_live": outcome_state == "live" and probability is not None,
                "observed_at": observed.isoformat() if observed else None,
                "age_hours": round(outcome_age, 2) if outcome_age is not None else None,
                "price_state": outcome_state,
                # Does THIS outcome answer the card's question? Curated in the
                # register, never inferred here — see the answer rule in
                # `tournament_register.validate_prop`.
                "is_answer": outcome.get("is_answer") is True,
            })

        # The card's own state is the AND over its priced outcomes: a ranked
        # field is a published artifact too, and a stale member can outrank
        # fresh ones inside it.
        age = governing_age_hours(priced_times, now)
        state = price_state(age)
        newest = freshest_observation(priced_times)
        freshest_age = (now - newest).total_seconds() / 3600.0 if newest else None
        stale_outcomes = [
            v["entity_key"]
            for v in views
            if v["probability"] is not None and v["price_state"] != "live"
        ]

        answer = next((v for v in views if v["is_answer"]), None)

        out.append({
            "key": prop.get("key"),
            "title": prop.get("title"),
            "hook": prop.get("hook"),
            "draw": prop.get("draw"),
            "source": prop.get("source"),
            "outcomes": views,
            # `None` is a real, supported state and NOT a defect: it means this
            # question has no single answering outcome (a field market), so the
            # card must show a ranked list rather than one headline number.
            "answer_entity_key": answer["entity_key"] if answer else None,
            "price_state": state,
            "observed_at": (
                min(t for t in priced_times if t is not None).isoformat()
                if age is not None
                else None
            ),
            "age_hours": round(age, 2) if age is not None else None,
            "freshest_observed_at": newest.isoformat() if newest else None,
            "freshest_age_hours": (
                round(freshest_age, 2) if freshest_age is not None else None
            ),
            "stale_outcomes": stale_outcomes,
            "mixed_freshness": 0 < len(stale_outcomes) < len(priced_times),
        })
    return out


def build_bracket(
    register: dict[str, Any],
    *,
    prices: dict[int, dict[str, Any]],
    draw: str,
) -> list[Optional[dict[str, Any]]]:
    """Positional bracket slots for one draw, or `[]` before the ceremony.

    THE FIXTURE SWAP (UX-P134). The bracket component has been rendering a
    synthetic 128-slot fixture since Day 3, because there was no draw. This is
    the path that replaces it, and it is deliberately built and proven BEFORE
    the ceremony so that Thursday is an ingest run, not a build day: the moment
    `ingest_tournament_draw.py` latches `draw_released` and writes the slots,
    this function starts returning them and the page stops being empty. No code
    change on the day.

    Returns a list indexed by draw slot (0-based), `None` where the draw has a
    slot we hold no registered player for. `None` is honest and load-bearing:
    the frontend's `buildBracket` refuses a non-power-of-two rather than
    truncating, so the list is always padded to the full draw size. A hole
    renders as an undetermined slot, which is what it is — not a bye, and never
    a name we invented to fill the shape.

    Empty before release, always. `draw_slot` is invalid while `draw_released`
    is false, so there is nothing to read and a bracket built here would be a
    guess wearing the authority of a fact.
    """
    reg = TournamentRegister(register)
    if not reg.draw_released:
        return []

    slotted = [
        p for p in reg.draw_players(draw)
        if isinstance(p.get("draw_slot"), int) and not isinstance(p.get("draw_slot"), bool)
    ]
    if not slotted:
        return []

    size = max(p["draw_slot"] for p in slotted)
    # Round up to the next power of two so the fold is always well-formed.
    full = 1
    while full < size:
        full *= 2

    out: list[Optional[dict[str, Any]]] = [None] * full
    for player in slotted:
        probability = None
        for block in player.get("sources") or []:
            if not isinstance(block, dict):
                continue
            loaded = prices.get(block.get("outcome_id")) or {}
            value = _as_float(loaded.get("probability"))
            if value is not None:
                probability = round(value, 6)
                break
        out[player["draw_slot"] - 1] = {
            "entity_key": player.get("entity_key"),
            "display_name": player.get("display_name"),
            "seed": player.get("seed"),
            # Never invented: a slot with no priced source carries `None` and
            # the component prints no number rather than a plausible one.
            "probability": probability,
        }
    return out
