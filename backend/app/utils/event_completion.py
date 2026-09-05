"""When did a game actually END, and is it safe to call it over?

Two staleness nets close events on elapsed wall-clock when no data source caught
the finish: ``espn_sync._transition_event_statuses_impl`` and
``odds_polling.detect_and_close_stale_events``. Both used ``now()`` as the
completion time and neither checked whether the game was still being played.
That combination is the PRODUCER of the CAL-P002 defect class:

  * A game that runs long (extra innings, overtime, a rain delay) exceeds its
    sport's max duration while still in progress. The net closes it, keeps
    whatever score the last poll happened to have written, and grades the blend
    to 1.0/0.0 off that mid-game number. An NBA row was found holding a literal
    halftime score, 45-56, for a game that finished 87-109 — with the derived
    "winner" inverted, which is what calibration then grades against.
  * ``completed_at = now()`` is a backend processing timestamp, not a game-end
    time (gotcha #22). It is wrong by however long the net took to notice, and
    it is what chart domains and "settled" language stand on.

``espn_sync``'s docstring has always PROMISED the missing guard — "live → closed:
commence_time + max_duration has passed AND no score updates in the last 30 min"
— but no such check was ever written. This module implements it, and derives the
completion time from the same evidence, so one query answers both questions.

The evidence is the last real post-commence snapshot from any source. If a source
captured something in the last ``STILL_ACTIVE_MINUTES``, the game is very likely
still being played and closing it would freeze a mid-game score. If nothing has
been captured for longer than that, the last capture is the best available
estimate of when the game ended.

Shared by both nets and by ``scripts/repair_event_final_scores.py`` so the
producer and the repair can never drift on what "when did this end" means.

It also answers the question one step earlier in the same chain — *did it
START?* — because both nets measure elapsed time from ``commence_time`` and
neither ever asked whether that field held a start anybody reported. See
``commence_time_is_a_reported_start``.
"""
from datetime import timedelta

# ── Is this commence_time a START, or a stand-in for one? (q076) ─────────────
#
#: The one ``events.commence_time_source`` value that says, in the writer's own
#: words, that no schedule published a time for this fixture.
#:
#: ``prediction_market_matching.auto_create_commence_time`` stamps it when it
#: falls back to the DATE parsed out of a Kalshi ticker, because Kalshi's own
#: ``commence_time`` is a close/resolution time (gotcha #14) and disagreed with
#: it. A ticker date has no time-of-day, so the value it resolves to is
#: **midnight UTC** — a day, rendered as an instant.
#:
#: This is provenance, not a heuristic. q066b established that CLUSTERING is not
#: a placeholder signature (a Saturday 3pm card genuinely is ten simultaneous
#: kickoffs, and ESPN's real order of play gives 15:05Z to three US Open matches
#: at once), so nothing here looks at the hour, the date, or how many rows share
#: a stamp. It reads the field where the writer already recorded what it did.
TICKER_DERIVED_COMMENCE_SOURCE = "kalshi_ticker"

#: Every provenance that means "derived because nothing published one". A set of
#: one today; named so a future derived source joins the rule instead of
#: inheriting the clock by omission.
DERIVED_COMMENCE_SOURCES = frozenset({TICKER_DERIVED_COMMENCE_SOURCE})


def commence_time_is_a_reported_start(commence_time_source) -> bool:
    """May a clock be run from this event's ``commence_time``?

    False ⇒ the field holds a stand-in, and every rule that reads it as an
    instant is reading something nobody reported. ``scheduled → live`` on
    ``commence_time <= now`` is such a rule, and it is the first domino: a row
    promoted off a stand-in then has ``hours_since_start`` measured from it, and
    the staleness nets settle it at the sport's maximum duration with whatever
    score it never had.

    MEASURED, production 2026-09-01. Of every event ever stamped
    ``kalshi_ticker``, **705 are ``closed`` and all 705 carry no score** — 468 of
    them in the preceding seven days. Not "mostly"; the whole population. This
    provenance has never once produced a settled row with a result, so declining
    to start its clock cannot cost a single real one. The 181 still ``scheduled``
    include 40 US Open matches — Alcaraz, Sabalenka, Swiatek, Osaka, Medvedev,
    Pegula — stamped ``2026-09-02T00:00:00Z``, i.e. midnight UTC of a ticker
    date, for matches played in the AFTERNOON of September 2. Each one holds live
    Kalshi markets and would have gone LIVE at 5:00 pm PT on the 1st and FINAL,
    unscored, before midnight.

    ── WHY REFUSING IS THE WHOLE FIX, AND NOT HALF OF ONE ──

    The obvious alternative is to promote such a row when some source has
    captured a post-commence snapshot, mirroring
    :func:`game_may_still_be_running`. It does not work HERE, and the asymmetry
    is worth stating because it looks like it should. That guard asks "is a game
    we know started still going?", where a snapshot after a REAL start is
    evidence of play. This one would ask "did a game start?", where a snapshot
    after a MIDNIGHT STAND-IN is evidence of nothing — Kalshi prices tomorrow's
    match all night, so every row would qualify and the guard would be a no-op
    that reads as a safeguard.

    So the honest answer is the plain one, and it is ``derive_completed_at``'s
    own principle one field over: **we do not have a start, so we do not act as
    if we do.** ``commence_time`` is ``NOT NULL`` and load-bearing for ordering
    and windowing, so the row keeps its stand-in and simply stops driving state
    off it. It is not stranded: ``_SOURCE_PRIORITY`` ranks this provenance 0 and
    "an unknown current source confers no immunity", so the moment odds_api,
    ESPN or StatPal publishes a real time onto the row, the source changes with
    it and the clock starts normally.

    A ``None`` source is deliberately NOT derived. Most of the table predates the
    column, and treating unknown provenance as un-startable would freeze the
    ordinary promotion path for nearly every event on the site — the opposite
    error, and a far larger one.
    """
    return commence_time_source not in DERIVED_COMMENCE_SOURCES


# ══ THE STATE LADDER (live/048 — EVENT-GRAPH-DOCTRINE §R) ════════════════════
#
#   authority state  >  venue settlement  >  scores  >  (never) price
#
# Read it as an ORDER OF ENTITLEMENT: what a signal is allowed to conclude about
# an event's state, strongest first.
#
#   1. AUTHORITY STATE — the schedule-of-record's own status feed (ESPN for the
#      major leagues, college, and — since lane1/057 anchored every US Open row
#      — tennis; DataGolf for golf). It is the only thing entitled to say a
#      match is over, because it is the only thing that WATCHES the match.
#      Doctrine rule 3 in one line.
#   2. VENUE SETTLEMENT — a venue paying out is a statement of record. Not the
#      price: the SETTLEMENT. Doctrine rule 8 gives the venue authority-of-last-
#      resort for the categories no schedule source covers (esports, table
#      tennis, ITF), and a settled Kalshi market is that authority speaking.
#   3. SCORES — a score feed reporting a result. Weaker than an authority
#      because a scoreboard lags and can carry a partial line, but it is still
#      somebody REPORTING ON the game.
#   4. PRICE — NEVER. A venue quotes a fixture whenever it will take the other
#      side of the bet: before the first serve, through a rain suspension, and
#      long after the players have left the court. So "Kalshi ticked two minutes
#      ago" answers *is this market open?*, never *is this game being played?*
#
# ── AND WALL-CLOCK IS NOT ON THE LADDER AT ALL ──
#
# The staleness nets reason from elapsed time and silence. Silence is weaker
# than the weakest rung: it is the ABSENCE of every signal above, and absence
# cannot end a match. So a staleness net may no longer write a terminal state.
# It writes :data:`EVENT_SUSPENDED`, which asserts nothing about the outcome.
#
# WHY THIS RULE EXISTS, MEASURED (CERT-752, production 2026-09-02). Six US Open
# matches read ``status='live'`` while carrying a ``completed_at``. All six were
# SUSPENDED mid-match — ESPN had them scheduled to resume that afternoon and our
# own scores were 0-1, 2-1, 1-2, 0-0, not one a legal completed tennis result.
# Removing venue ticks from the staleness evidence (below) is correct and it was
# not enough: with the ticks gone the next transition pass found no admitted
# snapshot, took the wall-clock fallback, wrote ``closed``, and resolved the
# prediction-market blend to 1.0/0.0 **off the partial score**. Every client
# renders ``closed`` as Final. That is a false LIVE traded for a false FINAL,
# and the false Final is the worse of the two: it grades.

#: The non-terminal state a staleness net writes when the clock has run out and
#: NO rung of the ladder has spoken. It is the ladder's SILENCE state — read it
#: as *"nothing that watches this match has said it ended"*, which is the honest
#: description of both a rain delay and a fixture whose only ever source went
#: dark. It deliberately asserts nothing about the outcome, so every query that
#: means "settled" excludes it by construction rather than by remembering to.
#:
#: First rung of the ladder live/044 asked for (``scheduled|live|suspended|
#: final``). ``Event.status`` is a bare ``String(20)`` with no CHECK constraint
#: and no enum, so the vocabulary widens without a migration — but it widens
#: HONESTLY: every consumer that had to learn the word is edited in this change,
#: and :func:`authority_may_settle` / :func:`play_resumes` are the two doors out
#: so the state can never become a terminal one by accident.
#:
#: ── §R, AMENDMENT (CERT-786): A STATE NOBODY CAN REACH IS NOT A BETTER LIE ──
#:
#: The paragraph above claimed "every consumer that had to learn the word is
#: edited in this change" and it was not true. The SETTLEMENT consumers had been
#: edited; the RETRIEVAL consumers had not. ``routes/feed.py`` and
#: ``routes/events.py`` each enumerated ``live | scheduled | completed |
#: closed``, so the moment a staleness net wrote this value the match stopped
#: printing a false Final and stopped being reachable at all — Discover, the
#: Sports list and search each dropped it silently, and My Stuff filed the
#: pinned copy under Upcoming.
#:
#: **A new state in a vocabulary is not shipped when the producer writes it. It
#: is shipped when every consumer that DISPATCHES on that vocabulary has been
#: shown the word.** Producing a truer value into readers that drop it converts
#: a display defect into an absence, and absence is the one defect class users
#: cannot report: there is no card to screenshot.
#:
#: The distinction that makes this tractable is between the two kinds of
#: consumer, and it is not "settlement vs display":
#:
#:   * queries meaning **"is this settled?"** must keep excluding it, and do so
#:     by construction via :data:`SETTLED_STATUSES` — nothing to edit;
#:   * queries meaning **"what is there to show?"** must include it, and each
#:     one is a hand-written literal list that has to be found.
#:
#: The second kind is why this cost a cert. When adding the next state, grep for
#: the enumerations that contain ``"scheduled"`` — those are the retrieval
#: surfaces, and they are the ones that will not fail loudly.
EVENT_SUSPENDED = "suspended"

#: Terminal. Something with standing said this event is over. ``completed`` is
#: the authority's word, ``closed`` the venue/scores word; both mean Final to
#: every client, which is exactly why staleness may no longer write either.
SETTLED_STATUSES = frozenset({"completed", "closed"})

#: States a TERMINAL verdict may be written onto. ``suspended`` is in the set —
#: that is the whole point of it being non-terminal: the authority's ``post``
#: settles a suspended match the moment it reports one, with no intermediate
#: hop back through ``live``.
SETTLEABLE_STATUSES = frozenset({"live", EVENT_SUSPENDED})

#: States that "this is being played right now" promotes back to ``live``.
#: ``suspended`` is in the set for the same reason: play resuming after a rain
#: delay is the ordinary case this state exists to survive.
RESUMABLE_STATUSES = frozenset({"scheduled", EVENT_SUSPENDED})

#: The RECENT rail's vocabulary — "what has already happened and is worth
#: showing", which is a DIFFERENT question from :data:`SETTLED_STATUSES`' "what
#: has a verdict". A list, not a frozenset, because it is spent on ``IN`` and
#: the emitted SQL should be stable across processes.
#:
#: 🔴 WHY ``suspended`` IS HERE, live/056. The note above says the retrieval
#: surfaces are the hand-written literal lists and that they will not fail
#: loudly. Two of them were still missed after CERT-786 swept the feed and
#: ``GET /api/events``: the league page's RECENT RESULTS rail
#: (``league_futures.recent_results_query``) and the team page's recent games
#: (``teams``). A suspended match is in NEITHER of those pages' rails — the
#: other rail on both pages is ``live``/``scheduled`` gated on
#: ``commence_time >= now - 2h``, and a match is suspended precisely because
#: hours have passed since it started. So the match does not appear on its own
#: league page or on either team's page at all. Vanishing is a worse answer to
#: "where did my match go" than the false Final live/048 removed, which is the
#: exact sentence :data:`EVENT_LIST_DEFAULT_STATUSES` was written to stop being
#: true a second time.
#:
#: 🔴 AND IT RIDES THE RECENT RAIL RATHER THAN THE UPCOMING ONE, which is the
#: half worth arguing rather than asserting.
#: ``eventState.eventSectionKey`` buckets ``suspended`` with ``live`` on the
#: surfaces that GROUP events, and that is right there: those three buckets
#: answer "has this happened yet?". These two rails are not those buckets. They
#: are a time-ordered pair, and the upcoming rail's ``now - 2h`` floor would
#: exclude essentially every suspended row while the recent rail's lookback is
#: the same shape as the finished window ``event_list_window_condition`` already
#: gives it — so it ages off exactly where the Final it replaced would have,
#: rather than sitting on an open floor forever.
#:
#: The rail's TITLE says "Recent Results" and a suspended match has none. The
#: card corrects it in the only place a reader looks: both pages render the
#: shared card, which prints ``No result reported · last score 1-2`` and
#: suppresses the chips, the bar and the projection (CERT-799). A rail heading
#: over a card that states its own state is not the lie; an absent match is.
RECENT_RAIL_STATUSES = ["completed", "closed", EVENT_SUSPENDED]

#: How long after its own ``commence_time`` a ``scheduled`` row is still
#: plausibly about to start.
#:
#: It is the grace the upcoming rails already spend — ``now - 2h`` was written
#: as a bare literal in ``league_futures.upcoming_games_query`` and again in
#: ``teams``, and the number is the same claim in both: a row whose kickoff is
#: within this of now may still be a fixture that has not quite begun, because
#: nothing writes ``live`` the instant the first ball is bowled. Named so the
#: two rails and the guard can spend ONE number, since the invariant below is
#: stated in terms of it and a copy would let the two halves disagree about
#: where the boundary is.
UPCOMING_GRACE = timedelta(hours=2)


def started_without_result(status, commence_time, now) -> bool:
    """Has this row's kickoff passed while it still claims to be a fixture?

    🔴 THE THIRD STATUS THROUGH THE SAME HOLE — #3211, lane1/134.

    :data:`RECENT_RAIL_STATUSES`' note above records ``suspended`` falling
    between a league page's two rails and appearing on it NOWHERE. The note
    fixed ``suspended`` and left the structure that produced it, so the same
    page had the same hole one status over, and much wider: **171 US Open
    matches** (99 ATP, 72 WTA, measured on production 2026-09-05) were on
    ``/sports/tennis_atp``, ``/sports/tennis_wta`` and the two ``/sport/tennis``
    league pages on neither rail and in no list, for the whole fortnight.

    The mechanism is the one live/056 named and did not close. Every surface
    that splits events in two asks the pair:

        upcoming  ``status IN (live, scheduled)`` AND ``commence >= now - 2h``
        recent    ``status IN (completed, closed, suspended)`` AND a lookback

    and a ``scheduled`` row more than two hours past its own kickoff answers
    NEITHER: the upcoming rail drops it on the clock, the recent rail drops it
    on the status. Nothing ages it into view — the lookback only ever moves
    away from it — so the row is unreachable permanently rather than briefly.

    ── WHY THE ROWS SIT IN THAT STATE, WHICH IS A DIFFERENT BUG ──

    All 171 share one signature: 100% ``commence_time_source = kalshi_ticker``
    and 100% ``commence_time`` at exactly ``00:00:00Z``. That is gotcha #14 — a
    Kalshi row's ``commence_time`` is the ticker-derived CLOSE date, not the
    start — so the row sits in Upcoming until 02:00Z of its own day and then
    falls through. It stays ``scheduled`` because tennis has no ESPN anchor at
    all (#2700), so 70% of past Kalshi-derived tennis rows never reach a settled
    state. **Both of those are real and neither is this function.** They are
    #2693 and #1946, and they would each leave the other's damage in place: fix
    the settlement hole and the rail gap still swallows every row that has not
    settled yet; fix the rail gap and the row is reachable and honest about
    having no result. Reachable-and-honest is a page; absent is not.

    ── WHAT THIS PREDICATE IS FOR ──

    It is the RAIL question — "has this row's own clock run out?" — and it is
    deliberately not a claim about the outcome, the score, or whether anybody
    played. ``suspended`` says a source watched and stopped; this says nothing
    watched at all. To a reader those are the same sentence, which is why the
    surfaces render them identically (``eventState.SUSPENDED_LABEL``,
    "No result reported") and why this rides the recent rail for the reason
    :data:`RECENT_RAIL_STATUSES` gives verbatim: the upcoming rail's grace
    excludes it by construction, and the recent rail's lookback ages it off
    exactly where the Final it never got would have.

    ``None`` for either time is False. A row we cannot place on the clock is a
    row we have no standing to move off the schedule — the same rule
    :func:`is_retired_event_status` applies to an unrecognised status.
    """
    if status != "scheduled":
        return False
    if commence_time is None or now is None:
        return False
    return commence_time < now - UPCOMING_GRACE


#: RETIRED. The row is still in the table and is still addressable by anything
#: that keys on its id — an admin page, a backfill, a foreign key — and it is
#: NOT part of the schedule any reader should be shown.
#:
#: Both words are already written by shipped code and both already have rows:
#:
#:   ``merged``  ``routes/admin_backfill_linkage.py`` —
#:               ``UPDATE events SET status = 'merged' WHERE id = :orphan_id``,
#:               stamped on the loser of a duplicate pair once its markets have
#:               been moved onto the row that keeps them.
#:   ``voided``  the event never happened and never will.
#:
#: 🔴 WHY THIS SET EXISTS, lane1/132. Every LIST-shaped surface reaches events
#: through a hand-written status ALLOWLIST — :data:`EVENT_LIST_DEFAULT_STATUSES`,
#: ``_SEARCH_STATUSES``, ``_SEARCH_STARTED_STATUSES``, :data:`RECENT_RAIL_STATUSES`
#: — so all four have excluded these two words since the day they were written,
#: by omission rather than on purpose. The BY-ID read had no such gate at all:
#: ``GET /api/events/{event_id}`` selected on the primary key and served whatever
#: came back. So a row could be marked retired and its page kept rendering, fully
#: dressed, with a price and a chart on it.
#:
#: That is the general clause, and it is the mirror image of the one
#: :data:`EVENT_SUSPENDED` is written under. There, a new word in the vocabulary
#: was not shipped until every consumer had been shown it. Here, a word means
#: "stop showing this" and is not shipped until every consumer that can reach a
#: row WITHOUT consulting the vocabulary has been taught to ask. An allowlist
#: asks by construction; a primary-key lookup never asks at all.
#:
#: A frozenset because it is spent on membership, never on ``IN`` — the surfaces
#: that emit SQL are allowlists and must stay allowlists. Widening this set is
#: not how a status gets hidden from a list; a status is hidden from a list by
#: not being in that list's allowlist, which is already true of anything new.
RETIRED_STATUSES = frozenset({"merged", "voided"})


def is_retired_event_status(status) -> bool:
    """Has this row been taken off the schedule without being deleted?

    The single question every user-facing BY-ID read of an event asks before it
    serves the row. ``None`` and any unrecognised word are False: a row whose
    state we do not recognise is a row we have no standing to hide.
    """
    return status in RETIRED_STATUSES


def authority_may_settle(status) -> bool:
    """May a terminal verdict be written onto a row in this state? (live/048)

    True for ``live`` and ``suspended``; False for a row already settled
    (churning ``closed`` into ``completed`` rewrites history for no reader) and
    for ``scheduled`` (a match nobody has started cannot have finished).
    """
    return status in SETTLEABLE_STATUSES


def play_resumes(status) -> bool:
    """Does a report of play in progress put this row back on court? (live/048)

    The door out of :data:`EVENT_SUSPENDED` in the direction of ``live``. Its
    twin in the terminal direction is :func:`authority_may_settle`; between
    them, a suspended row is reachable from both of the states it can legally
    become, which is what stops the new state being a trap.

    Deliberately NOT true for ``completed``/``closed``: un-settling a row that
    something with standing settled is a bigger claim and keeps its own
    predicate, ``espn_helpers.espn_replay_unsettles`` (#1201), which clears
    ``completed_at`` in the same write.
    """
    return status in RESUMABLE_STATUSES


# A source captured something this recently ⇒ the game is still being played, so
# a wall-clock timeout is NOT evidence that it is over. Deliberately the same 30
# minutes the espn_sync docstring has always claimed.
STILL_ACTIVE_MINUTES = 30

# ── A VENUE PRICE IS NOT EVIDENCE OF PLAY (rung 4: never) ────────────────────
#
#: Sources that quote a PRICE on a match rather than report ON it — the bottom
#: rung of the ladder above, named so the SQL can exclude it.
#:
#: This is the SAME argument :func:`commence_time_is_a_reported_start` already
#: makes one field over — *"Kalshi prices tomorrow's match all night, so every
#: row would qualify and the guard would be a no-op that reads as a safeguard"*
#: — and q076 applied it only to the START side. The HOLD side kept counting
#: venue ticks, so the two halves of the same rule disagreed.
#:
#: MEASURED, production 2026-09-02. Six US Open matches (De Jong/Passaro,
#: Bergs/Taberner, Kasatkina/Badosa, Molcan/Bonzi, Jović/Frech, Linette/Jones)
#: read ``status='live'`` while carrying a ``completed_at``. Every one of their
#: post-commence ``win_prob_snapshots`` rows — 1,037 of them across the seven
#: candidates — was ``source='kalshi'``. Not "mostly": there was no ESPN, MLB,
#: stat-model or StatPal snapshot on any of them. The hold guard was being
#: satisfied 100% by price ticks, and ``derive_completed_at`` then stamped a
#: game-end time off one. ESPN, the authority, had all six SCHEDULED to resume
#: that afternoon — none had finished at all.
#:
#: A DENYLIST, not an allowlist, and deliberately: StatPal writes
#: ``source='statpal'`` and is not in ``WIN_PROB_SOURCES`` at all, so an
#: allowlist would silently drop a real play source. The completeness risk runs
#: the other way — a NEW venue that nobody classifies — and that is what
#: ``test_every_market_source_is_named_a_venue`` pins against the registry's own
#: ``source_type == "market"``.
VENUE_PRICE_SOURCES = frozenset({"betting", "kalshi", "polymarket"})

_VENUE_SOURCE_SQL_LIST = ", ".join(f"'{s}'" for s in sorted(VENUE_PRICE_SOURCES))

# One batched query for a whole candidate set: the most recent snapshot from a
# source that REPORTS ON the game, landing at or after the event's own
# commence_time. Pre-commence rows are excluded because a pregame line says
# nothing about when play ended; venue prices are excluded because a price says
# nothing about play at all.
#
# ``odds_snapshots`` is gone from the union entirely rather than filtered: every
# row in that table is a bookmaker line, which is the "betting" venue by
# definition. There is no play-reporting arm of it left to keep.
LAST_POST_COMMENCE_SNAPSHOT_SQL = f"""
    SELECT x.event_id, MAX(x.captured_at) AS last_snap
    FROM (
        SELECT w.event_id, w.captured_at
          FROM win_prob_snapshots w
          JOIN events e ON e.id = w.event_id
         WHERE w.event_id = ANY(:event_ids) AND w.captured_at >= e.commence_time
           AND (w.source IS NULL OR w.source NOT IN ({_VENUE_SOURCE_SQL_LIST}))
    ) x
    GROUP BY x.event_id
"""


def game_may_still_be_running(last_snapshot, now) -> bool:
    """Is there live evidence that this game has NOT finished?

    True ⇒ hold off. A wall-clock timeout on a game something is still reporting
    on is the frozen-score producer: closing here writes a mid-game score into a
    settled event and grades the blend off it.

    No snapshot at all is NOT evidence of activity — that is the ordinary case
    for an event whose sources went quiet. Since live/048 that no longer makes
    the row CLOSEABLE, only SUSPENDABLE: the same absence, read at its true
    strength.

    ``last_snapshot`` must come from :data:`LAST_POST_COMMENCE_SNAPSHOT_SQL`,
    which excludes :data:`VENUE_PRICE_SOURCES`. Passing a venue tick in here
    re-opens live/042: a market that stays open holds a finished match live
    forever, because the hold renews itself every two minutes.
    """
    if last_snapshot is None or now is None:
        return False
    return (now - last_snapshot) < timedelta(minutes=STILL_ACTIVE_MINUTES)


def venue_live_write_is_a_resurrection(status, completed_at) -> bool:
    """Would writing ``live`` here un-settle a row on a VENUE's say-so? (live/042)

    True ⇒ refuse the status write. The score write is unaffected: a later score
    from the same feed converges a frozen mid-game number on the real one, and
    gotcha #21 keeps grading out of it either way.

    The Odds API scores feed reports ``completed: false`` for anything its books
    still quote, and the reader derives ``live`` from that plus a start in the
    past. On a row nothing has settled that is the ordinary promotion. On a row
    that ALREADY carries a completion it is a venue overruling a settlement it
    knows nothing about — and because it leaves ``completed_at`` in place, what
    it actually produces is a row that is live and finished at the same time.

    MEASURED, production 2026-09-02: five US Open matches served
    ``{"status": "live", "completed_at": "..."}`` from ``/api/events/{id}``
    simultaneously.

    ── ``suspended`` IS DELIBERATELY NOT REFUSED (live/048) ──

    A suspended row is not settled and carries no ``completed_at``, so this
    returns False for it and the scores feed may promote it straight back to
    ``live``. That is rung 3 of the ladder doing its job, and it is the reason
    suspending is not a quieter way of stranding a match: the same feed that
    reports play resuming is allowed to act on it. What the feed still may not
    do is un-settle — that stays reserved for ``espn_replay_unsettles`` (#1201),
    which clears ``completed_at`` in the same write so the row never holds both
    facts at once.
    """
    return status in SETTLED_STATUSES or completed_at is not None


def derive_completed_at(last_snapshot, commence_time, now=None):
    """Best available game-end time, or None to leave it unset.

    The last real post-commence snapshot (gotcha #22 — never a backend
    processing timestamp). Returns None rather than guessing when there is no
    such snapshot: a NULL ``completed_at`` is a visible gap the repair can fill,
    whereas a plausible-looking ``now()`` is a wrong value nothing will ever
    question.

    Never returns a time that precedes the start (gotcha #46) — that inversion
    means an earlier game's data merged onto this event, and stamping it would
    manufacture the very invariant violation the audit hunts for.
    """
    if last_snapshot is None or commence_time is None:
        return None
    if last_snapshot < commence_time:
        return None
    return last_snapshot


#: Statuses a staleness net USED to put an event into. Both are "we stopped
#: hearing about it", neither is "a source told us it finished" — which is why
#: since live/048 no net writes either and the artifact this repairs is a
#: historical population rather than a growing one. Aliased to the ladder's own
#: set so the two can never drift into disagreeing about what "settled" means.
_NET_SETTLED_STATUSES = SETTLED_STATUSES


def settlement_is_a_staleness_artifact(
    status, home_score, away_score, new_commence, completed_at
) -> bool:
    """Did a staleness net settle an event that had not been played? (q066b)

    Three facts have to hold at once, and the conjunction is what makes it safe:

    1. **The row is settled** — ``closed`` or ``completed``.
    2. **It carries no score.** This is the load-bearing one. Every net in this
       codebase settles on ELAPSED WALL-CLOCK, never on a result, so a settled
       row with no score is a row nothing ever reported a finish for. A scored
       row is left alone no matter what else is true: a real result outranks any
       schedule correction, and gotcha #21 says never bulk-disturb resolution.
    3. **The owning provider has since moved the start PAST the recorded
       completion.** ``completed_at < new_commence`` is the #46 inversion, read
       here from the other side: normally it means a wrong-sibling fold and the
       correction must be refused, but on an unscored row it means the settlement
       timestamp predates the game it claims to have ended — so the settlement is
       the wrong field, not the start.

    Same class of evidence as ``espn_helpers.espn_replay_unsettles`` (ESPN
    reporting IN PROGRESS on a row we call settled), reached through a different
    door: there the live source contradicts the state, here the SCHEDULE source
    does. Both are proof the settled state is wrong, and both clear it.

    The producing shape, measured on the live US Open slate 2026-09-01: The Odds
    API published all of Aug 31's matches at one session-start default of
    15:00:00Z, the clock promoted them to ``live`` at 15:00, the staleness nets
    closed them during an ordinary poll gap, and 35 matches sat marked finished
    with no result while bookmakers were still actively pricing them — nine of
    them being played the following day.
    """
    if status not in _NET_SETTLED_STATUSES:
        return False
    if home_score is not None or away_score is not None:
        return False
    if completed_at is None or new_commence is None:
        return False
    return completed_at < new_commence
