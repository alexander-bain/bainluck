"""#4898 — tonight's marquee game reaches Discover BEFORE it kicks off.

THE SPECIMEN, dated: San Francisco 49ers @ Los Angeles Rams, event ``14632820``,
kickoff ``2026-09-11T00:35:00Z``, primetime, ``tier:1``, ``class:pro_major``,
crests on both sides. Measured on production at 19:42-19:55Z on 2026-09-10 — the
reader's own page, ``limit=20&offset=0&event_pct=0.15`` — the card was **not on
Discover page one at T-4h53m, and could not be**. It was not ranked low; it was
deleted from the payload before any ordering pass saw it.

The same card, same endpoint, same parameters, measured again after kickoff:

* **T-4h53m** (``scheduled``) — absent. Pre-demotion score 40.
* **T-35m** (``scheduled``) — absent. Pre-demotion score **75**.
* **T+2m** (``live``, 0-0) — **rank 2, score 85**.
* **T+68m** (``live``, 10-7) — **rank 2, score 98**.

No code changed between those readings. That is the whole diagnosis in one
table: the row, the tags, the media and the matching were never the problem.

═══ WHY A PRE-GAME CARD COULD NEVER SURVIVE, STRUCTURALLY ═══

``_is_discover_event_demotion_exception`` reads excitement from
``_discover_event_excitement_score``, which for an unsettled game is its
pre-demotion feed score — built by ``compute_event_base_score`` from closeness,
upset, lead changes and momentum. **A game that has not kicked off has none of
those by construction.** Every arm needs 85, or 80, or 60-plus-a-keyword, and a
scheduled game cannot reach any of them however big it is. So it is capped to 35
and the noise filter's ``< 45`` check then deletes it. The predicate's own
docstring opens "A **live** sports event earns a Discover slot only if…"; the
scheduled game inherited a bar only an in-progress game can clear.

═══ WHY BOTH HALVES ARE NEEDED, MEASURED ═══

Skipping the demotion alone is NOT enough, and the specimen is what proves it:
at T-35m the natural score is 75 (clears the filter's 45 on its own) but at
T-4h53m it is **40** (does not). A score-preserving exemption alone would buy
roughly the last hour and keep failing over the rest of the window that was
asked for. Both passes are fed one set, for the reason the finals arm already
records: a card that survives only one of the two is still not on the page.

═══ WHY THE ARM IS BOUNDED, AND THE NUMBER THAT SETS THE BOUND ═══

An NFL Sunday. Measured 2026-09-11 01:55Z against production's own schedule, the
six hours from ``2026-09-13 17:00Z`` hold **TWELVE ``tier:1`` scheduled games,
eight of them kicking off in the same minute**. Unbounded, this arm would hand
Discover a twelve-card NFL scoreboard on the afternoon a reader is most likely
to open it — the exact outcome ``_DISCOVER_RECENT_FINAL_SLOTS`` exists to
prevent on the other arm. The cap is three, which is what ``compose_lead`` can
actually seat (``MAX_LEAD = 3``).

That same measurement is why the id tiebreak is load-bearing rather than
ceremonial: with eight kickoffs sharing one minute, a selection ordered on time
alone would differ between two requests a second apart.

═══ WHAT THIS SHIP DOES NOT CLAIM ═══

It makes the card SURVIVE from T-6h. It does not widen the lead pass:
``tonights_games.SOON_WINDOW_HOURS`` is 4, so between T-6h and T-4h the card is
present and findable at its own score, and from T-4h ``compose_lead`` seats it
in the top three. Widening the lead window is a separate question about C185's
ordering contract and is deliberately not answered here.
"""

import copy
from datetime import datetime, timedelta, timezone

import pytest

from app.routes.feed import (
    _DISCOVER_IMMINENT_KICKOFF_HOURS,
    _DISCOVER_IMMINENT_MARQUEE_SLOTS,
    _demote_non_exceptional_discover_events,
    _filter_discover_event_noise,
    _imminent_marquee_kickoff_ids,
)
from app.utils.tonights_games import MAX_LEAD, SOON_WINDOW_HOURS, compose_lead

# Fixed anchor, and no branch on the clock anywhere below (gotcha #44): every
# fixture offsets from this and every pass is handed it explicitly.
NOW = datetime(2026, 9, 10, 19, 42, 0, tzinfo=timezone.utc)

#: The specimen's own numbers, from the production measurement in the docstring.
SPECIMEN_ID = 14632820
SPECIMEN_SCORE_AT_T_MINUS_5H = 40
SPECIMEN_SCORE_AT_T_MINUS_35M = 75


def _scheduled_game(
    *,
    event_id: int,
    score: int = SPECIMEN_SCORE_AT_T_MINUS_5H,
    hours_to_kickoff: float = 4.883,
    tier: str = "tier:1",
    media: bool = True,
    status: str = "scheduled",
    sport: str = "americanfootball_nfl",
) -> dict:
    data = {
        "id": event_id,
        "sport": sport,
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


def _futures(i: int, score: float) -> dict:
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "headline": f"f{i}",
        "data": {"id": 90_000 + i, "name": f"market {i}"},
    }


def _run_both_passes(items: list[dict], *, with_fix: bool) -> list[dict]:
    """The served Discover chain's two deleting passes, with the arm on or off.

    ``with_fix=False`` is the pre-#4898 behaviour reproduced exactly — both
    passes handed an empty imminent set — so every assertion below has a control
    that fails without the change rather than merely restating the pool.

    DEEP-COPIES ITS INPUT, and that is not tidiness. ``_demote_non_exceptional_
    discover_events`` writes ``score`` **into the item dicts in place**, so a
    caller that runs the control and then the fix over ``list(items)`` — a new
    list of the SAME dicts — hands the second run a card the first run already
    capped to 35. Caught here by mutation testing: the "natural score 75" case
    was silently exercising a score-35 card, so the two halves of the fix looked
    inseparable when they are not. This file's own subject is a pass that
    mutates shared dicts (the route comments carry gotcha #6 for the same class),
    so every arm gets its own copy.
    """
    items = copy.deepcopy(items)
    kickoff_ids = _imminent_marquee_kickoff_ids(items, NOW) if with_fix else set()
    _demote_non_exceptional_discover_events(items, set(), kickoff_ids)
    return _filter_discover_event_noise(items, set(), kickoff_ids)


def _ids(items: list[dict]) -> list[int]:
    return [
        (it.get("data") or {}).get("id") for it in items if it.get("type") == "event"
    ]


# ── the ship, and its control ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "score,label",
    [
        (SPECIMEN_SCORE_AT_T_MINUS_5H, "T-4h53m, natural score 40"),
        (SPECIMEN_SCORE_AT_T_MINUS_35M, "T-35m, natural score 75"),
    ],
)
def test_the_marquee_pregame_card_survives_at_both_measured_scores(score, label):
    """The specimen reaches the page at BOTH scores production measured.

    The 75 case is the one a score-preserving exemption alone would already fix;
    the 40 case is the one it would not, and it is the reason the noise filter
    has its own branch. Parametrised so a change that recovers only the late
    window cannot pass this file.
    """
    items = [_scheduled_game(event_id=SPECIMEN_ID, score=score)] + [
        _futures(i, 80.0) for i in range(12)
    ]

    assert SPECIMEN_ID not in _ids(
        _run_both_passes(list(items), with_fix=False)
    ), f"control failed: the card should be deleted without the fix ({label})"

    assert SPECIMEN_ID in _ids(
        _run_both_passes(list(items), with_fix=True)
    ), f"the marquee pre-game card must reach the page ({label})"


@pytest.mark.parametrize(
    "score,survives_on_score_alone",
    [
        (SPECIMEN_SCORE_AT_T_MINUS_35M, True),
        (SPECIMEN_SCORE_AT_T_MINUS_5H, False),
    ],
)
def test_the_two_halves_of_the_fix_have_different_reach(score, survives_on_score_alone):
    """Why the noise-filter branch is not redundant with the demotion skip.

    Feeds the noise filter an UNDEMOTED card and no imminent set, which is the
    reach of a score-preserving exemption on its own: at 75 the card clears the
    filter's own 45 floor and needs no help, at 40 it does not. That gap is the
    part of the window a demotion-skip-only fix would silently fail over, and
    without this test the suite could not tell the two designs apart.
    """
    item = _scheduled_game(event_id=SPECIMEN_ID, score=score)

    kept = _filter_discover_event_noise([item], set(), set())

    assert (SPECIMEN_ID in _ids(kept)) is survives_on_score_alone


def test_the_kept_card_keeps_its_own_score_and_is_not_capped_to_35():
    """Survival is not enough — a card capped to 35 sits below every futures card.

    #4681 records this on the finals arm: surviving the noise filter alone would
    have bought that card nothing. The same is true here, and it is what lets the
    lead pass find the card at a rank a reader reaches.
    """
    items = [_scheduled_game(event_id=SPECIMEN_ID, score=SPECIMEN_SCORE_AT_T_MINUS_35M)]
    kept = _run_both_passes(items, with_fix=True)

    assert kept[0]["score"] == SPECIMEN_SCORE_AT_T_MINUS_35M
    assert kept[0]["_rank_score"] == float(SPECIMEN_SCORE_AT_T_MINUS_35M)


def test_a_surviving_card_is_then_seated_in_the_top_three_by_the_lead_pass():
    """End to end: the ship is the card on the page, not the id in a set.

    Runs the real ``compose_lead`` over the real post-filter output at a clock
    inside its own four-hour window, which is the pass #4898 says was already
    willing to lead this game and never got the chance.
    """
    items = [
        _scheduled_game(
            event_id=SPECIMEN_ID,
            score=SPECIMEN_SCORE_AT_T_MINUS_5H,
            hours_to_kickoff=2.0,
        )
    ] + [_futures(i, 95.0) for i in range(12)]

    survivors = _run_both_passes(items, with_fix=True)
    survivors.sort(key=lambda it: it.get("_rank_score", 0), reverse=True)
    led = compose_lead(survivors, NOW, include_tonights_games=True)

    assert SPECIMEN_ID in _ids(led[:MAX_LEAD]), (
        "a card that survives inside the lead window must be seated in the top "
        f"{MAX_LEAD} — it led at score {SPECIMEN_SCORE_AT_T_MINUS_5H} against "
        "futures scoring 95, which is the point of the arm"
    )


# ── the bound, measured on an NFL Sunday ─────────────────────────────────────


def test_an_nfl_sunday_is_capped_and_does_not_become_a_scoreboard():
    """Twelve marquee games in one six-hour window select exactly three.

    The population is the measured one: eight kickoffs sharing a single minute
    plus four in a later slot.
    """
    same_minute = [
        _scheduled_game(event_id=200 + i, score=50 + i, hours_to_kickoff=1.0)
        for i in range(8)
    ]
    later = [
        _scheduled_game(event_id=300 + i, score=45 + i, hours_to_kickoff=4.4)
        for i in range(4)
    ]
    items = same_minute + later

    selected = _imminent_marquee_kickoff_ids(items, NOW)

    assert len(selected) == _DISCOVER_IMMINENT_MARQUEE_SLOTS == 3
    # Chosen by score, so the three that get in are the three the scorer rates
    # highest — 57, 56, 55 — not the three that happen to be first in the list.
    assert selected == {207, 206, 205}


def test_the_selection_is_stable_when_eight_games_share_one_kickoff_minute():
    """Same population, shuffled input, identical result — twice.

    With eight kickoffs in one minute an ordering keyed on time alone is
    underdetermined, and the reader would see the page reshuffle between two
    requests a second apart.
    """
    items = [
        _scheduled_game(event_id=400 + i, score=60, hours_to_kickoff=1.0)
        for i in range(8)
    ]

    forward = _imminent_marquee_kickoff_ids(items, NOW)
    reversed_ = _imminent_marquee_kickoff_ids(list(reversed(items)), NOW)

    assert forward == reversed_
    # All scores equal, so the id tiebreak is the ONLY thing deciding this set.
    assert forward == {400, 401, 402}


# ── the arm is narrow: everything it must NOT admit ──────────────────────────


@pytest.mark.parametrize(
    "kwargs,why",
    [
        ({"tier": "tier:2"}, "tier 2 is not the marquee line"),
        ({"media": False}, "a crest-less card is not a game a reader recognises"),
        ({"hours_to_kickoff": 7.0}, "outside the six-hour window"),
        ({"hours_to_kickoff": -0.5}, "kickoff in the past means a lagging status"),
        ({"status": "completed"}, "a finished game belongs to the finals arm"),
    ],
)
def test_the_arm_refuses_what_it_must(kwargs, why):
    items = [_scheduled_game(event_id=SPECIMEN_ID, **kwargs)]
    assert _imminent_marquee_kickoff_ids(items, NOW) == set(), why


def test_a_routine_non_marquee_game_is_still_demoted_and_deleted():
    """Discover does not become the scoreboard — the blanket rule still holds.

    Without this, "let the marquee game through" and "let games through" are
    indistinguishable, and the demotion's whole purpose is the difference.
    """
    items = [
        _scheduled_game(event_id=777, tier="tier:3", sport="soccer_sweden_superettan")
    ] + [_futures(i, 80.0) for i in range(12)]

    assert 777 not in _ids(_run_both_passes(items, with_fix=True))


def test_the_window_is_wider_than_the_lead_pass_it_feeds():
    """A survival window narrower than the lead window is the defect, one over.

    If the filter deleted cards the lead pass still wants, ``compose_lead`` would
    be asking for something that no longer exists — which is precisely how this
    game vanished. Asserted as a relationship between the two constants so the
    invariant survives either being retuned.
    """
    assert _DISCOVER_IMMINENT_KICKOFF_HOURS >= SOON_WINDOW_HOURS


def test_the_cap_is_not_smaller_than_the_lead_the_page_can_seat():
    """Admitting fewer than the lead can hold leaves a lead slot it could fill."""
    assert _DISCOVER_IMMINENT_MARQUEE_SLOTS >= MAX_LEAD
