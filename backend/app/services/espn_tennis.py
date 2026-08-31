"""ESPN tennis results — the score behind a decided match (UX-P139, Alex's item 9).

    "Decided-match scores come from the ESPN API we already use for other
    scores — wire it; 'no data behind it' is not accepted."

UX-P138 built the seam and shipped it empty, and the report said so: nothing in
this codebase held the result of a tennis match, let alone its score.  That was
true of our own tables and it was the wrong place to have looked.  ESPN's
tennis scoreboard — the same ``site.api.espn.com`` host that already feeds
``sync_espn_live_events`` — carries the US Open in full, and it carries more
than we asked for.

MEASURED 2026-08-26, ``/sports/tennis/atp/scoreboard?dates=20260826``:

    event 189-2026 "US Open"
        grouping mens-singles    Men's Singles      239 competitions
        grouping womens-singles  Women's Singles    239
        grouping mens-doubles    Men's Doubles       63
        grouping womens-doubles  Women's Doubles     63
        grouping mixed-doubles   Mixed Doubles       21

Three things fall out of that shape, and each one answers a different item:

1. **The grouping slugs are the register's own ``draw`` vocabulary**, exactly —
   ``mens-singles`` / ``womens-singles``.  No mapping table, no gender
   inference, and nothing that touches ``llm_gender`` (dead) or
   ``llm_sport_category`` (which files every US Open match under table tennis).
2. **Per-set line scores with a winner flag**, plus ``round.displayName``
   ("Qualifying 1st Round"), so a decided match prints `6-3, 7-6` beside the
   name of whoever won it rather than a bare tick.
3. **Doubles and mixed doubles are already in the feed** (item 12).  No market
   exists for them yet on either source — censused 2026-08-26, zero US Open
   doubles markets platform-wide — but the RESULTS do, which is why
   ``DRAW_SLUGS`` lists all five and the parser does not filter.

THE JOIN, and the one rule it follows.  A result is matched to a register
matchup by the **unordered pair of normalized player names within a draw**, and
by nothing else.  Not by date (ESPN's competition date is the scheduled start
and a rain delay moves it), not by round (our register buckets all qualifying
into one ``qualifying`` while ESPN distinguishes three), and never by one name
alone.  Two players meet at most once in a knockout draw, so the pair is a key;
a single name is not, and a single-name join is how a first-round result lands
on a quarter-final card.

Read-only, and pure apart from the fetch: ``parse_results`` takes the decoded
payload so the whole join is testable without a network.
"""

from __future__ import annotations

import logging
import unicodedata
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

ESPN_TENNIS_BASE = "https://site.api.espn.com/apis/site/v2/sports/tennis"

#: Both tours are fetched because the US Open appears under BOTH, carrying the
#: same event id and the same groupings.  Fetching one would be enough today
#: and would be a silent single point of failure the first time ESPN files a
#: women's draw only under `wta`.
TOURS = ("atp", "wta")

#: ESPN grouping slug -> register draw.  Identity for the two singles draws,
#: which is the point; the three doubles draws are carried so item 12's section
#: has real results the day a market for them appears.
DRAW_SLUGS: dict[str, str] = {
    "mens-singles": "mens-singles",
    "womens-singles": "womens-singles",
    "mens-doubles": "mens-doubles",
    "womens-doubles": "womens-doubles",
    "mixed-doubles": "mixed-doubles",
}

#: Only a FINAL competition yields a result.  An in-progress match has line
#: scores too, and printing them as a result would be the settled-means-settled
#: rule broken in the one direction that matters.
FINAL_STATES = ("post",)

#: HOW a match ended, from ESPN's own status name (UX-P147, Alex's item 5).
#:
#: ═══ WHY THIS EXISTS: "no score" ON THE DIMITROV QUALIFYING FINAL ═══
#:
#: Alex, on the UX-P146 artifact: one row in the finished list printed **no
#: score**, and he asked whether that was an ingest gap or a render fallback.
#: Measured against the live ESPN scoreboard 2026-08-28T00:4xZ, it is NEITHER —
#: the fixture is a **walkover**, and ESPN says so in as many words::
#:
#:     competition 184769  round "Qualifying Final"
#:     status.type.name  = "STATUS_WALKOVER"
#:     notes[0].text     = "Grigor Dimitrov (BUL) bt Otto Virtanen (FIN) w/o"
#:     competitors[*]    — winner flag present, `linescores` ABSENT on both
#:
#: Virtanen withdrew before a ball was struck, so there is no score to have
#: ingested and ``format_score`` correctly returned ``None``.  The defect was
#: entirely in what we then SAID about it: the page printed the words "no
#: score" under a tooltip guessing "usually a retirement", when the source had
#: already told us exactly what happened and we threw it away.
#:
#: ═══ AND THE NEIGHBOUR THE MEASUREMENT FOUND ═══
#:
#: The same census over all 1,250 US Open competitions on that scoreboard::
#:
#:     STATUS_FINAL      434   line scores on both sides
#:     STATUS_RETIRED      8   line scores on both sides, EQUAL LENGTH
#:     STATUS_WALKOVER     2   no line scores at all
#:     STATUS_SCHEDULED  806   (792 unplayed + 14 in progress; `state` filters them)
#:
#: ``format_score``'s docstring claims it returns ``None`` for a retirement
#: because "a partial score printed as a final one is the same class of defect
#: as a stale price printed as live".  It does not, and cannot: its test is
#: *unequal set counts*, and a retirement reports EQUAL ones — the abandoned
#: set is filled in on both sides.  So all eight retirements printed a partial
#: score with nothing marking it, e.g. Lajovic beating Kwon at ``4-6, 7-5,
#: 3-1`` — a scoreline no completed tennis match can have, presented as one.
#:
#: The fix is not to suppress those eight.  ``4-6, 7-5, 3-1`` is TRUE and it is
#: most of what happened; what was missing is the two letters that make it
#: honest.  So the completion travels with the row and the renderer says it.
COMPLETION_BY_STATUS: dict[str, str] = {
    "STATUS_FINAL": "final",
    "STATUS_RETIRED": "retired",
    "STATUS_WALKOVER": "walkover",
    "STATUS_ABANDONED": "abandoned",
    "STATUS_FORFEIT": "walkover",
}

#: What an unrecognised final-state status becomes.  A new ESPN status name
#: must degrade to "we know it finished and not how", never to a confident
#: "final" — inventing a completion is the same defect in the other direction.
COMPLETION_UNKNOWN = "unknown"


def completion_of(status: dict[str, Any]) -> str:
    """ESPN ``status.type`` -> one of ``COMPLETION_BY_STATUS``' values.

    Keyed on ``name`` (``STATUS_WALKOVER``), which is ESPN's enum, and not on
    ``description`` (``"Walkover"``), which is display text and can be
    localised or reworded without notice.
    """
    return COMPLETION_BY_STATUS.get(
        str((status or {}).get("name") or ""), COMPLETION_UNKNOWN
    )

#: The register's round vocabulary for a knockout draw, LARGEST FIRST.  Indexed
#: by draw size rather than hard-coded to a 128 field: a 64-slot doubles draw's
#: "Round 1" is `R64`, and reading it as `R128` would file every doubles fixture
#: one round too early for the rest of its life.
_KNOCKOUT_ROUNDS = ("R128", "R64", "R32", "R16", "QF", "SF", "F")

#: ESPN's own names for the rounds that are not "Round N".
_NAMED_ROUNDS: dict[str, str] = {
    "quarterfinal": "QF",
    "quarterfinals": "QF",
    "semifinal": "SF",
    "semifinals": "SF",
    "final": "F",
}

#: A competitor slot ESPN has filled with a placeholder rather than a person.
#: ``Bye`` is the core API's word and ``TBD`` the site API's for the same thing:
#: a main-draw slot reserved for a qualifier who has not qualified yet.  Both
#: also come back with a non-positive athlete id, which is the check that
#: actually runs — the names are here so the reason is legible.
PLACEHOLDER_NAMES = frozenset({"tbd", "bye", "qualifier", "lucky loser", ""})


def round_names_for_size(size: int) -> list[str]:
    """Register round keys for a knockout draw of ``size`` slots, largest first.

    ``256`` and anything not a power of two return ``[]`` rather than a
    best-effort guess: a draw whose size we cannot name is a draw whose rounds
    we cannot name, and filing a fixture under the wrong round is exactly the
    wrong-question defect the register exists to refuse.
    """
    if size < 2 or size & (size - 1):
        return []
    try:
        start = _KNOCKOUT_ROUNDS.index(f"R{size}")
    except ValueError:
        # 8, 4 and 2 are QF / SF / F, which have no `R` name.
        tail = {8: 4, 4: 5, 2: 6}.get(size)
        if tail is None:
            return []
        start = tail
    return list(_KNOCKOUT_ROUNDS[start:])


def espn_round_key(display_name: Any, *, draw_size: int) -> Optional[str]:
    """ESPN's ``round.displayName`` -> a register round key, or ``None``.

    Qualifying collapses to one bucket because the register has one: ESPN
    distinguishes three qualifying rounds and our draw does not, and inventing
    `Q1`/`Q2`/`Q3` keys to preserve a distinction nothing renders would be
    schema churn bought with nothing.
    """
    raw = str(display_name or "").strip().lower()
    if not raw:
        return None
    if raw.startswith("qual"):
        return "qualifying"
    if raw in _NAMED_ROUNDS:
        return _NAMED_ROUNDS[raw]
    if raw.startswith("round "):
        try:
            index = int(raw.split()[1]) - 1
        except (IndexError, ValueError):
            return None
        names = round_names_for_size(draw_size)
        if 0 <= index < len(names):
            return names[index]
    return None


def _competitor_view(competitor: dict[str, Any]) -> dict[str, Any]:
    """One side of an ESPN competition, as the draw ingest wants it.

    ``determined`` is the load-bearing field.  A main draw released before
    qualifying finishes carries real placeholder slots — measured 18 of 128 on
    the men's side and 16 on the women's, 2026-08-27 — and a placeholder is a
    FACT about the draw, not a gap in our read of it.  It is carried through
    rather than dropped so the fixture still says "somebody plays Jack Kennedy",
    which is true, instead of vanishing because half of it is unknown.
    """
    athlete = competitor.get("athlete") or {}
    name = str(athlete.get("displayName") or competitor.get("name") or "").strip()
    raw_id = str(competitor.get("id") or "")
    espn_id = int(raw_id) if raw_id.lstrip("-").isdigit() else None
    determined = (
        espn_id is not None
        and espn_id > 0
        and name.lower() not in PLACEHOLDER_NAMES
    )
    flag = athlete.get("flag") or {}
    return {
        "name": name,
        "espn_athlete_id": espn_id if determined else None,
        "flag_url": flag.get("href") if determined else None,
        "country": flag.get("alt") if determined else None,
        "determined": determined,
        "order": competitor.get("order"),
    }


def parse_draw(
    payloads: Iterable[dict[str, Any]],
    *,
    event_name: str,
    draws: Iterable[str] = ("mens-singles", "womens-singles"),
) -> dict[str, Any]:
    """Decoded ESPN scoreboards -> the tournament's real fixtures, by draw.

    THE DRAW IS A FIXTURE LIST, NOT A DRAW SHEET, and the distinction is the
    whole reason this function exists instead of a slot writer.

    ESPN publishes **who plays whom** — 64 first-round competitions a side,
    every one of them a fact about today's ceremony.  It does not publish the
    draw-sheet POSITION of those competitions, and the competition ids are
    ingest order, not bracket order (measured 2026-08-27: the men's list opens
    on an unseeded qualifier slot and Alcaraz is 37th, so it is demonstrably not
    the sheet).  Position is what says which first-round winner meets which, so
    writing ``draw_slot`` from this order would fabricate the second round while
    looking exactly like the first.

    So the ingest writes the pairings and leaves ``draw_slot`` null.  A pairing
    is checkable against any published draw; an invented position is not.
    """
    wanted = set(draws)
    by_draw: dict[str, list[dict[str, Any]]] = {}
    seen: set[str] = set()
    stats = {"events": 0, "competitions": 0, "fixtures": 0, "placeholder_slots": 0}

    for payload in payloads:
        for event in (payload or {}).get("events") or []:
            if event_name not in str(event.get("name") or ""):
                continue
            stats["events"] += 1
            for grouping in event.get("groupings") or []:
                slug = ((grouping.get("grouping") or {}).get("slug")) or ""
                draw = DRAW_SLUGS.get(slug)
                if draw is None or draw not in wanted:
                    continue
                competitions = grouping.get("competitions") or []
                # The draw's size, read off its own first round rather than
                # assumed. `Round 1` is `R128` only because there are 64 of it.
                first_round = [
                    c
                    for c in competitions
                    if str(((c.get("round") or {}).get("displayName")) or "").strip().lower()
                    == "round 1"
                ]
                draw_size = 2 * len(first_round)

                for competition in competitions:
                    comp_id = str(competition.get("id") or "")
                    # Both tours carry this event with the same competition ids.
                    if not comp_id or comp_id in seen:
                        continue
                    seen.add(comp_id)
                    stats["competitions"] += 1

                    round_key = espn_round_key(
                        (competition.get("round") or {}).get("displayName"),
                        draw_size=draw_size,
                    )
                    if round_key is None:
                        continue

                    competitors = sorted(
                        (competition.get("competitors") or []),
                        key=lambda c: c.get("order") or 0,
                    )
                    if len(competitors) != 2:
                        continue
                    sides = [_competitor_view(c) for c in competitors]
                    if not any(side["determined"] for side in sides):
                        # Both sides placeholders: a slot pair reserved for two
                        # qualifiers. Nothing to say and nobody to name.
                        continue
                    stats["placeholder_slots"] += sum(
                        1 for side in sides if not side["determined"]
                    )
                    stats["fixtures"] += 1
                    by_draw.setdefault(draw, []).append({
                        "espn_competition_id": comp_id,
                        "round": round_key,
                        "espn_round": (competition.get("round") or {}).get("displayName"),
                        "scheduled_at": competition.get("date"),
                        "state": ((competition.get("status") or {}).get("type") or {}).get("state"),
                        "draw_size": draw_size,
                        "players": sides,
                    })

    return {"draws": by_draw, "stats": stats}


def normalize_name(name: Any) -> str:
    """NFD-fold to a comparison key — the register's own rule, restated.

    Deliberately identical in behaviour to
    ``tournament_register.normalize_player_name`` composed with an NFD pass:
    spaces dropped, not just punctuation, because ESPN writes ``Felix
    Auger-Aliassime`` and Polymarket writes ``Felix Auger Aliassime``.
    """
    if not isinstance(name, str):
        return ""
    folded = unicodedata.normalize("NFD", name)
    return "".join(ch for ch in folded.lower() if ch.isalnum())


def pair_key(names: Iterable[str]) -> str:
    """The unordered normalized pair — the join key, and the only one."""
    return "|".join(sorted(normalize_name(name) for name in names if name))


def format_score(competitors: list[dict[str, Any]]) -> Optional[str]:
    """``6-3, 7-6`` — the winner's games first, set by set.

    Winner-first, always, so the score reads the same way the outcome does.  A
    card that says "Fearnley won" over "3-6, 6-7" is asking the reader to
    reverse it in their head, and half of them will not.

    ``None`` when a competitor carries no line scores at all — a WALKOVER, in
    which no set was played and there is nothing to print — or when the two
    report different numbers of sets, which is a mid-match read.

    ⚠️ IT DOES NOT SUPPRESS A RETIREMENT, and an earlier version of this
    docstring said it did.  A retired match reports EQUAL set counts (the
    abandoned set is filled in on both sides), so the length test never fires
    for one; measured 2026-08-28, all 8 retirements on the US Open scoreboard
    returned a score here.  That score is true and worth printing — what it
    needs is the marker, which travels beside it as ``completion``.  See
    ``COMPLETION_BY_STATUS``.
    """
    scored = [
        (c, [ls.get("value") for ls in (c.get("linescores") or [])])
        for c in competitors
    ]
    if len(scored) != 2:
        return None
    (a, a_sets), (b, b_sets) = scored
    if not a_sets or len(a_sets) != len(b_sets):
        return None
    if any(v is None for v in (*a_sets, *b_sets)):
        return None

    winner_first = scored if a.get("winner") else [scored[1], scored[0]]
    (_w, w_sets), (_l, l_sets) = winner_first
    return ", ".join(
        f"{int(w)}-{int(l)}" for w, l in zip(w_sets, l_sets)
    )


#: ESPN ``status.type.state`` -> the word the slate uses for it.
#:
#: ``post`` IS HERE ON PURPOSE, and that is the whole of CERT-517's repair.
#:
#: Q463 shipped this map without it, so a decided match was represented in the
#: order of play by its ABSENCE, and the slate dropped anything it could not
#: find.  ``fetch_tournament_results`` deliberately permits a per-tour failure
#: and the partial payload is cached and served — so one flaky tour made every
#: LIVE fixture on it indistinguishable from a finished one, and the card could
#: empty itself all over again under a routine condition.  That is the same
#: absence-as-truth class the queue existed to kill (gotcha #53): an empty 200
#: is a response shape, not an absence.
#:
#: With ``post`` named, absence means only "the scoreboard did not mention this
#: fixture", which is a statement about the scoreboard and never about the
#: match.  Nothing is dropped as decided except on this explicit word.
SLATE_STATE_BY_ESPN_STATE: dict[str, str] = {
    "in": "in_progress",
    "pre": "upcoming",
    "post": "decided",
}

#: The one ``SLATE_STATE_BY_ESPN_STATE`` value that means "this belongs to the
#: results section, not the day's card".  Named so the slate tests the word
#: rather than a membership check that would silently widen.
DECIDED_SLATE_STATE = "decided"

#: ESPN's ``status.type.shortDetail`` for a fixture it has not given a time yet.
#:
#: This is the marker that keeps a placeholder from being printed as a start.
#: Measured over the 530 unplayed US Open competitions on the 2026-08-31T01:29Z
#: scoreboard, it partitions them exactly and three ways at once::
#:
#:     shortDetail "TBD"  ->  detail "M/d - 'TBD'"   date 04:00Z   508
#:     anything else      ->  "Mon, August 31st..."  a real time    22
#:
#: ``04:00Z`` is midnight in Flushing Meadows: ESPN's stand-in for "some time
#: that day", which is also what the register recorded at the draw ceremony and
#: what an elapsed-time rule then read as a start.  ``detail`` on those rows is
#: an UNSUBSTITUTED FORMAT STRING — ``M/d - 'TBD'`` — so it is display text only
#: in the sense that displaying it would be a bug; it is dropped, and the flag
#: is carried instead.
TBD_SHORT_DETAIL = "TBD"


def parse_results(payloads: Iterable[dict[str, Any]], *, event_name: str) -> dict[str, Any]:
    """Decoded ESPN scoreboards -> ``{draw: {pair_key: result}}`` + the day's card.

    ``event_name`` selects the tournament out of a scoreboard that also carries
    whatever else is on that week ("Winston-Salem Open", "Abierto GNP
    Seguros").  An exact-substring test rather than a fuzzy one: this module is
    on the same page as the register and inherits its posture — a tournament is
    served because somebody named it, never because a scorer picked it.

    ═══ ``order_of_play``: THE OTHER 80% OF THE PAYLOAD (Q463) ═══

    This function threw away every competition that was not ``post``, which is
    806 of the 1,250 on the US Open scoreboard, and among them is the answer to
    "what is on right now".  The slate had no other source for it and said
    **"No matches scheduled" through the whole of opening day** — measured
    2026-08-31T01:29Z with 2 matches in progress, 22 already decided and 73
    still to play.

    So the same pass now also publishes ``order_of_play``: ESPN's competition id
    -> its state and its REAL start time.  Three properties make it the right
    key for the slate to join on:

    - **It is an id, not a name.**  The register pins
      ``matchup.evidence.espn_competition_id`` at the draw ceremony, so the join
      is a dict lookup and this module's no-request-time-name-matching posture
      survives intact.
    - **The start time is ESPN's, not the register's.**  The register recorded
      the ceremony-day placeholder — midnight ET, ``2026-08-30T04:00Z``, on all
      96 main-draw fixtures — because that is what ESPN says before an order of
      play is published.  Once one is, ESPN's ``date`` is the real 15:05Z, and
      the register file cannot be rewritten every morning.
    - **``in`` is carried, not collapsed into ``pre``.**  A match in its second
      set is the single most interesting row on the page, and it is the one row
      an elapsed-time rule cannot keep (a five-setter outlives any window).

    ``post`` deliberately gets no entry: a decided match belongs to
    ``build_results``, and its absence from this map is what tells the slate to
    drop it.
    """
    by_draw: dict[str, dict[str, Any]] = {}
    order_of_play: dict[str, dict[str, Any]] = {}
    seen_competitions: set[str] = set()
    stats = {
        "events": 0,
        "competitions": 0,
        "final": 0,
        "scored": 0,
        "unpaired": 0,
        # UX-P147: counted at the SOURCE, so "22 finished without a score" can
        # be said as "2 walkovers" instead of "retirement or walkover" — the
        # shrug the page printed before anybody measured which it was.
        "walkovers": 0,
        "retirements": 0,
        # Q463: the day's card, counted where it is read. An empty slate is
        # either "nothing is on" or "the overlay joined nothing", and those need
        # different people (gotcha #53).
        #
        # CERT-517 added `decided`: these three are the `order_of_play` map's
        # own census, and their sum is how many competitions the map speaks
        # for. Keyed by the slate word so the counter cannot drift from the
        # thing it counts.
        "in_progress": 0,
        "upcoming": 0,
        "decided": 0,
        # CERT-526: a competition whose ESPN state we have no word for is left
        # OUT of the map (see `SLATE_STATE_BY_ESPN_STATE`) — which is the right
        # call, but it means the map is silently short. Counted here so
        # `order_of_play_complete` can refuse to call such a payload complete
        # rather than letting a consumer read the hole as "not on the
        # scoreboard".
        "unknown_state": 0,
    }

    for payload in payloads:
        for event in (payload or {}).get("events") or []:
            if event_name not in str(event.get("name") or ""):
                continue
            stats["events"] += 1
            for grouping in event.get("groupings") or []:
                slug = ((grouping.get("grouping") or {}).get("slug")) or ""
                draw = DRAW_SLUGS.get(slug)
                if draw is None:
                    continue
                for competition in grouping.get("competitions") or []:
                    # Both tours return the same competition ids for this
                    # event, so the second tour is a duplicate pass. Counted
                    # once.
                    comp_id = str(competition.get("id"))
                    if comp_id in seen_competitions:
                        continue
                    seen_competitions.add(comp_id)
                    stats["competitions"] += 1

                    status = ((competition.get("status") or {}).get("type") or {})
                    espn_state = str(status.get("state") or "")

                    # EVERY COMPETITION THE SCOREBOARD NAMES IS PUBLISHED, AND
                    # THAT INCLUDES THE FINISHED ONES (CERT-517).
                    #
                    # Written before the `continue` below, so the map is a
                    # statement about all 1,250 competitions rather than only
                    # the ones still to play. A caller can then read a missing
                    # id as "the scoreboard did not mention it" and nothing
                    # more — see `SLATE_STATE_BY_ESPN_STATE`.
                    #
                    # An ESPN state we have no word for is deliberately NOT
                    # published: an unknown state is not evidence of anything,
                    # and inventing a word for it would be the same mistake in
                    # the other direction. It falls to the caller's fallback.
                    slate_state = SLATE_STATE_BY_ESPN_STATE.get(espn_state)
                    if slate_state is not None:
                        tbd = (
                            str(status.get("shortDetail") or "") == TBD_SHORT_DETAIL
                        )
                        order_of_play[comp_id] = {
                            "espn_competition_id": comp_id,
                            "draw": draw,
                            "state": slate_state,
                            # ESPN's own scheduled start — real once an order
                            # of play is published, midnight-local until
                            # then. `start_is_tbd` says which, so a caller
                            # never has to infer it from the hour.
                            "start_at": competition.get("date"),
                            "start_is_tbd": tbd,
                            # Dropped when it is the unsubstituted template
                            # rather than text about this match. See
                            # `TBD_SHORT_DETAIL`.
                            "status_detail": None if tbd else status.get("detail"),
                            "espn_round": (
                                (competition.get("round") or {}).get("displayName")
                            ),
                        }
                        stats[slate_state] += 1
                    else:
                        stats["unknown_state"] += 1

                    if espn_state not in FINAL_STATES:
                        # NOT DECIDED — so it is the day's card, not a result,
                        # and the result parsing below has nothing to read.
                        continue
                    stats["final"] += 1

                    competitors = competition.get("competitors") or []
                    names = [
                        ((c.get("athlete") or {}).get("displayName") or "")
                        for c in competitors
                    ]
                    if len([n for n in names if n]) != 2:
                        # A doubles competition names a TEAM, not an athlete, in
                        # some ESPN payloads. Counted rather than dropped so the
                        # doubles section's coverage is a number and not a
                        # shrug.
                        stats["unpaired"] += 1
                        continue

                    winner = next(
                        (
                            (c.get("athlete") or {}).get("displayName")
                            for c in competitors
                            if c.get("winner")
                        ),
                        None,
                    )
                    by_draw.setdefault(draw, {})[pair_key(names)] = {
                        "score": format_score(competitors),
                        "winner_name": winner,
                        "winner_normalized": normalize_name(winner),
                        "players": names,
                        "espn_competition_id": comp_id,
                        "espn_round": (competition.get("round") or {}).get("displayName"),
                        "completed_at": competition.get("date"),
                        "status_detail": status.get("detail"),
                        # HOW it ended (UX-P147). `status_detail` was already
                        # here and is display text; this is the enum a renderer
                        # can branch on without matching on English.
                        "completion": completion_of(status),
                    }
                    if by_draw[draw][pair_key(names)]["score"]:
                        stats["scored"] += 1
                    completion = by_draw[draw][pair_key(names)]["completion"]
                    if completion == "walkover":
                        stats["walkovers"] += 1
                    elif completion == "retired":
                        stats["retirements"] += 1

    return {"draws": by_draw, "order_of_play": order_of_play, "stats": stats}


async def fetch_tournament_results(
    event_name: str, *, dates: Optional[str] = None
) -> dict[str, Any]:
    """Fetch and parse both tours' scoreboards for one tournament.

    ``dates`` is ESPN's ``YYYYMMDD``; omitted, the scoreboard returns the
    current day, which is what a live tournament wants.  A tour that fails to
    fetch contributes nothing and is REPORTED — an empty result set from a
    timed-out request must never read as "no matches have finished" (gotcha
    #53).
    """
    import httpx

    payloads: list[dict[str, Any]] = []
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for tour in TOURS:
            url = f"{ESPN_TENNIS_BASE}/{tour}/scoreboard"
            try:
                response = await client.get(
                    url, params={"dates": dates} if dates else None
                )
                response.raise_for_status()
                payloads.append(response.json())
            except Exception as exc:  # noqa: BLE001 — reported, never silent
                errors.append(f"{tour}: {exc}")

    result = parse_results(payloads, event_name=event_name)
    result["errors"] = errors
    result["tours_fetched"] = len(payloads)
    # THE ONE BIT A READER OF THE CACHED PAYLOAD CANNOT DERIVE (CERT-517).
    #
    # `errors` and `tours_fetched` were already written and already cached, and
    # the route already threw both away — so a consumer had no way to tell a
    # whole-scoreboard read from half of one. The reduction is done HERE, at the
    # only place that knows what a complete fetch even is, so no consumer has to
    # re-derive it from `len(TOURS)` and get the rule subtly different.
    #
    # ═══ CERT-526: TWO 200s ARE NOT A COMPLETE ANSWER ═══
    #
    # The first version of this line asked only "did both requests succeed",
    # and that is the same mistake one level up: **a successful HTTP response
    # that does not mention this tournament is an empty answer wearing a 200**
    # (gotcha #53). Two ways the map can be short while every request worked:
    #
    #   * the payload carries no event matching `event_name` at all — a quiet
    #     day, a renamed event, a scoreboard that has rolled over;
    #   * a competition carries an ESPN state we have no word for, so it is
    #     deliberately left out of the map.
    #
    # Either way a pinned fixture goes missing from a map that CLAIMS to be the
    # whole scoreboard, the slate's pinned-id exemption does not fire, and the
    # clock drops it on the `04:00Z` placeholder — recreating the empty card
    # this whole queue exists to prevent. So completeness now requires that we
    # actually saw the tournament and understood every competition on it.
    stats = result.get("stats") or {}
    result["order_of_play_complete"] = (
        not errors
        and len(payloads) == len(TOURS)
        and bool(stats.get("events"))
        and not stats.get("unknown_state")
    )
    return result


def fetch_scoreboards(dates: Optional[str] = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Both tours' scoreboards, synchronously — for the offline ingest scripts.

    ``fetch_tournament_results`` is the async path the Celery task uses.  The
    draw ingest is a one-shot command run by an agent on ceremony day, and an
    event loop bought nothing there but a way to get the error handling subtly
    different.  Returns ``(payloads, errors)`` so a caller can tell "no
    tournament today" from "both requests failed" — gotcha #53.
    """
    import httpx

    payloads: list[dict[str, Any]] = []
    errors: list[str] = []
    for tour in TOURS:
        url = f"{ESPN_TENNIS_BASE}/{tour}/scoreboard"
        try:
            response = httpx.get(
                url, params={"dates": dates} if dates else None, timeout=30.0
            )
            response.raise_for_status()
            payloads.append(response.json())
        except Exception as exc:  # noqa: BLE001 — reported, never silent
            errors.append(f"{tour}: {exc}")
    return payloads, errors
