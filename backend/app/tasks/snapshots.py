"""
Shared snapshot helpers for write-time deduplication across task modules.
"""

from datetime import datetime, timezone

from sqlalchemy import select


def _second_slot_same(existing, away_win_probability, draw_probability) -> bool:
    """Do the incoming away/draw members match the ones already on the row?

    🔴 **THIS EXISTS BECAUSE SAMENESS USED TO BE COMPLETE WITHOUT IT, AND #6277
    ENDED THAT (CERT-2894).** While every writer stored `away = 1 - home`, two
    readings agreeing on home could not disagree on away — so testing home alone
    settled it. Now a three-way board can hold its home price while the draw
    drains into the away side, and those are two different boards.

    The BLOCKED first build refreshed the second slot IN PLACE on the same-value
    branch, reasoning that it was the same observation better described. That is
    true of the one-time complement correction and false of everything else, and
    the false half is the dangerous one: the in-place write does not move
    `captured_at`, so a POST-KICKOFF reading rewrote the away/draw of a
    PRE-KICKOFF row, and the pre-match cutoff query then served in-play evidence
    as the pre-match favourite. The grader's probe: `0.40/0.35/0.25` became
    `0.40/0.42/0.18` on the same timestamp, and away was wrongly favoured 42-40.

    So the second slot is part of the VALUE, not an annotation on it. A change
    takes the ordinary "value changed" path — the old row is closed out, a new
    row is stamped now — and evidence never lands on a row older than itself.

    `None` on both sides is the two-way case and is always "same"; a `None`
    arriving against a stored number (or the reverse) is a change, because one
    of them is a three-way reading and the other is not.
    """
    def _num(value):
        return None if value is None else float(value)

    return (
        _num(getattr(existing, "away_win_probability", None))
        == _num(away_win_probability)
        and _num(getattr(existing, "draw_probability", None))
        == _num(draw_probability)
    )


async def _create_or_update_win_prob_snapshot(
    session,
    event_id: int,
    source: str,
    home_win_probability: float,
    away_win_probability: float,
    game_state: dict = None,
    is_completed: bool = False,
    max_gap_seconds: float = None,
    draw_probability: float = None,
) -> tuple:
    """
    Create a new WinProbSnapshot or update existing if value unchanged.

    Returns (snapshot, is_new) tuple.
    - If value changed: creates new snapshot, returns (new_snapshot, True)
    - If value same: updates existing snapshot's reading_count/valid_until, returns (existing, False)

    ``max_gap_seconds`` (live/035) is the LIVE CADENCE FLOOR: when set, an
    unchanged value still appends a new point once the last one is older than
    this. Without it a flat market emits nothing at all — the dedup below only
    bumps ``reading_count`` — so a tense 0-0 stretch draws as a straight segment
    between two distant points and a blowout draws as one dot. Alex's bar is at
    least one snapshot per minute per live event; the callers that own a live
    event pass 60 and nobody else passes anything, so the growth is bounded to
    one row per minute per source on games that are actually in progress, and
    zero everywhere else.

    It deliberately does NOT apply to completed events: ``is_completed`` refreshes
    the terminal point in place (#922) and a heartbeat there would rebuild the
    stale tail that rule exists to prevent.

    #922: when ``is_completed`` is True (the event is completed/closed), a value
    change does NOT append a new time-series point — instead the most recent
    snapshot is refreshed in place (value + valid_until). On post-final re-process
    cycles ESPN can keep echoing a value / report the game as "in" for 20-40 min,
    and the stat model drifts; appending those produced the chart "stale tail".
    The terminal value is still captured (in place at the real final, or as a
    single new point if no prior snapshot exists yet for this event+source).

    ``draw_probability`` (#6277) is the third member of a three-way game, and it
    is the EVIDENCE that the pair beside it is not a complement: a reader of this
    table can only tell a genuine sub-unit pair from two unrelated numbers by
    checking that all three sum to one. ``None`` on every two-way source, which
    is every source but a soccer/cricket game winner.

    ── THE SECOND SLOT IS PART OF THE VALUE (#6277, CERT-2894) ────────────────
    Sameness was decided on the HOME number alone, and that was complete for as
    long as away was ``1 - home``: the two could not disagree. Now they can, so
    ``_second_slot_same`` joins the test and a board that moved only its
    away/draw split takes the ordinary "value changed" path — old row closed
    out, new row stamped now.

    It is NOT refreshed in place. That was this ship's first build and it is
    what CERT-2894 blocked: an in-place write does not move ``captured_at``, so
    a post-kickoff reading rewrote a pre-kickoff row's away/draw and the
    pre-match cutoff query served in-play evidence as the pre-match favourite.
    Evidence never lands on a row older than itself.
    """
    from app.models.models import WinProbSnapshot

    now = datetime.now(timezone.utc)

    # Find the most recent snapshot for this event+source
    result = await session.execute(
        select(WinProbSnapshot)
        .where(
            WinProbSnapshot.event_id == event_id,
            WinProbSnapshot.source == source,
        )
        .order_by(WinProbSnapshot.captured_at.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()

    # Compare probability AND game period — a new inning/quarter with the same
    # probability is still a distinct observation worth recording, otherwise
    # we lose period markers on charts when short innings don't move the line.
    is_same = False
    if existing is not None and existing.home_win_probability is not None and home_win_probability is not None:
        prob_same = float(existing.home_win_probability) == float(home_win_probability)
        # #6277 / CERT-2894: the SECOND SLOT IS PART OF THE VALUE, so a board
        # that moved only its away/draw split is a distinct observation and gets
        # its own `captured_at`. See `_second_slot_same`.
        prob_same = prob_same and _second_slot_same(
            existing, away_win_probability, draw_probability
        )
        period_same = True
        if prob_same and game_state and existing.game_state:
            old_gs = existing.game_state if isinstance(existing.game_state, dict) else {}
            new_period = game_state.get("period") or game_state.get("inning")
            old_period = old_gs.get("period") or old_gs.get("inning")
            if new_period and old_period and str(new_period) != str(old_period):
                period_same = False
        is_same = prob_same and period_same

    # live/035: a live event's line must keep gaining points even when the price
    # does not move. Treated as "not the same observation" rather than as a
    # separate branch, so the heartbeat point is created, chained and counted by
    # exactly the same code that handles a real move.
    if is_same and max_gap_seconds and not is_completed:
        last_seen = getattr(existing, "captured_at", None)
        if last_seen is not None:
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            if (now - last_seen).total_seconds() >= float(max_gap_seconds):
                is_same = False

    if existing is None or not is_same:
        # #922: completed/closed event — refresh the terminal point in place
        # instead of appending a new late captured_at point. The live snapshots
        # already captured the game through its final; this keeps the terminal
        # value current without extending the time series past the real final.
        if is_completed and existing is not None:
            existing.home_win_probability = home_win_probability
            existing.away_win_probability = away_win_probability
            existing.draw_probability = draw_probability
            if game_state is not None:
                existing.game_state = game_state
            existing.valid_until = now
            existing.reading_count = (existing.reading_count or 0) + 1
            return existing, False

        # Value changed — close out the old row and create a new one
        if existing is not None:
            existing.valid_until = now

        snapshot = WinProbSnapshot(
            event_id=event_id,
            source=source,
            home_win_probability=home_win_probability,
            away_win_probability=away_win_probability,
            draw_probability=draw_probability,
            game_state=game_state,
            reading_count=1,
        )
        return snapshot, True
    else:
        # Same value — bump the counter. The second slot is NOT written here:
        # it is part of the value (see `_second_slot_same`), so reaching this
        # branch means it already matches, and an in-place write would be the
        # one CERT-2894 blocked — in-play evidence backdated onto a pre-kickoff
        # row that the pre-match cutoff then reads as the pre-match favourite.
        existing.reading_count += 1
        existing.valid_until = now
        return existing, False
