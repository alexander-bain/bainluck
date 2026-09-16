"""Put the contest date back on a row holding a Kalshi settlement backstop (#6568).

**SHIP: a boxing match that was fought two weeks ago stops being advertised as
upcoming.** (Pillar: TRUTH.)

──────────────────────────────────────────────────────────────────────────────
WHAT A READER SEES
──────────────────────────────────────────────────────────────────────────────
`/events/15309068` on 2026-09-16, 390px, screenshotted before this shipped:

    Starts in 10d 2h              Sep 26, 2026 · 3:00 PM PDT
    OJ   Opetaia J.   No price yet   Mikaelyan N.   MN
    Win Probability — "Chart available at game time"

Kalshi fought and graded that bout on **September 12**. The page is counting
down to a fight that happened four days before the reader opened it, and the
chart is promising a curve "at game time" for a game time that has passed.

`/sports/boxing_boxing` carries the same lie in list form: **four of its eight
"Upcoming" cards are September 3 fights**, advertised on September 17.

──────────────────────────────────────────────────────────────────────────────
THE ROW REFUTES ITSELF — THE STORED HOUR IS A CONTRACT EXPIRATION
──────────────────────────────────────────────────────────────────────────────
Measured on production 2026-09-16, event ``15309068`` and market ``60644426``::

    events.commence_time          2026-09-26 22:00:00+00   source 'kalshi'
    events.external_id            NULL          (no schedule provider, #2693)
    futures_markets.expiration_time
                                  2026-09-26 22:00:00+00   <- byte-identical
    futures_markets.external_id   KXBOXING-26SEP12JN       <- the venue's date
    futures_markets.settled_at    2026-09-13 10:52:48+00   <- graded already

The stored "start" is not an approximation of a start. It **is** the attached
contract's expiration instant, to the second — a settlement backstop Kalshi
hangs ~14 days out for a combat card, which is gotcha #14 exactly. This module
never infers that; it requires the two columns to be equal, so the row's own
data is what proves the hour is not a whistle.

``app/utils/kalshi_occurrence_start`` names this class in its own docstring and
declines it on purpose: *"Boxing returns ~14 days (those markets kept
``close_time``)"*. Its 180-minute soccer pad would be a fabrication here. So the
hour is not recoverable — but the DATE is, from the venue's own ticker.

──────────────────────────────────────────────────────────────────────────────
A DATE, AND DELIBERATELY NOT AN HOUR
──────────────────────────────────────────────────────────────────────────────
``market_identity.ticker_game_date`` reads ``26SEP12`` off the ticker: the day
the venue says the contest is, in US Eastern. That is the whole of what Kalshi
publishes for a combat card — ``prediction_market_matching.ticker_start_utc``
refuses a date-only ticker with *"there is no start time to place... A None
means 'no instant available', never 'midnight UTC'"*.

This module therefore claims a date and no hour, and says so in the house's
existing vocabulary for exactly that: ``commence_time_source = 'kalshi_ticker'``
at midnight UTC, the pair ``event_twin_fold.is_kalshi_date_only`` already reads
as "this row asserts a fixture's DATE and no kick-off hour". Inventing an hour
from the settlement instant would be the guessed kick-off this ship exists to
remove, one fortnight smaller.

🔴 **THE RESIDUAL, STATED RATHER THAN HIDDEN.** A date-only row still renders
through a wall-clock formatter, so a Pacific reader sees the evening before
(``2026-09-12T00:00Z`` prints as "Sep 11, 5:00 PM PDT"). That is the pre-existing
shape of the whole ``kalshi_ticker`` population and this ship neither creates nor
fixes it. What it removes is a fortnight and a countdown to a finished fight.

──────────────────────────────────────────────────────────────────────────────
REACH, MEASURED AT THE READER'S SCALE BEFORE IT WAS BUILT
──────────────────────────────────────────────────────────────────────────────
Production 2026-09-16, the full predicate below over every attached Kalshi
market::

    status       still upcoming   events
    ──────────────────────────────────────
    closed             no            967
    voided             no            120
    suspended          no              9
    scheduled         YES             12    <- every one of them boxing_boxing

**Twelve events are the reader-visible cohort**, and all twelve are boxing rows
whose ticker names a day exactly 14 before the hour we stored. The other 1,096
carry the same defect on rows that no longer advertise a countdown.

The withholding half was measured too, because a rule that removes rows must
leave the surface a surface: `/api/leagues/boxing_boxing` serves **8** upcoming
cards, **4** of them this class, so the rail keeps 4 real fights (Sep 19) plus
``upcoming_games_has_more``. It does not empty.

──────────────────────────────────────────────────────────────────────────────
WHAT THIS DOES NOT DO
──────────────────────────────────────────────────────────────────────────────
**It writes nothing.** Serve-time only, via ``set_committed_value`` (gotcha #4),
the same bargain `kalshi_occurrence_start` and `event_twin_fold` already strike.
The rows stay exactly as they are for the Grid and Flow sentinels and for the
id-anchored repair that is #2693's durable answer. Ruling 048 is untouched: no
row absorbs another and no id-less claim is promoted.

**It never moves a row a schedule provider stamped** (``external_id`` set) and
**it only ever moves a start EARLIER.** Moving a stand-in forward is
``kalshi._stand_in_refinement_target``'s job and is bounded there at 36h; this
module cannot push a real fixture further out however its ticker reads.

Refs #6568 (acceptance 2), #2693, #5905. Gotchas #14, #32, #42.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.utils.kalshi_occurrence_start import (
    KALSHI_OCCURRENCE_TIMED_SOURCES,
    KALSHI_RECOVERY_STAMP,
)
from app.utils.market_identity import eastern_game_date, ticker_game_date

__all__ = [
    "KALSHI_EXPIRATION_RECOVERY_STAMP",
    "TICKER_CONTEST_DATE_SOURCE",
    "contest_date_behind_expiration",
    "is_expiration_start_candidate",
    "recover_kalshi_expiration_starts",
    "still_upcoming_after_recovery",
]

#: The provenance a recovered row carries, and it is not a new vocabulary word.
#: ``event_twin_fold.KALSHI_DATE_ONLY_SOURCE`` and
#: ``event_completion.TICKER_DERIVED_COMMENCE_SOURCE`` are both this same string,
#: and ``event_twin_fold.is_kalshi_date_only`` reads it together with midnight
#: UTC as "asserts a DATE and no kick-off hour" — which is precisely the claim
#: this module is entitled to make. Stamping the value without stamping its
#: provenance would leave a ticker-derived date wearing ``'kalshi'``, i.e. a
#: value disagreeing with the column that names its writer.
TICKER_CONTEST_DATE_SOURCE = "kalshi_ticker"

#: The unmapped attribute marking a row this module has already corrected, so a
#: second pass over the same objects in one request is a no-op.
#:
#: The same hazard `kalshi_occurrence_start` measured and the same remedy: a
#: caller can hand the fold the same row objects twice (``/api/leagues`` does),
#: and this function's gates key on fields it DOES change, so a second pass
#: would find the row already wearing ``kalshi_ticker`` and refuse anyway. The
#: stamp makes that refusal explicit rather than incidental, and it is what the
#: returned count is honest about: corrections MADE, never rows examined.
#:
#: An unmapped attribute is the right sentinel for the reason that module gives:
#: its lifetime is exactly the lifetime of the reading it guards. It lives on the
#: hydrated instance, dies with the request, and the mapper never sees it — a
#: name it does not map is not a column it can flush (gotcha #4).
KALSHI_EXPIRATION_RECOVERY_STAMP = "_bl_kalshi_expiration_start_recovered"


def is_expiration_start_candidate(event: Any) -> bool:
    """Could this row's hour be a Kalshi expiration? Pure, and cheap on purpose.

    Callers use this to decide whether to spend a query at all:
    :func:`recover_kalshi_expiration_starts` needs the event's Kalshi markets,
    and almost no row on almost any page is a candidate. An unanchored,
    Kalshi-timed row is rare enough that the serve paths pay nothing for the
    correction on the pages that do not need it.

    It is deliberately the SUBSET of the full predicate that needs no market:
    saying yes here is not saying the row is defective.
    """
    if getattr(event, "external_id", None) is not None:
        return False  # a schedule provider reported this start; not ours to move
    if getattr(event, KALSHI_RECOVERY_STAMP, False):
        return False  # the soccer pad already recovered it; see the note below
    if getattr(event, KALSHI_EXPIRATION_RECOVERY_STAMP, False):
        return False
    source = getattr(event, "commence_time_source", None)
    if source not in KALSHI_OCCURRENCE_TIMED_SOURCES:
        return False
    return isinstance(getattr(event, "commence_time", None), datetime)


def contest_date_behind_expiration(
    event: Any, ticker: Optional[str], expiration_time: Any
) -> Optional[datetime]:
    """Midnight UTC of the contest date, or ``None`` to leave the row alone.

    ``None`` is the answer for the overwhelming majority of rows and means "this
    hour is not provably a contract expiration". Pure: no DB, no clock, no I/O.

    The four gates past :func:`is_expiration_start_candidate`, each carrying its
    own weight:

    1. **The stored hour must EQUAL the contract's expiration instant, exactly.**
       This is the proof and it is the reason nothing here is an inference: an
       approximate match would let a real start that merely sits near a
       settlement backstop be rewritten. Equality says the auto-create path
       copied the backstop into the start column, which is the defect.
    2. **The ticker must name a date** (:func:`ticker_game_date` — the house's
       one parser, and it returns ``None`` for a ticker it cannot read rather
       than guessing, which is load-bearing here too).
    3. **That date must be STRICTLY EARLIER than the row's US Eastern day.** The
       ticker's calendar is Eastern, so the comparison is against
       :func:`eastern_game_date` and not the UTC date — comparing UTC days would
       manufacture a disagreement for every night event. Strictly earlier is
       also what makes this a one-way correction: a same-day ticker changes
       nothing, and a later ticker is a linkage question
       (``_ticker_date_conflicts_with_event``), never a licence to push a
       fixture further out.

    The returned instant is midnight UTC because that, with
    :data:`TICKER_CONTEST_DATE_SOURCE`, is the house's existing representation of
    a date with no hour. It is not a claim about when the bell rang.
    """
    if not is_expiration_start_candidate(event):
        return None
    commence = event.commence_time
    if not isinstance(expiration_time, datetime):
        return None
    if _as_utc(expiration_time) != _as_utc(commence):
        return None
    contest_day = ticker_game_date(ticker)
    if contest_day is None:
        return None
    stored_day = eastern_game_date(commence)
    if stored_day is None or contest_day >= stored_day:
        return None
    return datetime(
        contest_day.year, contest_day.month, contest_day.day, tzinfo=timezone.utc
    )


def _as_utc(value: datetime) -> datetime:
    """Tz-aware UTC, treating a naive value as UTC.

    The two instants being compared come from two columns and one of them can
    arrive naive depending on the driver. Comparing a naive to an aware datetime
    raises ``TypeError``, and this function runs inside a caller's bare
    ``except`` (gotcha #42) — so it would not fail loudly, it would silently
    disable the correction for the whole page.
    """
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def apply_contest_date(event: Any, recovered: datetime) -> None:
    """Place the recovered date on the row without making it a pending write.

    Public because the rail and its tests both need exactly this, and two copies
    of a "do not mark the row dirty" idiom is how one of them rots.

    An ORM row takes ``set_committed_value``, which loads the value as though
    the database returned it, so the row is never dirty and no later flush can
    persist a serve-time reading into ``events`` (gotcha #4). Anything else — a
    test double, a detached object — takes a plain assignment, because
    ``set_committed_value`` needs instance state it has not got.

    Both fields move together, always. A recovered ``commence_time`` still
    wearing ``commence_time_source = 'kalshi'`` would be a value disagreeing
    with the column that names its writer, and the pair is what
    ``is_kalshi_date_only`` reads.
    """
    try:
        from sqlalchemy import inspect as _sa_inspect
        from sqlalchemy.orm.state import InstanceState

        is_orm = isinstance(_sa_inspect(event, raiseerr=False), InstanceState)
    except Exception:  # noqa: BLE001 — no SQLAlchemy opinion means not an ORM row
        is_orm = False

    if is_orm:
        from sqlalchemy.orm.attributes import set_committed_value

        set_committed_value(event, "commence_time", recovered)
        set_committed_value(event, "commence_time_source", TICKER_CONTEST_DATE_SOURCE)
        return
    event.commence_time = recovered
    event.commence_time_source = TICKER_CONTEST_DATE_SOURCE


def still_upcoming_after_recovery(event: Any, now: datetime) -> bool:
    """Does this row still belong on an "Upcoming" rail after the correction?

    ``True`` for every row this module did not touch, and that is the whole
    point: a row that is in the past for some other reason is some other rule's
    business, and a rail that started dropping those would be a different ship
    wearing this one's tests. :data:`KALSHI_EXPIRATION_RECOVERY_STAMP` is the
    test, never "is it in the past".

    An upcoming rail selects on ``commence_time > now`` in SQL, against the
    STORED column. When that column held a contract expiration, the row was
    selected for a date the contest never had. Re-dating it without this is not
    one lie fewer — it prints a September 3 fight under "Upcoming".
    """
    if not getattr(event, KALSHI_EXPIRATION_RECOVERY_STAMP, False):
        return True
    commence = getattr(event, "commence_time", None)
    if not isinstance(commence, datetime):
        return True
    return _as_utc(commence) > _as_utc(now)


async def recover_kalshi_expiration_starts(session: Any, events: Any) -> int:
    """Correct every row in ``events`` whose hour is a Kalshi expiration.

    Returns how many rows were corrected. **Serve-time only: writes nothing.**

    One query for the whole batch, and none at all when nothing is a candidate —
    which is the common case on every page. Best-effort per row (gotcha #42):
    one row that cannot be read must never cost the page its other corrections,
    and a failure to reach the database leaves every row exactly as stored.

    **ONE CORRECTION PER EVENT, chosen deterministically.** An event can hold
    several Kalshi markets and two of them can carry different tickers, so the
    markets are ordered by ``external_id`` and the first that yields a target
    wins. Without the ordering the served date would depend on the order the
    server happened to return rows — a deterministic tiebreak is not
    automatically a correct one, but an arbitrary one is reliably wrong.

    **MUTUALLY EXCLUSIVE WITH THE SOCCER PAD, BY CONSTRUCTION AND IN BOTH
    DIRECTIONS.** :func:`is_expiration_start_candidate` refuses a row carrying
    ``kalshi_occurrence_start.KALSHI_RECOVERY_STAMP``, and that module in turn
    refuses any row whose ``commence_time_source`` is not one of its own two —
    which a row corrected here no longer is. So call order cannot produce a
    doubly-corrected row in either arrangement, and the ladder
    `kalshi_occurrence_start` measured (21:45 → 18:45 → 15:45) cannot start here.
    """
    candidates = {}
    for event in events or ():
        try:
            if is_expiration_start_candidate(event):
                event_id = getattr(event, "id", None)
                if event_id is not None:
                    candidates.setdefault(event_id, event)
        except Exception:  # noqa: BLE001 — see the gotcha #42 note above
            continue
    if not candidates:
        return 0

    try:
        from sqlalchemy import select

        from app.models.models import FuturesMarket

        result = await session.execute(
            select(
                FuturesMarket.event_id,
                FuturesMarket.external_id,
                FuturesMarket.expiration_time,
            )
            .where(
                FuturesMarket.event_id.in_(list(candidates)),
                FuturesMarket.source == "kalshi",
                FuturesMarket.expiration_time.isnot(None),
                FuturesMarket.external_id.isnot(None),
            )
            .order_by(FuturesMarket.event_id, FuturesMarket.external_id)
        )
        rows = result.all()
    except Exception:  # noqa: BLE001 — the page is served with the stored column
        return 0

    corrected = 0
    for event_id, external_id, expiration_time in rows:
        event = candidates.get(event_id)
        if event is None:
            continue  # already corrected on an earlier market of this event
        try:
            recovered = contest_date_behind_expiration(
                event, external_id, expiration_time
            )
            if recovered is None:
                continue
            # Stamp BEFORE correcting, never after. A row that cannot take the
            # stamp must not take the correction either — that is this module's
            # own refusal rule — and the stamp is also the whole of what makes
            # the FIRST market win rather than the last: every later row for the
            # same event fails `is_expiration_start_candidate` on it. A second
            # guard here would be dead code, which a mutation pass confirmed by
            # surviving its removal.
            setattr(event, KALSHI_EXPIRATION_RECOVERY_STAMP, True)
            apply_contest_date(event, recovered)
            corrected += 1
        except Exception:  # noqa: BLE001 — see the gotcha #42 note above
            continue
    return corrected
