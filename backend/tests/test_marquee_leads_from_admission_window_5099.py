"""T4-A1 (#5099) — tonight's marquee game leads from the moment it is admitted.

THE SHIP
--------
A reader who opens Discover six hours before the night's marquee game finds it
in the first three cards. Before this, it was on the page from T-6h but was not
SEATED until T-4h, and its placement in between was whatever the diversity pass
happened to do with it.

THE TWO DEFECTS, BOTH MEASURED BEFORE THEY WERE FIXED
-----------------------------------------------------
1. **Two clocks in one selection decision.** ``apply_discover_display_chain``
   threaded its ``now`` to ``_imminent_marquee_kickoff_ids`` (admission) and NOT
   to ``compose_lead`` (seating), which fell back to the wall clock. In
   production the two agree, so no reader saw it. Every fixed-clock caller —
   the admin ratification instrument, and the T-6h/T-1h/live acceptance
   evidence this issue asks for — got a chain whose lead pass had silently
   no-opped, because the fixtures' kickoff times were computed from the fixed
   clock and read against the real one. Reproduced by running the real chain at
   ``NOW`` and watching ``compose_lead`` make no change to the first six slots.

2. **Two windows.** ``_DISCOVER_IMMINENT_KICKOFF_HOURS = 6`` decided what
   SURVIVED; ``SOON_WINDOW_HOURS = 4`` decided what LED. Measured on the real
   chain with defect 1 worked around: the specimen sat at rank 3 at T-6h, T-5h
   and T-4.5h — placed there by ``diversify_discover_first_page``, not by any
   pass that meant to — and reached rank 1 only at T-3h when the lead pass's own
   window opened.

THE FIX IS ONE SELECTION DECISION WITH TWO CONSUMERS, not a wider window.
``SOON_WINDOW_HOURS`` is C185's contract and governs every routine game; the
admission arm's chosen set is handed to the lead pass instead, the same shape
#4898 used for its two deleting passes.

Every fixture offsets from ``NOW`` and every pass is handed it explicitly, so
nothing here branches on the clock (gotcha #44).
"""

import copy
from datetime import datetime, timedelta, timezone

import pytest

from app.routes.feed import (
    _DISCOVER_IMMINENT_KICKOFF_HOURS,
    _DISCOVER_IMMINENT_MARQUEE_SLOTS,
    apply_discover_display_chain,
)
from app.utils.personalization import PersonalizationContext
from app.utils.tonights_games import (
    MAX_LEAD,
    SOON_WINDOW_HOURS,
    compose_lead,
    select_tonights_games,
)

NOW = datetime(2026, 9, 10, 19, 42, 0, tzinfo=timezone.utc)

#: The production specimen from #4898 — SF @ LAR, tier:1 primetime.
SPECIMEN_ID = 14632820

#: Its measured pre-kickoff feed score. Deliberately LOW: the whole point is
#: that a pre-game card cannot earn excitement, so the arm must carry it.
PREGAME_SCORE = 40


def _game(
    *,
    event_id: int = SPECIMEN_ID,
    score: int = PREGAME_SCORE,
    hours_to_kickoff: float = 5.0,
    tier: str = "tier:1",
    media: bool = True,
    status: str = "scheduled",
) -> dict:
    data = {
        "id": event_id,
        "sport": "americanfootball_nfl",
        "status": status,
        "event_tags": [tier, "class:pro_major", "timing:primetime"],
        "home_team": "Los Angeles Rams",
        "away_team": "San Francisco 49ers",
        "commence_time": (NOW + timedelta(hours=hours_to_kickoff))
        .isoformat()
        .replace("+00:00", "Z"),
    }
    if media:
        data["home_team_data"] = {"logo": "h"}
        data["away_team_data"] = {"logo": "a"}
    return {
        "type": "event",
        "score": score,
        "_rank_score": float(score),
        "_sort_time": 0,
        "headline": None,
        "data": data,
    }


def _futures(i: int, score: float = 95.0) -> dict:
    """A futures card that outscores the pre-game game card, and SPEAKS.

    The captions matter: a silent futures card is an offender to the first-page
    quality floor, which would swap it out and hand this file a page whose
    ordering came from the floor rather than from the lead pass.
    """
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "headline": f"f{i}",
        "context_summary": f"moved {i} points today",
        "reason": f"r{i}",
        "data": {"id": 90_000 + i, "name": f"market {i}"},
    }


def _run_chain(pool: list[dict], *, now: datetime = NOW, limit: int = 20):
    """The REAL served chain at a fixed clock. Deep-copies (gotcha #6)."""
    return apply_discover_display_chain(
        copy.deepcopy(pool),
        limit=limit,
        ctx=PersonalizationContext(),
        event_pct=0.15,
        now=now,
    )


def _event_ids(items: list[dict]) -> list[int]:
    return [
        (it.get("data") or {}).get("id") for it in items if it.get("type") == "event"
    ]


def _rank_of(items: list[dict], event_id: int) -> int | None:
    for position, item in enumerate(items, start=1):
        if item.get("type") == "event":
            if (item.get("data") or {}).get("id") == event_id:
                return position
    return None


# ── the ship: T-6h / T-1h / live, on the real chain, at a fixed clock ────────


@pytest.mark.parametrize(
    "label,hours,status,score",
    [
        ("T-6h", float(_DISCOVER_IMMINENT_KICKOFF_HOURS), "scheduled", PREGAME_SCORE),
        ("T-5h", 5.0, "scheduled", PREGAME_SCORE),
        ("T-4h30m", 4.5, "scheduled", PREGAME_SCORE),
        ("T-1h", 1.0, "scheduled", PREGAME_SCORE),
        ("T-35m", 0.583, "scheduled", 75),
        ("live", 0.0, "live", 98),
    ],
)
def test_the_marquee_game_is_in_the_first_three_cards(label, hours, status, score):
    """#5099's acceptance evidence: the top three, every clock from admission on.

    T-4h30m is the case that failed before this ship — inside the admission
    window, outside the lead pass's own window.
    """
    pool = [_game(hours_to_kickoff=hours, status=status, score=score)] + [
        _futures(i) for i in range(25)
    ]

    served, _meta = _run_chain(pool)
    rank = _rank_of(served, SPECIMEN_ID)

    assert rank is not None, f"{label}: the marquee card was not served at all"
    assert rank <= MAX_LEAD, (
        f"{label}: the marquee game is at rank {rank}, outside the first "
        f"{MAX_LEAD} cards — it scored {score} against futures scoring 95, "
        "which is exactly the case the admission arm exists to carry"
    )


def test_the_band_between_the_two_windows_is_the_one_that_was_broken():
    """The control that fails without the fix: T-6h..T-4h, seated vs incidental.

    Not merely "is it in the top three" — the pre-fix page ALSO had it at rank 3
    in a thin field, placed by the diversity pass. This asserts the lead pass is
    what put it there, by giving the field enough events that the diversity
    quota cannot account for the position.
    """
    assert _DISCOVER_IMMINENT_KICKOFF_HOURS > SOON_WINDOW_HOURS, (
        "this test's subject is the band between the two windows; if they are "
        "equal there is no band and the fix has been undone at the constants"
    )
    midband = (SOON_WINDOW_HOURS + _DISCOVER_IMMINENT_KICKOFF_HOURS) / 2

    pool = [_game(hours_to_kickoff=midband)] + [_futures(i) for i in range(25)]
    served, _meta = _run_chain(pool)

    assert _rank_of(served, SPECIMEN_ID) == 1, (
        f"at T-{midband}h the marquee game must LEAD, not merely appear: the "
        "admission arm kept it for this request, so the pass that decides the "
        "lead has to know that"
    )


def test_the_request_clock_reaches_the_lead_pass():
    """Defect 1, pinned directly: the chain's `now` governs seating.

    Without the thread this fails, because the fixture's kickoff is computed
    from ``NOW`` and the lead pass reads the wall clock — under which the game
    started years ago or has not been scheduled yet, either way not "tonight".
    """
    pool = [_game(hours_to_kickoff=1.0)] + [_futures(i) for i in range(25)]

    served, _meta = _run_chain(pool, now=NOW)

    assert _rank_of(served, SPECIMEN_ID) == 1, (
        "a game one hour from the REQUEST's clock must lead; if this fails the "
        "lead pass is reading some other clock than the one the chain was given"
    )


def test_a_clock_far_from_the_wall_clock_still_composes():
    """The same assertion at two anchors years apart, so neither can be the
    wall clock by accident (a fixed anchor that happens to sit near `now` would
    let the un-threaded pass pass this file)."""
    for anchor in (
        datetime(2027, 3, 2, 4, 15, 0, tzinfo=timezone.utc),
        datetime(2025, 11, 19, 23, 5, 0, tzinfo=timezone.utc),
    ):
        game = _game(hours_to_kickoff=1.0)
        game["data"]["commence_time"] = (
            (anchor + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        )
        served, _meta = _run_chain(
            [game] + [_futures(i) for i in range(25)], now=anchor
        )
        assert (
            _rank_of(served, SPECIMEN_ID) == 1
        ), f"anchored at {anchor.isoformat()} the marquee game must still lead"


# ── negative controls: what the widened window must NOT admit ────────────────


@pytest.mark.parametrize(
    "kwargs,why",
    [
        ({"tier": "tier:3"}, "a routine fixture is not marquee and never leads"),
        ({"media": False}, "a crest-less card is not a game a reader recognises"),
        (
            {"hours_to_kickoff": _DISCOVER_IMMINENT_KICKOFF_HOURS + 2},
            "a game outside the admission window is not protected by it",
        ),
    ],
)
def test_a_game_the_arm_did_not_choose_is_not_seated(kwargs, why):
    pool = [_game(**kwargs)] + [_futures(i) for i in range(25)]
    served, _meta = _run_chain(pool)
    rank = _rank_of(served, SPECIMEN_ID)
    assert rank is None or rank > MAX_LEAD, f"{why} (landed at rank {rank})"


def test_protection_widens_the_window_and_nothing_else():
    """A protected id may not smuggle a card past the OTHER eligibility gates.

    `_is_eligible` rejects finished, suspended, media-less and lagging-status
    rows. Those rejections are about what a lead card IS, not about when it
    starts, so protection must not reach them — otherwise the two selectors
    could disagree about the same card and #4898's own warning applies.
    """
    protected = {SPECIMEN_ID}
    for kwargs, why in [
        ({"status": "completed"}, "a finished game is a result, not tonight's game"),
        ({"status": "suspended"}, "a suspended match is not the game to lead with"),
        ({"media": False}, "the media bar is not a window"),
        ({"hours_to_kickoff": -1.0}, "a start time in the past is a lagging status"),
    ]:
        led = select_tonights_games(
            [_game(**kwargs)], NOW, MAX_LEAD, SOON_WINDOW_HOURS, protected
        )
        assert led == [], f"{why} — protection must not bypass this gate"


def test_a_protected_game_never_displaces_a_more_imminent_one():
    """Order inside the lead is still 'soonest first'.

    A game six hours out must not take the slot of one starting in twenty
    minutes just because the arm protected it.

    ONLY THE FAR GAME IS PROTECTED, and that asymmetry is the test. Protecting
    both made this vacuous: a mutation that sorts protected games to the front
    is a no-op when every game is protected, and it survived exactly that way
    until mutation M7 caught it. The near game needs no protection — it is
    inside ``SOON_WINDOW_HOURS`` on its own.
    """
    soon = _game(event_id=555, hours_to_kickoff=0.333, score=10)
    far = _game(event_id=SPECIMEN_ID, hours_to_kickoff=5.5, score=99)

    assert 0.333 < SOON_WINDOW_HOURS, (
        "the near game must be naturally eligible, or this test protects both "
        "and stops discriminating"
    )

    led = compose_lead([far, soon], NOW, protected_event_ids={SPECIMEN_ID})

    assert _event_ids(led)[:2] == [555, SPECIMEN_ID], (
        "the game starting in twenty minutes leads the one five and a half "
        "hours out, regardless of score or protection"
    )


def test_the_lead_is_still_capped_and_does_not_become_a_scoreboard():
    """An NFL Sunday admits three and seats three — not twelve.

    The measured population from #4898: eight kickoffs in one minute plus four
    later. Widening the seating window must not widen the cap.
    """
    pool = (
        [_game(event_id=200 + i, score=50 + i, hours_to_kickoff=5.5) for i in range(8)]
        + [
            _game(event_id=300 + i, score=60 + i, hours_to_kickoff=5.75)
            for i in range(4)
        ]
        + [_futures(i) for i in range(25)]
    )

    served, _meta = _run_chain(pool)
    games_on_page = _event_ids(served)

    assert len(games_on_page) <= _DISCOVER_IMMINENT_MARQUEE_SLOTS, (
        f"twelve marquee games produced {len(games_on_page)} cards — the cap is "
        f"{_DISCOVER_IMMINENT_MARQUEE_SLOTS} and a wider seating window must "
        "not widen it"
    )


def test_compose_lead_without_protection_is_unchanged():
    """C185's contract: the default call behaves exactly as it did.

    `protected_event_ids=None` must select the identical set as before, or this
    ship has quietly re-tuned every surface that calls the default.
    """
    pool = [
        _game(event_id=1, hours_to_kickoff=1.0),
        _game(event_id=2, hours_to_kickoff=5.0),  # outside SOON_WINDOW_HOURS
        _futures(1),
    ]
    led = compose_lead(pool, NOW)
    assert _event_ids(led)[:1] == [1]
    assert _rank_of(led, 2) is not None, "nothing is dropped by a reorder"
    assert (
        _event_ids(led).index(2) > 0
    ), "a game outside the window must not lead when nothing protected it"


# ── the failed-edition check ─────────────────────────────────────────────────


def test_a_required_marquee_that_misses_the_lead_is_reported():
    """ "A missing required marquee is a FAILED edition check, not filler."

    Forced by pinning three marquee CONCEPT cards, which outrank games in
    C185's order and legitimately take all three lead slots.
    """
    from app.utils.tonights_games import MARQUEE_PIN_KEY

    pins = []
    for i in range(MAX_LEAD):
        pin = _futures(500 + i, score=99.0)
        pin[MARQUEE_PIN_KEY] = True
        pins.append(pin)

    pool = pins + [_game(hours_to_kickoff=5.0)] + [_futures(i) for i in range(25)]
    served, meta = _run_chain(pool)

    assert (
        meta["marquee_lead_required"] == 1
    ), "the arm admitted one marquee game this request"
    assert meta["marquee_lead_shortfall"] == 1, (
        "it was admitted and did not reach the lead, which is the failed "
        f"edition check — lead holds {[i.get('type') for i in served[:MAX_LEAD]]}"
    )


def test_a_quiet_night_does_not_read_as_a_passing_check():
    """Zero shortfall with zero required is not the same fact as a pass.

    Gotcha #53: an empty result and a successful one must be distinguishable.
    """
    served, meta = _run_chain([_futures(i) for i in range(25)])

    assert meta["marquee_lead_required"] == 0
    assert meta["marquee_lead_shortfall"] == 0
    assert _event_ids(served) == [], "no games were in the pool at all"


def test_the_check_passes_when_the_marquee_does_lead():
    pool = [_game(hours_to_kickoff=5.0)] + [_futures(i) for i in range(25)]
    served, meta = _run_chain(pool)

    assert meta["marquee_lead_required"] == 1
    assert meta["marquee_lead_shortfall"] == 0
    assert _rank_of(served, SPECIMEN_ID) == 1


# ── the constants this ship depends on ───────────────────────────────────────


def test_the_admission_window_is_still_wider_than_the_lead_window():
    """If these ever equalise, the protected path stops being exercised and
    every assertion above would still pass while testing nothing."""
    assert _DISCOVER_IMMINENT_KICKOFF_HOURS > SOON_WINDOW_HOURS


def test_the_cap_matches_what_the_lead_can_seat():
    """Admitting more than the lead can hold would guarantee a shortfall log on
    every marquee night; admitting fewer would leave a lead slot empty."""
    assert _DISCOVER_IMMINENT_MARQUEE_SLOTS == MAX_LEAD
