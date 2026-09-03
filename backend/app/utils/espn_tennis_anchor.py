"""Which ESPN competition IS this tennis event? — the anchor, and its receipt.

═══ WHY THIS EXISTS: 30,199 TENNIS ROWS, ZERO ANCHORS (lane1/057 STEP 0) ═══

Measured 2026-09-02 across production::

    tennis_atp          13,876 rows   with espn_id: 0
    tennis_other         8,003                      0
    tennis_wta           4,792                      0
    tennis_atp_us_open      95                      0
    tennis_wta_us_open      98                      0
    ... every tournament bucket below them
                        ──────                     ──
                        30,199                      0

``espn_sync`` — the task that corrects ``status``, ``commence_time`` and
``completed_at`` from the authority — contains the string "tennis" zero times
in 1,739 lines.  It has never run for a tennis row, and it could not: it writes
through ``espn_id``, and no tennis row has one.  ``tournament_slate`` reads the
same ESPN tennis scoreboard already, but only to RENDER a hub card; it writes
nothing back to ``events``.

So a tennis ``events`` row is whatever ``odds_api`` last said plus whatever the
wall-clock staleness nets did to it, and **the authority has no channel to
correct it**.  What that cost, on the live US Open board at 2026-09-02T18:50Z:
Linette v Jones served as ``closed 0-1`` while ESPN scored her second set, and
three rows held ``status='live'`` and a ``completed_at`` at the same time —
which the serve layer resolves as *completed*, so ``/api/events/15293808`` said
"Final, Bonzi 3-1" while Bonzi was playing the fourth set.

Ruling D27 says event-graph correctness outranks card freshness.  For tennis the
graph had no authority wired into it at all.  This module is the join that lets
one be.

═══ THE JOIN, AND WHY IT IS THREE PASSES ═══

The key is the **unordered pair of player names**, which ``espn_tennis`` already
establishes as the only sound tennis join: two players meet at most once in a
knockout draw, so the pair is a key and a single name is not.

Three passes, strictest first, each requiring **exactly one** candidate in the
whole draw.  Measured over all 194 US Open ``events`` rows against the 478
singles competitions on the live board, 2026-09-02T21:0xZ::

    pass 1  exact pair_key                     174     89.7%
    pass 2  both names agree (token sets)       13     ->  96.4%
    pass 3  one name agrees + shared surname     3     ->  97.9%
    refused no candidate                         4

Pass 2 exists because ESPN and Odds API disagree on word order and on how much
of a name to print: ``Wang Xiyu``/``Xiyu Wang``, ``Camila Osorio``/``Maria
Camila Osorio Serrano``, ``Martin Damm``/``Martin Damm Jr.``.  All 13 are one
person under ``player_names.names_agree``, which is the comparator the slate
has used for this since CERT-548.

Pass 3 exists because ``names_agree`` is a person-level test and two real
classes defeat it: a transliteration (``Aleksandr``/``Alexander`` Shevchenko)
and a diminutive (``Caty``/``Catherine`` McNally) — neither is a prefix of the
other, so no token rule short of a nickname table will join them.  The PAIRING
is what rescues them: the opponent agrees outright, the surname is shared whole,
and exactly one competition in a 478-row draw satisfies both.  It is the pair
doing the work, which is the same principle as pass 1.

═══ AND WHAT IT REFUSES, WHICH IS THE POINT ═══

The 4 refusals are not near-misses to be tuned away.  In every one, a player we
name **is not in the ESPN draw at all**, and the opponent played someone else::

    15293812  Marin Cilic v Andrey Rublev      Cilic absent; Rublev bt Virtanen
    15293823  Juan M Cerundolo v Casper Ruud   Ruud absent; Cerundolo bt Gea
    15293674  Potapova v Tereza Valentova      Valentova absent; Potapova bt Semenistaja
    15293847  Rafael Jodar v Kokkinakis        Kokkinakis absent; Jodar bt Bu Yunchaokete

These are fabricated pairings — the class ruling D26a names, and the Jodar row
is the one ``tournament_slate`` already documents as ``espn:182703``.  A looser
matcher would anchor each of them to *the opponent's real match* and then let
the authority write that match's score onto our wrong fixture, which is worse
than the blank we have now.  **The refusal is a finding**, and
:func:`anchor_receipt` is how it gets said out loud rather than counted as a
miss: it names the player the draw does not contain.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from app.services.espn_tennis import is_placeholder_pairing, pair_key
from app.utils.player_names import names_agree, shares_substantial_token

#: The pass that produced a link, in the order they are tried. Carried on the
#: receipt so a widening can be measured against the population it widened —
#: "pass 3 went from 3 to 60" is a review trigger, and a bare match count
#: cannot say it.
MATCH_EXACT_PAIR = "exact-pair-key"
MATCH_NAMES_AGREE = "names-agree"
MATCH_PAIRING_ANCHORED = "pairing-anchored"

#: Why no link was written. Every one is a sentence a person can act on.
REJECT_NO_CANDIDATE = "no-candidate"
REJECT_AMBIGUOUS = "ambiguous"
REJECT_UNNAMED_EVENT = "event-names-no-pair"
REJECT_EMPTY_BOARD = "authority-dark"
REJECT_OFF_BOARD = "off-board"

#: How far our ``commence_time`` may sit from ESPN's competition date and still
#: be the same match.
#:
#: ═══ THE PAIR IS A KEY WITHIN A DRAW, NOT ACROSS TOURNAMENTS ═══
#:
#: ``espn_tennis``' own docstring says the join is the unordered pair "within a
#: draw", and the first version of this module dropped those three words.  What
#: that cost, measured over all 1,000 in-window tennis rows on 2026-09-02:
#: **58 ESPN competitions were claimed by more than one of our events**, and
#: competition 182710 was claimed by four — a ``tennis_atp_cincinnati_open``
#: row, a ``tennis_other`` row, a bare ``tennis_atp`` row and the
#: ``tennis_atp_us_open`` row that actually is it.  Cerundolo and Gea met in
#: Cincinnati AND at Flushing Meadows, so the pair keys are identical and the
#: matcher had nothing to tell them apart.  Anchoring the Cincinnati row would
#: then let the US Open's state be written onto it — the authority write turning
#: into a corruption channel.
#:
#: Three days, and the margin is measured rather than picked.  Every one of the
#: 190 US Open anchors sits within **1.47 days** of ESPN's clock (138 within
#: half a day; the tail is the TBD placeholder at midnight ET on rows whose real
#: session is the next afternoon).  Cincinnati is a fortnight away.  Nothing in
#: between.
#:
#: This is NOT the date-matching ``espn_tennis`` refuses.  That warning is about
#: picking WHICH competition inside a draw — where a rain delay moves a fixture
#: and the pair already answers it uniquely.  Here the date is doing one job the
#: pair provably cannot: saying which TOURNAMENT, at a granularity no rain delay
#: comes near.
SAME_TOURNAMENT_DAYS = 3.0


def within_tournament_window(
    our_commence_time: Any,
    competition: dict[str, Any],
    *,
    max_days: float = SAME_TOURNAMENT_DAYS,
) -> bool:
    """Could this competition and this event be the same tournament's match?

    An unreadable date on EITHER side returns ``True`` — a missing clock is a
    fact about the read, and letting it refuse would silently narrow the pool to
    nothing.  The pair still has to match; this only ever removes candidates the
    pair would otherwise tie.
    """
    espn_start = parse_espn_moment(competition.get("date"))
    if espn_start is None or our_commence_time is None:
        return True
    try:
        apart = abs((espn_start - our_commence_time).total_seconds())
    except TypeError:
        # A naive `commence_time` cannot be compared with an aware one. Refusing
        # to guess a timezone is this codebase's posture everywhere else.
        return True
    return apart <= max_days * 86400.0


def anchorable_competitions(
    competitions: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The competitions an event may be anchored to: two real, named players.

    A half-read pairing and a draw placeholder are both removed here rather than
    inside the passes, so every pass below can assume two names and none of them
    has to re-derive what "a real fixture" means.
    """
    return [
        competition
        for competition in competitions
        if len(competition.get("players") or []) == 2
        and all(competition.get("players") or [])
        and not is_placeholder_pairing(competition["players"])
    ]


def pairing_matches(ours: list[str], theirs: list[str]) -> bool:
    """Do these two pairings name the same two people? (pass 2)

    Both orderings tried, because ESPN's competitor order is ingest order and
    ours is home/away from a different source entirely.

    Unlike ``player_names.pairing_agrees`` — which answers "does the authority
    CONTRADICT this fixture" and therefore treats silence as agreement — this
    demands two real names on both sides.  A matcher that inherited the
    permissive reading would anchor an event to the first competition with a
    missing name.
    """
    if len(ours) != 2 or len(theirs) != 2:
        return False
    if not all(ours) or not all(theirs):
        return False
    straight = names_agree(ours[0], theirs[0]) and names_agree(ours[1], theirs[1])
    crossed = names_agree(ours[0], theirs[1]) and names_agree(ours[1], theirs[0])
    return straight or crossed


def pairing_anchors(ours: list[str], theirs: list[str]) -> bool:
    """One side agrees outright, the other shares a whole surname. (pass 3)

    The weaker half is deliberately EXACT token equality
    (:func:`player_names.shares_substantial_token`), not the prefix rule: the
    prefix tolerance is safe when both names must agree and becomes a wildcard
    when only one does.  ``Caty``/``Catherine`` share ``mcnally``; ``Cilic`` and
    ``Rublev`` share nothing, which is what keeps the four fabricated pairings
    refused.

    The strong side must ALSO share a substantial token, so a fully-agreeing
    pair of one-letter tokens cannot stand in for the anchor.

    ALL FOUR ASSIGNMENTS ARE TRIED, and that is not the same as the two
    orderings :func:`pairing_matches` needs.  There, both names must agree, so
    "straight or crossed" exhausts it.  Here the two sides play DIFFERENT roles
    — one agrees, the other only shares a surname — so each ordering has to be
    tried with each side as the strong one.  The first version looped over
    ``((0, 0), (0, 1))`` and therefore only ever asked whether OUR FIRST name
    was the agreeing one; it linked ``[Koevermans, Caty McNally]`` against
    ``[Catherine McNally, Koevermans]`` (strong name at index 0) and silently
    refused the same fixture written the other way round.
    """
    if len(ours) != 2 or len(theirs) != 2:
        return False
    if not all(ours) or not all(theirs):
        return False
    for strong_ours, strong_theirs in ((0, 0), (0, 1), (1, 0), (1, 1)):
        weak_ours, weak_theirs = 1 - strong_ours, 1 - strong_theirs
        if (
            names_agree(ours[strong_ours], theirs[strong_theirs])
            and shares_substantial_token(ours[strong_ours], theirs[strong_theirs])
            and shares_substantial_token(ours[weak_ours], theirs[weak_theirs])
        ):
            return True
    return False


def _absent_players(ours: list[str], competitions: list[dict[str, Any]]) -> list[str]:
    """Which of our two names does the draw not contain, under any pairing?

    THE RECEIPT THAT MAKES A REFUSAL ACTIONABLE.  "no candidate" is a fact about
    our search; "Casper Ruud is not in this draw" is a fact about the fixture,
    and it is the one that says the row is fabricated rather than that the
    matcher is weak.
    """
    absent = []
    for name in ours:
        if not name:
            continue
        present = any(
            any(names_agree(name, theirs) for theirs in competition["players"])
            for competition in competitions
        )
        if not present:
            absent.append(name)
    return absent


def anchor_receipt(
    ours: list[str],
    competitions: Iterable[dict[str, Any]],
    *,
    our_commence_time: Any = None,
    max_days: float = SAME_TOURNAMENT_DAYS,
) -> dict[str, Any]:
    """Anchor one event's pairing, and say why — link or refusal, always both.

    Returns ``{espn_competition_id, method, reason, candidates, absent_players}``
    where ``espn_competition_id`` is ``None`` unless exactly one competition
    matched.  ``candidates`` lists the competition ids a pass found, so an
    ``ambiguous`` refusal can be read without re-running the match.

    ``our_commence_time`` narrows the pool to competitions within
    :data:`SAME_TOURNAMENT_DAYS` — the tournament discriminator the pair cannot
    provide.  Passing ``None`` disables it, which is only right for a caller
    that has already scoped the board to one tournament.

    ═══ FOUR REFUSALS, AND THEY MEAN FOUR DIFFERENT THINGS ═══

    Collapsing them into "no match" is what would make this an audit instead of
    a receipt, because only two of the four are about the fixture at all:

    ``authority-dark``   the board itself is empty — we know nothing, and that
                         is a fact about the read (gotcha #53).
    ``off-board``        neither of our players is on this board within the
                         window.  A Cincinnati fixture read against the US Open
                         scoreboard, and the ordinary case at any scope wider
                         than one tournament.  **Not a defect.**
    ``no-candidate``     with ``absent_players`` naming exactly the player the
                         draw does not contain while the OPPONENT is right
                         there.  This is the fabricated-pairing shape, and it is
                         the one that says the row is wrong rather than that the
                         matcher is weak.
    ``ambiguous``        two competitions fit; refusing beats guessing.

    Nothing here touches the database, so the acceptance number can be
    re-derived from a saved payload by anybody.
    """
    board = anchorable_competitions(competitions)

    if not board:
        # AN EMPTY BOARD IS A FACT ABOUT THE READ (gotcha #53). A scoreboard we
        # failed to fetch and a tournament with no matches produce the same
        # empty list, and neither is evidence that this event is wrong.
        return {
            "espn_competition_id": None,
            "method": None,
            "reason": REJECT_EMPTY_BOARD,
            "candidates": [],
            "absent_players": [],
        }

    if len(ours) != 2 or not all(ours):
        return {
            "espn_competition_id": None,
            "method": None,
            "reason": REJECT_UNNAMED_EVENT,
            "candidates": [],
            "absent_players": [],
        }

    pool = [
        c for c in board
        if within_tournament_window(our_commence_time, c, max_days=max_days)
    ]

    if not pool:
        # The board is real and none of it is near this event's date — a
        # different tournament's fixture, not a broken one.
        return {
            "espn_competition_id": None,
            "method": None,
            "reason": REJECT_OFF_BOARD,
            "candidates": [],
            "absent_players": [],
        }

    passes = (
        (MATCH_EXACT_PAIR, lambda c: c.get("pair_key") == pair_key(ours)),
        (MATCH_NAMES_AGREE, lambda c: pairing_matches(ours, c["players"])),
        (MATCH_PAIRING_ANCHORED, lambda c: pairing_anchors(ours, c["players"])),
    )

    for method, test in passes:
        hits = [c for c in pool if test(c)]
        if len(hits) == 1:
            return {
                "espn_competition_id": hits[0]["espn_competition_id"],
                "method": method,
                "reason": None,
                "candidates": [hits[0]["espn_competition_id"]],
                "absent_players": [],
            }
        if len(hits) > 1:
            # AMBIGUITY STOPS THE SEARCH — it does not fall through to a looser
            # pass. A later pass is strictly more permissive, so it can only
            # find MORE of the same collision; falling through would turn "two
            # candidates" into "several" and then into a coin flip.
            return {
                "espn_competition_id": None,
                "method": method,
                "reason": REJECT_AMBIGUOUS,
                "candidates": [c["espn_competition_id"] for c in hits],
                "absent_players": [],
            }

    absent = _absent_players(ours, pool)
    if len(absent) == 2:
        # NEITHER player is here. This event belongs to some other tournament,
        # which is the ordinary reading and never a claim about the fixture.
        return {
            "espn_competition_id": None,
            "method": None,
            "reason": REJECT_OFF_BOARD,
            "candidates": [],
            "absent_players": absent,
        }

    return {
        "espn_competition_id": None,
        "method": None,
        "reason": REJECT_NO_CANDIDATE,
        "candidates": [],
        "absent_players": absent,
    }


#: ESPN slate state -> the ``events.status`` it authorises. ``in_progress``
#: already has lane1/054's ``play_refutes_upcoming`` folded into it upstream in
#: ``scoreboard_competitions``, so a match ESPN calls ``pre`` while scoring its
#: fourth set arrives here as ``in_progress``.
STATUS_BY_SLATE_STATE: dict[str, str] = {
    "upcoming": "scheduled",
    "in_progress": "live",
    "decided": "completed",
}

#: The statuses that mean "this event is over" in our own vocabulary. ``closed``
#: and ``completed`` are both settled; the authority write must not churn one
#: into the other, so a ``decided`` competition leaves an already-settled row's
#: status alone and only fills what is missing.
SETTLED_STATUSES = frozenset({"completed", "closed"})


def state_contradiction(
    our_status: Optional[str],
    our_completed_at: Any,
    espn_state: Optional[str],
    *,
    competition: Optional[dict[str, Any]] = None,
    now: Any = None,
) -> Optional[str]:
    """Does our row contradict the authority? — the needle, as one function.

    Returns a short reason, or ``None`` when the row and the board agree.  Three
    contradictions, and the first is visible without ESPN at all:

    * ``live-and-completed`` — ``status='live'`` with a ``completed_at`` set.
      A row cannot be both.  Three US Open rows held this at 2026-09-02T21:00Z
      (de Jong, Bergs, Jović): the staleness net closed them overnight off an
      ``odds_api`` ``commence_time`` stamped for the wrong day, then later
      writes flipped ``status`` back to ``live`` without revoking the close.
      The serve layer resolves the pair as *completed*, which is how a card
      printed "Final" over a match in its fourth set.
    * ``settled-but-in-play`` — we call it over, the authority is scoring it.
      **The revoking direction, and the clause that did not exist anywhere.**
      ``completed_at`` is only ever written, never cleared; nothing in the
      codebase said *the authority reports this match in progress, so the close
      was wrong.*
    * ``in-play-but-decided`` — we call it live, the authority finished it.
      A stale live card, the everyday shape of a match that ended while nothing
      was watching.
    * ``in-play-but-not-started`` — we call it live and ESPN's own clock puts
      the start in the future. Needs ``competition`` and ``now``; without them
      it is not reported, because the class cannot be judged without a clock.

    An ``espn_state`` of ``None`` yields ``None`` for the last two: a state we
    have no word for is not evidence about the event (gotcha #53).  The
    self-contradiction is still reported, because it needs no authority.
    """
    if our_status == "live" and our_completed_at is not None:
        return "live-and-completed"
    if espn_state is None:
        return None
    if espn_state == "in_progress" and our_status in SETTLED_STATUSES:
        return "settled-but-in-play"
    if espn_state == "decided" and our_status == "live":
        return "in-play-but-decided"
    if (
        espn_state == "upcoming"
        and our_status == "live"
        and competition is not None
        and now is not None
        and not competition.get("start_is_tbd")
    ):
        espn_start = parse_espn_moment(competition.get("date"))
        if espn_start is not None and espn_start > now:
            # WE SAY LIVE, ESPN SAYS IT STARTS LATER. Reported only on a real
            # future start — an `upcoming` whose clock has passed is a
            # scoreboard that has not caught up, and calling that a
            # contradiction would make the needle cry wolf every session.
            return "in-play-but-not-started"
    return None


#: A ``commence_time`` correction smaller than this is ESPN and Odds API
#: rounding the same start differently, not a fixture that moved. Writing on it
#: would churn every anchored row on every cycle for no reader-visible gain.
COMMENCE_DRIFT_TOLERANCE_SECONDS = 300


def parse_espn_moment(value: Any) -> Optional[Any]:
    """ESPN's ``2026-09-02T15:05Z`` -> an aware datetime, or ``None``.

    Naive input is REFUSED rather than assumed UTC — the same posture
    ``tournament_slate._parse_moment`` takes, and for the same reason: stamping
    a timezone onto a fixture time is guessing, and every comparison downstream
    is against an aware ``now``.
    """
    from datetime import datetime

    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def authority_write(
    *,
    our_status: Optional[str],
    our_completed_at: Any,
    our_commence_time: Any,
    competition: dict[str, Any],
    now: Any = None,
) -> dict[str, Any]:
    """What the authority changes on an anchored tennis row — changes only.

    Returns a dict of the columns that must move, empty when the row already
    agrees.  Pure, so the whole write policy is testable without a database and
    without a network.

    ═══ ASYMMETRIC ON PURPOSE ═══

    Every write here is driven by a POSITIVE statement from the authority, and
    the one direction that is only ever reported is the one where the
    authority's silence could be wrong:

    * ``in_progress`` -> ``status='live'`` **and ``completed_at=None``.**
      The revoke is the clause that did not exist anywhere in this codebase:
      ``completed_at`` was only ever written, never cleared, so nothing could
      say *the authority reports this match in progress, so the close was
      wrong.*  It is safe precisely because ``in_progress`` here has lane1/054's
      ``play_refutes_upcoming`` folded in — a game on the board, not an inferred
      clock.
    * ``decided`` -> ``status='completed'``, and only when the row is not
      already settled.  ``closed`` and ``completed`` are both settled and
      churning one into the other would rewrite history for no reader.
      ``completed_at`` is deliberately NOT invented from ESPN's ``date``, which
      is the match's START: a plausible-looking end time is the value nothing
      ever questions (gotcha #22).  Setting the status is enough —
      ``_transition_event_statuses_impl`` already fills a missing
      ``completed_at`` from the last real post-commence snapshot.
    * ``upcoming`` alone -> **status is not touched.**  A match that has
      genuinely not begun and a match whose first game ESPN has not published
      yet are the same read, and demoting ``live`` on that read would blank a
      real live card.
    * ``upcoming`` **with a real start still in the future** -> ``scheduled``,
      and any completion cleared.  THIS one is not silence: a match ESPN says
      begins in 37 minutes has not begun, and that is a statement, not an
      absence.  It cannot fire on a scoreboard merely lagging a match already
      under way, because such a fixture's scheduled start is in the PAST.
      Measured 2026-09-02T22:22Z: ESPN had 11 US Open singles in play and we
      called 14 live — one already decided, and two (Wu Yibing v Duckworth,
      Navone v Berrettini) both scheduled for 23:00Z with no games on the board.
    * An unknown ``state`` writes nothing at all (gotcha #53).

    ``commence_time`` is corrected from ESPN's own clock whenever ESPN has a
    real one — that is the half of #2550 the renderer cannot reach, since a
    stale start time is stale in the database.  Two guards: the TBD placeholder
    (midnight ET, ESPN's stand-in for "some time that day") is never written,
    and a correction that would push the start PAST a recorded completion is
    refused, because that inversion is gotcha #46 and manufacturing it here
    would trip the audit that hunts for it.
    """
    state = competition.get("state")
    changes: dict[str, Any] = {}

    if state == "in_progress":
        if our_status != "live":
            changes["status"] = "live"
        if our_completed_at is not None:
            changes["completed_at"] = None
    elif state == "decided":
        if our_status not in SETTLED_STATUSES:
            changes["status"] = "completed"
    elif state == "upcoming":
        # NOT YET PLAYED, AND ESPN SAYS SO WITH A CLOCK RATHER THAN A SILENCE.
        # Only a real (non-TBD) start still in the future counts; see the
        # docstring. A row cannot be live, or complete, before it begins.
        espn_start = parse_espn_moment(competition.get("date"))
        not_started = (
            not competition.get("start_is_tbd")
            and espn_start is not None
            and now is not None
            and espn_start > now
        )
        if not_started:
            if our_status == "live":
                changes["status"] = "scheduled"
            if our_completed_at is not None:
                changes["completed_at"] = None
    elif state is None:
        return {}

    if not competition.get("start_is_tbd"):
        espn_start = parse_espn_moment(competition.get("date"))
        if espn_start is not None:
            moved = (
                our_commence_time is None
                or abs((espn_start - our_commence_time).total_seconds())
                > COMMENCE_DRIFT_TOLERANCE_SECONDS
            )
            # The completion this row will HOLD once these changes land — so a
            # revoke in the same pass does not make the inversion guard refuse
            # a correction that is no longer an inversion.
            completion = changes.get("completed_at", our_completed_at)
            inverts = completion is not None and espn_start > completion
            if moved and not inverts:
                changes["commence_time"] = espn_start

    return changes


#: The tour segment in a tennis sport key: ``tennis_<tour>_<tournament>``.
TENNIS_TOURS = ("atp", "wta")


def tournament_token(sport_key: Any) -> Optional[str]:
    """``tennis_atp_us_open`` -> ``usopen``; ``tennis_atp`` -> ``None``.

    A sport key names a tournament only when it carries a segment PAST the tour.
    The three generic buckets — ``tennis_atp`` (1,450 rows in the 21-day window),
    ``tennis_other`` (626) and ``tennis_wta`` (399) — name none, and returning
    ``None`` for them is the point rather than a shortfall: see
    :func:`board_tournaments`.
    """
    if not isinstance(sport_key, str):
        return None
    parts = sport_key.split("_")
    if len(parts) < 4 or parts[0] != "tennis" or parts[1] not in TENNIS_TOURS:
        return None
    return "".join(ch for ch in "".join(parts[2:]).lower() if ch.isalnum()) or None


def board_tournaments(competitions: Iterable[dict[str, Any]]) -> set[str]:
    """The tournaments this scoreboard actually carries, as comparable tokens.

    ESPN's ``"US Open"`` folds to ``usopen``, which is what
    :func:`tournament_token` makes of ``tennis_atp_us_open``.
    """
    return {
        token
        for token in (
            "".join(ch for ch in str(c.get("event_name") or "").lower() if ch.isalnum())
            for c in competitions
        )
        if token
    }


def anchorable_sport_keys(
    sport_keys: Iterable[str], competitions: Iterable[dict[str, Any]]
) -> list[str]:
    """Which of our tennis buckets may be anchored against this board.

    ═══ WHY THE RAIL IS SCOPED TO TOURNAMENT BUCKETS (and this is the ship) ═══

    The obvious scope — every ``tennis%`` row in the window — is wrong, and
    measurably so.  Run over all in-window tennis rows on 2026-09-02, the
    matcher anchored 452 events onto 285 competitions: **319 of those events
    were contesting 152 competitions with a twin.**  Almost every contest is the
    same shape — a ``tennis_atp`` row and its ``tennis_atp_us_open`` twin are one
    match written twice — and under the at-most-one-event rule that contest
    anchors NEITHER, so the wide scope wins nothing and loses the tournament
    rows that are the point.

    Scoped to the buckets that NAME a tournament on the board, the same
    population is 194 events, 190 anchored, **zero contested**.

    The generic buckets are not abandoned; they are deferred to the twin
    cleanup, which is where a duplicate instance gets re-pointed rather than
    silently half-anchored (#2693 step 2).  A row that is one of two copies of a
    match does not become correct by acquiring an authority id — it becomes a
    violation of the invariant with an id on it.
    """
    on_board = board_tournaments(competitions)
    return [
        key for key in sport_keys
        if (token := tournament_token(key)) is not None and token in on_board
    ]
