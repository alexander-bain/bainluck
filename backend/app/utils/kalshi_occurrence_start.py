"""Recover a soccer kick-off from the Kalshi instant we mistook for one (#5905).

**SHIP: the Europa League page stops showing the same tie twice — once priced at
the right hour and once, three hours later, as a dead card with no crest and no
number.** (Pillar: MATCHING.)

──────────────────────────────────────────────────────────────────────────────
WHAT A READER SEES
──────────────────────────────────────────────────────────────────────────────
Alex, LOOKing at `/sports/soccer_uefa_europa_league` on 2026-09-13: **6 of the 24
"Upcoming" cards are ghosts — one in four.** Every one of them is a second card
for a tie already on the page, sitting exactly three hours later:

    Omonoia FC v Celta Vigo      32/68   Sep 16 09:45   <- the real card
    Omonia Nicosia v Celta Vigo  no price Sep 16 12:45  <- the ghost

On La Liga it is worse, because next weekend's fixtures have no second card to
give the game away: **Sevilla v Barcelona is advertised at 22:00Z for a 19:00Z
kick-off, and the Madrid derby at 17:15Z for 14:15Z.** A reader looking up the
derby is told 10:15 AM PT for a game that starts at 7:15 AM PT.

──────────────────────────────────────────────────────────────────────────────
THE CAUSE IS ONE FIELD WE READ AS SOMETHING IT IS NOT
──────────────────────────────────────────────────────────────────────────────
`app/tasks/kalshi.py::_earliest_start` prefers Kalshi's `occurrence_datetime`
over `close_time` for a dated fixture, on the documented belief (#3488/#3544,
restated in `event_completion.KALSHI_OCCURRENCE_COMMENCE_SOURCE`) that it is
"the hour the venue says the thing STARTS". That belief was a large improvement
over `close_time` — a multi-day settlement backstop, +3d NFL, +14d UFC — and it
is still wrong about what the field holds.

**READ AT THE VENUE 2026-09-13 (notice 26: the venue's own API, by series
discovery, not our tables), `occurrence_datetime` is byte-identical to
`expected_expiration_time` on every market returned**, and it is the *expected
expiration* — when the contract is expected to resolve, i.e. after the thing has
FINISHED:

    series           ticker                      occurrence == expected_exp   real start
    KXLALIGAGAME     …-26SEP20VCFRSO             2026-09-20T22:00Z            19:00Z
    KXSERIEAGAME     …-26SEP20ACMLEC             2026-09-20T21:45Z            18:45Z
    KXEPLGAME        …-26SEP20FULMUN             2026-09-20T18:30Z            15:30Z
    KXLIGUE1GAME     …-26SEP20OLMPSG             2026-09-20T21:45Z            18:45Z
    KXNFLGAME        …-26SEP20INDKC              2026-09-21T03:20Z            00:20Z

Kalshi publishes **no kick-off field at all**: the event payload carries only
`sub_title` "VCF vs RSO (Sep 20)" — a date. So the hour cannot be *derived* from
the venue, only *recovered*, and that is what this module does.

──────────────────────────────────────────────────────────────────────────────
THE PAD IS EXACT, WHICH IS WHY RECOVERING IT IS NOT A GUESS
──────────────────────────────────────────────────────────────────────────────
Measured on production 2026-09-13 against rows a SCHEDULE PROVIDER anchored
(`external_id IS NOT NULL`, i.e. the side that is not in question):

    ghost.commence_time - real.commence_time   rows
    ──────────────────────────────────────────────
    180 minutes                                  11
    anything else                                 0

Eleven of eleven, to the minute, across Ligue 1, La Liga, Serie A, the Europa
League, Copa Libertadores and Copa Sudamericana. Not a mean, not a mode with a
tail — a single value, because it is a constant the venue applies rather than an
estimate it makes.

🔴 **SOCCER ONLY, AND THE GATE IS LOAD-BEARING.** The same census over MMA
returns 255, 265, 275, 285, 295 and 345 minutes — a spread, because a fight
card's expected expiration tracks a card that runs long, not a fixed whistle.
Boxing returns ~14 days (those markets kept `close_time`). A pad that is exact
for soccer is a fabrication anywhere else, so this module refuses every other
sport rather than inheriting one sport's constant into all of them.

──────────────────────────────────────────────────────────────────────────────
WHAT THIS DOES NOT DO
──────────────────────────────────────────────────────────────────────────────
**It writes nothing.** It is a serve-time reading, in the same spirit as — and
consumed by — `event_twin_fold`, which says it best: the duplicate rows stay in
the database exactly as they are, visible to the Grid and Flow sentinels and to
#2693. Ruling 048 is untouched: no row absorbs another, no id-less claim is
promoted, and every scrap of provider-id evidence survives for the id-anchored
drain that is the durable repair.

**It never moves a row a schedule provider has stamped.** `external_id` set
means Odds API or ESPN reported the start; that time is a reported start and
this module leaves it alone. The only rows it touches are the ones whose hour
came from the instant described above and nowhere else.

**It cannot break a fold that works today.** The census above has no 0-minute
bucket: not one Kalshi-timed soccer row currently shares a minute with its twin,
so there is no correct fold for a shift to spoil. It can only create folds.

Refs #5905, #2693. Root cause of the ghost half of #5896's class.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

__all__ = [
    "KALSHI_DERIVATIVE_SERIES_EXCESS",
    "KALSHI_EXPECTED_EXPIRATION_PAD",
    "KALSHI_MEASURED_SOCCER_LEAGUE_PREFIXES",
    "KALSHI_OCCURRENCE_TIMED_SOURCES",
    "KALSHI_RECOVERY_STAMP",
    "KALSHI_SOCCER_DERIVATIVE_KINDS",
    "kalshi_derivative_series_excess",
    "kalshi_game_scale_commence",
    "kalshi_occurrence_hour_is_recoverable",
    "kalshi_occurrence_scheduled_start",
    "loaded_sport_key",
    "recover_kalshi_occurrence_starts",
]

#: What Kalshi's `occurrence_datetime` (== `expected_expiration_time`) sits AFTER
#: a soccer kick-off. Venue-read and census-measured above: 180 minutes, exactly,
#: on 11 of 11 anchored comparisons and on five series read at the venue.
#:
#: Not a tolerance and not a knob. If a future measurement finds a second value,
#: the answer is a per-competition table with its own census — never a widening
#: of this one, which would turn an exact recovery into an approximate one.
KALSHI_EXPECTED_EXPIRATION_PAD = timedelta(hours=3)

#: The `commence_time_source` values that mean "this hour came from Kalshi's
#: expected-expiration instant".
#:
#: `kalshi` is here because the auto-create path stamps `identity.claim.source`,
#: which is the bare provider name — all 29 reader-visible ghosts carry it.
#: `kalshi_occurrence` is the explicit label
#: (`event_completion.KALSHI_OCCURRENCE_COMMENCE_SOURCE`) and means the same
#: instant by construction.
#:
#: `kalshi_ticker` is deliberately ABSENT. That provenance is a DATE parsed out
#: of a ticker and resolves to midnight UTC — it is not this instant, it is not
#: three hours after anything, and subtracting a pad from it would move a
#: stand-in to 21:00 the previous day and call it a kick-off.
KALSHI_OCCURRENCE_TIMED_SOURCES = frozenset({"kalshi", "kalshi_occurrence"})

#: The unmapped attribute :func:`recover_kalshi_occurrence_starts` stamps on a row
#: it has already corrected, so a second pass over the same objects leaves them
#: alone.
#:
#: **THIS IS NOT BELT-AND-BRACES — WITHOUT IT THE RECOVERY IS NOT IDEMPOTENT AND
#: ONE LIVE ROUTE ALREADY FOLDS TWICE.** The function keys on
#: `commence_time_source`, which it does not change, so on a second pass the row
#: still looks exactly like one needing a pad subtracted and it subtracts another
#: (authority/179 measured the ladder: 21:45 → 18:45 → 15:45 → 12:45).
#: `/api/leagues/{sport_key}` passes the SAME upcoming row objects through
#: :func:`app.utils.event_twin_fold.fold_twin_events` twice in one request —
#: `league_futures.py` `_folded_upcoming(_g_events)` and then
#: `_folded_past_rails(..., _g_events)` — with no re-query between them.
#:
#: 🔴 **THIS STAMP IS THE SOLE GUARD ON THAT ROUTE, AND IT IS LOAD-BEARING
#: TODAY.** Until 2026-09-13 this note said the double fold was "latent only
#: because `upcoming_games_query` is a bare `select(Event)` with no
#: `selectinload(Event.sport)`", so :func:`loaded_sport_key` answered ``None``
#: and nothing fired. That has been FALSE since #5918: `eda376abc` (08:34Z)
#: wrote the sentence and `0ccf6e77c` (09:19Z) added the eager load 45 minutes
#: later — it is `league_futures.py`'s `upcoming_games_query`, on the
#: `.options(selectinload(Event.sport))` line. The recovery therefore DOES fire
#: on that route, the second fold is real, and the only thing standing between a
#: reader and a kick-off advertised SIX hours early is this attribute.
#: Measured holding on production 2026-09-13 21:5xZ (lane1/299, #5998): the page
#: served `19:00:00Z` — one subtraction, not two. Delete this stamp, or let a
#: caller hand the recovery freshly-queried objects twice, and the ladder
#: authority/179 measured returns: 21:45 → 18:45 → 15:45 → 12:45.
#:
#: Line numbers are deliberately not quoted here: the previous version of this
#: note pinned `:2483`/`:2543` and both had moved within the day.
#:
#: An unmapped attribute is the right sentinel because its lifetime is exactly
#: the lifetime of the reading it guards: it lives on the hydrated instance, dies
#: with the request, and is cleared by the same expiry that would reload
#: `commence_time` from the database. Nothing is written, and the mapper never
#: sees it — a name it does not map is not a column it can flush (gotcha #4).
KALSHI_RECOVERY_STAMP = "_bl_kalshi_occurrence_start_recovered"


#: How much LATER a soccer DERIVATIVE series publishes its occurrence than the
#: GAME series does for the very same fixture.
#:
#: 🔴 **THIS IS WHY THE PAD ABOVE LOOKED BIMODAL, AND IT IS NOT A SECOND PAD.**
#: #6715 measured the ghost/real delta as 180 minutes x10 and 240 minutes x2 and
#: recorded the 240 as an unexplained second value — which would have been
#: "answered" either by widening :data:`KALSHI_EXPECTED_EXPIRATION_PAD` (forbidden
#: above, and the wrong shape) or by the per-competition table that note
#: prescribes (which cannot work: La Liga produces BOTH values).
#:
#: The specimen refutes the competition theory inside one event id. `15312871`
#: (Levante v Bilbao, stored 23:30Z, true kick-off 19:30Z) holds four Kalshi
#: markets and they do not agree with each other:
#:
#:     KXLALIGAGAME-26SEP16LEVATH     22:30Z   <- kick-off + 180, the pad is EXACT
#:     KXLALIGATOTAL-26SEP16LEVATH    23:30Z
#:     KXLALIGASPREAD-26SEP16LEVATH   23:30Z
#:     KXLALIGABTTS-26SEP16LEVATH     23:30Z
#:
#: The event took the derivative's hour, so the 3h recovery landed it at 20:30Z
#: against a 19:30Z kick-off and `fold_twin_events` then correctly refused the
#: pair — a duplicate card in the La Liga "No result reported" rail (#6715).
#:
#: Read at the venue 2026-09-17 (notice 26, series discovery, pairing each
#: derivative event ticker to its own fixture's GAME ticker):
#:
#:     league          fixtures    BTTS      SPREAD    TOTAL
#:     KXLALIGA            10      +60 x10   +60 x10   +60 x10
#:     KXEPL               10      +60 x10   +60 x10   +60 x10
#:     KXSERIEA            10      +60 x10   +60 x10   +60 x10
#:     KXLIGUE1             9      +60 x9    +60 x9    +60 x9
#:     KXMLS               16      +60 x16   +60 x16   +60 x16
#:     KXEREDIVISIE         9       --       +60 x9    +60 x9
#:
#: **183 of 183 comparisons at exactly +60 minutes; zero exceptions.** Six
#: independent league families, three derivative kinds. That is the same
#: character as the 11-of-11 census behind the pad above — a single value to the
#: minute, because it is a constant the venue applies rather than an estimate it
#: makes. So BOTH values are exact and the discriminator is the series KIND:
#: `…GAME` is kick-off +180, `…TOTAL`/`…SPREAD`/`…BTTS` is kick-off +240.
KALSHI_DERIVATIVE_SERIES_EXCESS = timedelta(minutes=60)

#: The derivative series kinds the census above covers.
#:
#: `BTTS` ("both teams to score") is soccer by construction, but `TOTAL` and
#: `SPREAD` are not — Kalshi runs those shapes over several sports, and an
#: NFL spread's expected expiration tracks a game that can run long. Nothing here
#: is inherited into those: the league gate below is what keeps this measurement
#: inside the population it was taken on, exactly as `_soccer` does for the pad.
KALSHI_SOCCER_DERIVATIVE_KINDS = ("TOTAL", "SPREAD", "BTTS")

#: The soccer league series families the +60 census above actually measured.
#:
#: An ALLOWLIST rather than a pattern, and the distinction is the whole safety
#: argument: `^KX[A-Z]+(TOTAL|SPREAD)-` is a grammar, and a grammar reaches every
#: sport Kalshi ever gives that shape to — including the NFL and MMA series whose
#: spread this constant is measured to be WRONG about. A league absent here is not
#: asserted to be 0; it is UNMEASURED, and it is left exactly as it is until
#: somebody reads it at the venue and adds it. KXUCL, KXUEL, KXBUNDES, KXLIGAMX
#: and six more were probed the same day and had no open GAME market to pair
#: against — unpaired, not disagreeing.
KALSHI_MEASURED_SOCCER_LEAGUE_PREFIXES = frozenset(
    {"KXLALIGA", "KXEPL", "KXSERIEA", "KXLIGUE1", "KXMLS", "KXEREDIVISIE"}
)

#: Every measured `<league><kind>` series, precomputed. Membership is tested by
#: EQUALITY against the ticker's series segment — never by `startswith` — so a
#: longer series that merely opens with a measured name (a hypothetical
#: `KXEPLTOTALCORNERS`) is a miss and is left alone, which is the safe answer.
_KALSHI_MEASURED_DERIVATIVE_SERIES = frozenset(
    league + kind
    for league in KALSHI_MEASURED_SOCCER_LEAGUE_PREFIXES
    for kind in KALSHI_SOCCER_DERIVATIVE_KINDS
)


def kalshi_derivative_series_excess(ticker: Optional[str]) -> timedelta:
    """How much later than the GAME series this ticker's occurrence sits.

    :data:`KALSHI_DERIVATIVE_SERIES_EXCESS` for a measured soccer derivative
    series, and a zero timedelta for everything else — which is the answer for
    the overwhelming majority of tickers and always means "leave this alone".
    Pure: no DB, no clock, no I/O.

    Returning a zero timedelta rather than ``None`` is deliberate: the caller
    subtracts it, so an unmeasured series costs one subtraction of nothing
    instead of a branch that a later edit can forget to write.
    """
    if not isinstance(ticker, str) or "-" not in ticker:
        return timedelta(0)
    series = ticker.split("-", 1)[0]
    if series in _KALSHI_MEASURED_DERIVATIVE_SERIES:
        return KALSHI_DERIVATIVE_SERIES_EXCESS
    return timedelta(0)


def kalshi_game_scale_commence(market: Any) -> Any:
    """``market.commence_time`` expressed on the GAME series' clock.

    The value is returned UNCHANGED — including ``None``, and including anything
    that is not a datetime — unless the market is a Kalshi row whose ticker names
    one of the measured soccer derivative series, in which case the measured hour
    of venue excess comes off it. Pure: no DB, no clock, no I/O.

    **This normalises what an EVENT is minted with, not what the MARKET stores.**
    A derivative market's own `commence_time` is the venue's honest occurrence for
    that series and other readers are entitled to it; what is wrong is letting
    that series' clock become the fixture's kick-off, because every consumer
    downstream — `recover_kalshi_occurrence_starts` above, the twin fold, the
    "starts in" line — reasons with the GAME series' 180-minute pad. Putting the
    instant on the GAME scale HERE means the pad stays exact and nothing
    downstream needs to learn a second constant.
    """
    commence = getattr(market, "commence_time", None)
    if not isinstance(commence, datetime):
        return commence
    if getattr(market, "source", None) != "kalshi":
        return commence
    return commence - kalshi_derivative_series_excess(
        getattr(market, "external_id", None)
    )


def _soccer(sport_key: Optional[str]) -> bool:
    """Our `sports.key` vocabulary spans ~40 soccer keys and grows per league.

    A prefix test rather than a set, for the reason
    `stamp_v1_statpal_fixtures.SOCCER.sport_key_is_prefix` gives: the league
    vocabulary is the widest we have and any enumeration of it is stale the week
    a competition is added.
    """
    return bool(sport_key) and sport_key.startswith("soccer")


def kalshi_occurrence_hour_is_recoverable(sport_key: Optional[str]) -> bool:
    """Is a Kalshi occurrence hour convertible to a real start for this sport?

    The same question :func:`kalshi_occurrence_scheduled_start` answers about a
    ROW, asked about a SPORT alone — for callers that must decide before they
    have a row, or that want to refuse rather than read. Pure: no DB, no clock,
    no I/O. Fails CLOSED: ``None``, an empty key and every unmeasured sport are
    ``False``.

    🔴 **THIS IS A WRITE GATE, NOT A DISPLAY ONE (#3565, CERT-3342).** Everything
    above this line is serve-time: it corrects a hydrated row on its way to a
    reader, writes nothing, and a wrong answer lasts one request. A task that
    copies an occurrence hour into ``events.commence_time`` is different in kind
    — it persists the value, the source stamp then says the venue published it
    as a start, and no later reader can tell the difference. So a writer asks
    this FIRST and declines when it is ``False``.

    The distinction that makes the refusal necessary: ``occurrence_datetime`` is
    byte-identical to ``expected_expiration_time`` (the venue read at the top of
    this module), so it is never a kick-off anywhere — it is only *recoverable*
    where the pad from the real start has been measured and found exact.
    :data:`KALSHI_EXPECTED_EXPIRATION_PAD` is that measurement and it is soccer's
    alone: 180 minutes on 11 of 11 anchored rows, against 255/265/275/285/295/345
    for MMA and ~14 days for boxing. **Tennis has no measurement at all** —
    CERT-3342's specimen 15317314 stored 09:10Z for play in the 07:00Z hour — so
    a tennis occurrence written as a start is an expiration wearing a kick-off's
    label, which is the exact defect #5905 was filed for.

    Widening this is a census, never an edit. Adding a sport means measuring its
    ghost/real delta the way the module header does and finding a SINGLE value;
    a spread means there is no pad to recover and the answer stays ``False``.
    """
    return _soccer(sport_key)


def kalshi_occurrence_scheduled_start(
    event: Any, sport_key: Optional[str]
) -> Optional[datetime]:
    """The kick-off behind a Kalshi expected-expiration hour, or ``None``.

    ``None`` means "this row's time is not the instant this module knows how to
    read — leave it exactly as it is", and it is the answer for the overwhelming
    majority of rows. Pure: no DB, no clock, no I/O.

    ``sport_key`` is passed IN rather than read off ``event.sport`` on purpose.
    The caller is a serve-time fold wrapped in a bare ``except`` (gotcha #42), so
    touching an unloaded relationship here would not raise loudly — it would
    disable the whole fold and serve today's page. The caller resolves the key
    from what it has actually loaded, and passes ``None`` when it cannot.
    """
    if not _soccer(sport_key):
        return None
    if getattr(event, "external_id", None) is not None:
        return None  # a schedule provider reported this start; it is not ours to move
    source = getattr(event, "commence_time_source", None)
    if source not in KALSHI_OCCURRENCE_TIMED_SOURCES:
        return None
    commence = getattr(event, "commence_time", None)
    if not isinstance(commence, datetime):
        return None
    return commence - KALSHI_EXPECTED_EXPIRATION_PAD


def loaded_sport_key(event: Any) -> Optional[str]:
    """``event.sport.key`` when it is already in memory, else ``None``.

    Public because it has a second caller: the soccer gate in
    `#5918`'s name-pair fold (authority/179) needs exactly this answer, and two
    copies of a lazy-safe relationship read is how one of them rots.

    Most serve paths `selectinload(Event.sport)`, but not all of them, and a lazy
    load from here would emit IO inside a stage every caller wraps in a bare
    ``except`` (gotcha #42) — so a page would silently stop being corrected
    rather than fail loudly. `inspect(...).unloaded` answers without touching the
    attribute, and anything unexpected reads as "not loaded", which is the safe
    answer: the row is left exactly as the database has it.
    """
    try:
        from sqlalchemy import inspect as _sa_inspect

        if "sport" in _sa_inspect(event).unloaded:
            return None
    except Exception:  # noqa: BLE001 — a plain object (a test double) is fine
        pass
    try:
        key = getattr(getattr(event, "sport", None), "key", None)
    except Exception:  # noqa: BLE001 — a lazy load that raises is "not loaded"
        return None
    return key if isinstance(key, str) else None


#: The name this function had while it had one caller. Kept so a branch based on
#: that sha keeps importing successfully; new callers use the public name.
_loaded_sport_key = loaded_sport_key


def recover_kalshi_occurrence_starts(events: Any) -> int:
    """Put the kick-off back on every row holding an expected expiration.

    Returns how many rows were corrected. **Serve-time only: this writes nothing
    to the database.** `set_committed_value` places the value on the hydrated row
    without marking it dirty (gotcha #4), exactly as the twin fold already does
    for its unioned `win_probability_sources`, so no later flush can persist a
    served reading back into `events`.

    Correcting the ROW rather than only the fold's key is deliberate and is most
    of this ship. Measured on production 2026-09-13, **16 of the 29
    reader-visible ghosts have no twin at all** — nine of them next weekend's La
    Liga, where Kalshi lists before Odds API does and ours is the only row there
    is. A fold cannot help those; they are not duplicated, they are simply shown
    at the wrong hour, and Sevilla v Barcelona and the Madrid derby are among
    them. Only the row's own served time reaches that reader.

    It is best-effort per row (gotcha #42): one row that cannot be read must
    never cost the page its other corrections.

    **It is idempotent, and that is load-bearing rather than tidy.** Callers hand
    the same row objects to the fold more than once — `/api/leagues` does it
    twice in one request — and the test this function applies (a
    `commence_time_source` it does not change) is still true of a row it has
    already corrected, so an unguarded second pass subtracts a second pad and
    advertises a kick-off six hours early. :data:`KALSHI_RECOVERY_STAMP` carries
    the reasoning and the measured ladder. The returned count is corrections
    MADE, so a second pass over corrected rows returns 0 — a caller reporting
    "rows fixed" never double-counts one row.
    """
    corrected = 0
    for event in events or ():
        try:
            if getattr(event, KALSHI_RECOVERY_STAMP, False):
                continue  # already recovered in this request; see the stamp's note
            recovered = kalshi_occurrence_scheduled_start(
                event, loaded_sport_key(event)
            )
            if recovered is None:
                continue
            # Stamp BEFORE correcting, never after. A row that cannot take the
            # stamp cannot take the correction either (the non-ORM arm of
            # `_set_served_commence_time` is a plain assignment), so raising here
            # skips it entirely — which is this function's own refusal rule:
            # serving the stored hour is today's bug, serving a twice-padded one
            # would be a new and worse one.
            setattr(event, KALSHI_RECOVERY_STAMP, True)
            _set_served_commence_time(event, recovered)
            corrected += 1
        except Exception:  # noqa: BLE001 — see the gotcha #42 note above
            continue
    return corrected


def _is_orm_instance(event: Any) -> bool:
    try:
        from sqlalchemy import inspect as _sa_inspect
        from sqlalchemy.orm.state import InstanceState

        return isinstance(_sa_inspect(event, raiseerr=False), InstanceState)
    except Exception:  # noqa: BLE001 — no SQLAlchemy opinion means not an ORM row
        return False


def _set_served_commence_time(event: Any, value: datetime) -> None:
    """Place a served reading on the row without making it a pending write.

    The branch is not defensive clutter — the two arms are the whole safety
    argument, and getting it backwards is the failure this function exists to
    avoid:

    * an ORM row takes `set_committed_value`, which loads the value into the
      instance as though the database had returned it, so the row is never
      marked dirty and no later flush on this session can persist a serve-time
      reading into `events` (gotcha #4, and the same call the twin fold already
      makes for its unioned sources);
    * anything else — a test double, a detached row object — takes a plain
      assignment, because `set_committed_value` needs instance state it has not
      got and would raise.

    A plain assignment on an ORM row WOULD mark it dirty, which is exactly the
    accident that turns "we read this differently" into "we wrote this down".
    """
    if _is_orm_instance(event):
        from sqlalchemy.orm.attributes import set_committed_value

        set_committed_value(event, "commence_time", value)
        return
    event.commence_time = value
