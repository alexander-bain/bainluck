"""#7274 — one leg, one number: the card and the page divide by the same set.

WHAT A READER SAW, measured on production 2026-09-19 (latency filed it from a
D48 pass; `routes/feed.py` and `routes/futures.py` are this lane's files). The
Discover card for market 58776433 — *When will the Danube River return to normal
levels?* — printed `October 1 - 31, 2026` at **59%**. Tapping the card,
`/futures/58776433` printed the same leg at **49%**. The card reproduced on two
independently rebuilt feed payloads, so neither number was a stale artifact.

THE CAUSE IS THE DIVISOR'S MEMBERSHIP, NOT A PRICE. Both surfaces divide by the
sum of the legs they show, and only one of them stripped rungs whose own
deadline had passed:

    feed    survivors 0.8845  -> under the squeeze band -> prints the stored 0.590
    detail  all legs  1.1935  -> squeezed               -> prints 0.590/1.1935 = 0.494

So on the 19th the detail page priced `Before September 1, 2026` — an outcome
that could no longer happen — at 14%, and charged every live rung for it.

THE SECOND HALF, AND WHY IT IS THE SAME SHIP. Sharing the feed's membership rule
means sharing its parser, and that parser dated a RANGE rung by its OPENING day:
`September 15 - 30, 2026` read as expired on the 19th, four days into its own
open window. On the card that silently deleted a live 14.5% option; routed to
the detail page unfixed, it would have deleted a row the page renders today. A
range is dated by its closing day here, so both surfaces keep it.

Fixture values are market 58776433's `futures_outcomes` rows copied on
2026-09-19, not invented, so a later reader can re-fetch the id and check them.
The clock is frozen at the minute of the measurement: these rung names carry
absolute dates, so a wall-clock test would change its own subject matter every
day (gotcha #44).
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import app.routes.futures as futures_routes
from app.routes.futures import _format_market_detail
from app.utils.market_staleness import expired_ladder_rungs, outcome_deadline_expired

MARKET_ID = 58776433

#: The minute latency photographed the two surfaces disagreeing.
MEASURED_AT = datetime(2026, 9, 19, 18, 0, tzinfo=timezone.utc)

# (outcome_id, name, current_probability) — production rows, in stored order.
DANUBE_ROWS = [
    (1, "October 1 - 31, 2026", 0.590000),
    (2, "Does not return by November 1, 2026", 0.294500),
    (3, "Before September 1, 2026", 0.163000),
    (4, "September 15 - 30, 2026", 0.145000),
    (5, "September 1 - 14, 2026", 0.001000),
]

#: What the reader was owed: the stored price, which is what the card printed.
STORED_LEADER = 0.590000

#: What the page printed instead — 0.590 / 1.1935, the all-legs divisor.
SQUEEZED_LEADER = 0.4943


def _frozen(at=MEASURED_AT):
    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return at if tz is None else at.astimezone(tz)

    return patch.object(futures_routes, "datetime", _Frozen)


def _outcome(outcome_id, name, prob):
    """One `futures_outcomes` row as the detail serializer meets it."""
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        external_id=f"0x{outcome_id:064x}",
        current_probability=prob,
        current_american_odds=None,
        rank=None,
        rank_change_24h=None,
        probability_change_24h=None,
        opening_probability=None,
        opening_american_odds=None,
        is_winner=None,
        resolution_source=None,
        last_updated=MEASURED_AT,
        price_changed_at=MEASURED_AT,
        team_id=None,
    )


def _danube(rows=None, status="open"):
    return SimpleNamespace(
        id=MARKET_ID,
        name="When will the Danube River return to normal levels?",
        description=None,
        category="weather",
        source="polymarket",
        external_id="828358",
        status=status,
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=2,
        llm_sport_category="weather",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id="polymarket:828358",
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=[_outcome(*r) for r in (rows if rows is not None else DANUBE_ROWS)],
    )


def _detail(market):
    with _frozen():
        return _format_market_detail(market, None, set())


def _by_name(payload, name):
    return next((o for o in payload["outcomes"] if o["name"] == name), None)


# ───────────────────────── the parser: a range ends when it ends ──────────────


class TestARangeRungIsDatedByItsClosingDay:
    """`September 15 - 30, 2026` cannot expire on the 19th."""

    def test_the_live_window_is_not_expired_mid_window(self):
        assert outcome_deadline_expired("September 15 - 30, 2026", MEASURED_AT) is False

    def test_the_same_window_expires_once_it_closes(self):
        after = datetime(2026, 10, 2, 18, 0, tzinfo=timezone.utc)
        assert outcome_deadline_expired("September 15 - 30, 2026", after) is True

    def test_a_range_that_really_did_elapse_still_expires(self):
        """The control: the fix must not make every range immortal."""
        assert outcome_deadline_expired("September 1 - 14, 2026", MEASURED_AT) is True

    def test_the_leader_survives_its_own_window(self):
        """`October 1 - 31, 2026` on October 15 — the next month's specimen.

        Kept separately from the 0.59 leader because `expired_ladder_rungs`
        would spare that row anyway (it prices above
        ``EXPIRED_RUNG_MAX_PROBABILITY``): this asks the parser directly, so the
        assertion cannot pass on the wrong reason.
        """
        mid = datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)
        assert outcome_deadline_expired("October 1 - 31, 2026", mid) is False

    @pytest.mark.parametrize(
        "name",
        [
            "September 15 - 30, 2026",
            "September 15-30, 2026",
            "September 15 – 30, 2026",  # en dash
            "September 15 — 30, 2026",  # em dash
            "September 15 to 30, 2026",
            "September 15 through 30, 2026",
            "Sept 15 - 30, 2026",
            "September 15 - 30",  # no year at all
        ],
        ids=lambda n: n,
    )
    def test_every_spelling_of_the_same_window(self, name):
        assert outcome_deadline_expired(name, MEASURED_AT) is False

    def test_a_word_separator_needs_real_whitespace_around_it(self):
        """Spaced, it is a range whose end has passed; run together, it is nothing.

        The second half is unchanged behaviour — neither parser can date
        `1to14`, because the day-requiring regex needs a word boundary after the
        day — and it is asserted so a looser separator can never be added
        without this line going red.
        """
        assert outcome_deadline_expired("September 1 to 14, 2026", MEASURED_AT) is True
        assert outcome_deadline_expired("September 1to14, 2026", MEASURED_AT) is False


class TestTheRangeRuleLeavesEveryOtherShapeAlone:
    """Controls. A parser change is only safe if the untouched shapes are pinned."""

    @pytest.mark.parametrize(
        "name,expired",
        [
            ("Before September 1, 2026", True),
            ("Does not return by November 1, 2026", False),
            ("October 1 - 31, 2026", False),
            ("Before July", True),
            ("Before 2027", False),
            ("Dec 28 - Jan 3, 2027", False),  # cross-month: the old path, unchanged
            ("Yes", False),
            ("", False),
        ],
        ids=lambda v: str(v),
    )
    def test_unchanged(self, name, expired):
        assert outcome_deadline_expired(name, MEASURED_AT) is expired

    def test_a_later_date_outside_the_range_still_wins(self):
        """Last-match-wins is intact: the containment test is what protects it."""
        name = "September 15 - 30, 2026, resolves October 5, 2026"
        assert outcome_deadline_expired(name, MEASURED_AT) is False
        later = datetime(2026, 10, 7, 18, 0, tzinfo=timezone.utc)
        assert outcome_deadline_expired(name, later) is True

    @pytest.mark.parametrize(
        "name", ["September 30 - 2, 2026", "February 1 - 31, 2026"]
    )
    def test_an_end_we_cannot_date_keeps_the_rung(self, name):
        """A rollover we were not given, and a day that does not exist.

        Fail open: we delete rows we can prove are dead, never rows we merely
        failed to parse.
        """
        november = datetime(2026, 11, 5, 18, 0, tzinfo=timezone.utc)
        assert outcome_deadline_expired(name, november) is False


# ───────────────────────── the page: one divisor, one number ──────────────────


class TestTheDetailPagePrintsTheCardsNumber:
    def test_the_specimen_really_does_squeeze_without_the_fix(self):
        """The strawman guard: this fixture must be able to fail.

        Runs the pre-fix membership — every leg in the divisor — through the same
        normalizer the page uses, and pins the 49% the reader was shown. If a
        later change makes this field stop squeezing, the assertions below would
        pass for a reason that has nothing to do with #7274.
        """
        from app.utils.outcome_display import normalize_display_probs

        all_legs = [{"name": n, "probability": p} for _, n, p in DANUBE_ROWS]
        assert normalize_display_probs(all_legs, mutually_exclusive=True) is True
        assert all_legs[0]["probability"] == pytest.approx(SQUEEZED_LEADER, abs=0.0005)

    def test_the_leader_prints_the_stored_price(self):
        leader = _by_name(_detail(_danube()), "October 1 - 31, 2026")
        assert leader["probability"] == pytest.approx(STORED_LEADER)

    def test_the_impossible_rungs_are_no_longer_priced(self):
        payload = _detail(_danube())
        assert _by_name(payload, "Before September 1, 2026") is None
        assert _by_name(payload, "September 1 - 14, 2026") is None
        assert payload["expired_rungs_dropped"] == 2

    def test_the_still_open_window_is_kept_and_keeps_its_price(self):
        """The half the parser fix pays for: this row must survive the drop."""
        rung = _by_name(_detail(_danube()), "September 15 - 30, 2026")
        assert rung is not None
        assert rung["probability"] == pytest.approx(0.145)

    def test_the_two_surfaces_divide_by_one_set(self):
        """The contract in the issue's title, asserted across both modules.

        The feed's scale is asked of the feed's own helper on the feed's own
        survivor set; the page's number is read off the served payload. They must
        be the same number, or a reader tapping a card sees it change.
        """
        from app.routes.feed import _feed_display_scale

        survivors = [
            SimpleNamespace(name=n, current_probability=p)
            for _, n, p in DANUBE_ROWS
            if n
            not in expired_ladder_rungs(
                [(n, p) for _, n, p in DANUBE_ROWS], MEASURED_AT
            )
        ]
        card_number = STORED_LEADER * _feed_display_scale(survivors)

        page_number = _by_name(_detail(_danube()), "October 1 - 31, 2026")["probability"]
        assert page_number == pytest.approx(card_number)

    def test_the_count_is_present_on_a_board_with_nothing_to_drop(self):
        """Absence of the key must mean an old build, never `no expired rungs`."""
        undated = [(1, "Yes", 0.62), (2, "No", 0.38)]
        payload = _detail(_danube(rows=undated))
        assert payload["expired_rungs_dropped"] == 0
        assert len(payload["outcomes"]) == 2


class TestTheDropIsBoundedToWhatItIsFor:
    def test_a_settled_board_shows_every_window_that_ran(self):
        """A result is a record of what happened, expired windows included."""
        payload = _detail(_danube(status="resolved"))
        assert len(payload["outcomes"]) == 5
        assert payload["expired_rungs_dropped"] == 0
        assert _by_name(payload, "Before September 1, 2026") is not None

    def test_a_dead_ladder_is_never_emptied(self):
        """Every rung expired: the feed drops the card, the page cannot."""
        all_dead = [
            (1, "Before September 1, 2026", 0.40),
            (2, "September 1 - 14, 2026", 0.35),
            (3, "Before August 1, 2026", 0.25),
        ]
        payload = _detail(_danube(rows=all_dead))
        assert len(payload["outcomes"]) == 3
        assert payload["expired_rungs_dropped"] == 0

    def test_the_ladders_own_answer_is_never_stripped(self):
        """A past-dated rung priced above the guard already resolved YES."""
        answered = [
            (1, "September 1 - 14, 2026", 0.960),
            (2, "October 1 - 31, 2026", 0.030),
            (3, "Before September 1, 2026", 0.010),
        ]
        payload = _detail(_danube(rows=answered))
        answer = _by_name(payload, "September 1 - 14, 2026")
        assert answer is not None
        assert answer["probability"] == pytest.approx(0.96)
        assert payload["expired_rungs_dropped"] == 1  # only the 1% ghost

    def test_a_date_ladder_does_not_become_a_fight(self):
        """UX-P164's rule, applied to a drop that now lands above its line.

        `derive_market_concept_key` is forwarded an outcome count, and the combat
        adapters read `n_outcomes == 2` as a fight. A four-rung ladder with two
        expired rungs must not hand them a two-outcome market and invent a
        breadcrumb.
        """
        import app.utils.concept_links as concept_links

        four_rungs = [
            (1, "October 1 - 31, 2026", 0.50),
            (2, "Does not return by November 1, 2026", 0.30),
            (3, "Before September 1, 2026", 0.12),
            (4, "September 1 - 14, 2026", 0.08),
        ]
        seen = []

        def _spy(external_id, name, category, outcome_count):
            seen.append(outcome_count)
            return None

        with patch.object(concept_links, "derive_market_concept_key", _spy):
            payload = _detail(_danube(rows=four_rungs))

        assert payload["expired_rungs_dropped"] == 2
        assert len(payload["outcomes"]) == 2
        assert seen == [4], "the identity count must stay pre-drop"
