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

   ⚠️ **AND IT MUST NOT DO THAT BY GUESSING FROM A PLACEHOLDER (Q463).**  That
   bound is an *elapsed-time* rule over the register's ``scheduled_date``, and
   on ceremony day the register records what ESPN records before an order of
   play exists: **midnight, local** — ``2026-08-30T04:00Z`` on all 96 US Open
   main-draw fixtures.  Six hours later is 10:00Z; the first ball of the
   tournament was at 15:05Z.  So every fixture of opening day was dropped
   ``ALREADY_PLAYED`` **five hours before opening day began**, and the card read
   "No matches scheduled" from morning to night while Djokovic was on court —
   Alex, 2026-08-30: *"It's weird that there's no matches scheduled. that's
   obviously not true."*

   The fix is not a wider window.  A window is a guess about a fixture we have
   an authority for: the same ESPN scoreboard this page already fetches every
   three minutes says, per competition, ``pre`` / ``in`` / ``post`` and the real
   start.  So ``order_of_play`` overrides the clock rule wherever it speaks, the
   elapsed-time bound survives only as the fallback for a fixture ESPN does not
   list, and **a decided match leaves the slate because ESPN says it is decided
   — never because enough hours went by.**

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
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.utils.market_liquidity import LIQUIDITY_UNKNOWN, thinnest_liquidity
from app.utils.prematch_reading import prematch_source_rank
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

#: How much of a *ceremony stamp* is actually a claim (CERT-532, CERT-544).
#:
#: A draw-ceremony fixture's ``scheduled_date`` is not a start.  It is what ESPN
#: publishes before an order of play exists, and the register writes it once for
#: the whole ceremony: **96 of 96 pinned US Open main-draw fixtures carry the
#: single value 2026-08-30T04:00:00+00:00**, the tournament's opening day.
#: Measuring elapsed time against it therefore says nothing about any
#: individual match.
#:
#: CERT-532's repair called it "the day the stamp names" and allowed 24 hours.
#: CERT-544 showed why that is still the same mistake: one instant shared by the
#: whole draw expires for the whole draw at once, so from day two onward a
#: truncated scoreboard could empty the card again — every day of the tournament
#: except the first.
#:
#: So the stamp is read for the only thing it can support.  A draw ceremony
#: opens a tournament of bounded length, so it bounds **the register's own
#: relevance** and nothing finer.  Inside this window a pinned fixture is never
#: retired by the clock; only ESPN's explicit ``decided`` retires it.  Outside
#: it, the register describes a tournament that is over and the clock may clear
#: it away.
#:
#: 21 days: a grand slam main draw runs 14 from the ceremony, and the slack is
#: deliberate — being late to clear a finished register costs a stale row on a
#: page nobody is loading, while being early costs the live card mid-tournament,
#: which is the whole defect.
#:
#: CERT-548: BOTH ends of this window are computed from the stamp and the clock
#: ALONE.  The far end was for one revision conjoined with
#: ``order_of_play_complete``, and that is the same category error the near end
#: had — a fact about a request standing in for a fact about the tournament.  It
#: bit hardest at the far end, because a tournament that is over is exactly the
#: thing ESPN stops listing, so completeness reads false from then on and the
#: bound could never fire again.  Nothing in this module's row rules reads the
#: flag; it is reported in the slate payload and it decides nothing.
CEREMONY_STAMP_COVERS_THE_TOURNAMENT_HOURS = 24.0 * 21

#: A move smaller than this is noise, not a story. Same dead band as the board's
#: trend direction, so "moved" means one thing across the whole page.
MOVE_DEAD_BAND = 0.003


def _parse_moment(value: Any) -> Optional[datetime]:
    """An ISO-8601 string -> an aware datetime, or ``None``.

    Naive input is REFUSED rather than assumed UTC.  Every comparison this
    module makes is against an aware ``now``, so a naive value would raise at
    the comparison — and the version that silently stamped UTC on it would be
    guessing a timezone onto a fixture time, which is the exact class of defect
    this file exists to refuse.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def espn_competition_id(matchup: dict[str, Any]) -> Optional[str]:
    """The ESPN competition id the register pinned for this fixture, if any.

    Matchup-level ``evidence`` FIRST, and that ordering is load-bearing.  The
    draw ceremony writes ``{"kind": "draw-ceremony-espn",
    "espn_competition_id": ...}`` onto the matchup itself, and
    ``apply_resolved_links`` may only rewrite ``sources`` — so the matchup-level
    id is the one anchor on this fixture the price overlay cannot destroy.  The
    per-source fallback is real (the ceremony census stamps it there too) but it
    is exactly the copy a linked block replaces, which on today's payload it has
    already done 72 times.
    """
    pinned = (matchup.get("evidence") or {}).get("espn_competition_id")
    if pinned:
        return str(pinned)
    for block in matchup.get("sources") or []:
        if not isinstance(block, dict):
            continue
        candidate = (block.get("evidence") or {}).get("espn_competition_id")
        if candidate:
            return str(candidate)
    return None


# THE NAME COMPARATORS NOW LIVE IN `player_names` (lane1/057 STEP 0).
#
# Same functions, same rules, same sweep behind `SUBSTANTIAL_TOKEN_CHARS` —
# moved because the tennis ESPN anchor has to ask "are these the same person"
# before it may stamp an `espn_id`, and a SECOND comparator over there is how
# the slate would come to withhold a fixture the anchor had just linked.
#
# Bound to the private names this module has always used so every call site and
# the existing test keep reading unchanged.
from app.utils.player_names import (  # noqa: E402
    SUBSTANTIAL_TOKEN_CHARS,
    name_tokens as _name_tokens,
    names_agree as _names_agree,
    pairing_agrees,
    token_covered as _token_covered,
)

__all_name_comparators__ = (
    "SUBSTANTIAL_TOKEN_CHARS",
    "_name_tokens",
    "_names_agree",
    "_token_covered",
    "pairing_agrees",
)


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
        # This side's OWN book grade (UX-P157). Both sides of a match are two
        # tokens on one venue book, but they are two DIFFERENT venue rows here
        # and either may be the thin one, so neither speaks for the other.
        "liquidity": (loaded.get("liquidity") or {}).get("level") or LIQUIDITY_UNKNOWN,
        "liquidity_reasons": sorted((loaded.get("liquidity") or {}).get("reasons") or []),
    }


def build_match_row(
    reg: TournamentRegister,
    matchup: dict[str, Any],
    *,
    prices: dict[int, dict[str, Any]],
    now: datetime,
    cutoff: Optional[datetime],
    event_ids: Optional[dict[str, int]] = None,
    order_of_play: Optional[dict[str, dict[str, Any]]] = None,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """ONE matchup -> one slate row, or a named reason it is not one.

    Extracted from ``build_slate``'s loop by UX-P149 so the match detail page
    (``app.utils.tournament_match``) renders a fixture through **the same
    definition of a match row** the list does, rather than through a second
    copy that agrees today.  Two surfaces each computing "the favourite" or
    "is this coherent" is the divergence bug in miniature; the standing ruling
    is that the blend is the product and one question gets one number.

    ``cutoff`` is the only difference between the two callers, and it is the
    reason this is a parameter rather than a constant:

    * The **slate** passes ``now - MATCH_STALE_AFTER_HOURS`` and drops anything
      older, because a list of "what is on" must not still be showing this
      morning's matches at midnight (refusal 3 in the module docstring).
    * The **match page** passes ``None``.  A page about one fixture is not a
      claim that the fixture is upcoming, and 404-ing a match because it has
      started is the worst possible moment to stop answering questions about
      it.

    ``order_of_play`` (Q463) is ESPN's live card, keyed by competition id — see
    doctrine 3 in the module docstring for why an elapsed-time rule alone read
    "No matches scheduled" through the whole of the US Open's opening day.
    ``cutoff`` gates its refusal too, and for the same reason it gates the
    clock's: only a caller asking "what is on" wants a decided match withheld.

    This row builder takes **no completeness argument** (CERT-548).  It used to,
    and the flag decided whether a pinned fixture the scoreboard never mentioned
    was retired by the clock.  Both ends of that rule have since been shown to
    be the wrong question — the near end by CERT-532, the far end by CERT-548 —
    for the same reason twice: ``order_of_play_complete`` is a fact about a
    REQUEST, and neither "is this match still to come" nor "is this tournament
    over" can be answered from one.  It survives as a payload diagnostic on
    ``build_slate``, which is what CERT-517 actually needed it for.

    Returns ``(row, None)`` or ``(None, reason)``.  Never both, never neither.
    """
    players = matchup.get("players")
    if not isinstance(players, list) or len(players) != 2:
        return None, "NOT_A_PAIR"

    started = _parse_moment(matchup.get("scheduled_date"))

    # THE SCOREBOARD FIRST, THE CLOCK ONLY WHERE IT IS SILENT (Q463).
    #
    # `comp_id` is an id the register pinned at the draw ceremony, so this is a
    # dict lookup and none of this page's no-request-time-name-matching posture
    # is spent on it.
    # LAZY, like this module's other `espn_tennis` import, and load-bearing.
    # `app/services/__init__` imports SQLAlchemy, and `test_comparison_specimen`
    # runs the specimen producer with `-S` and no third-party packages to keep
    # it runnable inside the frontend CI job. A module-level import here breaks
    # that job — same discipline as gotcha #3's for `sport_keys`.
    from app.services.espn_tennis import DECIDED_SLATE_STATE

    comp_id = espn_competition_id(matchup)
    listed = (order_of_play or {}).get(comp_id) if comp_id else None
    live_state: Optional[str] = None
    status_detail: Optional[str] = None
    start_is_tbd = False

    if listed is not None:
        live_state = str(listed.get("state") or "") or None
        status_detail = listed.get("status_detail")
        start_is_tbd = listed.get("start_is_tbd") is True
        # ESPN's real start supersedes the register's ceremony-day placeholder
        # — but only when ESPN has one. A missing or unparseable date must not
        # blank a start we already hold.
        started = _parse_moment(listed.get("start_at")) or started
        if live_state == DECIDED_SLATE_STATE and cutoff is not None:
            # ESPN SAYS SO, IN A WORD (CERT-517).
            #
            # This is the ONLY route to DECIDED. Q463 inferred it from absence
            # instead, and a partial scoreboard fetch — which
            # `fetch_tournament_results` permits by design and the task caches
            # anyway — then read every live fixture on the failed tour as
            # finished. The match belongs to `build_results`; its own reason,
            # never folded into ALREADY_PLAYED, because one of these is a fact
            # from the source and the other is an inference from the clock.
            return None, "DECIDED"

        # ═══ Q503: THE SCOREBOARD NAMES THE PLAYERS, TOO ═══
        #
        # Checked AFTER `DECIDED` on purpose: a finished match belongs to
        # `build_results` whatever else is wrong with it, and re-labelling one
        # as a pairing dispute would move it out of the section that can show
        # its score.
        #
        # THE DEFECT, measured on production 2026-09-01: the register's pairing
        # for competition 182710 was `Cerundolo vs Ruud` — a KALSHI MARKET'S
        # NAME, pinned into the register by the post-ceremony census because no
        # match market existed at ceremony time. Ruud had withdrawn; Arthur Gea
        # was on court. The ceremony anchor was CORRECT, so every id-based check
        # passed, and the card rendered ESPN's clock ("3rd Set") over a market's
        # idea of who was playing. Four of 96 anchored fixtures were in this
        # state, three of them on the day's card.
        #
        # A market ATTACHES to a fixture; it does not get to name one. So where
        # the authority names both competitors and contradicts us, the fixture
        # is withheld — not re-labelled. Re-labelling would carry a price
        # quoted for a match nobody is playing onto the two people who really
        # are, which is the same fabrication wearing better names. Rendering
        # the authority's pairing as a first-class unpriced card is the next
        # slice and needs player identity we do not hold for a post-ceremony
        # entrant.
        registered_names = [
            (reg.by_entity.get(key) or {}).get("display_name") or key
            for key in players
        ]
        if not pairing_agrees(registered_names, listed.get("players")):
            return None, "PAIRING_DISAGREES"

    if started is None:
        return None, "NO_SCHEDULED_START"
    if cutoff is not None and listed is None and started < cutoff:
        # THE CLOCK, ONLY WHERE THE SCOREBOARD NEVER SPOKE.
        #
        # Registered when it was upcoming, not on the scoreboard now. Reached by
        # the qualifying draw, whose matchups the ceremony census never stamped
        # with a competition id at all.
        #
        # CERT-517: a fixture that DOES carry a pinned id is exempt while the
        # scoreboard read is INCOMPLETE. A pinned id means the ceremony matched
        # this fixture to a real ESPN competition, so a complete scoreboard
        # would have said a word about it; its silence is then a fact about the
        # fetch, and the register's `scheduled_date` — for the main draw, the
        # 04:00Z midnight-local placeholder — is not a start to measure against.
        # Dropping on it is exactly how opening day emptied itself. The
        # qualifying draw has no id and is unaffected, so this exemption costs
        # nothing on a healthy read and saves the card on a flaky one.
        #
        # ═══ CERT-532: THE FLAG WAS NEVER THE RIGHT THING TO ASK ═══
        #
        # That exemption is only as good as `order_of_play_complete`, and the
        # cert's finding is that the flag can be wrong while every clause
        # computing it is satisfied — a named shell with no competitions, and
        # in general "a nonempty but truncated map has the same uncovered shape
        # for any omitted pinned id". Tightening the flag closes the routes we
        # have thought of. It cannot close the class, because the class is a
        # consumer reading ABSENCE from the map as a fact about the match.
        #
        # So the second condition does not consult the flag at all.
        #
        # ⚠️ THAT SENTENCE WAS NOT TRUE WHEN IT WAS WRITTEN, and CERT-548 is what
        # it cost. Q468 freed the NEAR end and left the FAR end conjoined with
        # the flag, then wrote the rule as though both were done. It is true now
        # — see the CERT-548 block below, which is the change that made it so.
        #
        # ═══ CERT-544: AND IT MUST NOT CONSULT THE STAMP AS A DAY EITHER ═══
        #
        # The first version of this said "a ceremony stamp names a day, so the
        # clock may not retire a pinned fixture until that day has elapsed",
        # and allowed 24 hours. But the stamp is written ONCE FOR THE WHOLE
        # CEREMONY — 96 of 96 pinned fixtures share `2026-08-30T04:00Z` — so it
        # names opening day for every match in the draw, including the final
        # two weeks later. The bound expired for all 96 at once at 06:01 ET on
        # day two, and the card could empty itself again on every day of the
        # tournament except the first. Fixing the opening-day blank alone is
        # not the ship.
        #
        # The stamp is now read only for what it can support. A draw ceremony
        # opens a tournament of bounded length, so it bounds the REGISTER'S
        # RELEVANCE and nothing finer. Inside that window the clock has no
        # authority over a pinned fixture at all: absence is never a fact about
        # the match, and the only thing that retires one is ESPN's explicit
        # `decided`, handled above. Outside it, the register describes a
        # tournament that is over.
        #
        # The cost is named: a pinned fixture that really did finish, on a day
        # ESPN's scoreboard never covered while it was `post`, now lingers for
        # the rest of the tournament rather than a day. That is the ambiguous
        # case, and it is still the direction to be wrong in — a stale row is a
        # smaller lie than a draw that vanishes on the morning it is played,
        # and it takes a sustained scoreboard outage to reach at all.
        #
        # ═══ CERT-548: AND THE FAR END IS NOT ABOUT THE SCOREBOARD EITHER ═══
        #
        # Q469 freed the NEAR end from `order_of_play_complete` and left the FAR
        # end conjoined with it, so the bound only existed on a read we had
        # called complete. **After a tournament ends ESPN stops listing it, and
        # that is exactly when completeness reads false — permanently.** The
        # register's fixtures then had no far end at all: a month past the
        # ceremony all 96 pinned main-draw rows were still on "what is on".
        #
        # The two questions are about different things and only one of them is
        # about the fetch. `order_of_play_complete` is a fact about a REQUEST.
        # The far end is a claim about the REGISTER — "the tournament this
        # ceremony opened is over" — and the clock and the ceremony stamp are the
        # only two things that can answer it. Conjoining them made retirement
        # conditional on the scoreboard mentioning a tournament it has no reason
        # to mention any more: a condition that, once unmet, can never be met
        # again. So neither end consults the flag, and the flag governs nothing
        # here at all — it is reported in the payload and it does not decide.
        if comp_id:
            retire = started < (
                cutoff - timedelta(hours=CEREMONY_STAMP_COVERS_THE_TOURNAMENT_HOURS)
            )
        else:
            retire = True
        if retire:
            return None, "ALREADY_PLAYED"

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
            return None, "SIDES_UNMAPPED"
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
        return None, "PLAYER_NOT_REGISTERED"

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
    return {
        "priced": block is not None,
        "matchup_key": matchup.get("matchup_key"),
        # OUR `events.id` for this fixture — the row this match card ROUTES TO
        # (UX-P139 item 7, made real by UX-P152).
        #
        # Two ways it can be filled, both id-anchored and neither a name match:
        # the register may pin it directly, or `tournament_event_link` may
        # dereference the pinned match-winner `market_id` through
        # `futures_markets.event_id`. `event_ids` carries the second and the
        # register's own value wins when both exist.
        #
        # Measured 2026-08-28: the Odds API ingested US Open main-draw singles
        # the previous evening, so 94 of the 96 R128 fixtures now have a
        # standard `events` row. It is no longer true that "the draw has no
        # events rows" — that was measured before the ingest and expired.
        "event_id": matchup.get("event_id")
        or (event_ids or {}).get(matchup.get("matchup_key")),
        "draw": matchup.get("draw"),
        "draw_label": draw_label(str(matchup.get("draw") or "")),
        "round": matchup.get("round"),
        "scheduled_date": started.isoformat(),
        # IS THIS ON RIGHT NOW (Q463)? `in_progress` / `upcoming` / `None`, from
        # ESPN's own state and never from comparing the start to the clock — a
        # five-set match outlives any elapsed-time window, and "started 7 hours
        # ago" is not evidence a match is over. `None` means no scoreboard entry
        # for this fixture, which is honest and is what every caller that passes
        # no `order_of_play` gets.
        "live_state": live_state,
        # ESPN's display text for that state ("2nd Set"). Beside the enum, never
        # instead of it: a renderer branches on `live_state` and prints this.
        "status_detail": status_detail,
        # IS `scheduled_date` A TIME, OR A DAY WEARING ONE (Q463)?
        #
        # `True` means the source has not published an order of play for this
        # fixture, so the timestamp is midnight local — the exact value that,
        # read as a start, emptied this card for a whole day. A renderer must
        # print "TBD" and not "12:00 AM": the placeholder was never wrong as
        # DATA, only as something displayed or compared without this flag.
        "start_is_tbd": start_is_tbd,
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
        # THE AND, again: a match row prints one pair, so it is as solid as its
        # thinner side. A 90/10 built from a traded favourite and an untraded
        # underdog is not a traded 90/10 — the underdog's book is half of it.
        "liquidity": thinnest_liquidity([v.get("liquidity") for v in views]),
        "liquidity_reasons": sorted(
            {r for v in views for r in (v.get("liquidity_reasons") or [])}
        ),
    }, None


def authority_match_row(
    matchup: dict[str, Any],
    listed: dict[str, Any],
    *,
    now: datetime,
    link: Optional[dict[str, Any]] = None,
    prices: Optional[dict[int, dict[str, Any]]] = None,
) -> Optional[dict[str, Any]]:
    """The fixture as the AUTHORITY names it, or ``None``.

    ═══ Q505: WITHHOLDING THE WRONG MATCH IS HALF THE REPAIR ═══

    Q503 established that a market may not name a fixture, and withheld the
    four US Open fixtures whose register pairing ESPN contradicted.  That was
    the right refusal and it left the card with a hole: at 15:20 PT on
    2026-09-01 the top row read *"Casper Ruud 60% / Juan Manuel Cerundolo
    40% — 1:20 PM"* while Cerundolo was on court against **Arthur Gea**, and
    Q503's answer was for that row to disappear.  Three matches really being
    played would then have been absent from the day's card — which is doctrine
    rule 1's other failure, "every match exactly once", arrived at from the
    other side.

    **Only the NAMES were ever in dispute.**  The ESPN competition anchor on
    each of these fixtures is correct (182710 really is the match on court),
    so its draw, its round, its clock and its state are facts about a fixture
    we have correctly identified.  What the register got wrong — from a Kalshi
    market's title, pinned by a post-ceremony census — is who is playing it.
    So this row is the register's fixture with **the authority's two people
    substituted and the price removed**, not a new fixture invented here.

    THE REGISTER'S PRICE IS REMOVED AND THAT IS THE POINT.  Q503 declined to
    re-label because carrying a 60/40 quoted for a match nobody is playing onto
    the two who really are "would be the same fabrication wearing better names".
    That objection is to that NUMBER, not to the names, and it is unchanged: the
    register's pinned outcome ids are never read on this path.

    ═══ lane1/047: AND THE MATCH'S OWN MARKET IS NOT THAT NUMBER ═══

    Q505 finished with *"when the match market for the real pairing is linked,
    the ordinary priced row takes over"*, and nothing linked it, so no such row
    ever existed.  Measured on production 2026-09-02, the US Open slate carried
    one authority row — ``espn:182703``, Rafael Jodar vs Bu Yunchaokete — and it
    printed *"Nobody is quoting this match yet."*  We were holding
    ``KXATPMATCH-26SEP01JODYUN`` at that moment, open, both legs named in full,
    at 0.895 / 0.105.  A probability product telling a reader the market is
    silent while quoting 90/10 one tab over is the worst version of this bug,
    and the absence was structural: this function was never passed a price.

    ``link`` is now that price, and it is emphatically NOT a re-label of the
    withheld one.  It is a block ``resolve_authority_links`` minted on the
    linker's beat by matching **the two players ESPN names** against the same
    Kalshi candidate pool, under the same token-set correspondence, the same
    unique-bijection requirement and the same one-day date window the register
    path uses.  Its ``sides`` map is keyed by this row's own
    ``espn:athlete:<id>``, so reading it here is a dict lookup on an id — the
    request-time work is a hash, not a name comparison, and the page's "no
    matching on the request path" guarantee is intact.

    Absent, unmatched, or priced on only one side, every field falls back to
    exactly the constant Q505 wrote and the card prints two people and a clock.

    IT ALSO DOES NOT LINK.  ``event_id`` is ``None``, so the card is not
    clickable — ``build_match_detail`` is passed no ``order_of_play`` and would
    render the fabricated pairing on the detail page (Q503 carry-forward 1).  A
    dead-ended honest card is better than a live link to the lie.

    ``None`` when the scoreboard does not name two identified people for this
    competition: doubles competitions name a team and no athlete, and a
    qualifier slot names "TBD" with a non-positive id.  A half-read is silence,
    and silence leaves Q503's plain withhold in place — the caller must not
    invent a side.
    """
    competitors = listed.get("competitors")
    if not isinstance(competitors, list) or len(competitors) != 2:
        return None
    if not all(
        isinstance(c, dict) and c.get("determined") and c.get("name")
        for c in competitors
    ):
        return None

    # ESPN's `order` is the scoreboard's own top-to-bottom, and it is the only
    # ordering available: with no probabilities there is no favourite to lead
    # with, and the register's side order describes a pairing that is wrong.
    ordered = sorted(
        competitors,
        key=lambda c: (c.get("order") is None, c.get("order") or 0),
    )

    started = _parse_moment(listed.get("start_at")) or _parse_moment(
        matchup.get("scheduled_date")
    )
    if started is None:
        # Every row on this card sorts on its start and every renderer prints
        # one. A row with no start is not a better card than no row.
        return None

    comp_id = listed.get("espn_competition_id") or espn_competition_id(matchup)

    # THE PRICE FOR THE PAIRING THAT IS ACTUALLY ON (lane1/047).
    #
    # `link` is a pre-resolved block from `resolve_authority_links`, minted on
    # the linker's beat and keyed on this row's own `espn:<comp id>`. Its
    # `sides` map is `espn:athlete:<id> -> {"outcome_id": ...}`, so what happens
    # here is a dict lookup on an id — the same kind of read the register path
    # makes, and NOT the request-time name matching this page forbids. `None`
    # (no link, a link whose sides do not cover both of these two athletes, or
    # a link whose outcomes we hold no price for) leaves the row exactly as
    # Q505 built it: two people, a clock, and no number.
    sides_map: dict[str, Any] = {}
    if isinstance(link, dict):
        candidate_sides = link.get("sides")
        if isinstance(candidate_sides, dict):
            sides_map = candidate_sides
    loaded_by_key: dict[str, dict[str, Any]] = {}
    for c in ordered:
        entity_key = f"espn:athlete:{c.get('espn_athlete_id')}"
        outcome_id = (sides_map.get(entity_key) or {}).get("outcome_id")
        loaded = (prices or {}).get(outcome_id) if isinstance(outcome_id, int) else None
        if loaded is not None:
            loaded_by_key[entity_key] = loaded
    # BOTH SIDES OR NEITHER. One priced side is not half a match — it is a
    # single independent binary, and normalising a pair against a missing
    # partner is exactly the fabrication `normalize_pair` exists to refuse.
    if len(loaded_by_key) != 2:
        loaded_by_key = {}

    sides = []
    for c in ordered:
        # NOT a register entity key — there is no register entity for a player
        # who entered after the ceremony, which is exactly how two of these
        # four arrived. Namespaced so it can never collide with one, and so a
        # reader of the payload can see at a glance that this side came from
        # the scoreboard.
        entity_key = f"espn:athlete:{c.get('espn_athlete_id')}"
        loaded = loaded_by_key.get(entity_key) or {}
        liquidity = loaded.get("liquidity") or {}
        sides.append({
            "entity_key": entity_key,
            "display_name": c.get("name"),
            # The register holds the seed, and the register is what is wrong
            # about this fixture. ESPN's scoreboard competitor carries none.
            "seed": None,
            "country": c.get("country"),
            # No face: the verified-photograph census is keyed on register
            # entities (`census_player_images.py`), and ESPN's own headshots
            # failed that census at 40%/28% coverage. The flag is on the same
            # record as the name at 100%, which is `PlayerAvatar`'s second step
            # and what every draw sheet in tennis has printed for fifty years.
            "image": {"url": None, "flag_url": c.get("flag_url")},
            "role": "contender",
            "probability": None,
            "opening_probability": None,
            "move": None,
            "raw_probability": _as_float(loaded.get("probability")),
            "raw_opening_probability": _as_float(loaded.get("opening_probability")),
            "observed_at": loaded.get("observed_at"),
            "age_hours": None,
            "price_state": "unpriced",
            "liquidity": liquidity.get("level") or LIQUIDITY_UNKNOWN,
            "liquidity_reasons": sorted(liquidity.get("reasons") or []),
        })

    # Everything below is the ordinary priced-row arithmetic, reached only when
    # both sides found a price. With `loaded_by_key` empty every `raw_*` above
    # is None, `normalize_pair` refuses, and each field falls back to exactly
    # the constant Q505 wrote.
    side_times: list[Optional[datetime]] = [
        s["observed_at"] if isinstance(s["observed_at"], datetime) else None
        for s in sides
    ]
    a_norm, b_norm, raw_sum, coherent = normalize_pair(
        sides[0]["raw_probability"], sides[1]["raw_probability"]
    )
    a_open, b_open, open_sum, open_coherent = normalize_pair(
        sides[0]["raw_opening_probability"], sides[1]["raw_opening_probability"]
    )
    if coherent:
        sides[0]["probability"] = a_norm
        sides[1]["probability"] = b_norm
    if open_coherent:
        sides[0]["opening_probability"] = a_open
        sides[1]["opening_probability"] = b_open
    if coherent and open_coherent:
        for side in sides:
            side["move"] = round(
                side["probability"] - side["opening_probability"], 6
            )

    # THE AND (UX-P135): the pair is as old as its older side — the same rule
    # `build_match_row` holds itself to, so an authority row and a register row
    # on one card cannot be graded on two different definitions of fresh.
    age = governing_age_hours(side_times, now)
    state = price_state(age)
    newest = freshest_observation(side_times)
    freshest_age = (now - newest).total_seconds() / 3600.0 if newest else None
    priced = bool(loaded_by_key)
    if priced:
        # ONLY WHEN A PRICE EXISTS. `price_state(None)` is `dark` — "a reading
        # we have, gone stale" — and an unpriced side has no reading to have
        # gone stale. Writing it here would turn Q505's honest `unpriced` into a
        # word that means the opposite, which is the distinction the row-level
        # field's own comment calls out as not collapsible.
        for side, observed in zip(sides, side_times):
            side_age = (
                (now - observed).total_seconds() / 3600.0
                if observed is not None
                else None
            )
            side["age_hours"] = round(side_age, 2) if side_age is not None else None
            side["price_state"] = price_state(side_age)
    favourite = None
    if coherent:
        favourite = (
            sides[0]["entity_key"]
            if (sides[0]["probability"] or 0) >= (sides[1]["probability"] or 0)
            else sides[1]["entity_key"]
        )
    moves = [s["move"] for s in sides if s["move"] is not None]

    return {
        "priced": priced,
        # THE COMPETITION IS THE KEY, NOT THE REGISTER'S MATCHUP.
        #
        # Reusing the register's `matchup_key` would file two different
        # pairings under one id and hand the fabricated one a route into every
        # consumer that keys on it. The competition id is the thing both
        # halves actually agree on, and it is the authority's own name for
        # this fixture.
        "matchup_key": f"espn:{comp_id}",
        "event_id": None,
        # Facts about the FIXTURE, which is correctly anchored — see the
        # docstring. Only the pairing was ever in dispute.
        "draw": matchup.get("draw"),
        "draw_label": draw_label(str(matchup.get("draw") or "")),
        "round": matchup.get("round"),
        "scheduled_date": started.isoformat(),
        "live_state": str(listed.get("state") or "") or None,
        "status_detail": listed.get("status_detail"),
        "start_is_tbd": listed.get("start_is_tbd") is True,
        "sides": sides,
        # UNPRICED, `coherent: False` with `priced: False` is the released-draw
        # shape the card already renders (UX-P142): a full row, faces and names,
        # and no number. It is NOT the incoherent-pair shape, which collapses
        # the row to one line — that treatment is for a split we are refusing to
        # show, and there is no split to refuse when nothing quoted the pairing.
        #
        # PRICED (lane1/047), every one of these carries the same value the
        # ordinary register row would: the honesty fields are the reader's, not
        # the pairing path's, and an authority row that quoted a number while
        # reporting `price_state: "unpriced"` would be lying in a new place.
        "coherent": coherent,
        "raw_sum": raw_sum,
        "opening_raw_sum": open_sum,
        "probability_is_live": state == "live" and coherent,
        "price_state": state if priced else "unpriced",
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
        "stale_sides": [s["entity_key"] for s in sides if s["price_state"] != "live"]
        if priced
        else [],
        "mixed_freshness": (
            0 < len([s for s in sides if s["price_state"] != "live"]) < len(sides)
            if priced
            else False
        ),
        "favourite": favourite,
        "has_moved": any(abs(m) > MOVE_DEAD_BAND for m in moves),
        # `1` is a claim that a source priced this pairing, so it is only true
        # once one has. Unpriced it stays `0`, exactly as Q505 wrote it.
        "source_count": 1 if priced else 0,
        # THE AND, again: a match row prints one pair, so it is as solid as its
        # thinner side.
        "liquidity": thinnest_liquidity([s.get("liquidity") for s in sides]),
        "liquidity_reasons": sorted(
            {r for s in sides for r in (s.get("liquidity_reasons") or [])}
        ),
        # WHO NAMED THESE TWO PEOPLE. Absent on every ordinary row, so a
        # consumer that has never heard of this field cannot mistake one for
        # the other, and a guard can assert the substitution actually happened
        # rather than inferring it from a missing price.
        "pairing_source": "authority",
    }


def build_slate(
    register: dict[str, Any],
    *,
    prices: dict[int, dict[str, Any]],
    now: datetime,
    max_stale_hours: float = MATCH_STALE_AFTER_HOURS,
    event_ids: Optional[dict[str, int]] = None,
    order_of_play: Optional[dict[str, dict[str, Any]]] = None,
    order_of_play_complete: bool = True,
    authority_links: Optional[dict[str, dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Assemble the daily slate payload.

    ``prices`` is keyed by ``outcome_id`` and carries ``{"probability",
    "opening_probability", "observed_at"}``.  Keying on the outcome id the
    register pins — rather than on anything derived from a name at request time
    — is what makes the sides mapping load-bearing instead of decorative.

    ``order_of_play`` is ``espn_tennis.parse_results``' map of ESPN competition
    id -> ``{"state", "start_at", ...}`` for **every** competition on the
    scoreboard, decided ones included.  Where it speaks it is the authority on
    both questions the clock rule was guessing at — is this fixture still to
    come, and when does it actually start — for the reasons set out as doctrine
    3 in the module docstring.  ``None`` or ``{}`` leaves every fixture on the
    elapsed-time fallback, which is what a caller with no scoreboard gets and
    what this page did before Q463.

    ``order_of_play_complete`` says whether that map is the whole scoreboard or
    the surviving half of a partial fetch (CERT-517).  **It is a diagnostic and
    nothing else** — it is reported in the payload and no row is built, kept or
    dropped on it.  That is CERT-548's correction, and CERT-532's before it: the
    flag is a fact about a request, so it cannot answer either question the row
    rule asks, and gating retirement on it made a finished tournament — which no
    scoreboard has any reason to keep listing — unretirable forever.

    It earns the payload slot for the reason CERT-517 named.  A short slate under
    a partial fetch and a short slate on a quiet day are otherwise the same
    bytes, and only one of them is somebody's emergency.
    """
    reg = TournamentRegister(register)
    cutoff = now - timedelta(hours=max_stale_hours)

    rows: list[dict[str, Any]] = []
    dropped: dict[str, int] = {}
    withheld_pairings: list[dict[str, Any]] = []

    for matchup in reg.matchups:
        row, reason = build_match_row(
            reg,
            matchup,
            prices=prices,
            now=now,
            cutoff=cutoff,
            event_ids=event_ids,
            order_of_play=order_of_play,
        )
        if row is None:
            reason = reason or "UNKNOWN"
            dropped[reason] = dropped.get(reason, 0) + 1
            if reason == "PAIRING_DISAGREES":
                # THE QUARANTINE SAYS WHO (Q503, doctrine rule 6). A count
                # alone is a shrug: "3 withheld" cannot be acted on, and the
                # repair — the register naming a player who left the draw —
                # is only obvious once both pairings are side by side.
                comp_id = espn_competition_id(matchup)
                listed = (order_of_play or {}).get(comp_id) if comp_id else None
                # ═══ Q505: AND THE CARD SHOWS THE MATCH THAT IS ON ═══
                #
                # The withhold above removes a pairing nobody is playing. On
                # its own it also removes a fixture that IS being played, and
                # the reader is left with a hole where a live match should be.
                # So the same fixture comes back named by the authority and
                # carrying no price — see `authority_match_row`. `None` means
                # the scoreboard did not name two identified people, and then
                # the plain withhold stands.
                # lane1/047: and it carries the price for the pairing that is
                # actually on, when the linker's beat resolved one. Looked up by
                # the row's own key, so a link for a different competition can
                # never reach this row.
                replacement = (
                    authority_match_row(
                        matchup,
                        listed,
                        now=now,
                        link=(authority_links or {}).get(f"espn:{comp_id}|kalshi"),
                        prices=prices,
                    )
                    if listed is not None
                    else None
                )
                if replacement is not None:
                    rows.append(replacement)
                withheld_pairings.append({
                    "matchup_key": matchup.get("matchup_key"),
                    "draw": matchup.get("draw"),
                    "espn_competition_id": comp_id,
                    "registered": [
                        (reg.by_entity.get(key) or {}).get("display_name") or key
                        for key in (matchup.get("players") or [])
                    ],
                    "authority": list((listed or {}).get("players") or []),
                    # Did the reader get the real match back, or only lose the
                    # wrong one? Two different states of this page, and a
                    # count of withholds cannot tell them apart.
                    "replaced_by": (
                        replacement.get("matchup_key") if replacement else None
                    ),
                })
            continue
        rows.append(row)

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
        # THE TWO NUMBERS THAT MAKE AN EMPTY SLATE DIAGNOSABLE (Q463, gotcha
        # #53). "Nothing is on" and "the overlay joined nothing" render
        # identically and need different people; before this, opening day's
        # empty card carried no signal at all that a whole draw had been
        # dropped by a clock rule.
        "in_progress": sum(1 for r in rows if r.get("live_state") == "in_progress"),
        "order_of_play_listed": len(order_of_play or {}),
        # WHETHER THE MAP ABOVE IS THE WHOLE SCOREBOARD (CERT-517). A short
        # slate under a partial fetch and a short slate on a quiet day are the
        # same payload without this, and the second one is nobody's emergency.
        "order_of_play_complete": bool(order_of_play_complete),
        "dropped": dict(sorted(dropped.items())),
        # WHICH FIXTURES THE AUTHORITY CONTRADICTED, BY NAME (Q503). Empty is
        # the healthy state and the honest one — an empty list says the
        # scoreboard agreed with every anchored pairing it named, which is a
        # different statement from never having asked.
        "withheld_pairings": withheld_pairings,
        # HOW MANY ROWS THE SCOREBOARD NAMED RATHER THAN THE REGISTER (Q505).
        # A repair backlog with a number on it: every one of these is a
        # register row still carrying a player who is not in the draw.
        "authority_pairings": sum(
            1 for r in rows if r.get("pairing_source") == "authority"
        ),
        # AND HOW MANY OF THOSE CARRY A NUMBER (lane1/047). The two counts are
        # different questions and the gap between them is the live one: a
        # substituted row with no price is a reader being told nobody quotes a
        # match we may well hold. `authority_pairings - authority_priced` is
        # that population, on the payload, without a database round trip.
        "authority_priced": sum(
            1
            for r in rows
            if r.get("pairing_source") == "authority" and r.get("priced")
        ),
        "price_state": price_state(slate_age),
        "newest_observed_at": newest_overall.isoformat() if newest_overall else None,
        "age_hours": round(slate_age, 2) if slate_age is not None else None,
        "dark_after_hours": DARK_PRICE_HOURS,
    }


def _prematch_by_pair(
    reg: TournamentRegister, prices: dict[int, dict[str, Any]]
) -> dict[tuple, dict[str, float]]:
    """``(draw, sorted entity keys) -> {entity_key: pre-match probability}``.

    ═══ UX-P146: A RESULT WITHOUT ITS PRIOR IS HALF THE STORY ═══

    Alex, on the UX-P145 desktop artifact: "finished outcomes on the right must
    show their PRE-MATCH probabilities alongside the result — a result without
    the prior probability is half the story on a probability product."  He is
    describing the whole reason this site exists: *Kubka beat Penickova* is a
    scoreline anyone can get; *Kubka beat Penickova, and the market had her at
    38%* is the product.

    THE NUMBER IS THE OPENING QUOTE, and that is a deliberate choice rather than
    a convenience.  ``futures_outcomes`` carries exactly two prices per outcome:
    ``current_probability`` and ``opening_probability``.  The current one is
    poisoned for this purpose — a decided match's market settles, so "what the
    market thought" would render as 100% for every winner and 0% for every
    loser, a perfectly confident number that is really just the result read
    back.  The opening quote is the only stored price that is guaranteed to
    pre-date the match.  It is what the slate already calls THE SCRIPT.

    NORMALIZED AS A PAIR, through the same ``normalize_pair`` the slate uses, so
    a finished match and a live one on the same page are quoted on the same
    basis — and so an incoherent pair yields nothing at all rather than a tidy
    fabricated split (see refusal 2 in the module docstring).

    WHY THIS IS NOT AVAILABLE FOR EVERY RESULT, stated here because the caller
    has to report it honestly: a pre-match probability exists only where the
    register pinned a MATCHUP market for that pair.  Measured against the
    2026-08-27 production payload, 12 of 76 joined results have one.  The other
    64 are qualifying matches we hold player-level markets for but for which no
    match market was ever registered — there is no prior to show, and inventing
    one from the title board (a player's chance of winning the tournament is not
    their chance of winning a first-round match) would be a fabricated number
    wearing a real player's name.
    """
    out: dict[tuple, dict[str, Any]] = {}
    for matchup in reg.matchups:
        players = matchup.get("players")
        if not isinstance(players, list) or len(players) != 2:
            continue
        # ══ ux/1036: THE LADDER IS ORDERED, AND IT USED TO BE WHICHEVER CAME
        #    FIRST ══
        #
        # This took `next(... status == "live")` — the first live block in
        # register order. Where a pair is pinned at BOTH venues that is an
        # arbitrary choice between two different numbers, decided by the order
        # an agent happened to write the register file in.
        #
        # Alex's rule for the settled pre-match reading, given for #2747 and
        # applied to every surface by ux/1036: **Kalshi → Polymarket → books**,
        # ordered and never merged. `prematch_source_rank` is that order, and it
        # is the SAME constant the feed's game cards resolve against, so the two
        # surfaces cannot drift into quoting different venues for the same kind
        # of question.
        #
        # The books rung is not reachable from here and that is stated rather
        # than half-built: `Event.opening_*` is per-EVENT, and the only
        # id-anchored path from a finished row to its event is
        # `event_links.by_matchup`, which by construction covers only pairs the
        # register still carries a matchup for. The row Alex read
        # (Shelton–Hurkacz, `espn:182730`) is not one of them — see #2747, which
        # stays open for it.
        blocks = sorted(
            (
                b for b in (matchup.get("sources") or [])
                if isinstance(b, dict) and b.get("status") == "live"
            ),
            key=lambda b: prematch_source_rank(b.get("source")),
        )
        for block in blocks:
            sides = block.get("sides")
            if not isinstance(sides, dict) or set(sides) != set(players):
                continue

            raw: list[Optional[float]] = []
            for entity_key in players:
                side = sides.get(entity_key) or {}
                outcome_id = side.get("outcome_id")
                loaded = prices.get(outcome_id) if isinstance(outcome_id, int) else None
                raw.append(_as_float((loaded or {}).get("opening_probability")))

            a_open, b_open, _sum, coherent = normalize_pair(raw[0], raw[1])
            if not coherent or a_open is None or b_open is None:
                # Not "this pair has no prior" — "this VENUE has no coherent one".
                # Falling through to the next rung is the whole point of an
                # ordered ladder; the old single-block form could not.
                continue
            out[(str(matchup.get("draw")), tuple(sorted(players)))] = {
                "probabilities": {players[0]: a_open, players[1]: b_open},
                "source": block.get("source"),
            }
            break
    return out


def build_results(
    register: dict[str, Any],
    *,
    results: dict[str, Any],
    prices: Optional[dict[int, dict[str, Any]]] = None,
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

    from app.services.espn_tennis import COMPLETION_UNKNOWN, normalize_name

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

    # What the market said BEFORE the match (UX-P146). Same pair key as the
    # matchup lookup above, so a result carries its prior exactly when the
    # register still pins the market that published it.
    prematch_by_pair = _prematch_by_pair(reg, prices or {})
    with_prematch = 0
    # Which avatar step each of the two slots on each row lands on (UX-P206).
    with_face = 0
    with_flag = 0

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

            prematch = prematch_by_pair.get((draw, tuple(sorted(keys))))
            prematch_probs = (prematch or {}).get("probabilities") or {}
            prematch_source = (prematch or {}).get("source")
            if prematch:
                with_prematch += 1

            for entry in entries:
                image = player_image(entry)
                if image and image.get("url"):
                    with_face += 1
                elif image and image.get("flag_url"):
                    with_flag += 1

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
                     "seed": entry.get("seed"), "is_winner": key == winner_key,
                     # THE PLAYER'S FACE (UX-P206). The register-pinned block,
                     # through the same `player_image` the board and the slate
                     # read — so a finished match draws the same person, from
                     # the same verified pin, as the row that was live an hour
                     # ago. `None` where the register holds neither a picture
                     # nor a flag, which the renderer turns into initials.
                     "image": player_image(entry),
                     # WHAT THE MARKET SAID BEFORE IT (UX-P146). `None` where no
                     # match market was ever registered for this pair — an
                     # absence the section states rather than fills in. See
                     # `_prematch_by_pair` for why the opening quote and not the
                     # current one.
                     "prematch_probability": prematch_probs.get(key),
                     # WHICH VENUE SAID IT (ux/1036). Alex: label the number when
                     # it is not a prediction-market opening. Carried per player
                     # rather than per row because the ladder is resolved per
                     # PAIR and a row could one day hold two rungs; today both
                     # slots always agree, and a renderer that reads it off the
                     # player it labels cannot mislabel one of them.
                     "prematch_source": prematch_source if prematch_probs.get(key) is not None else None}
                    for key, entry in zip(keys, entries)
                ],
                "winner_entity_key": winner_key,
                # Winner's games first, set by set. `None` for a WALKOVER (no
                # set was played) or a partial read — see `format_score`.
                "score": found.get("score"),
                # HOW it ended (UX-P147, Alex's item 5): `final`, `retired`,
                # `walkover`, or `unknown`. The row that made him ask carried
                # neither a score nor a reason; ESPN had the reason all along
                # (`STATUS_WALKOVER`) and this is it reaching the reader. It
                # also marks the eight retirements whose scores are REAL but
                # partial, which nothing on the page said before.
                "completion": found.get("completion") or COMPLETION_UNKNOWN,
                "completed_at": found.get("completed_at"),
                "source_round": found.get("espn_round"),
                "source": "espn",
                # THE AUTHORITY'S OWN ID FOR THIS MATCH (#2693 step 2).
                # Published on EVERY row, not only on the rows whose
                # `matchup_key` happens to be `espn:…`. A register-keyed row has
                # a competition id too — it was simply being thrown away, and
                # with it the only channel that can link a finished match whose
                # market never attached (28 of the 34 `MARKET_UNLINKED` rows).
                # A field, not a prefix on another field: a reader should not
                # have to parse an identifier out of a key to find an id we
                # already hold.
                "espn_competition_id": (
                    str(found["espn_competition_id"])
                    if found.get("espn_competition_id") is not None
                    else None
                ),
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
        # How many of `matches` carry a pre-match probability (UX-P146). The
        # section prints this ratio: a prior shown on 12 rows and absent on 64
        # reads as a bug unless the page says which it is.
        "with_prematch": with_prematch,
        # IMAGE COVERAGE, IN PLAYER SLOTS, NOT ROWS (UX-P206).
        #
        # Alex's ruling-8 gate is coverage — "enable ONLY if coverage is
        # ~complete per draw; half-covered looks worse than none" — and a gate
        # nobody can read after the fact is a gate that gets re-argued from
        # memory.  These three sum to `2 * count` and say which of the three
        # avatar steps each slot landed on, so the day the register loses a
        # tranche of pins the payload says so instead of the page quietly
        # filling with grey initials.
        "player_slots": 2 * len(rows),
        "with_face": with_face,
        "with_flag": with_flag,
        "source_competitions": (results or {}).get("stats", {}).get("final", 0),
        "source_scored": (results or {}).get("stats", {}).get("scored", 0),
        # UX-P147: how the unscored ones ended, counted at the source rather
        # than guessed in prose. The provenance line said "retirement or
        # walkover" because nobody had measured which; now it can name them.
        "source_walkovers": (results or {}).get("stats", {}).get("walkovers", 0),
        "source_retirements": (results or {}).get("stats", {}).get("retirements", 0),
        "source_errors": (results or {}).get("errors") or [],
    }


def _prop_settlement(
    prop: dict[str, Any], *, now: datetime
) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """Is this curated question already answered by the calendar? (Q465)

    Returns ``(settled, settled_answer, settled_at, withhold_reason)``.  At most
    one of the last two is ever set: a card is either renderable — settled or
    not — or withheld with a named reason.

    ``settles_at`` is the instant the QUESTION is answered, which is not the
    instant the MARKET closes and not the instant we notice.  It is curated,
    because only the agent writing the register knows that "Will Sinner actually
    play?" is decided by the draw and the first ball rather than by
    ``resolution_date`` — which on that market reads five weeks out and is a
    close time anyway (gotcha #14).
    """
    raw = prop.get("settles_at")
    settles_at: Optional[datetime] = None
    if isinstance(raw, str) and raw:
        try:
            settles_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            # An unparseable instant is NOT a licence to guess. The card stays
            # live and the register validator names it — see
            # `PROP_SETTLES_AT_NOT_ISO`, which is structural precisely so this
            # branch is unreachable on a register that passed its gate.
            settles_at = None
    if settles_at is not None and settles_at.tzinfo is None:
        # A NAIVE STAMP IS READ AS UTC (CERT-527), and this line is load-bearing
        # rather than tidy. `is_iso8601` accepts an offset-less instant, so
        # `2026-08-30T15:05:00` passes the register's gate — and comparing it
        # with an aware `now` raises `TypeError`, which is a **500 on the whole
        # tournament route** from curated data the validator called valid.
        #
        # UTC is the right reading and not a shrug: every other writer in this
        # codebase stamps UTC, and `tournament_board._hours_since` already
        # states the same rule for the same reason. Coercing here means no
        # curated register can take the page down, whatever the gate let past.
        settles_at = settles_at.replace(tzinfo=timezone.utc)
    if settles_at is None or now < settles_at:
        # Not yet, or never declared. Either way the card is a live question and
        # renders exactly as it did before this function existed.
        return False, None, None, None

    answer = prop.get("settled_answer")
    if not isinstance(answer, str) or not answer.strip():
        # PROVABLY ANSWERED, ANSWER NOT HELD. The one state where the honest
        # move is to show nothing: printing it would present a decided question
        # in the live type, which is the defect Alex reported. Named and
        # counted by the caller, never a silent disappearance.
        return False, None, None, "SETTLED_WITHOUT_AN_ANSWER"

    return True, answer.strip(), settles_at.isoformat(), None


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

    ═══ A COMPARISON IS COMPLETE OR IT IS NOT LIVE (CERT-430, finding 1) ═══

    A card built from ONE market may be partially quoted and still current: an
    eighty-name field with sixty unpriced rows is a field with sixty unpriced
    rows, and the ones that are quoted are the card.

    A card built from SEVERAL DECLARED MARKETS is a different object.  Its whole
    reason to exist is the comparison — "Who wins a second major this year?" is
    two questions printed side by side — and a leg with no reading does not
    make the comparison thinner, it makes it *false*.  The measured specimen:
    Alcaraz unpriced, Sinner fresh at .555, and this function returned the card
    as ``price_state='live'`` because only PRICED outcomes voted on freshness.
    Rendered, that is one man's number under a two-man question, in the
    confident type.  Gotcha #53's shape exactly — an absence read as a good
    answer.

    So a declared leg that produced no reading is a contributor that was never
    seen, and ``governing_age_hours`` already knows what those are worth.  The
    card still RENDERS (Alex, 2026-08-28: illiquid questions are never hidden);
    it renders muted, with every declared subject on it, and ``unpriced_legs``
    names the ones we have nothing for so the page can say so out loud.

    ═══ A TIME-BOUNDED QUESTION STOPS BEING A QUESTION (Q465, Alex) ═══

    Alex, on the US Open page an hour into opening day: *"The 'Will Sinner
    actually play?' prop doesn't make sense now that the tourney has started."*
    He is right, and the reason it is a TRUTH defect rather than a copy one is
    that the card was still printing a live probability under a question the
    world had already answered.  The standing ruling is *settled means settled*:
    one system-wide settled language, and a prop is not exempt from it.

    Some questions are not resolved by their market closing — they are resolved
    by an EVENT, at a known instant.  "Will he play?" is answered the moment the
    draw is fixed and play begins, whatever the market does afterwards, and
    Kalshi leaving the market ``status='open'`` (gotcha #33) does not make the
    question open.  So the register carries the instant:

    ``settles_at``      ISO instant after which this question is answered.
    ``settled_answer``  the answer, as a STRING.

    A string, not an entity key, and that is load-bearing: ``sinner-competes``
    carries only a ``Yes`` row, so "he did not play" cannot be said by pointing
    at an outcome.  There is no outcome to point at.

    Past ``settles_at`` with an answer, the card renders SETTLED and the three
    keys below say so.  Past it WITHOUT one, the card is **withheld and logged**
    — a question we can prove is answered but whose answer we do not hold must
    not be printed as though it were still open.  That is the one case where
    showing nothing beats showing the card, and it is counted rather than
    silent (gotcha #53).  Before ``settles_at``, and for a prop that declares no
    ``settles_at`` at all, nothing changes: ``settled`` is ``False`` and the card
    renders exactly as it does today.
    """
    out: list[dict[str, Any]] = []
    withheld: dict[str, str] = {}
    for prop in TournamentRegister(register).props:
        settled, settled_answer, settled_at, withhold = _prop_settlement(prop, now=now)
        if withhold is not None:
            withheld[str(prop.get("key"))] = withhold
            continue
        views: list[dict[str, Any]] = []
        priced_times: list[Optional[datetime]] = []
        card_liquidity: list[Optional[str]] = []
        card_liquidity_reasons: set[str] = set()
        # WHAT THE REGISTER DECLARED, not what happened to arrive.  A leg is
        # identified by its external id where it has one, because our own
        # `market_id` is a local surrogate a re-ingest can move.
        declared = [
            str(entry.get("market_external_id") or entry.get("market_id"))
            for entry in (prop.get("markets") or [])
            if isinstance(entry, dict)
        ]
        if not declared:
            # A pre-`markets` register entry: one card, one market, by shape.
            declared = [
                str(
                    prop.get("market_external_id")
                    or prop.get("market_id")
                    or prop.get("key")
                )
            ]
        legs_with_a_reading: set[str] = set()

        for outcome in prop.get("outcomes") or []:
            if not isinstance(outcome, dict):
                continue
            leg = str(
                outcome.get("market_external_id")
                or outcome.get("market_id")
                or declared[0]
            )
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
                legs_with_a_reading.add(leg)
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
                # Its own book grade (UX-P157). Per row rather than per card,
                # because a field card's leader can be heavily traded while the
                # tail rows it is printed above are not quoted by anybody.
                "liquidity": (
                    (loaded.get("liquidity") or {}).get("level") or LIQUIDITY_UNKNOWN
                ),
                "liquidity_reasons": sorted(
                    (loaded.get("liquidity") or {}).get("reasons") or []
                ),
            })
            if probability is not None:
                # Only a PRICED row votes on the CARD's grade, matching the
                # freshness rule three lines up. An unpriced row has no book
                # reading to be thin, and letting it vote would mark every
                # partially-quoted field card as barely traded.
                card_liquidity.append((loaded.get("liquidity") or {}).get("level"))
                card_liquidity_reasons.update(
                    (loaded.get("liquidity") or {}).get("reasons") or []
                )

        # The card's own state is the AND over its priced outcomes: a ranked
        # field is a published artifact too, and a stale member can outrank
        # fresh ones inside it.
        #
        # AND over its DECLARED LEGS too, when there is more than one of them.
        # A leg that produced nothing is a contributor older than any
        # timestamp, which is what `governing_age_hours` reads `None` as; see
        # the comparison note in this function's docstring.
        unpriced_legs = [leg for leg in declared if leg not in legs_with_a_reading]
        contributors: list[Optional[datetime]] = list(priced_times)
        if len(declared) > 1 and unpriced_legs:
            contributors.append(None)
        age = governing_age_hours(contributors, now)
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
            # HOW MANY MARKETS THE REGISTER DECLARED for this card, and which of
            # them we have nothing for. `legs > 1` is what makes a card a
            # comparison, and the renderer needs both facts: to print every
            # declared subject rather than only the quoted ones, and to name the
            # missing one instead of leaving a two-name question one name short.
            "legs": len(declared),
            "unpriced_legs": unpriced_legs,
            # `None` is a real, supported state and NOT a defect: it means this
            # question has no single answering outcome (a field market), so the
            # card must show a ranked list rather than one headline number.
            "answer_entity_key": answer["entity_key"] if answer else None,
            # ═══ THE SETTLED CONTRACT (Q465) ═══
            #
            # Exactly these three names, because the renderer is already built
            # against them and a near-miss ships the fix dead. `settled` is an
            # explicit boolean so the card never has to infer its own state
            # from the absence of a key; `settled_answer` is a STRING because
            # a one-outcome prop has nothing to point at (see the docstring).
            "settled": settled,
            "settled_answer": settled_answer,
            "settled_at": settled_at,
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
            # THE AND over the card's priced rows (UX-P157, #2256).
            "liquidity": thinnest_liquidity(card_liquidity),
            "liquidity_reasons": sorted(card_liquidity_reasons),
        })
    if withheld:
        # A card that disappears must leave a trace somewhere a person can read.
        # This section has no diagnostics channel in its payload — it is a bare
        # list by contract — so the log is the channel, and the guard below
        # asserts the withholding rather than trusting it.
        logger.info(
            "tournament props withheld %d settled card(s) with no answer: %s",
            len(withheld), withheld,
        )
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
