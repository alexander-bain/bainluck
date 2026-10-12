"""#1541 — an Odds API outright the provider has CLOSED becomes a finished question. Pure.

═══ WHAT A READER SAW ═══

``/futures/10`` (*FIFA World Cup Winner*, ``odds_api``) still reads as an open
question three months after Spain won the final on 2026-07-19: no settled
language, a "Games This Week" strip of MLS fixtures, and a ladder the page can
only say has "no current prices" (#8011 withheld the frozen 59% hero, and
deliberately left the lifecycle question here). The concept page one tap away
already says Spain won, off the venue-settled Polymarket copy.

═══ WHY NOTHING EVER CLOSED IT ═══

The poller (``tasks/futures.py::_poll_futures_odds``) only ever visits the
sport keys The Odds API currently LISTS (``/sports`` returns in-season keys
only). When the provider closed ``soccer_fifa_world_cup_winner`` the poller
simply stopped visiting the row, and nothing else owns an ``odds_api`` futures
row: ``resolution_date`` is NULL (so ``mark_resolved_futures`` never fires),
there is no ticker for any venue grader to join, and the row is a ROLLING key
(one row per sport key, overwritten edition after edition — #1541 premise
correction of 2026-08-12), so a settlement bolted onto it would also be
overwritten by the next edition the provider lists under the same key.

═══ THE EVIDENCE, AND WHY IT IS NOT A TITLE HEURISTIC ═══

Two facts, both from our own provider reads, never from the market's name:

1. **The provider no longer lists the key.** The same successful ``/sports``
   read the poll is driven by. Absence from a listing that DID come back, in a
   poll that DID write at least one market, is the provider closing the
   question — not our outage (a failed read raises before anything here runs;
   an empty listing or a poll that wrote nothing refuses the pass).
2. **Nothing has been quoted for the quiet window**, on BOTH clocks #8011
   proved must be read together: the newest leg observation AND the parent
   row's poller stamp (``updated_at`` is rewritten by every poll that returned
   prices for the key). That turns a one-poll listing blip into a non-event —
   a key the provider really offers is re-quoted every 4 hours.

What it does NOT know is who won. So the transition is ``resolved`` under the
enumerated no-winner reason ``REASON_PROVIDER_DELISTED`` (CAL-P086A's gate:
resolving without a winner is allowed only when it SAYS so), and nothing here
writes ``is_winner`` or ``resolution_source``. Every leg keeps
``resolution_source = NULL``, which every reader already treats as "no verdict"
(``OutcomeRow.outcomeRowVerdict``; calibration's truth-eligibility allowlist) —
the page goes to its settled view without crowning anybody or marking anybody
Lost.

═══ THE ROLLING KEY IS RELEASED, SO THE FINISHED EDITION STAYS FINISHED ═══

The retired row's ``external_id`` gains a ``:retired:<last-quote-date>`` suffix
(the original is kept in ``market_metadata.odds_api_retirement.rolling_key``).
When the provider lists the key again — the 2030 World Cup — the poll's upsert
finds no row on the key and inserts a fresh one with its own openings, instead
of pouring the next edition's prices onto the finished 2026 page. The suffix
keeps the sport-key PREFIX intact, so prefix readers (``grid_sentinel``,
``golf.py``) still classify the row.

The one case where a release is wrong is a false retirement: the provider
stopped listing a key for longer than the quiet window and then resumed the
SAME edition. ``same_edition_reopens`` decides that from the provider's own
event identity (#9387's ``odds_api_current_event``): the retired row reopens
only when both sides carry an identity and the provider event id matches. An
unknown identity on either side is not a match — the finished row stays
finished and the new listing gets its own row.

Pure: no DB, no network, no clock of its own.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from app.utils.resolved_write_gate import REASON_PROVIDER_DELISTED

#: How long an unlisted key must have gone unquoted, on both clocks, before its
#: row is retired. The poll runs every 4 hours (``poll-futures-every-4h``), so
#: this is 42 consecutive polls in which the provider neither listed the key
#: nor priced it. It is NOT a staleness threshold for listed markets — a listed
#: key is never retired, however quiet — so it does not compete with
#: ``PRICES_STOPPED_DAYS`` / ``BOARD_UNOBSERVED_DAYS``, which measure a
#: different thing (whether a price we serve is still sourced). The harmful
#: direction is retiring an edition the provider resumes, and
#: ``same_edition_reopens`` is the repair for that case, so the window only
#: has to make a resumption rare, not impossible.
PROVIDER_DELISTED_QUIET_DAYS = 7

#: The suffix that releases a rolling key. ``:`` never appears in an Odds API
#: sport key, so a retired id cannot collide with a live one.
RETIRED_KEY_INFIX = ":retired:"

#: Sibling metadata key recording what the retirement knew.
RETIREMENT_METADATA_KEY = "odds_api_retirement"

# Verdicts, one per open odds_api row per pass.
LISTED = "listed"
STALE_LISTED = "stale_listed"
RETIRE = "retire"
RECENTLY_QUOTED = "recently_quoted"
NO_EVIDENCE = "no_evidence"
GRADED = "graded"

#: The verdicts that are a finding rather than a state: an open row nobody will
#: close on its own. Reported by the poll (the stale-unsettled guard) so the
#: next market the provider drops while still LISTING it is not caught by
#: nobody, the way market 10 was for three months.
STALE_UNSETTLED_VERDICTS = frozenset({STALE_LISTED, NO_EVIDENCE, GRADED})

#: Price-derived crowners in ``backfill_winners`` (``clean_resolution`` and
#: ``all_losers``) run over every resolved market of every source. A retired
#: board's last quote is not a settlement: the provider closed the question and
#: never said who won, and it lists the WHOLE field, so the "winning outcome
#: isn't in our DB" premise of ``all_losers`` is false here — it would stamp the
#: real champion Lost. Spliced into both passes' market predicate.
NOT_RETIRED_BY_PROVIDER_SQL = (
    "COALESCE(fm.market_metadata -> 'resolution_gate' ->> 'reason', '') <> '"
    + REASON_PROVIDER_DELISTED
    + "'"
)


def _as_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def listing_is_usable(listed_keys: Iterable[str] | None, markets_processed: int) -> bool:
    """May this poll's listing testify that a key is absent?

    Only when the listing came back non-empty AND the poll wrote at least one
    market. An empty listing is a response shape, not a closure (gotcha #53);
    a poll that wrote nothing cannot prove our own ingestion is alive.
    """
    return bool(listed_keys) and markets_processed >= 1


def classify_board(
    *,
    external_id: str | None,
    listed_keys: frozenset[str] | set[str],
    poll_clock: datetime,
    newest_leg_at: Any,
    parent_touched_at: Any,
    has_graded_leg: bool,
    quiet_days: float = PROVIDER_DELISTED_QUIET_DAYS,
) -> str:
    """One verdict for one OPEN ``odds_api`` row.

    ``newest_leg_at`` is the newest ``futures_outcomes.last_updated`` on the
    row, ``parent_touched_at`` its ``futures_markets.updated_at``.
    """
    clock = _as_utc(poll_clock)
    leg = _as_utc(newest_leg_at)
    parent = _as_utc(parent_touched_at)
    window = quiet_days * 86400

    def quiet(stamp: datetime | None) -> bool:
        return stamp is not None and clock is not None and (clock - stamp).total_seconds() > window

    if external_id in listed_keys:
        # Never retired while listed, however quiet. A listed key with nothing
        # quoted for the window is the case nothing closes — flag it.
        if quiet(leg) and quiet(parent):
            return STALE_LISTED
        return LISTED
    if has_graded_leg:
        # Somebody already put a verdict on a leg; resolving it under a
        # no-winner reason would contradict that. Not this writer's question.
        return GRADED
    if leg is None or parent is None or clock is None:
        # No evidence is not evidence of closure.
        return NO_EVIDENCE
    if quiet(leg) and quiet(parent):
        return RETIRE
    return RECENTLY_QUOTED


def retired_external_id(external_id: str, last_observed_at: datetime) -> str:
    """The key the retired row moves to, freeing ``external_id`` for the next edition."""
    stamp = _as_utc(last_observed_at)
    return f"{external_id}{RETIRED_KEY_INFIX}{stamp.date().isoformat()}"


def retirement_metadata(
    *, rolling_key: str, last_observed_at: datetime, checked_at: datetime
) -> dict:
    """What the retirement knew, merged into ``market_metadata`` with ``||``."""
    return {
        RETIREMENT_METADATA_KEY: {
            "rolling_key": rolling_key,
            "last_observed_at": _as_utc(last_observed_at).isoformat(),
            "provider_listing_checked_at": _as_utc(checked_at).isoformat(),
            "quiet_days": PROVIDER_DELISTED_QUIET_DAYS,
        }
    }


def _event_id(identity: Any) -> str | None:
    if not isinstance(identity, dict):
        return None
    value = identity.get("event_id")
    if isinstance(value, str) and value.strip():
        return value
    return None


def same_edition_reopens(retired_identity: Any, incoming_identity: Any) -> bool:
    """Is a relisted key the SAME provider edition the retired row was carrying?

    True only when both identities are present and name the same provider
    event id. Unknown on either side is "not shown to be the same", and the
    finished row stays finished.
    """
    retired = _event_id(retired_identity)
    incoming = _event_id(incoming_identity)
    return retired is not None and retired == incoming
