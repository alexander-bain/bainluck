"""#4971 / D136 rung 3 — the feed card carries THE one number, not just the market's.

WHY THIS FILE EXISTS
════════════════════

`current_odds` is the market number. The number a reader is owed for "who wins
this question" is the `resolve_hero` cascade — settled, then blend, then opening
— and the card payload did not carry it. So every card-shaped surface re-derived
the cascade for itself, and the three of them drifted:

    `FeedCard`             finished -> `opening_odds`
    Discover `EventCard`   finished -> `prematchReading(data)`
    `RelatedByTag`         finished -> raw `current_odds`, no state at all

MEASURED on production 2026-09-12 08:30Z over the 100 events that finished in the
preceding 48h and carry sources: 95 serve a card probability, and on **11 of them
the raw blend names the LOSER as the favourite**. Median card->page gap 6.1pt,
max 76.1pt. Two specimens, read from both endpoints in the same minute:

    14792834  Kansas 21-38 Missouri   card 0.001   page 0.0  [settled, away]
    15309702  Athletics 6-5 Mariners  card 0.61    page 1.0  [settled, home]

The test that matters here is
`test_the_card_and_the_event_page_cannot_answer_differently`: it does not check a
value, it checks that BOTH payloads are built from the same reading, which is the
only form of this assertion a later constant change cannot quietly invalidate.
"""

from datetime import datetime, timezone

from app.utils.feed_scoring import format_event_data
from app.utils.hero_probability import resolve_hero


COMPLETED_AT = datetime(2026, 9, 12, 3, 56, 20, tzinfo=timezone.utc)


def _card(**overrides):
    kwargs = dict(
        event_id=14792834,
        external_id="x",
        sport_key="americanfootball_ncaaf",
        sport_name="NCAAF",
        home_team="Kansas Jayhawks",
        away_team="Missouri Tigers",
        commence_time=datetime(2026, 9, 12, 0, 0, tzinfo=timezone.utc),
        status="completed",
        home_score=21,
        away_score=38,
        current_home_prob=None,
        current_away_prob=None,
        opening_home_prob=None,
        opening_away_prob=None,
        opening_favorite=None,
        win_probability_sources=None,
        prob_source=None,
        game_clock=None,
        period=None,
        broadcast_info=None,
        highlight_label=None,
        raw_ei=None,
        inline_tags=[],
        ended_at=None,
    )
    kwargs.update(overrides)
    return format_event_data(**kwargs)


class _Row:
    """The plain-attribute shape `resolve_hero` documents that it accepts."""

    def __init__(self, **kw):
        self.status = kw.get("status")
        self.home_score = kw.get("home_score")
        self.away_score = kw.get("away_score")
        self.completed_at = kw.get("completed_at")
        self.win_probability_sources = kw.get("win_probability_sources")
        self.espn_win_prob_home = kw.get("espn_win_prob_home")
        self.opening_home_probability = kw.get("opening_home_probability")
        self.opening_away_probability = kw.get("opening_away_probability")


# ── the defect, in the shape production served it ────────────────────────────


def test_a_finished_game_serves_the_settled_result_not_the_last_traded_price():
    """Kansas 21-38 Missouri: the blend said the home side was the 0.1% side, which
    is nearly right by luck. The claim being fixed is that the card had no way to
    say the game is OVER and who won — it served a live-shaped market number."""
    row = _Row(
        status="completed",
        home_score=21,
        away_score=38,
        completed_at=COMPLETED_AT,
        win_probability_sources={"betting": {"value": 0.001}},
    )
    data = _card(hero=resolve_hero(row), current_home_prob=0.001, current_away_prob=0.999)

    assert data["hero_probability"] == 0.0
    assert data["hero_probability_away"] == 1.0
    assert data["hero_probability_source"] == "settled"
    assert data["hero_settled_result"] == "away"


def test_the_card_stops_naming_the_loser_as_the_favourite():
    """11 of 95 finished cards did this on 2026-09-12. Athletics won 6-5 and the
    raw blend served 0.61 for... the team that won, at 61% instead of certainty;
    the class is the same one that serves 0.76 for a side that lost."""
    row = _Row(
        status="completed",
        home_score=1,
        away_score=4,
        completed_at=COMPLETED_AT,
        win_probability_sources={"betting": {"value": 0.707}},
    )
    data = _card(hero=resolve_hero(row), current_home_prob=0.707, current_away_prob=0.293)

    # the market's number is UNCHANGED and still served — this is additive
    assert data["current_odds"]["home_probability"] == 0.707
    # ...but the one number says the home side lost
    assert data["hero_probability"] == 0.0
    assert data["hero_settled_result"] == "away"


def test_a_draw_is_nobody_won_and_not_we_do_not_know():
    row = _Row(
        status="completed",
        home_score=1,
        away_score=1,
        completed_at=COMPLETED_AT,
        win_probability_sources={"betting": {"value": 0.525}},
    )
    data = _card(hero=resolve_hero(row), current_home_prob=0.525, current_away_prob=0.475)

    assert data["hero_probability"] == 0.5
    assert data["hero_settled_result"] == "draw"
    assert data["hero_probability_source"] == "settled"


# ── the arms that must NOT change ────────────────────────────────────────────


def test_a_live_game_serves_the_blend_and_it_agrees_with_current_odds():
    """The blend arm must restate `current_odds`, not introduce a second number.
    If these two ever disagree the card contradicts itself, which is the bug one
    level down from the one this ship fixes."""
    row = _Row(
        status="live",
        home_score=2,
        away_score=1,
        completed_at=None,
        win_probability_sources={"betting": {"value": 0.62}},
    )
    hero = resolve_hero(row)
    data = _card(status="live", hero=hero, current_home_prob=0.62, current_away_prob=0.38)

    assert data["hero_probability_source"] == "blend"
    assert data["hero_probability"] == data["current_odds"]["home_probability"]
    assert "hero_settled_result" not in data


def test_a_finished_row_with_no_completed_at_does_not_resolve_as_settled():
    """`completed_at` is the trust gate in `settled_hero`, and it is the reason
    the caller resolves the hero rather than this serializer: `format_event_data`
    is pure and never receives that column. A card that invented a settled result
    from status+scores alone would publish a winner for a row whose scores are
    frozen mid-game (the `closed` failure this gate was bought with)."""
    row = _Row(
        status="completed",
        home_score=21,
        away_score=38,
        completed_at=None,
        win_probability_sources={"betting": {"value": 0.001}},
    )
    data = _card(hero=resolve_hero(row), current_home_prob=0.001, current_away_prob=0.999)

    # `final_unresolved`, not `blend`: the game IS over, we just cannot name the
    # winner. The number is unchanged; only the claim about it is (CERT-1938).
    assert data["hero_probability_source"] == "final_unresolved"
    assert "hero_settled_result" not in data


def test_an_opening_only_row_is_labelled_blend_today_which_is_wrong_see_issue():
    """CHARACTERIZATION, NOT AN ENDORSEMENT — this asserts today's WRONG label.

    `resolve_hero`'s third arm is supposed to say `opening` for a row nobody has
    quoted since the line was posted. It is UNREACHABLE: `compute_aggregate_probability`
    Tier 3 (`aggregation.py:902`) returns `opening_home_probability` itself, so the
    blend arm answers first and calls a bare opening line "blend". The arm below it
    reads the same attribute, so it can only ever be reached when that attribute is
    `None` — in which case it also returns `None`. Dead by construction.

    This is not cosmetic: `routes/events.py::_PINNABLE_HERO_SOURCE` is `"blend"`, so
    an opening line wearing that label is PINNED to the chart as the curve's live
    edge — precisely the "a number no aggregator produced" outcome that constant's
    own comment says it exists to prevent.

    Filed separately; this ship does not change the vocabulary, it only stops the
    card from having to guess at it. When the label is fixed, this test fails and
    is updated to assert `opening` — which is the point of pinning it here.
    """
    row = _Row(
        status="scheduled",
        completed_at=None,
        win_probability_sources=None,
        opening_home_probability=0.5865,
    )
    data = _card(status="scheduled", home_score=None, away_score=None, hero=resolve_hero(row))

    assert data["hero_probability"] == 0.5865
    assert data["hero_probability_source"] == "blend"  # should be "opening"


def test_no_hero_means_no_keys_and_never_a_zero():
    """`None` is a real state — nothing to print. A card that defaulted to 0.0
    would print a confident 0% for a question nobody has quoted."""
    data = _card(hero=None, current_home_prob=0.5, current_away_prob=0.5)

    assert "hero_probability" not in data
    assert "hero_probability_away" not in data
    assert "hero_probability_source" not in data
    assert "hero_settled_result" not in data


def test_the_hero_is_additive_and_leaves_the_market_number_alone():
    """Ruling 021 — share the DECISION, not the ingredient. Everything that ranks,
    filters or scores reads `current_odds`; this ship must be invisible to it."""
    row = _Row(
        status="completed",
        home_score=6,
        away_score=5,
        completed_at=COMPLETED_AT,
        win_probability_sources={"betting": {"value": 0.61}},
    )
    without = _card(current_home_prob=0.61, current_away_prob=0.39)
    with_hero = _card(hero=resolve_hero(row), current_home_prob=0.61, current_away_prob=0.39)

    for key, value in without.items():
        assert with_hero[key] == value, f"{key} moved when the hero was added"


# ── the guard that is the whole point ────────────────────────────────────────


def test_the_card_and_the_event_page_cannot_answer_differently():
    """THE ANTI-DRIFT GUARD.

    `routes/events.py` serves the detail payload's hero as four keys off a
    `resolve_hero` reading. This asserts the card serves the SAME FOUR KEYS off
    the SAME READING — so the two payloads are one decision rendered twice, and a
    surface that can read one can read the other without a second cascade.

    Asserted against the reading rather than against literals on purpose: a later
    change to the cascade must move both payloads or fail here, which a pair of
    hard-coded numbers would not catch.
    """
    row = _Row(
        status="completed",
        home_score=21,
        away_score=38,
        completed_at=COMPLETED_AT,
        win_probability_sources={"betting": {"value": 0.001}},
    )
    hero = resolve_hero(row)
    card = _card(hero=hero, current_home_prob=0.001, current_away_prob=0.999)

    # the four keys routes/events.py writes, and the same values
    page = {
        "hero_probability": hero.home_probability,
        "hero_probability_away": hero.away_probability,
        "hero_probability_source": hero.source,
    }
    if hero.settled_result is not None:
        page["hero_settled_result"] = hero.settled_result

    for key, value in page.items():
        assert card[key] == value, f"card and page disagree on {key}"
