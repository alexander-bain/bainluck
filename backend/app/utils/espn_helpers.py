"""
Extracted helpers for ESPN sync — team upsert, event matching, and per-pass logic.

Pulled out of the 950-line `_sync_espn_live_events` god function in
`app/tasks/espn_sync.py` to keep the orchestrator thin and each helper testable.
"""

import dataclasses as _dataclasses
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update as _sql_update

# live/048 — the state ladder's two doors (EVENT-GRAPH-DOCTRINE §R). Safe to
# import here: `event_completion` imports nothing but `datetime`.
from app.utils.event_completion import authority_may_settle, play_resumes
# #5390: the period-string predicate lives in a leaf module, so this is a
# plain module-level import rather than five function-local ones dodging a cycle.
from app.utils.game_state import _sanitize_period, live_write_would_revert
from app.utils.live_state_write import write_live_state_if_unmoved
from app.utils.name_normalization import (
    names_match as _canonical_names_match,
    normalize_name as _normalize_name,
    shared_token_rivals as _shared_token_rivals,
)
from app.utils.espn_candidate_selection import (
    select_authorized_espn_candidate as _select_authorized_espn_candidate,
)
from app.utils.espn_id_stamp import (
    REFUSED as _ESPN_STAMP_REFUSED,
    STAMPED as _ESPN_STAMP_STAMPED,
    espn_id_holder,
    stamp_espn_id_if_unheld,
)
from app.utils.game_pairing import (
    PREGAME_LIVE_GRACE as _PREGAME_LIVE_GRACE,
    Pairing,
    live_write_is_premature as espn_live_write_is_premature,
    pair_verdict,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cross-merged-events guard (#189/#190; gotcha #32 family)
# ---------------------------------------------------------------------------
# ESPN's finished-game handling can fold an EARLIER same-matchup game's terminal
# state (completed_at + final win prob) onto a LATER sibling event, because both
# write-side match paths are time-loose: the 28h structured match
# (`_find_by_structured_match`) has no minimum-distance floor — a single
# name-matching candidate up to 28h away is returned unconditionally — and the
# ESPN name match (`match_event_to_espn`) has no time guard at all. MLB / NCAA
# baseball series and doubleheaders repeat the identical matchup inside that
# window, so the wrong sibling gets stamped. The observable damage is 439 events
# with `completed_at < commence_time` — impossible, since a game cannot finish
# before it starts (the empty settled-chart + impossible My-Stuff-date class).
#
# These two pure guards enforce that invariant from BOTH directions at the write
# sites, so the class can never be written again regardless of which match path
# folded — the fix at the source, complementing the flow-sentinel detector +
# audit that catch any residual.
_FOLD_GUARD_SLACK = timedelta(hours=2)  # tolerate clock/commence jitter near start


def completion_stamp_inverts_commence(commence_time, completed_at) -> bool:
    """True when stamping ``completed_at`` onto an event with ``commence_time``
    would create ``completed_at < commence_time`` — an earlier game's finish
    folded onto a later sibling. Missing either side is not an inversion."""
    if commence_time is None or completed_at is None:
        return False
    return completed_at < commence_time


def commence_correction_inverts_completion(new_commence, completed_at) -> bool:
    """True when moving an already-completed event's commence_time to
    ``new_commence`` would push the start AFTER its recorded completion (the same
    ``completed_at < commence_time`` inversion, approached from the commence side)."""
    if new_commence is None or completed_at is None:
        return False
    return completed_at < new_commence


def espn_replay_unsettles(event_status, espn_status) -> bool:
    """True when ESPN (the authoritative live source) reports a game IN PROGRESS
    on an event we currently have SETTLED — the un-settle-on-replay signal (#1201).

    A game that was prematurely settled (postponed → closed by the staleness net,
    then rescheduled/replayed) or a wrong-sibling fold (gotcha #32) that never
    really finished will be reported ``in`` by ESPN once it actually plays. That
    is definitive proof the completed/closed state is wrong, so the caller reverts
    the event to ``live`` and clears ``completed_at`` (removing any leftover
    ``completed_at < commence_time`` inversion). Idempotent: the live→completed
    branch re-settles it correctly once ESPN reports post/final again."""
    return espn_status == "in" and event_status in ("completed", "closed")


def play_evidence(home_score=None, away_score=None, period=None, game_clock=None) -> bool:
    """Is there positive evidence on this row that the game is being PLAYED?

    THE ONE DEFINITION, shared by all four sites that ask (#5324, CERT-2782).
    The demotion refuses on it, the promoter's hold is superseded by it, the
    marker is cleared on it, and the refresh declines on it. They were three
    copies of the same loop for one revision and that is how a row starts
    ping-ponging between two tasks that disagree by a field — so the agreement
    is structural here rather than a convention three docstrings promise.

    A non-zero score, a period, or a game clock. A 0-0 with no clock is NOT
    evidence: ``COALESCE(home_score,0)=0`` conflates absence with a real nil-nil
    (live/182 rider 2), and that ambiguous shape is precisely what the authority
    exists to break the tie on.

    ``isinstance(True, int)`` is True in Python, so a bool in a score column
    would otherwise read as 1. A bool there is garbage, not an observation.
    """
    if period or game_clock:
        return True
    for side in (home_score, away_score):
        if isinstance(side, bool) or not isinstance(side, int):
            continue
        if side != 0:
            return True
    return False


def espn_scheduled_marks_not_started(
    event_status,
    espn_status,
    home_score=None,
    away_score=None,
    period=None,
    game_clock=None,
) -> bool:
    """Should this row CARRY the "authority says not started" marker right now?

    CERT-2782's required repair, `5324-REPEATED-SCHEDULED-PASS-RETAINS-HOLD`.
    The demotion predicate below answers a narrower question — *should the
    status change* — and it is False once the row is already ``scheduled``. The
    first cut used "the demotion did not fire" as the cue to CLEAR the marker,
    so the second consecutive ESPN `scheduled` pass deleted the very fact the
    first one recorded and the next transition restored ``LIVE``. The flicker
    came back with a period of two passes instead of one.

    So the marker's presence is its own question, asked of the same authority
    statement: ESPN says not started, our row is ``live`` (about to be demoted)
    or already ``scheduled`` (demoted on an earlier pass), and nothing on the
    row says it is being played. While all three hold the marker is REFRESHED,
    which is also what keeps the hold alive past its TTL for a start that slides
    a long way.

    Any other ESPN state leaves the marker exactly where it is. In particular
    ``status_delayed`` neither stamps nor clears — ESPN publishes it before a
    start and mid-game alike, so it is not a statement either way.
    """
    if espn_status != "scheduled" or event_status not in ("live", "scheduled"):
        return False
    return not play_evidence(home_score, away_score, period, game_clock)


def espn_scheduled_demotes_live(
    event_status,
    espn_status,
    home_score=None,
    away_score=None,
    period=None,
    game_clock=None,
) -> bool:
    """True when the authority positively reports a game as NOT YET STARTED on a
    row we are serving as ``live`` — the second half of #5324.

    ``events.status`` is a LATCH. ``transition_event_statuses`` promotes
    ``scheduled -> live`` the moment ``commence_time <= now`` and nothing ever
    re-derives it, so a start that slides leaves the row asserting ``live``
    against a game nobody has begun. live/171 closed the half that is decidable
    from the row alone (``live`` with its OWN start still ahead) inside
    ``served_event_status``. This is the other half, and it needs a fact from
    outside the row: between slides ``commence_time`` sits in the past and the
    row is internally consistent while still being wrong.

    ═══ WHY NOT A GRACE WINDOW ═══

    The cheap rule — "live, nothing ever observed, started less than N minutes
    ago" — was measured and RULED OUT (M-20260912-live171, 23:37Z 2026-09-12).
    Twelve rows would have been demoted at N>=25 and **all twelve were genuinely
    being played**; eleven simply had ``home_score IS NULL`` because we hold no
    observation channel for their sport at all. That is gotcha #53's shape —
    absence of an observation read as an observation of absence — and no value
    of N can fix it while whole sports observe nothing. Re-taken after #5697
    released (02:55Z 2026-09-13) the same set is 1 of 6 rows, and that row is
    anchorless AFLW, on which this rule is silent by construction.

    ═══ ASYMMETRIC, LIKE EVERY OTHER AUTHORITY WRITE HERE ═══

    Only a POSITIVE statement moves the row, and our own observation outranks
    the authority's negative one:

    * ``espn_status == "scheduled"`` is ESPN's ``STATUS_SCHEDULED`` — it says
      this game has not begun. Silence, an unmatched row, or any other state
      writes nothing, so the sports ESPN does not cover are untouched rather
      than wrongly demoted.
    * ``status_delayed`` deliberately does NOT demote. ESPN publishes it both
      before a start and mid-game, and it carries ``state="in"`` either way
      (see :func:`espn_terminal_state`'s note) — an ambiguous read, so this
      stays silent on it. Same for ``status_halftime``, which is not
      "not started" by any reading.
    * A real observation of our own REFUSES the demotion: a non-zero score, a
      period, or a game clock. If we hold 21-14 and the authority says
      scheduled, the anchor is wrong and the answer is to write nothing, not to
      blank a game in progress.
    * A 0-0 with no clock is NOT an observation. It is the ambiguous value
      ``COALESCE(home_score,0)=0`` conflates with absence, and the whole reason
      live/182's rider 2 insists on splitting ``IS NULL`` from ``= 0``; the
      authority is the tiebreak on exactly that shape.
    * Only ``live`` is demoted. A settled row contradicted by ``scheduled`` is
      the cross-merge/fold class and belongs to ``_is_bogus_future_settled``,
      which already judges it on different evidence.

    Pure, so the whole policy is testable without a database and without a
    network — the same reason :func:`authority_write` next door is pure.
    """
    if espn_status != "scheduled" or event_status != "live":
        return False
    return not play_evidence(home_score, away_score, period, game_clock)


# ───────────────────────────────────────────────────────────────────────────
# THE DEMOTION HAS TO SURVIVE THE CLOCK (#5324, CERT-2777's required repair)
# ───────────────────────────────────────────────────────────────────────────
#
# `espn_scheduled_demotes_live` above writes `scheduled`. Sixty seconds later
# `_transition_event_statuses_impl` selects `status == "scheduled" AND
# commence_time <= now` and promotes the very same row back to `live`. Both
# tasks run every 60s on the realtime queue, so without the fact below the ship
# is a one-minute flicker and then nothing — CERT-2777 drove the two real tasks
# in sequence and got `live` back, while the single-task band passed.
#
# The two tasks cannot both be right, and the tie-break is evidence: one of them
# has read the authority and the other has read a clock. `transition` makes ZERO
# API calls by design, so the authority's statement has to reach it through the
# row. It travels in the `win_probability_sources` JSONB — the same mirror
# `statpal_end_time` already uses for a non-probability fact
# (`event_completion.statpal_end_time` reads it out of there), so this is an
# established shape on an existing column and not a migration.
#
# IT EXPIRES, and the bound is derived rather than chosen: `sync-espn-live` is
# a 60s interval beat, so a live stamp is re-written every pass while ESPN keeps
# saying the game has not begun. The hold therefore only has to outlive a few
# missed passes, and anything longer is a row frozen by a dead poller rather
# than by the authority. Fifteen minutes is fifteen consecutive missed passes;
# past that the clock wins again and the row promotes normally. A test asserts
# this constant against the beat's own cadence rather than against a literal,
# because two records of one capability drift.
ESPN_NOT_STARTED_KEY = "espn_not_started_at"
_ESPN_LIVE_BEAT_SECONDS = 60
_AUTHORITY_NOT_STARTED_MISSED_PASSES = 15
AUTHORITY_NOT_STARTED_TTL = timedelta(
    seconds=_ESPN_LIVE_BEAT_SECONDS * _AUTHORITY_NOT_STARTED_MISSED_PASSES
)


def stamp_authority_not_started(sources, now):
    """A NEW sources dict carrying "the authority says this has not begun, at ``now``".

    Returns a fresh object rather than mutating in place: an in-place change to a
    JSONB value is not seen by the ORM's change tracking and is silently dropped
    (gotcha #4), which is the single most expensive way for this repair to look
    like it works.
    """
    updated = dict(sources or {})
    updated[ESPN_NOT_STARTED_KEY] = now.isoformat()
    return updated


def clear_authority_not_started(sources):
    """A NEW sources dict with the marker removed, or the original when absent.

    Returning the original unchanged when there is nothing to clear matters: the
    caller writes only when the object differs, so an ordinary live pass over an
    ordinary game issues no extra UPDATE.
    """
    if not sources or ESPN_NOT_STARTED_KEY not in sources:
        return sources
    updated = dict(sources)
    updated.pop(ESPN_NOT_STARTED_KEY, None)
    return updated


def authority_not_started_holds(
    sources,
    now,
    home_score=None,
    away_score=None,
    period=None,
    game_clock=None,
    ttl=AUTHORITY_NOT_STARTED_TTL,
) -> bool:
    """True when the clock may NOT promote this row, because the authority said
    within :data:`AUTHORITY_NOT_STARTED_TTL` that the game has not begun.

    POSITIVE PLAY EVIDENCE SUPERSEDES THE HOLD, and it is the same evidence
    :func:`espn_scheduled_demotes_live` refuses a demotion on — a non-zero score,
    a period, or a game clock. Stated once here and once there deliberately: the
    two tasks have to agree about what counts as "being played", or a row
    ping-pongs between them, which is the class of defect this function exists
    to end rather than to re-create in the other direction.

    A 0-0 with no clock is NOT evidence, for the reason it is not evidence next
    door: ``COALESCE(home_score,0)=0`` conflates absence with a real nil-nil, and
    the authority is the tie-break on exactly that shape.

    Fails OPEN on every unreadable input — absent key, ``None``, a non-string, an
    unparseable stamp, a stamp in the future. A hold is a refusal to act on the
    clock, so when in doubt the ordinary promotion path must win; the alternative
    is a row stuck out of `live` on a corrupt string nobody can see.
    """
    if play_evidence(home_score, away_score, period, game_clock):
        return False

    raw = (sources or {}).get(ESPN_NOT_STARTED_KEY)
    if not isinstance(raw, str):
        return False
    try:
        stamped = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return False
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=timezone.utc)
    age = now - stamped
    if age < timedelta(0):
        # A stamp from the future is a clock fault, not an authority statement.
        return False
    return age <= ttl


def espn_terminal_write_is_fold(event_commence, now, slack=_FOLD_GUARD_SLACK) -> bool:
    """True when writing terminal/live ESPN state onto an EXISTING event whose own
    ``commence_time`` is still in the future (beyond ``slack``) — i.e. an ESPN game
    that already started/finished was resolved onto a not-yet-played sibling. That
    is exactly the fold that produces ``completed_at < commence_time``; the caller
    skips the win-prob + completion write instead of corrupting the sibling."""
    if event_commence is None or now is None:
        return False
    return event_commence > now + slack


# ``_PREGAME_LIVE_GRACE`` and ``espn_live_write_is_premature`` now live in
# ``app/utils/game_pairing.py`` and are imported at the top of this module. They
# are re-exported under their historical names so existing importers and
# ``tests/test_espn_fold_guard.py`` keep working — but there is exactly ONE
# implementation, because StatPal needed the identical guard (#1945) and a second
# copy is how the two providers drifted apart in the first place.
#
# ESPN occasionally publishes a pregame ``in`` status and a pregame win-probability
# hours before first pitch (#1207: an event flipped ``live`` + ESPN win-prob ~4h
# early). Distinct from ``espn_terminal_write_is_fold`` (a 2h fold-detection
# tolerance for a wrong-sibling resolve): the premature guard is a small "not
# started yet" grace on the event's OWN commence_time.


# ---------------------------------------------------------------------------
# Team upsert
# ---------------------------------------------------------------------------

#: The ESPN fields that NAME A CLUB. `abbreviation` is deliberately absent: a
#: three-letter code carries no name to compare, and feeding it to a
#: token-overlap matcher buys nothing but false agreement.
_ESPN_CLUB_NAME_FIELDS = (
    "display_name",
    "name",
    "short_name",
    "nickname",
)

#: `location` NAMES A CITY, NOT A CLUB, and it is the one field the rival veto
#: cannot protect (#6215, CERT-2881 follow-through). Manchester City's payload
#: carries `location = "Manchester"`, and `Manchester` sits inside
#: `Manchester United` with nothing left over — so it is not a "rival" by any
#: token test, it is a strict subset, and `names_match` accepts it. A guard that
#: lets the city vouch therefore hands United's row City's badge no matter how
#: good the rival rule above it is.
#:
#: So the city may only corroborate by EXACT normalized equality — `Leeds
#: United`/`Leeds United`, where ESPN happens to put the full club name in the
#: field. It can never establish identity on its own by containment.
#:
#: THE ALTERNATIVE WAS MEASURED AND REJECTED. Requiring "their name is at least
#: as specific as ours" across all fields refuses 188 of 1,000 legitimate
#: adopters — `Seattle Seahawks` vs `Seattle`, `New England Patriots` vs
#: `New England` — because location-is-a-prefix is the NORMAL shape for US
#: clubs. Those rows keep their identity here because `display_name` carries the
#: club name and answers first; only a payload with no club-naming field at all
#: is refused, and that costs a missing crest, which is visible and reversible.
_ESPN_IDENTITY_LOCATION_FIELD = "location"


def _sole_candidate_the_payload_names(team_name, candidates, espn_team):
    """The one candidate this ESPN payload actually names, or nothing.

    `upsert_team`'s pre-mint scans took the FIRST row that satisfied
    `_canonical_names_match`, and that predicate is a RECALL instrument —
    `espn_identity_corresponds` documents that it "admits every cross-town
    rival" (CERT-2881). So in a league holding both `Los Angeles FC` and
    `LA Galaxy`, an incoming `Los Angeles G` matches BOTH, and which club it
    binds to is decided by the order the scan happened to return rows in.
    Measured on the parent, before the probe below existed: `Los Angeles G`
    carrying the Galaxy payload resolves to `Los Angeles FC` under BOTH row
    orders (CERT-3134).

    Binding to the wrong club is worse than the duplicate this file exists to
    stop: a duplicate is a second card, a wrong bind is another club's schedule
    on this club's page. So the payload breaks the tie — it names exactly one
    club, and it is the same evidence the mint refusal below already trusts.

    Returns None when nothing corresponds AND when more than one does; an
    ambiguous answer is refused rather than guessed (the tie doctrine this lane
    shipped for `resolve_team` in #7230).
    """
    return _sole_named_candidate(
        team_name,
        [(c.name, c) for c in candidates if c is not None],
        espn_team,
    )


def _sole_named_candidate(team_name, named_candidates, espn_team):
    """As above, over ``(name, row)`` pairs.

    The in-memory `team_cache` is keyed by the name a caller looked up, which is
    not always `row.name`, so its selection has to be made against the KEY. Both
    production callers of `upsert_team` pass a full-sport cache, so this path —
    not the DB scans — is the one that decides identity on a warm run
    (CERT-3136).
    """
    accepted = [
        (name, row)
        for name, row in named_candidates
        if name and _canonical_names_match(team_name, name)
    ]
    if not accepted:
        return None

    city, initial = _city_plus_initial(team_name)
    if initial:
        # THE FRAGMENT NAMES ITS CLUB BY ONE LETTER, SO HONOUR THE LETTER.
        # Neither `names_match` nor `espn_identity_corresponds` can separate
        # these: `names_match('Los Angeles FC', 'LA Galaxy')` is True, the rival
        # veto reads False, and the payload therefore "corresponds" to both. The
        # only thing that distinguishes them is the initial the fragment
        # actually carries — `G` is Galaxy, not FC. Same rule this lane shipped
        # for `resolve_team` in #7230: a city-plus-initial fragment resolves to
        # one club or to none.
        city_tokens = set(_normalize_name(city).split())
        accepted = [
            (name, row)
            for name, row in accepted
            if any(
                token.startswith(initial)
                for token in _normalize_name(name or "").split()
                if token not in city_tokens
            )
        ]

    if len(accepted) == 1:
        return accepted[0][1]
    if not accepted:
        return None

    # Still ambiguous: `names_match` is a RECALL instrument, so the first row the
    # scan happened to return would decide identity by heap order. Refuse.
    named = [
        (name, row)
        for name, row in accepted
        if espn_identity_corresponds(name, getattr(row, "alternate_names", None), espn_team)
    ]
    return named[0][1] if len(named) == 1 else None


def _city_plus_initial(team_name):
    """``'Los Angeles G'`` -> ``('Los Angeles', 'g')``; anything else -> (None, None)."""
    parts = (team_name or "").split()
    if len(parts) >= 2 and len(parts[-1]) == 1 and parts[-1].isalpha():
        return " ".join(parts[:-1]), parts[-1].lower()
    return None, None


def _espn_name_probes(espn_team, exclude_word: str = "") -> list[str]:
    """Significant words from the ESPN payload's club-name fields.

    These are SEARCH PROBES, not evidence. `upsert_team` narrows its pre-mint
    candidate set with an ILIKE on the first word of the name it was handed,
    which is the CALLER's spelling of the city — so it can never reach a
    canonical row that spells the city the other way. `%Los%` does not match
    `LA Galaxy`, and that is why `Los Angeles G` (12617) was minted beside it
    while `Los Angeles C`/`New York I`/`New York R` were not: those three share
    a first word with their canonical and this one does not (#6974).

    The ESPN payload names the club we are about to stamp onto the row, so it
    is the one probe available here that does not depend on the caller's
    spelling. Widening the candidate set cannot widen what is ACCEPTED: every
    candidate still has to pass `_canonical_names_match` against the incoming
    name, exactly as before. This lets that predicate see rows the ILIKE hid.

    `location` is excluded for the reason the constant above gives — it names a
    city, not a club. Only `_ESPN_CLUB_NAME_FIELDS` are probed, and words
    shorter than three characters are dropped because a one-letter fragment
    (`G`, `C`) is what put us here.
    """
    if not espn_team:
        return []
    skip = exclude_word.strip().lower()
    seen: set[str] = set()
    for field in _ESPN_CLUB_NAME_FIELDS:
        value = getattr(espn_team, field, None)
        if not value:
            continue
        for raw in str(value).split():
            word = raw.strip().strip(".,'\"")
            if len(word) < 3:
                continue
            lowered = word.lower()
            if lowered == skip:
                continue
            seen.add(lowered)
    return sorted(seen)


def espn_identity_corresponds(team_name, existing_alternate_names, espn_team) -> bool:
    """Does this ESPN payload name the club we are about to stamp it onto?

    The question ``upsert_team``'s own guard has always meant to ask and could
    never reach (#6215): that guard is written ``if team.espn_id and ...``, so
    it is unreachable for a row with no ESPN id — which is precisely the
    wrong-event-match case its comment names, because a brand-new row is created
    without one twelve lines earlier.

    Measured on production 2026-09-14: **1,077 team rows carry ESPN identity
    fields with no ESPN id, and ~1,010 of them are wearing another club's
    identity** — MLS 581, NCAAB 168, EPL 162, WNCAAB 26. Fluminense is stored as
    ``ARS · 19-7-3 · Arsenal`` under ``soccer_epl``; Marist Red Foxes wears
    ``OSU · 18-11 · Ohio State``. 143 of the EPL cohort are bound to real events
    by FK, so the borrowed badge travels to every surface that resolves a team
    off ``home_team_id``.

    Both sides are plural on purpose. Ours is the name we were handed plus any
    alias the row already carries, so the answer is RECOVERABLE: once
    ``Internazionale`` is a known alternate of ``Inter Milan``, ESPN's spelling
    corresponds and enrichment resumes. Theirs is every field ESPN uses to name
    a club, because which one is populated varies by endpoint.

    FAIL-CLOSED, INCLUDING ON SILENCE: a payload carrying no name at all cannot
    be shown to be about this club, so it does not get to rewrite its identity.
    The cost of a wrong refusal is a missing crest — visible and reversible. The
    cost of a wrong acceptance is a lie on an event-bound row, which is what
    #6215 is.

    🔴 **`names_match` ALONE ADMITS EVERY CROSS-TOWN RIVAL (CERT-2881).** It is a
    recall instrument — stage 3 accepts any pair with ≥0.5 token overlap — so
    `names_match("Manchester United", "Manchester City")` is True, as are
    Real Madrid/Real Sociedad, Jets/Giants and Lakers/Clippers. Meanwhile the
    legitimate alias this function's own paragraph above promises,
    `Inter Milan`/`Internazionale`, is False. On exactly the pairs that decide an
    identity the house matcher is backwards, so `shared_token_rivals` vetoes in
    front of it. Measured on 1,000 legitimate adopters the veto costs ONE row,
    and that row (`Qarabag FK` wearing `Viking FK`) is itself borrowed.
    """
    ours = [o for o in [team_name, *(existing_alternate_names or [])] if o]
    club_names = [
        v
        for v in (getattr(espn_team, f, None) for f in _ESPN_CLUB_NAME_FIELDS)
        if v
    ]
    if any(
        _canonical_names_match(o, t) and not _shared_token_rivals(o, t)
        for o in ours
        for t in club_names
    ):
        return True

    # The city, exact only — see `_ESPN_IDENTITY_LOCATION_FIELD`.
    city = getattr(espn_team, _ESPN_IDENTITY_LOCATION_FIELD, None)
    if not city:
        return False
    return any(_normalize_name(o) == _normalize_name(city) for o in ours)


def espn_payload_renames_the_stored_id(team_name, espn_team) -> bool:
    """Is this payload strong enough to OVERWRITE an ESPN id the row already has?

    `espn_identity_corresponds` answers a different question: may a payload
    *fill* an identity the row does not have. This one decides whether a payload
    may *replace* one it does, and it is deliberately the stricter of the two —
    the row is handing over its anchor, so the evidence has to be an identity,
    not a resemblance. Exact normalized equality against a field that NAMES A
    CLUB; no city arm, no aliases, no token overlap.

    ═══ WHY NOT JUST REUSE `espn_identity_corresponds` ═══

    Because it is measurably unsafe on this arm, and unsafe in exactly the place
    #6974 has already been burnt. Run on the real helpers, 2026-09-20:

        espn_identity_corresponds('Los Angeles C', None, <Lakers, id 13>) -> True
        espn_payload_renames_the_stored_id('Los Angeles C', <Lakers, id 13>)-> False

    `Los Angeles C` is a #6974 FRAGMENT row whose stored id `12` is the Clippers
    and is CORRECT. `normalize_name` deletes a trailing `c` (it is in
    `_RESERVE_SUFFIX_RE`), so the row normalizes to `los angeles`, which
    token-overlaps the Lakers at 0.5 and is not a "rival" of them by any token
    test — the loose predicate says yes and would hand the Clippers' row the
    Lakers' id. Same shape for `Los Angeles G`/`LA Galaxy`. Strict equality
    refuses all four fragment pairs, because `los angeles` is not `los angeles
    lakers` and is not `lakers`.

    ═══ WHY NOT `alternate_names` ═══

    `upsert_team` WRITES `alternate_names` from the ESPN payload, so on a row
    that has already taken a foreign identity every alias on it is the other
    club's. Production, 2026-09-20: team 839 `Wisconsin Badgers` carries
    `['Fighting Irish', 'Notre Dame Fighting Irish', 'Notre Dame']` and not one
    Wisconsin alias. Letting the aliases vouch would make a Notre Dame payload
    correspond to the Badgers — the corrupted field arbitrating its own
    corruption. `team.name` is the ONE identity field `upsert_team` never
    writes, which is the whole reason it is the witness here.

    FAIL-CLOSED ON SILENCE, like its sibling: no name on either side is not
    agreement. The cost of a wrong refusal is the status quo (a stale badge);
    the cost of a wrong acceptance is a correct anchor destroyed.
    """
    ours = _normalize_name(team_name or "")
    if not ours:
        return False
    return any(
        _normalize_name(value) == ours
        for value in (
            getattr(espn_team, field, None) for field in _ESPN_CLUB_NAME_FIELDS
        )
        if value
    )


async def upsert_team(session, team_name, espn_team, sport_id, team_cache=None, stats=None):
    """Create or update a Team record with ESPN enrichment data.

    Returns the Team record (for linking back to events), or None.
    """
    from app.models.models import Team

    if not espn_team:
        return None

    team = team_cache.get((team_name, sport_id)) if team_cache is not None else None
    if team is None:
        team_result = await session.execute(
            select(Team).where(
                Team.name == team_name,
                Team.sport_id == sport_id,
            )
        )
        team = team_result.scalar_one_or_none()

    # Fuzzy match: "Stanford" should find "Stanford Cardinal" (and vice versa).
    # Selected the same way as the DB scans below — this loop used to take the
    # first cross-town match, and since both production callers pass a
    # full-sport cache it is this path, not the scans, that decides identity on
    # a warm run (CERT-3136).
    if team is None and team_cache is not None:
        team = _sole_named_candidate(
            team_name,
            [
                (cached_name, cached_team)
                for (cached_name, cached_sport_id), cached_team in team_cache.items()
                if cached_sport_id == sport_id
            ],
            espn_team,
        )

    if not team:
        # Check DB with fuzzy matching before creating a new record.
        # Use ILIKE on the first significant word to narrow candidates,
        # then apply names_match for final verification.
        _first_word = team_name.split()[0] if team_name else ""
        if len(_first_word) >= 3:
            fuzzy_result = await session.execute(
                select(Team).where(
                    Team.sport_id == sport_id,
                    Team.name.ilike(f"%{_first_word}%"),
                )
            )
            team = _sole_candidate_the_payload_names(
                team_name, list(fuzzy_result.scalars()), espn_team
            )

    if not team:
        # The probe above is the CALLER's spelling of the city, so it cannot
        # reach a canonical that spells it the other way — see
        # `_espn_name_probes`. Same acceptance test, wider candidate set.
        _probes = _espn_name_probes(
            espn_team, team_name.split()[0] if team_name else ""
        )
        if _probes:
            probe_result = await session.execute(
                select(Team).where(
                    Team.sport_id == sport_id,
                    or_(*[Team.name.ilike(f"%{p}%") for p in _probes]),
                )
            )
            team = _sole_candidate_the_payload_names(
                team_name, list(probe_result.scalars()), espn_team
            )

    if not team:
        # REFUSE THE MINT, not just the enrichment (#6215, CERT-2877). The
        # caller's `sport_id` is the EVENT's, so a wrong event-level match does
        # not merely borrow a badge — it creates the club under the wrong
        # league, and THAT is what the reader sees: `Deportivo Achuapa · EPL`
        # is `teams.sport_id`, not `abbreviation`. Clearing the badge on a row
        # minted under `soccer_epl` leaves the caption exactly as wrong.
        #
        # The payload not corresponding is the only evidence available at this
        # point that the caller's sport is not this club's, so it has to stop
        # the row from existing rather than stop it from being decorated.
        # Refusing here cannot strand an event: both call sites already write
        # the FK behind `if home_team and ...`, because this function has
        # always been able to return None.
        if not espn_identity_corresponds(team_name, None, espn_team):
            logger.warning(
                "ESPN mint refused for %r under sport_id=%s: payload names "
                "%r/%r/%r do not correspond, so this is a wrong event-level "
                "match and the club would be created under the wrong league",
                team_name,
                sport_id,
                espn_team.display_name,
                espn_team.name,
                espn_team.location,
            )
            if stats is not None:
                stats["teams_espn_mint_refused"] = (
                    stats.get("teams_espn_mint_refused", 0) + 1
                )
            return None

        team = Team(
            name=team_name,
            sport_id=sport_id,
        )
        session.add(team)
        await session.flush()  # Assign team.id for FK linking

    if team_cache is not None:
        team_cache[(team_name, sport_id)] = team

    # Update ESPN fields — but guard against overwriting correct data
    # with mismatched ESPN data (e.g., from a wrong event-level match).
    # If the team already has an espn_id that differs from this ESPN team,
    # don't apply any ESPN data — the existing ID is likely correct.
    #
    # …UNLESS THE PAYLOAD NAMES THIS CLUB OUTRIGHT (#7419). "Likely correct" was
    # an assumption with nothing behind it, and where it is wrong it is the rail
    # that SEALS the row: the stored id is the only thing consulted, so the one
    # payload that could fix it is the one this line throws away. Two clubs
    # cannot share an ESPN id, so a payload whose own club name IS this row's
    # name, arriving under a different id, is proof the stored id is the wrong
    # one. ESPN is the authority for the event graph (D27); it wins.
    #
    # ═══ MEASURED, PRODUCTION 2026-09-20 ═══
    # 555 team rows hold an `espn_id` across the eight leagues ESPN publishes a
    # team directory for. Dereferencing each row's id in that directory and
    # comparing against the row's own NAME: 538 agree, 11 hold an id the
    # directory does not list (EPL 5, MLB 2, MLS 2, NCAAF 1, NCAAB 1 — untouched
    # here, the payload never corresponds so this arm cannot reach them), 4 are
    # the accent/fragment rows whose ids are right (`CF Montreal`/`CF Montréal`,
    # `Los Angeles C`/`LA Clippers`, `Los Angeles G`/`LA Galaxy`), and **2 wear
    # another club's identity**:
    #
    #   837 `Ohio State Buckeyes`  espn_id 326 -> Texas State Bobcats
    #   839 `Wisconsin Badgers`    espn_id  87 -> Notre Dame Fighting Irish
    #
    # Both serve the other club's crest, colours, abbreviation and location on
    # their team page, and both carry ONLY the other club's `alternate_names`,
    # so search reaches them under the wrong club too. They are #6215's residue:
    # that fix measured and closed the ID-LESS cohort (1,077 rows, ~1,010
    # borrowed), and a row that already holds a foreign id was never in it.
    #
    # THE REFUSAL IS UNCHANGED FOR EVERY OTHER SHAPE. A wrong event-level match
    # hands us a payload for a club this row is not, its names do not equal this
    # row's, and we return exactly as before — that protection is the reason
    # this guard exists and it is not being traded away. What changes is only
    # that the id stops being a veto it never earned.
    if team.espn_id and team.espn_id != espn_team.espn_id:
        if not espn_payload_renames_the_stored_id(team_name, espn_team):
            # ESPN ID mismatch — skip all ESPN data updates
            if stats is not None:
                stats["teams_upserted"] = stats.get("teams_upserted", 0) + 1
            return team

        logger.warning(
            "ESPN id corrected for team %r (sport_id=%s): stored %r is another "
            "club's id, payload names this club outright as %r under %r",
            team_name,
            sport_id,
            team.espn_id,
            espn_team.display_name,
            espn_team.espn_id,
        )
        if stats is not None:
            stats["teams_espn_id_corrected"] = (
                stats.get("teams_espn_id_corrected", 0) + 1
            )
        # The aliases go with the id. They were written FROM the foreign payload
        # (the block at the bottom of this function), so unioning the correct
        # club's names into them would leave `Notre Dame` a searchable alias of
        # `Wisconsin Badgers` forever. A correction replaces; only a fill unions.
        correcting_a_foreign_id = True
    else:
        correcting_a_foreign_id = False

    # The same guard for a row that has no ESPN id to disagree with (#6215).
    # Above, the id is the witness; here there is none, so the NAMES are —
    # see `espn_identity_corresponds`. Only this arm can reach a row created
    # moments ago, which is the wrong-event-match case both arms exist for.
    if not team.espn_id and not espn_identity_corresponds(
        team_name, team.alternate_names, espn_team
    ):
        logger.warning(
            "ESPN identity refused for team %r (sport_id=%s): payload names "
            "%r/%r/%r (abbr %r, record %r) do not correspond",
            team_name,
            sport_id,
            espn_team.display_name,
            espn_team.name,
            espn_team.location,
            espn_team.abbreviation,
            espn_team.record,
        )
        if stats is not None:
            stats["teams_espn_identity_refused"] = (
                stats.get("teams_espn_identity_refused", 0) + 1
            )
            stats["teams_upserted"] = stats.get("teams_upserted", 0) + 1
        return team

    team.espn_id = espn_team.espn_id
    if espn_team.abbreviation:
        team.abbreviation = espn_team.abbreviation
    if espn_team.primary_color:
        color = espn_team.primary_color
        if not color.startswith("#"):
            color = f"#{color}"
        team.primary_color = color
    if espn_team.secondary_color:
        color = espn_team.secondary_color
        if not color.startswith("#"):
            color = f"#{color}"
        team.secondary_color = color
    if espn_team.logo_url:
        team.logo_url_small = espn_team.logo_url
        team.logo_url_large = espn_team.logo_url
    if espn_team.record:
        team.current_record = espn_team.record
    if espn_team.location:
        team.location = espn_team.location

    # Store alternate names for lookup
    alt_names = set()
    for n in [espn_team.display_name, espn_team.short_name, espn_team.nickname, espn_team.name]:
        if n and n != team_name:
            alt_names.add(n)
    # A correction REPLACES; only a fill unions. Written so that a payload
    # carrying no alias at all still clears the foreign ones — `if alt_names:`
    # alone would leave `Notre Dame` on the Badgers whenever ESPN happened to
    # send nothing to put in its place.
    existing = set() if correcting_a_foreign_id else set(team.alternate_names or [])
    if alt_names or correcting_a_foreign_id:
        team.alternate_names = list(existing | alt_names)

    if stats is not None:
        stats["teams_upserted"] = stats.get("teams_upserted", 0) + 1
    return team


# ---------------------------------------------------------------------------
# Team identity registration
# ---------------------------------------------------------------------------

async def register_espn_team_identities(
    session, home_team, away_team, ee, sport_key, identity_cache
):
    """Register ESPN team identities for home and away teams (cached)."""
    from app.services.team_identity import team_identity_service

    if home_team and ee.home_team and (home_team.id, "espn") not in identity_cache:
        await team_identity_service.register_team_identity(
            session, home_team.id, "espn", sport_key,
            source_id=str(ee.home_team.espn_id) if ee.home_team.espn_id else None,
            source_name=ee.home_team.display_name or ee.home_team.name,
        )
        identity_cache.add((home_team.id, "espn"))
    if away_team and ee.away_team and (away_team.id, "espn") not in identity_cache:
        await team_identity_service.register_team_identity(
            session, away_team.id, "espn", sport_key,
            source_id=str(ee.away_team.espn_id) if ee.away_team.espn_id else None,
            source_name=ee.away_team.display_name or ee.away_team.name,
        )
        identity_cache.add((away_team.id, "espn"))


# ---------------------------------------------------------------------------
# Event ↔ ESPN matching
# ---------------------------------------------------------------------------

def match_event_to_espn(event, espn_events, espn_by_id, claimed_espn_ids, espn_names_match):
    """Match one of our events to an ESPN scoreboard entry.

    Returns (matched_espn_event, match_method) or (None, None).
    Uses a two-signal cascade:
      1. ESPN ID (most reliable — set during scheduled sync)
      2. Name matching (all ESPN name variants), TIME-AUTHORIZED

    #2049 / C-2049-2050-REVIEW: arm 2 used to take the **first unclaimed name
    hit** with no distance comparison and no same-game check. Codex executed
    this helper on a pool ordered ``[next-day, correct-day]`` and it selected
    the next-day sibling at **24.0h** error; the row then flowed into
    ``write_espn_win_probability`` and compiled a Core update carrying the wrong
    ``espn_id``. This is the LIVE path (``espn_sync.process_sport_events``), not
    a dormant helper, so closing only ``discover_events`` closed nothing.

    Arm 1 is untouched: an id-anchored hit already carries ESPN's own identity.
    """
    from app.tasks.espn_sync import get_event_name_variations
    from app.utils.espn_candidate_selection import select_authorized_espn_candidate

    # 1. Match by ESPN ID (most reliable — set during scheduled sync)
    if event.espn_id and event.espn_id in espn_by_id:
        return espn_by_id[event.espn_id], "espn_id"

    # 2. Fall back to name matching — nearest candidate, and only if the
    #    same-game gate authorizes it. An unverifiable match stamps nothing.
    home_names, away_names = get_event_name_variations(event)
    matched, reason = select_authorized_espn_candidate(
        espn_events,
        getattr(event, "commence_time", None),
        is_name_match=lambda ee: (
            espn_names_match(home_names, ee.home_team)
            and espn_names_match(away_names, ee.away_team)
        ),
        exclude_ids=claimed_espn_ids,
        # FF1/#2058: an id we already hold is ESPN's own identity evidence.
        # Passed for the callers that need it, but note it cannot fire from
        # ``espn_sync.process_sport_events``: that caller builds ``espn_by_id``
        # from this same pool (so arm 1 short-circuits) AND pre-seeds every held
        # id into ``claimed_espn_ids`` (so the row is excluded anyway). The live
        # path therefore always runs on the TIGHT, uncorroborated bound, which
        # is the conservative outcome and is intended.
        anchor_espn_id=getattr(event, "espn_id", None),
    )
    if matched is not None:
        return matched, "name"
    if reason not in ("no-name-match",):
        # gotcha #53: "nothing matched" and "matched but refused" are different
        # facts. Log the refusal so a suppressed stamp is visible, not silent.
        logger.info(
            "ESPN name match REFUSED for event %s (%s vs %s): %s",
            getattr(event, "id", "?"),
            getattr(event, "away_team_name", "?"),
            getattr(event, "home_team_name", "?"),
            reason,
        )

    # 3. Commence_time proximity fallback REMOVED
    # Previously matched by time proximity when exactly 1 ESPN
    # candidate was within 6 hours. This caused logo contamination
    # for college sports — a single-candidate time match assigned
    # wrong team data. Name matching (step 2) is sufficient.

    return None, None


# ---------------------------------------------------------------------------
# Orientation — which of OUR sides is ESPN's `home` competitor standing on?
# ---------------------------------------------------------------------------

ESPN_ORIENTATION_ALIGNED = "aligned"
ESPN_ORIENTATION_SWAPPED = "swapped"
ESPN_ORIENTATION_UNRESOLVED = "unresolved"


def espn_row_name_variations(event) -> tuple[list[str], list[str]]:
    """Every name our row offers for each side, read defensively.

    Deliberately a mirror of ``espn_sync.get_event_name_variations`` rather than
    a call to it, for two reasons. It is read here on the LIVE write path, where
    a row that cannot be read must degrade to "I cannot tell" rather than raise:
    that helper reaches straight through ``event.home_team_normalized``, so any
    caller holding a partial row — every test stand-in in this suite, and any
    future reduced projection — would take an ``AttributeError`` inside a
    writer whose failure mode should be silence. And it keeps a leaf-ish helper
    out of a function-local import of ``app.tasks.espn_sync``.

    ``test_the_two_name_readers_agree_on_a_real_event_7338`` pins the two
    against a real ``Event`` in both directions, so the mirror cannot drift.
    """
    home_names = [
        n for n in (
            getattr(event, "home_team_name", None),
            getattr(event, "home_team_normalized", None),
        ) if n
    ]
    away_names = [
        n for n in (
            getattr(event, "away_team_name", None),
            getattr(event, "away_team_normalized", None),
        ) if n
    ]
    home_names.extend(n for n in (getattr(event, "home_team_alt_names", None) or []) if n)
    away_names.extend(n for n in (getattr(event, "away_team_alt_names", None) or []) if n)
    return home_names, away_names


def espn_orientation_verdict(event, ee) -> str:
    """Does ESPN's ``homeAway="home"`` competitor sit on OUR home side?

    🔴 **AN ESPN ID PROVES THE SAME GAME, NEVER THE SAME ORIENTATION (#7338).**
    ``match_event_to_espn`` arm 2 compares home-to-home AND away-to-away, so a
    name-matched row is oriented by construction. **Arm 1 compares nothing** —
    its docstring says "an id-anchored hit already carries ESPN's own identity",
    which is true of the *fixture* and false of the *sides*. Everything
    downstream then copies by ESPN's slot (``home_score=ee.home_score``), so
    when the two disagree every score and the ESPN probability leg land on the
    wrong team, silently.

    **A neutral-site game is where they disagree**, because there is no true
    home side for the two providers to agree about: whoever minted our row (the
    Odds API, here) is free to nominate the opposite side to ESPN. Measured on
    production 2026-09-19 over today's NCAAF, 70 rows whose ``espn_id`` ESPN
    also serves: 62 aligned, 7 unjudgeable on spelling, **1 swapped — and that
    one is the only judgeable neutral-site game in the window** (0 of 61
    non-neutral rows are swapped). Event 15308929 printed *Virginia 28 · West
    Virginia 21* on Discover page one while West Virginia was winning 28–21, and
    handed the team it showed losing a 58% chance on the same card. Bowl games,
    neutral-site openers, NFL international games and cup finals at a neutral
    ground are the population.

    Identity, not slot, is the question, so this asks
    :func:`espn_identity_corresponds` — the file's own primitive, which carries
    the cross-town-rival veto that makes ``names_match`` alone unsafe for
    deciding an identity (CERT-2881: it calls Manchester United/Manchester City
    a match).

    **BOTH DIRECTIONS ARE TESTED AND AMBIGUITY IS NOT A VERDICT.** A payload
    that corresponds to our home on *both* of its competitors has told us
    nothing, and a row we cannot read at all is not evidence of a swap. Both
    return ``UNRESOLVED``, which leaves the write exactly as it is today — this
    function only ever moves a row it can positively show is reversed.
    """
    # `getattr` throughout, never attribute access: a board row carrying no
    # competitor objects cannot be shown to be reversed, and neither can a row
    # that does not expose its own naming surface. Both are UNRESOLVED, which
    # changes nothing — this function is only ever allowed to move a row it can
    # positively read.
    espn_home = getattr(ee, "home_team", None)
    espn_away = getattr(ee, "away_team", None)
    if espn_home is None or espn_away is None:
        return ESPN_ORIENTATION_UNRESOLVED

    home_names, away_names = espn_row_name_variations(event)
    if not home_names or not away_names:
        return ESPN_ORIENTATION_UNRESOLVED

    def _corresponds(ours, espn_team) -> bool:
        return espn_identity_corresponds(ours[0], ours[1:], espn_team)

    aligned = (
        _corresponds(home_names, espn_home)
        and _corresponds(away_names, espn_away)
    )
    swapped = (
        _corresponds(home_names, espn_away)
        and _corresponds(away_names, espn_home)
    )

    if aligned and not swapped:
        return ESPN_ORIENTATION_ALIGNED
    if swapped and not aligned:
        return ESPN_ORIENTATION_SWAPPED
    return ESPN_ORIENTATION_UNRESOLVED


def orient_espn_event_to_row(event, ee, stats=None):
    """Return ``ee`` re-oriented onto THIS row's sides, or ``ee`` unchanged.

    Called at the top of every function that copies ESPN's home/away values
    onto our row, so the ~15 individual ``ee.home_score`` reads below each of
    them become correct together. Patching the copy sites one at a time is how
    a sibling site spelling the same concept differently survives the fix.

    The swap is total and the probability is complemented with it: a leg stored
    as "ESPN says the home team wins with p" is, on the other side, ``1 - p``.
    Leaving ``home_win_probability`` alone while moving the teams would replace
    a swapped blend with an inverted one.

    ``stats`` is passed ONLY by :func:`update_event_fields_from_espn`, which
    runs first and unconditionally for every event on the live path, so a
    corrected game is counted once per poll rather than once per write site.
    Counting is bookkeeping: the correction does not depend on it.
    """
    verdict = espn_orientation_verdict(event, ee)

    if stats is not None and verdict != ESPN_ORIENTATION_ALIGNED:
        _key = f"espn_orientation_{verdict}"
        stats[_key] = stats.get(_key, 0) + 1

    if verdict != ESPN_ORIENTATION_SWAPPED:
        # UNRESOLVED deliberately writes what it writes today. Refusing here
        # would stop live scores for every row whose names we merely cannot
        # read, which is a far larger population than the one being repaired —
        # so the silence ends with a counter first, and the counter is what a
        # later refusal gets to be argued from.
        return ee

    logger.warning(
        "ESPN orientation SWAPPED for event %s (%s @ %s): ESPN's home is %s "
        "(#7338). Re-orienting scores and the ESPN probability leg onto our "
        "sides rather than writing them by ESPN's slot.",
        getattr(event, "id", "?"),
        getattr(event, "away_team_name", "?"),
        getattr(event, "home_team_name", "?"),
        getattr(ee.home_team, "display_name", None) or getattr(ee.home_team, "name", "?"),
    )

    return _dataclasses.replace(
        ee,
        home_team=ee.away_team,
        away_team=ee.home_team,
        home_score=ee.away_score,
        away_score=ee.home_score,
        home_win_probability=(
            1.0 - ee.home_win_probability
            if ee.home_win_probability is not None
            else None
        ),
    )


# ---------------------------------------------------------------------------
# Live event field updates
# ---------------------------------------------------------------------------

async def update_event_fields_from_espn(session, event, ee, claimed_espn_ids, stats):
    """Update clock, scores, broadcast, importance, and commence_time from ESPN.

    Returns True if any field changed.
    """
    from app.models.models import Event

    # #7338, BEFORE the first read of `ee`: an id-anchored match proves the
    # fixture, not which side is which. Everything below copies by ESPN's slot.
    ee = orient_espn_event_to_row(event, ee, stats)

    changed = False

    # Correct commence_time from ESPN if significantly different
    # The Odds API occasionally returns local times as UTC
    # Skip if StatPal set the commence_time (more reliable source)
    if ee.date and event.commence_time:
        time_diff = abs((ee.date - event.commence_time).total_seconds())
        # #190 guard: never move commence_time to AFTER an already-recorded
        # completed_at — that inverts the invariant (a game finishing before it
        # starts) and is a signal this ESPN game belongs to a different sibling.
        _would_invert = commence_correction_inverts_completion(
            ee.date, getattr(event, "completed_at", None)
        )
        if _would_invert:
            logger.warning(
                "ESPN fold guard: refused commence_time correction on event %d "
                "(%s vs %s) — new commence %s is after completed_at %s (#190/gotcha #32)",
                event.id, event.home_team_name, event.away_team_name,
                ee.date.isoformat(), event.completed_at.isoformat(),
            )
        if time_diff > 300 and getattr(event, 'commence_time_source', None) != "statpal" \
                and not _would_invert:
            logger.info(
                f"ESPN: Correcting commence_time for event {event.id} "
                f"({event.home_team_name} vs {event.away_team_name}): "
                f"{event.commence_time.isoformat()} -> {ee.date.isoformat()} "
                f"(diff: {time_diff/3600:.1f}h)"
            )
            event.commence_time = ee.date
            event.commence_time_source = "espn"
            changed = True

    # ── #6056: is this fetch OLDER, in game time, than the row already is? ────
    #
    # ESPN is one of at least two unarbitrated writers on `game_clock`,
    # `period`, `home_score` and `away_score` (`statpal_sync` is the other), and
    # neither checks whether the state it is about to overwrite came from a
    # LATER moment of the same game. On 2026-09-14 that served a reader a
    # disappearing touchdown and a clock running backwards; the evidence and the
    # reasoning are in `live_write_would_revert`'s module note.
    #
    # Computed ONCE, here, from the row as it stands BEFORE any of the four
    # assignments below — reading it again between them would compare the fetch
    # against a row it had itself half-updated, which is how a guard silently
    # stops guarding.
    #
    # It gates exactly the four live-state fields. `commence_time` above, the
    # broadcast/importance fields and the settle transition below are all
    # deliberately outside it: none of them is positioned in game time, and a
    # stale-looking clock must never be allowed to block a game from ending.
    # The position the decision is taken on, read once and held so the
    # compare-and-write at the end of the block can re-assert it in the database
    # (#6056 / CERT-2829).
    _observed_period = getattr(event, "period", None)
    _observed_clock = getattr(event, "game_clock", None)
    # #6251: read BESIDE the position and on the same terms, because the guard's
    # tie-break consults them and the compare-and-write re-asserts them. Read
    # once, here, before the four live-state values are composed — a score read
    # again at write time would be the row this same call had half-updated.
    _observed_home_score = getattr(event, "home_score", None)
    _observed_away_score = getattr(event, "away_score", None)
    # Collected here and written as ONE conditional statement below; never
    # assigned onto the ORM row. See the compare-and-write note.
    _live_values: dict = {}

    _new_period = _sanitize_period(ee.status_detail)
    _live_state_is_stale = live_write_would_revert(
        _observed_period,
        _observed_clock,
        _new_period,
        ee.clock,
        # #6251. On a clocked sport these rarely change the verdict — two ESPN
        # fetches at the same clock to the second are uncommon — but ESPN is a
        # writer on MLB rows too, where the position ties for a whole
        # half-inning and this is the only discriminator there is.
        stored_home_score=_observed_home_score,
        stored_away_score=_observed_away_score,
        incoming_home_score=ee.home_score,
        incoming_away_score=ee.away_score,
        # #6251 SECOND PASS: this is the AUTHORITY feed, so the span tie-break
        # does not apply to it — a feed cannot lag behind itself, and refusing
        # ESPN's correction of its own phantom run is what kept one on the page
        # for nine minutes instead of three (specimen 15312655; the measurement
        # and its controls are in `_authority_is_correcting_itself`).
        #
        # ONLY THE TIE-BREAK IS EXEMPTED. An ESPN fetch from a strictly earlier
        # inning is still refused by the rule above it, which is the case that
        # is provably a reversion. And this flag is not a general "ESPN wins":
        # StatPal and the odds feed keep the tie-break in full, because they are
        # the lagging writers the 221-reversion population was actually made of.
        incoming_is_authority=True,
    )
    if _live_state_is_stale:
        logger.info(
            "#6056: refused a reverting live write on event %s — row is at "
            "%r/%r, ESPN offered %r/%r (%s-%s)",
            event.id, _observed_period, _observed_clock, _new_period, ee.clock,
            ee.home_score, ee.away_score,
        )
        stats["live_state_reversions_refused"] = (
            stats.get("live_state_reversions_refused", 0) + 1
        )

    # Update game clock
    if ee.clock and event.game_clock != ee.clock and not _live_state_is_stale:
        _live_values["game_clock"] = ee.clock

    # Update period.
    #
    # #5390 (#5012 layer 2): ESPN keeps its PRE-GAME status detail — "Thu,
    # September 10th at 8:35 PM EDT", or the short "5/23 - TBD" — in
    # status_detail until its first in-game update lands, which is a window of
    # a few minutes on every kickoff. A raw copy therefore stores a DATE in a
    # column that the pace estimator, the served `game_period` and the
    # Discover badge all read as a period; "September 10th" parsed as period
    # 10 and badged a 0-0 NFL game "Overtime".
    #
    # Two rules, and the second is why this is not a one-line sanitize:
    #   - refuse the date, never store it;
    #   - never blank a real period. ESPN is not the only writer here
    #     (mlb_sync and statpal_sync write this column too) and it is the
    #     slowest, so it routinely still says "pre-game" while MLB already
    #     says "Top 1st". Overwriting that with None would trade one wrong
    #     answer for a missing one.
    # A date already stored is cleared rather than frozen, so the column
    # self-heals on the next sync and needs no migration.
    # `_new_period` is computed above, with the staleness check that reads it.
    if _new_period:
        if event.period != _new_period and not _live_state_is_stale:
            _live_values["period"] = _new_period
    elif ee.status_detail and event.period is not None and _sanitize_period(event.period) is None:
        # Both sides are the same class of garbage — drop ours.
        #
        # This clear rides the compare-and-write with the rest of the block
        # rather than going round it, and that is deliberate twice over. It has
        # to, mechanically: an ORM assignment to `period` here would be flushed
        # ahead of the statement below and make its predicate compare the row
        # against a value this same call had just written, which is a guard that
        # has stopped guarding. And it is also right on the merits — if the
        # predicate fails, another writer has just put a REAL period on the row,
        # so the garbage this branch exists to clear is already gone.
        _live_values["period"] = None

    # Update scores + capture ScoreSnapshot for score differential chart
    score_changed = False
    if (
        ee.home_score is not None
        and event.home_score != ee.home_score
        and not _live_state_is_stale
    ):
        _live_values["home_score"] = ee.home_score
        score_changed = True
    if (
        ee.away_score is not None
        and event.away_score != ee.away_score
        and not _live_state_is_stale
    ):
        _live_values["away_score"] = ee.away_score
        score_changed = True

    # ── #6056 / CERT-2829: THE FOUR LIVE-STATE WRITES LAND AS ONE ACT ────────
    #
    # ESPN runs on the REALTIME queue at concurrency 4 beside the 30-second
    # StatPal livescore writer, and the hourly schedule pass writes the same
    # four columns from BACKGROUND. Everything above read the row without a lock
    # and decided; nothing above has reached Postgres, and this helper is called
    # inside a caller-owned transaction that commits well after it returns. An
    # ORM assignment would therefore let a decision taken on a current row land
    # on top of a newer one committed by another queue in between — the reader
    # sees the touchdown leave the page, with the sequential guard reporting
    # nothing because it was right about the row it was shown.
    #
    # Re-asserting the observed position in the UPDATE's own WHERE makes the
    # comparison and the write one act; `utils/live_state_write` carries the
    # reasoning for why that is true under READ COMMITTED and not just a
    # narrower window.
    _live_write_landed = await write_live_state_if_unmoved(
        session, event, _live_values,
        observed_period=_observed_period,
        observed_clock=_observed_clock,
        observed_home_score=_observed_home_score,
        observed_away_score=_observed_away_score,
        what="ESPN live state",
    )
    if _live_values:
        if _live_write_landed:
            changed = True
        else:
            stats["live_state_write_lost_race"] = (
                stats.get("live_state_write_lost_race", 0) + 1
            )

    # Gated on the write having LANDED. A snapshot is a claim that the game
    # stood at this score at this moment; writing one for a score the
    # compare-and-write just refused would put the overtaken observation into
    # the Score Differential chart — the table this whole defect was diagnosed
    # from — after successfully keeping it off the row.
    if (
        score_changed
        and _live_write_landed
        and ee.home_score is not None
        and ee.away_score is not None
    ):
        from app.models.models import ScoreSnapshot
        session.add(ScoreSnapshot(
            event_id=event.id,
            home_score=ee.home_score,
            away_score=ee.away_score,
        ))

    # Update broadcast info
    if ee.broadcasts:
        broadcast_str = ", ".join(ee.broadcasts[:3])
        if event.broadcast_info != broadcast_str:
            event.broadcast_info = broadcast_str
            changed = True

    # Update importance from ESPN season type
    # (more reliable than LLM text classification)
    if ee.season_type is not None:
        espn_importance = {1: "exhibition", 2: "regular_season", 3: "playoff"}.get(ee.season_type)
        if espn_importance and event.llm_importance != espn_importance:
            # Don't downgrade "championship" to "playoff" —
            # LLM text match is more specific
            if not (event.llm_importance == "championship" and espn_importance == "playoff"):
                event.llm_importance = espn_importance
                changed = True

    # Transition status when ESPN reports the game is over.
    # This is the PRIMARY mechanism for live → completed transitions;
    # the transition_event_statuses Celery task is only a fallback.
    # BR76: without this, events stayed "live" for hours because
    # find_or_create_event ignores identity.status for existing events,
    # and no other code path updated event.status from ESPN data.
    #
    # live/048: it is now the ONLY mechanism, not the primary one. The fallback
    # stopped being allowed to end a match (EVENT-GRAPH-DOCTRINE §R — silence is
    # below the lowest rung of the state ladder), so this branch also has to
    # reach the state the fallback leaves behind. `authority_may_settle` admits
    # `live` and `suspended` and refuses a row already settled; a match that
    # went quiet, was suspended, and is then reported `post` settles here in one
    # hop, which is exactly the path the six US Open rows in CERT-752 needed.
    if ee.status in ("post", "final") and authority_may_settle(event.status):
        _completed_at = event.completed_at or datetime.now(timezone.utc)
        # #190 guard: don't stamp a completion that predates the event's own
        # commence_time (the earlier-game-folded-onto-later-sibling class). A
        # genuinely live event has a past commence_time, so this only trips when
        # the fold put ESPN's finished game onto the wrong (future) event.
        if completion_stamp_inverts_commence(event.commence_time, _completed_at):
            logger.warning(
                "ESPN fold guard: refused completed stamp on event %d (%s vs %s) — "
                "completed_at %s precedes commence_time %s (#190/gotcha #32)",
                event.id, event.home_team_name, event.away_team_name,
                _completed_at.isoformat(), event.commence_time.isoformat(),
            )
            stats["espn_fold_guard_skipped"] = stats.get("espn_fold_guard_skipped", 0) + 1
        else:
            await session.execute(
                _sql_update(Event)
                .where(Event.id == event.id)
                .values(
                    status="completed",
                    completed_at=_completed_at,
                )
            )
            event.status = "completed"
            changed = True
            stats["espn_completed"] = stats.get("espn_completed", 0) + 1
    elif getattr(ee, "stopped_without_result", False) and event.status == "live":
        # #3397: the branch the settle arm above leaves open. ESPN reports
        # `state="post"` with `completed` not True — postponed, abandoned,
        # canceled — which is the authority saying BOTH "this is not being
        # played" and "nobody finished it". The arm above correctly refuses to
        # settle it; without this one nothing else touches the column, so the
        # row keeps whatever it had, and what it had was `live`.
        #
        # MEASURED (production 2026-09-05, #3397): event 15291065, D.C. United
        # @ FC Cincinnati, `status='live'` / `period='Postponed'` / 0-0 / zero
        # espn_snapshots — a match that never kicked off, drawn on the MLS
        # league page inside `Live Now 3` with a green dot and a `Postponed 0'`
        # chip, and counted in the native tab bar's `13 live` badge. The other
        # two rows in that rail were genuinely live and read correctly, so the
        # rail was right about two of its three members.
        #
        # SUSPENDED, NOT CLOSED, AND THIS IS THE CERT-752 RULE (live/048,
        # EVENT-GRAPH-DOCTRINE §R). A stoppage is not a result: writing
        # `completed`/`closed` here would stamp a Final and resolve the
        # prediction-market blend off a 0-0 nobody played, which is precisely
        # the trade CERT-752 was filed about — a false LIVE swapped for a false
        # FINAL, and only one of the two grades. `EVENT_SUSPENDED` is the state
        # the ladder already keeps for "not live, and nobody reported an end":
        # it rides a past rail rather than `Live Now`, it leaves the live count,
        # and it grades nothing.
        #
        # SELF-HEALING, so a resumed match needs no second mechanism.
        # `play_resumes` admits `suspended`, so the moment ESPN reports the
        # fixture `in` again the branch below flips it straight back to live —
        # the same door the six suspended US Open matches came back through.
        # And because the scheduled→live promotion in `transition_event_statuses`
        # selects only `status == "scheduled"`, a suspended row is never
        # clock-promoted back into the rail behind ESPN's back.
        from app.utils.event_completion import EVENT_SUSPENDED
        await session.execute(
            _sql_update(Event)
            .where(Event.id == event.id)
            .values(status=EVENT_SUSPENDED)
        )
        event.status = EVENT_SUSPENDED
        changed = True
        stats["espn_stopped_without_result"] = stats.get("espn_stopped_without_result", 0) + 1
        logger.info(
            "ESPN stoppage: event %d (%s vs %s) was live but ESPN reports "
            "state=post/completed=false (%s) — demoted to %s, not settled (#3397)",
            event.id, event.home_team_name, event.away_team_name,
            ee.status_detail, EVENT_SUSPENDED,
        )
    elif ee.status == "in" and play_resumes(event.status):
        # #1207 premature-live guard: ESPN can report a game "in" (and publish a
        # pregame win-prob) hours before first pitch. Don't flip the event live
        # until its own commence_time has actually arrived (commence correction
        # above already re-aligned commence_time to ESPN's date when they diverge).
        #
        # live/048: `play_resumes` widens this from `scheduled` to also admit
        # `suspended` — the authority reporting a match in progress is the
        # strongest possible answer to "did play resume?", and a suspended row is
        # by construction one that carries no completion, so nothing has to be
        # revoked to let it back. A row the authority ALREADY settled is a bigger
        # claim and stays with `espn_replay_unsettles` below, which clears
        # `completed_at` in the same write (#1201).
        _now = datetime.now(timezone.utc)
        if espn_live_write_is_premature(event.commence_time, _now):
            logger.warning(
                "ESPN premature-live guard: refused live status on event %d (%s vs %s) "
                "— commence_time %s is still beyond the %s grace (now %s) (#1207)",
                event.id, event.home_team_name, event.away_team_name,
                event.commence_time.isoformat() if event.commence_time else None,
                _PREGAME_LIVE_GRACE, _now.isoformat(),
            )
            stats["espn_premature_live_skipped"] = stats.get("espn_premature_live_skipped", 0) + 1
        else:
            await session.execute(
                _sql_update(Event)
                .where(Event.id == event.id)
                .values(status="live")
            )
            event.status = "live"
            changed = True
    elif espn_replay_unsettles(event.status, ee.status):
        # #1201 un-settle-on-replay: ESPN (the authoritative live source) reports
        # this game is IN PROGRESS, but we have it settled. That means a premature
        # settle — a postponed game that got closed by the staleness net and was
        # then rescheduled/replayed, OR a wrong-sibling fold (gotcha #32) whose
        # settled state was never real. Either way the settled state is now
        # definitively wrong: revert to live and CLEAR completed_at so a leftover
        # inverted stamp (completed_at < commence_time) can't persist. Idempotent —
        # once ESPN reports the replay as post/final again, the live→completed
        # branch above re-settles it with a correct completed_at.
        _prev_status = event.status
        await session.execute(
            _sql_update(Event)
            .where(Event.id == event.id)
            .values(status="live", completed_at=None)
        )
        event.status = "live"
        event.completed_at = None
        changed = True
        stats["espn_unsettled_on_replay"] = stats.get("espn_unsettled_on_replay", 0) + 1
        logger.warning(
            "un-settle-on-replay: event %d (%s vs %s) was %s but ESPN reports LIVE "
            "— reverted to live and cleared completed_at (#1201/gotcha #32)",
            event.id, event.home_team_name, event.away_team_name, _prev_status,
        )

    return changed


# ---------------------------------------------------------------------------
# ESPN win probability + snapshot writing
# ---------------------------------------------------------------------------

async def write_espn_win_probability(session, event, ee, match_method, claimed_espn_ids, stats):
    """Write ESPN win probability to event and create ESPN + win_prob snapshots.

    Returns True if any change was made.
    """
    from app.models.models import Event, ESPNSnapshot

    # #7338, before the probability is read: on a swapped row ESPN's
    # `homeWinPercentage` is our AWAY team's chance. Stamping it as the home leg
    # points the blend's ESPN source at the opposite team from its venue legs.
    ee = orient_espn_event_to_row(event, ee)

    if ee.home_win_probability is None:
        return False

    # #1207 premature-live guard: ESPN publishes a pregame win-probability hours
    # before first pitch. Don't store it (or the derived snapshot) until the game
    # has actually started — a genuinely live/completed event has a past
    # commence_time, so this only trips on the not-yet-started case.
    _now = datetime.now(timezone.utc)
    if espn_live_write_is_premature(event.commence_time, _now):
        stats["espn_premature_winprob_skipped"] = stats.get("espn_premature_winprob_skipped", 0) + 1
        return False

    # #922: our own resolved status is the authoritative "game is over" signal
    # (more reliable than ESPN's ee.status, which can lag 20-40 min on MLB). When
    # the event is completed/closed we capture the terminal win-prob point once
    # and stop appending new time-series points on post-final re-process cycles
    # (the appends were the chart "stale tail"). Score/metadata updates still flow.
    is_completed = getattr(event, "status", None) in ("completed", "closed")

    # Write espn_win_prob_home, win_probability_sources, AND espn_id
    # in one atomic Core update. espn_id was previously set via ORM
    # attribute assignment which could fail to flush when mixed with
    # Core updates on the same row.
    # #1829: value + write time, so the hero can age this reading against the
    # other sources on the event instead of trusting it forever.
    from app.utils.aggregation import stamp_source_reading
    _wps = stamp_source_reading(
        event.win_probability_sources, "espn", round(ee.home_win_probability, 4)
    )
    _update_vals: dict = {
        "win_probability_sources": _wps,
        "espn_win_prob_home": ee.home_win_probability,
    }
    # #2049 defence in depth: the caller is supposed to have selected through
    # the authorization gate, but codex demonstrated the manufacture by passing
    # a hand-picked 24.0h sibling STRAIGHT into this writer. A writer that will
    # compile any id it is handed is a manufacturer regardless of who calls it,
    # so the gate runs again at the point of the write.
    #
    # FF1/#2058: this check has NO pool, so it can never see a rejected sibling
    # — it is therefore the uncorroborated arm by construction, which is what
    # makes it real defence rather than a copy of the selector's arithmetic. The
    # one thing it can corroborate is an id-anchored match: ``match_method ==
    # "espn_id"`` means ESPN's own id already tied this row to this event, so
    # the clock is not what is being trusted.
    from app.utils.espn_candidate_selection import authorize_espn_pair
    _id_authorized, _id_reason = authorize_espn_pair(
        getattr(ee, "date", None),
        getattr(event, "commence_time", None),
        corroboration=("provider-anchor" if match_method == "espn_id" else None),
    )
    # #2693 CERT-784: THE HOLDER CHECK, which the authorization above does not
    # perform. `authorize_espn_pair` answers "is this row and this ESPN event
    # the same game"; it says nothing about whether a DIFFERENT row is already
    # wearing the id. Both questions have to be answered before a stamp, or the
    # step-2 repair is undone by the next live sync.
    #
    # Core `update()` here rather than `stamp_espn_id_if_unheld`, because this
    # writer builds a payload for a single Core UPDATE (gotcha #4) instead of
    # assigning to the ORM object. The check is the helper's `espn_id_holder`,
    # imported rather than re-implemented.
    # Written ONCE and held in a name: the same three-term predicate spelled out
    # twice is a guard that half-survives the next edit.
    _wants_stamp = bool(ee.espn_id) and ee.espn_id not in claimed_espn_ids
    if _wants_stamp and _id_authorized:
        _held_by = await espn_id_holder(
            session, ee.espn_id, exclude_event_id=getattr(event, "id", None)
        )
        if _held_by is None:
            _update_vals["espn_id"] = ee.espn_id
            claimed_espn_ids.add(ee.espn_id)
        else:
            logger.warning(
                "ESPN id stamp REFUSED at write for event %s -> %s: event %s "
                "already holds it (#2017/#2693). The row keeps its NULL rather "
                "than a contradicted id.",
                getattr(event, "id", "?"), ee.espn_id, _held_by,
            )
    elif ee.espn_id and not _id_authorized:
        logger.warning(
            "ESPN id stamp REFUSED at write for event %s -> %s: %s",
            getattr(event, "id", "?"), ee.espn_id, _id_reason,
        )
    await session.execute(
        _sql_update(Event)
        .where(Event.id == event.id)
        .values(**_update_vals)
    )
    event.win_probability_sources = _wps

    # #922: skip the ESPNSnapshot append for completed/closed events — it is a
    # plain append (no dedup) and post-final cycles would stamp new espnHistory
    # points at `now`, extending the chart past the real final. The live-captured
    # ESPNSnapshots already cover the game through its end.
    if not is_completed:
        snapshot = ESPNSnapshot(
            event_id=event.id,
            home_win_probability=ee.home_win_probability,
            away_win_probability=1.0 - ee.home_win_probability if ee.home_win_probability else None,
            home_score=ee.home_score,
            away_score=ee.away_score,
            game_clock=ee.clock,
            # #5390: a snapshot's period is served back out (events.py `snap.period`),
            # so a pre-game date is as wrong here as it is on the event row.
            period=_sanitize_period(ee.status_detail),
        )
        session.add(snapshot)
        stats["snapshots_created"] = stats.get("snapshots_created", 0) + 1

    # Write ESPN to win_prob_snapshots only for espn_id matches.
    # Name-based matches can be false positives (especially
    # college sports), contaminating the probability time-series.
    if match_method == "espn_id":
        try:
            from app.tasks.snapshots import _create_or_update_win_prob_snapshot
            espn_wp_snap, is_new = await _create_or_update_win_prob_snapshot(
                session,
                event_id=event.id,
                source="espn",
                home_win_probability=ee.home_win_probability,
                away_win_probability=1.0 - ee.home_win_probability if ee.home_win_probability else None,
                game_state={
                    "clock": ee.clock,
                    "period": _sanitize_period(ee.status_detail) or (str(ee.period) if ee.period else None),
                    "home_score": ee.home_score,
                    "away_score": ee.away_score,
                },
                is_completed=is_completed,
            )
            if is_new:
                session.add(espn_wp_snap)
        except Exception:
            pass  # Table may not exist yet

    return True


# ---------------------------------------------------------------------------
# Statistical model win probability
# ---------------------------------------------------------------------------

async def compute_and_write_stat_model(session, event, ee, sport_key, stats):
    """Compute statistical model win probability for live games and write snapshot.

    Only runs for espn_id matches with active game progress.
    Returns True if stat_model was computed and written.
    """
    from app.models.models import Event

    # #7338: the model is fed `home_score`/`away_score` and returns a HOME win
    # probability, so a swapped feed inverts it one step downstream — the
    # specimen read `stat_model` 0.0762 for a team up 7 in the 4th.
    ee = orient_espn_event_to_row(event, ee)

    has_game_progress = ee.clock or sport_key.startswith("baseball_")
    if ee.status != "in" or ee.home_score is None or ee.away_score is None or not has_game_progress:
        # Track missing data for live games
        if ee.status == "in":
            if ee.home_score is None or ee.away_score is None:
                stats["stat_model_no_score"] = stats.get("stat_model_no_score", 0) + 1
            elif not ee.clock:
                stats["stat_model_no_clock"] = stats.get("stat_model_no_clock", 0) + 1
        return False

    try:
        from app.utils.win_probability import compute_statistical_win_prob

        # Use opening spread if available
        pregame_spread = None
        if event.opening_home_spread is not None:
            pregame_spread = float(event.opening_home_spread)

        # Pass opening probability as prior so the model
        # doesn't start at 50% when no spread is available.
        opening_prob = None
        if event.opening_home_probability is not None:
            opening_prob = float(event.opening_home_probability)

        # Prefer numeric period for reliability
        period_str = _sanitize_period(ee.status_detail)
        if ee.period and not period_str:
            period_str = str(ee.period)

        stat_wp = compute_statistical_win_prob(
            home_score=ee.home_score,
            away_score=ee.away_score,
            clock=ee.clock,
            period=period_str,
            sport_key=sport_key,
            pregame_spread=pregame_spread,
            opening_home_probability=opening_prob,
        )
        if stat_wp is not None:
            # #1829: `stat_model` has TWO writers — this one and
            # odds_polling.py's. Both stamp, or the source's age depends on
            # which task happened to write last.
            from app.utils.aggregation import stamp_source_reading as _stamp2
            _wps2 = _stamp2(
                event.win_probability_sources, "stat_model", round(stat_wp, 4)
            )
            await session.execute(
                _sql_update(Event)
                .where(Event.id == event.id)
                .values(win_probability_sources=_wps2)
            )
            event.win_probability_sources = _wps2

            from app.tasks.snapshots import _create_or_update_win_prob_snapshot
            # #922: if OUR event is already completed/closed (ESPN can lag and
            # keep reporting MLB as "in" for 20-40 min post-final), capture the
            # terminal stat_model point once and stop appending drift points —
            # those post-final stat_model re-stamps were the MLB chart stale tail.
            is_completed = getattr(event, "status", None) in ("completed", "closed")
            stat_snap, is_new = await _create_or_update_win_prob_snapshot(
                session,
                event_id=event.id,
                source="stat_model",
                home_win_probability=round(stat_wp, 4),
                away_win_probability=round(1.0 - stat_wp, 4),
                game_state={
                    "clock": ee.clock,
                    "period": period_str,
                    "home_score": ee.home_score,
                    "away_score": ee.away_score,
                    "pregame_spread": pregame_spread,
                    "time_source": "espn",
                },
                is_completed=is_completed,
            )
            if is_new:
                session.add(stat_snap)
            stats["stat_model_computed"] = stats.get("stat_model_computed", 0) + 1
            return True
        else:
            logger.warning(
                f"stat_model returned None for event {event.id} "
                f"(sport={sport_key}, clock={ee.clock!r}, period={ee.status_detail!r}, "
                f"score={ee.home_score}-{ee.away_score})"
            )
    except Exception as e:
        logger.error(f"stat_model error for event {event.id}: {e}")

    return False


# ---------------------------------------------------------------------------
# Create events from unmatched ESPN games
# ---------------------------------------------------------------------------

async def create_events_from_unmatched_espn(session, our_events, espn_events, sport_key, stats):
    """Create Event records for ESPN games that don't match any of our events.

    ESPN is a first-class source. If ESPN has a game and we don't, create it.
    Other sources (Odds API, StatPal) will find it later via the Event Registry.
    """
    from app.models.models import Event, ESPNSnapshot

    matched_espn_ids = set()
    for event in our_events:
        if event.espn_id:
            matched_espn_ids.add(event.espn_id)

    from app.services.event_registry import (
        find_or_create_event as _foc,
        EventIdentity as _EI,
        EventClaim as _EC,
    )
    for ee in espn_events:
        if not ee.espn_id or ee.espn_id in matched_espn_ids:
            continue
        if not ee.home_team or not ee.away_team:
            continue
        espn_home = ee.home_team.display_name or ee.home_team.name or ""
        espn_away = ee.away_team.display_name or ee.away_team.name or ""
        if not espn_home or not espn_away:
            continue

        try:
            # #1207 premature-live guard: don't birth an event as ``live`` when ESPN
            # reports it "in" but its commence_time (ee.date) is still beyond the
            # grace — that pregame "in" leak is the exact source of a game showing
            # live hours before first pitch. Fall back to ``scheduled``.
            _now = datetime.now(timezone.utc)
            _espn_premature = ee.status == "in" and espn_live_write_is_premature(ee.date, _now)
            if _espn_premature:
                stats["espn_premature_live_skipped"] = stats.get("espn_premature_live_skipped", 0) + 1
            _create_status = (
                "live" if (ee.status == "in" and not _espn_premature) else (
                    "completed" if ee.status in ("post", "final") else "scheduled"
                )
            )
            identity = _EI(
                sport_key=sport_key,
                home_team_name=espn_home,
                away_team_name=espn_away,
                commence_time=ee.date,
                # Ruling 048 arm B — THE canonical legitimate cross-source join.
                # espn_home/espn_away/ee.date are read straight off the ESPN
                # scoreboard entry that ee.espn_id names, so this claim's teams and
                # date carry that id's authority even though the candidate row
                # (created by Odds API) does not hold the espn_id yet. This is the
                # join 048 explicitly preserves; if it ever stops joining, the
                # ESPN-finds-Odds-row test in test_event_registry.py goes red.
                claim=_EC("espn", ee.espn_id, schedule_derived=True),
                commence_time_source="espn",
                status=_create_status,
            )
            event, created = await _foc(session, identity)

            # #190/#189 fold guard (gotcha #32): find_or_create_event can resolve
            # this ESPN game onto a LATER same-matchup sibling within the 28h
            # structured-match window (no minimum-distance floor). When the ESPN
            # game already started/finished but the event we attached to is a
            # not-yet-played sibling (its own commence_time is still in the future),
            # writing ESPN's live/terminal state here is exactly what produces the
            # completed_at < commence_time class. Skip the write and log so the flow
            # sentinel / audit surface it, rather than corrupt the sibling.
            if not created and espn_terminal_write_is_fold(event.commence_time, _now):
                logger.warning(
                    "ESPN fold guard: skipped write — game %s (%s vs %s, espn_id=%s) "
                    "resolved onto event %d whose commence_time %s is still in the "
                    "future (now %s); would fold an earlier game onto a later sibling "
                    "(#190/gotcha #32)",
                    ee.date, espn_home, espn_away, ee.espn_id, event.id,
                    event.commence_time.isoformat() if event.commence_time else None,
                    _now.isoformat(),
                )
                stats["espn_fold_guard_skipped"] = stats.get("espn_fold_guard_skipped", 0) + 1
                continue

            # Write win probability snapshot (#1207: skip the pregame win-prob when
            # ESPN reports "in" but the game hasn't started — same premature leak).
            if ee.home_win_probability is not None and not _espn_premature:
                # #1829: value + write time (see the sibling writer above).
                from app.utils.aggregation import (
                    stamp_source_reading as _stamp3,
                )
                _wps3 = _stamp3(
                    event.win_probability_sources,
                    "espn",
                    round(ee.home_win_probability, 4),
                )
                await session.execute(
                    _sql_update(Event)
                    .where(Event.id == event.id)
                    .values(
                        win_probability_sources=_wps3,
                        espn_win_prob_home=ee.home_win_probability,
                    )
                )
                event.win_probability_sources = _wps3

                snapshot = ESPNSnapshot(
                    event_id=event.id,
                    home_win_probability=ee.home_win_probability,
                    away_win_probability=1.0 - ee.home_win_probability,
                    home_score=ee.home_score,
                    away_score=ee.away_score,
                    game_clock=ee.clock,
                    period=_sanitize_period(ee.status_detail),  # #5390
                )
                session.add(snapshot)

            if ee.status in ("post", "final"):
                _completed_vals: dict = {}
                if not event.completed_at:
                    _completed_vals["completed_at"] = datetime.now(timezone.utc)
                if event.status != "completed":
                    _completed_vals["status"] = "completed"
                if _completed_vals:
                    await session.execute(
                        _sql_update(Event)
                        .where(Event.id == event.id)
                        .values(**_completed_vals)
                    )

            if created:
                stats["espn_events_created"] = stats.get("espn_events_created", 0) + 1
                logger.info(
                    "ESPN: created event %d for %s: %s vs %s (espn_id=%s)",
                    event.id, sport_key, espn_home, espn_away, ee.espn_id,
                )
            else:
                stats["espn_events_attached"] = stats.get("espn_events_attached", 0) + 1
        except Exception as exc:
            logger.warning("ESPN create/attach failed for %s vs %s: %s", espn_home, espn_away, exc)


# ---------------------------------------------------------------------------
# Scheduled events pass (team data pre-population)
# ---------------------------------------------------------------------------

async def sync_scheduled_events(session, sport_key, espn_events, stats):
    """Second pass: sync team data for scheduled events.

    Pre-populates colors/logos before games go live, and sets ESPN IDs
    for reliable matching when the game starts.
    """
    from app.models.models import Event, Team
    from sqlalchemy.orm import selectinload
    from app.tasks.espn_sync import get_event_name_variations, espn_team_matches

    events_result = await session.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            Event.sport.has(key=sport_key),
            Event.status == "scheduled",
        )
    )
    scheduled_events = events_result.scalars().all()

    # Batch-load teams for this sport to avoid N+1 queries
    sched_sport_obj = scheduled_events[0].sport if scheduled_events else None
    if sched_sport_obj:
        _sched_team_result = await session.execute(
            select(Team).where(Team.sport_id == sched_sport_obj.id)
        )
        sched_team_cache = {(t.name, t.sport_id): t for t in _sched_team_result.scalars().all()}
    else:
        sched_team_cache = {}

    # Build ESPN ID lookup for scheduled pass
    espn_by_id_sched = {}
    for ee in espn_events:
        if ee.espn_id:
            espn_by_id_sched[ee.espn_id] = ee

    stats["scheduled_pass"] = stats.get("scheduled_pass", {})
    stats["scheduled_pass"][sport_key] = {
        "our_events": len(scheduled_events),
        "espn_events": len(espn_events),
    }

    sched_identity_cache: set[tuple[int, str]] = set()

    # #2017: track espn_ids already spoken for by a row in this pass, the same
    # way the live pass does (`espn_sync.py` `claimed_espn_ids`). The DB check
    # inside `stamp_espn_id_if_unheld` is the real guard; this set makes the
    # in-pass case explicit instead of relying on autoflush ordering.
    sched_claimed_espn_ids: set[str] = {
        ev.espn_id for ev in scheduled_events if ev.espn_id
    }

    for event in scheduled_events:
        matched_espn = None

        # 1. Match by ESPN ID (most reliable)
        if event.espn_id and event.espn_id in espn_by_id_sched:
            matched_espn = espn_by_id_sched[event.espn_id]

        # 2. Fall back to name matching (using all ESPN name variants)
        #
        # #1947: the name match alone is a MATCHUP, not a game. This pass loads
        # every `scheduled` row for the sport with no time window, and
        # `espn_events` is today's scoreboard — so in a 3-4 game MLB series the
        # first name hit is tonight's game and the row being matched can be two
        # days out. That stamped tonight's `espn_id` onto five genuinely-scheduled
        # Aug-19/20 rows on 2026-08-17, and the id is what every downstream rail
        # then dereferences. The pairing verdict below is the date half of the
        # identity; UNKNOWN (ESPN gave no date) REFUSES, because an id is an
        # identity claim and this row already has none worth defending.
        if not matched_espn:
            home_names, away_names = get_event_name_variations(event)
            for ee in espn_events:
                if not ee.home_team or not ee.away_team:
                    continue
                if espn_team_matches(home_names, ee.home_team) and espn_team_matches(away_names, ee.away_team):
                    if pair_verdict(event.commence_time, ee.date) is not Pairing.SAME:
                        stats["scheduled_pair_refused"] = stats.get("scheduled_pair_refused", 0) + 1
                        continue
                    matched_espn = ee
                    break

        # 3. Commence_time proximity fallback REMOVED
        # Caused massive logo contamination for college sports.

        if not matched_espn:
            continue

        ee = matched_espn
        home_team = await upsert_team(session, event.home_team_name, ee.home_team, event.sport_id, sched_team_cache, stats)
        away_team = await upsert_team(session, event.away_team_name, ee.away_team, event.sport_id, sched_team_cache, stats)
        if home_team and event.home_team_id != home_team.id:
            event.home_team_id = home_team.id
        if away_team and event.away_team_id != away_team.id:
            event.away_team_id = away_team.id

        # Register ESPN team identities (cached to avoid re-registering)
        await register_espn_team_identities(
            session, home_team, away_team, ee, sport_key, sched_identity_cache
        )

        # Correct commence_time from ESPN if significantly different
        # Skip if StatPal set the commence_time (more reliable source)
        #
        # #1947, measured 2026-08-18: this correction is reachable via match arm 1
        # (the row's OWN espn_id), which is id-anchored and therefore NOT gated by
        # the pairing verdict above — correctly, per ruling 048 arm A. But when the
        # id on the row is itself wrong, "refine the time from the id" drags the row
        # onto the wrong day: five real Aug-19 games were moved to Aug-18 that way,
        # after which no row existed for the Aug-19 games at all. A correction of
        # MINUTES is a refinement; a correction of DAYS is evidence the ID is wrong,
        # and the answer to a wrong id is never to move the game to meet it. Refuse
        # and count, so the wrongly-keyed row stays findable instead of being tidied
        # into plausibility.
        if ee.date and event.commence_time:
            time_diff = abs((ee.date - event.commence_time).total_seconds())
            if time_diff > 300 and pair_verdict(event.commence_time, ee.date) is not Pairing.SAME:
                stats["scheduled_commence_move_refused"] = (
                    stats.get("scheduled_commence_move_refused", 0) + 1
                )
                logger.warning(
                    "ESPN: REFUSED commence_time move for event %d (%s vs %s): "
                    "%s -> %s is %.1fh, beyond the same-game window — the espn_id "
                    "on this row (%s) points at a different game (#1947)",
                    event.id, event.home_team_name, event.away_team_name,
                    event.commence_time.isoformat(), ee.date.isoformat(),
                    time_diff / 3600, event.espn_id,
                )
            elif time_diff > 300 and getattr(event, 'commence_time_source', None) != "statpal":
                logger.info(
                    f"ESPN: Correcting commence_time for scheduled event {event.id} "
                    f"({event.home_team_name} vs {event.away_team_name}): "
                    f"{event.commence_time.isoformat()} -> {ee.date.isoformat()} "
                    f"(diff: {time_diff/3600:.1f}h)"
                )
                event.commence_time = ee.date
                event.commence_time_source = "espn"
        if ee.broadcasts and not event.broadcast_info:
            event.broadcast_info = ", ".join(ee.broadcasts)

        # #2017: this pass is the AMPLIFIER for the espn_id collision class.
        # It loads every `scheduled` row for the sport with NO time window and,
        # unlike its live-pass sibling in `espn_sync.py` (which keeps a
        # `claimed_espn_ids` set), it kept none — so once a duplicate exists,
        # the next 60s tick stamped the same espn_id onto both halves. The
        # write now refuses when another row already holds the id, and the
        # refusal is counted rather than logged-and-forgotten.
        if ee.espn_id and not event.espn_id:
            verdict, _holder = await stamp_espn_id_if_unheld(
                session, event, ee.espn_id,
                context=f"sync_scheduled_events[{sport_key}]",
                claimed=sched_claimed_espn_ids,
            )
            if verdict == _ESPN_STAMP_REFUSED:
                stats["scheduled_espn_id_refused"] = (
                    stats.get("scheduled_espn_id_refused", 0) + 1
                )
            elif verdict == _ESPN_STAMP_STAMPED:
                stats["scheduled_espn_ids_set"] = stats.get("scheduled_espn_ids_set", 0) + 1

        # Update importance from ESPN season type for scheduled events too
        if ee.season_type is not None:
            espn_importance = {1: "exhibition", 2: "regular_season", 3: "playoff"}.get(ee.season_type)
            if espn_importance and event.llm_importance != espn_importance:
                if not (event.llm_importance == "championship" and espn_importance == "playoff"):
                    event.llm_importance = espn_importance


# ---------------------------------------------------------------------------
# Box score fetching (completed + live)
# ---------------------------------------------------------------------------

async def fetch_completed_box_scores(session, stats):
    """Third pass: fetch box scores for recently completed events
    that have an ESPN ID but no box_score_data yet.
    """
    from app.services.espn_api import ESPNAPIService
    from app.models.models import Event
    from app.tasks.config import ESPN_SPORT_MAPPING
    from sqlalchemy.orm import selectinload
    import json as _json_mod
    from sqlalchemy import text as _raw_text

    recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    completed_result = await session.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            Event.status.in_(["completed", "closed"]),
            Event.espn_id.isnot(None),
            Event.box_score_data.is_(None),
            Event.commence_time >= recent_cutoff,
        )
        .order_by(Event.commence_time.desc())
        .limit(10)
    )
    box_events = completed_result.scalars().all()

    if not box_events:
        return

    box_espn = ESPNAPIService()
    try:
        for event in box_events:
            sport_key = event.sport.key if event.sport else None
            if not sport_key or sport_key not in ESPN_SPORT_MAPPING:
                continue
            try:
                context = await box_espn.get_event_context(sport_key, event.espn_id)
                if context is None:
                    # AUTHORITY DARK (lane1/045). The else-branch below stamps
                    # box_score_data with error="not_available" — a durable
                    # claim about the GAME. ESPN not answering is a claim about
                    # ESPN, so nothing is written and the row is retried later.
                    stats["box_scores_authority_dark"] = (
                        stats.get("box_scores_authority_dark", 0) + 1
                    )
                    continue
                box_score = context.get("box_score", {})
                scoring_plays = context.get("scoring_plays", [])
                now_str = datetime.now(timezone.utc).isoformat()

                if box_score or scoring_plays:
                    bsd = {
                        "source": "espn",
                        "fetched_at": now_str,
                        "players": box_score,
                        "scoring_plays": scoring_plays,
                    }
                    await session.execute(
                        _raw_text("UPDATE events SET box_score_data = cast(:bsd AS jsonb) WHERE id = :eid"),
                        {"bsd": _json_mod.dumps(bsd), "eid": event.id},
                    )
                    event.box_score_data = bsd
                    stats["box_scores_fetched"] = stats.get("box_scores_fetched", 0) + 1
                else:
                    err_bsd = {
                        "source": "espn",
                        "error": "not_available",
                        "fetched_at": now_str,
                    }
                    await session.execute(
                        _raw_text("UPDATE events SET box_score_data = cast(:bsd AS jsonb) WHERE id = :eid"),
                        {"bsd": _json_mod.dumps(err_bsd), "eid": event.id},
                    )
                    event.box_score_data = err_bsd
            except Exception as e:
                logger.error(f"Box score fetch error for event {event.id}: {e}")
    finally:
        await box_espn.close()


async def fetch_live_box_scores(session, stats):
    """Fourth pass: update box scores for live events (every 2 minutes).

    #5088 — THIS PASS IS WHERE A LIVE LINE SCORE COMES FROM, AND IT WAS DROPPING IT.

    ``get_event_context`` returns four things and this function persisted three.
    ``context["scores"]`` carries ``home_period_scores`` / ``away_period_scores``
    — ESPN's per-period line score, populated while the game is in progress —
    and the settled writer (``espn_sync._backfill_box_scores``) has always kept
    it. This one never read the key, so the only line score in the database was
    the one fetched AFTER full time.

    Measured on production 2026-09-11: of the 46 MLB events completed in the
    trailing four days that carry ``box_score_data``, **46 have period scores
    and all 46 were fetched strictly after ``completed_at`` — zero at or before
    it**. That is why ``_grade_closed_windows`` could only ever grade a finished
    game: mid-game its one input did not exist. The route's ability to say "the
    third inning is over and here is its result" begins here.

    THE ORDER IS STALENESS, NOT KICKOFF, BECAUSE NEWEST-FIRST STARVED THE SHIP
    -------------------------------------------------------------------------
    The query took the 10 most recently STARTED live events every minute, and
    the 2-minute staleness filter below then discarded the ones it had just
    fetched — so on alternate minutes the pass did nothing at all, and an event
    outside the newest ten was never reached however long it ran. Measured over
    the trailing week, 42 of 166 live hours carried more than 10 concurrent
    ESPN-linked live events and the peak was 54, so at peak 44 games were
    unreachable.

    Newest-first is also backwards for THIS ship specifically: the games with
    the most closed windows are the ones furthest into themselves, which is
    exactly the tail the ordering dropped.

    Ordering by ``fetched_at`` (nulls — never fetched — first) makes the same
    10 slots a round-robin over every live event instead of a fixed window on
    ten of them. It costs no additional ESPN calls: the limit and the 2-minute
    staleness rule are both unchanged.
    """
    from app.services.espn_api import ESPNAPIService
    from app.models.models import Event
    from app.tasks.config import ESPN_SPORT_MAPPING
    from sqlalchemy.orm import selectinload
    import json as _json_mod
    from sqlalchemy import text as _raw_text

    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
    live_box_result = await session.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            Event.status == "live",
            Event.espn_id.isnot(None),
        )
        .order_by(
            Event.box_score_data["fetched_at"].astext.asc().nullsfirst(),
            Event.commence_time.desc(),
        )
        .limit(10)
    )
    live_box_events = live_box_result.scalars().all()

    live_to_fetch = []
    for ev in live_box_events:
        if ev.box_score_data is None:
            live_to_fetch.append(ev)
        elif ev.box_score_data.get("live"):
            fetched_str = ev.box_score_data.get("fetched_at")
            if fetched_str:
                try:
                    fetched_at = datetime.fromisoformat(fetched_str)
                    if fetched_at < stale_cutoff:
                        live_to_fetch.append(ev)
                except (ValueError, TypeError):
                    live_to_fetch.append(ev)
            else:
                live_to_fetch.append(ev)

    if not live_to_fetch:
        return

    live_espn = ESPNAPIService()
    try:
        for ev in live_to_fetch:
            sport_key = ev.sport.key if ev.sport else None
            if not sport_key or sport_key not in ESPN_SPORT_MAPPING:
                continue
            try:
                context = await live_espn.get_event_context(sport_key, ev.espn_id)
                if context is None:
                    # AUTHORITY DARK (lane1/045) — keep the last live box score.
                    stats["live_box_scores_authority_dark"] = (
                        stats.get("live_box_scores_authority_dark", 0) + 1
                    )
                    continue
                box_data = context.get("box_score", {})
                scoring_plays = context.get("scoring_plays", [])
                scores = context.get("scores") or {}
                now_str = datetime.now(timezone.utc).isoformat()
                if box_data or scoring_plays:
                    bsd = {
                        "source": "espn",
                        "fetched_at": now_str,
                        "players": box_data,
                        "scoring_plays": scoring_plays,
                        "live": True,
                    }
                    # #5088: the same two keys, written the same way, as the
                    # settled writer in `espn_sync._backfill_box_scores`. The
                    # LAST entry of a live line score is the period currently
                    # being played and is therefore partial — every reader of
                    # these arrays must prove the period is over before summing
                    # it, which `prop_window_closed` does for the one reader
                    # that consumes them mid-game.
                    if scores.get("home_period_scores"):
                        bsd["home_period_scores"] = scores["home_period_scores"]
                        bsd["away_period_scores"] = scores.get(
                            "away_period_scores", []
                        )
                    await session.execute(
                        _raw_text("UPDATE events SET box_score_data = cast(:bsd AS jsonb) WHERE id = :eid"),
                        {"bsd": _json_mod.dumps(bsd), "eid": ev.id},
                    )
                    ev.box_score_data = bsd
                    stats["live_box_scores_fetched"] = (
                        stats.get("live_box_scores_fetched", 0) + 1
                    )
            except Exception as e:
                logger.error(f"Live box score error for event {ev.id}: {e}")
    finally:
        await live_espn.close()


# ---------------------------------------------------------------------------
# Score backfill for completed events with no scores/ESPN ID
# ---------------------------------------------------------------------------

async def backfill_missing_scores(session, stats):
    """Fifth pass: backfill scores for recently completed events
    that have NO scores and NO espn_id. Catches niche sports that were
    added to ESPN_SPORT_MAPPING after the events completed.
    """
    from app.services.espn_api import ESPNAPIService
    from app.models.models import Event, Team
    from app.tasks.config import ESPN_SPORT_MAPPING
    from app.tasks.espn_sync import get_event_name_variations
    # #6215 follow-up `6215-REMOVE-ACCIDENTAL-BACKFILL-IMPORTS`. The rival veto
    # and `normalize_name` were imported here and never used — and they must
    # NOT be wired in, which is why this comment replaces them rather than a
    # TODO.
    #
    # 🔴 MEASURED ON THIS RAIL, 2026-09-15, and the number does not resemble
    # either of the other two. Over 1,060 real alias pairs from 500
    # ESPN-anchored teams (`name` vs each of its `alternate_names`, which is
    # exactly the comparison below), `names_match` accepts 943 and
    # `shared_token_rivals` would refuse **10 of them** — of which NINE are
    # genuine aliases this backfill needs (`LA Clippers`, `C Palace`,
    # `NY Red Bulls`, `UAlbany Great Danes`, `Mt. St. Mary's` /
    # `Mount St. Mary's`) and one is a true rival pair. Nine real clubs would
    # silently stop getting their scores backfilled to refuse one.
    #
    # The veto belongs on the two rails that DECIDE AN IDENTITY and write it
    # down (`espn_identity_corresponds`, `location_corresponds`). This rail
    # RECALLS a candidate and then requires both teams to agree, so its failure
    # mode and its cost are different. `test_the_backfill_rail_keeps_its_aliases_6215`
    # pins the nine.
    from app.utils.name_normalization import names_match as _canonical_names_match
    from sqlalchemy.orm import selectinload

    def names_match(our_names: list, espn_name: str) -> bool:
        if not espn_name:
            return False
        return any(_canonical_names_match(name, espn_name) for name in our_names if name)

    score_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    missing_scores_result = await session.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            Event.status.in_(["completed", "closed"]),
            Event.home_score.is_(None),
            Event.away_score.is_(None),
            Event.commence_time >= score_cutoff,
        )
        .order_by(Event.commence_time.desc())
        .limit(20)
    )
    missing_score_events = missing_scores_result.scalars().all()

    # Group by sport key to batch ESPN fetches
    events_by_sport: dict[str, list] = {}
    for ev in missing_score_events:
        sk = ev.sport.key if ev.sport else None
        if sk and sk in ESPN_SPORT_MAPPING:
            events_by_sport.setdefault(sk, []).append(ev)

    if not events_by_sport:
        return

    # Batch-load teams for score backfill to avoid N+1
    backfill_team_cache = {}
    for _sk, _evts in events_by_sport.items():
        if _evts and _evts[0].sport:
            _bt_result = await session.execute(
                select(Team).where(Team.sport_id == _evts[0].sport.id)
            )
            for t in _bt_result.scalars().all():
                backfill_team_cache[(t.name, t.sport_id)] = t

    score_espn = ESPNAPIService()
    try:
        for sport_key, events_list in events_by_sport.items():
            try:
                # Fetch scoreboard with date range covering these events
                dates = set()
                for ev in events_list:
                    if ev.commence_time:
                        dates.add(ev.commence_time.strftime("%Y%m%d"))
                for date_str in dates:
                    espn_events = await score_espn.get_scoreboard(sport_key, date=date_str)
                    if espn_events is None:
                        # AUTHORITY DARK (lane1/045) — no board, no backfill.
                        stats["score_backfill_authority_dark"] = (
                            stats.get("score_backfill_authority_dark", 0) + 1
                        )
                        logger.warning(
                            "ESPN score backfill: authority dark for "
                            f"{sport_key}/{date_str} — scores left missing"
                        )
                        continue
                    if not espn_events:
                        continue
                    for ev in events_list:
                        if ev.commence_time and ev.commence_time.strftime("%Y%m%d") != date_str:
                            continue
                        if ev.home_score is not None:
                            continue  # Already got scores
                        home_names, away_names = get_event_name_variations(ev)
                        # #2049: this rail had date-STRING equality only (above)
                        # and no within-day discrimination, then a raw stamp. A
                        # shared UTC date is not a shared game — a doubleheader
                        # and a same-day series pair both live inside one bucket.
                        _matched, _reason = _select_authorized_espn_candidate(
                            espn_events,
                            ev.commence_time,
                            anchor_espn_id=getattr(ev, "espn_id", None),
                            is_name_match=lambda ee: (
                                names_match(
                                    home_names,
                                    ee.home_team.display_name or ee.home_team.name or "",
                                )
                                and names_match(
                                    away_names,
                                    ee.away_team.display_name or ee.away_team.name or "",
                                )
                            ),
                        )
                        if _matched is None:
                            if _reason != "no-name-match":
                                logger.info(
                                    f"ESPN score backfill REFUSED event {ev.id} "
                                    f"({ev.away_team_name} @ {ev.home_team_name}): "
                                    f"{_reason}"
                                )
                            continue
                        ee = _matched
                        if ee.home_score is not None:
                            ev.home_score = ee.home_score
                            ev.away_score = ee.away_score
                            _bf_period = _sanitize_period(ee.status_detail)  # #5390
                            if _bf_period:
                                ev.period = _bf_period
                            # #2693 CERT-784: `not ev.espn_id` asks whether THIS
                            # row has one and never whether another row already
                            # holds it — the exact question #2017 exists to add.
                            # This rail selects rows missing a score, which is
                            # the same population the step-2 repair leaves with
                            # a cleared id, so a raw stamp here hands a
                            # contested id straight back.
                            _verdict, _holder = await stamp_espn_id_if_unheld(
                                session, ev, ee.espn_id,
                                context="espn backfill_missing_scores",
                            )
                            if _verdict == _ESPN_STAMP_REFUSED:
                                stats["espn_id_held"] = stats.get("espn_id_held", 0) + 1
                            # Upsert teams for colors/logos
                            home_team = await upsert_team(session, ev.home_team_name, ee.home_team, ev.sport_id, backfill_team_cache, stats)
                            away_team = await upsert_team(session, ev.away_team_name, ee.away_team, ev.sport_id, backfill_team_cache, stats)
                            if home_team and ev.home_team_id != home_team.id:
                                ev.home_team_id = home_team.id
                            if away_team and ev.away_team_id != away_team.id:
                                ev.away_team_id = away_team.id
                            stats["scores_backfilled"] = stats.get("scores_backfilled", 0) + 1
                            logger.info(
                                f"ESPN: Backfilled scores for event {ev.id} "
                                f"({ev.away_team_name} @ {ev.home_team_name}): "
                                f"{ee.away_score}-{ee.home_score}"
                            )
            except Exception as e:
                stats["errors"].append(f"score_backfill_{sport_key}: {str(e)}")
    finally:
        await score_espn.close()
