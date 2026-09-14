"""#6181 + #5567 — the settled upset line says the card's number, about a name.

Served on production 2026-09-14 16:50Z, Discover at phone width, event 14637256
(`Dallas Cowboys @ New York Giants`, 20-28). The card printed its own pre-match
row as ``62% · Pre-match · 38%`` and the sentence directly beneath it read:

    Won as 39% underdog

One team, one pre-game chance, two numbers, two lines apart — and no subject.

WHY THIS FILE EXISTS RATHER THAN ONE ASSERTION: the specimen sat on TWO
independent causes, and either one alone reproduces the defect.

  1. THE WRONG RUNG. The card's row is ``prematch_odds``, resolved through
     Alex's ladder (kalshi -> polymarket -> books). The sentence read
     ``Event.opening_*``, the books median. 0.385 against 0.3908.
  2. THE WRONG ROUNDING, and this is the half that makes a source-only fix
     useless: ``rendered_percent(0.385)`` is 39, while the card derives the
     underdog's side as ``100 - leader`` = 38. A derived percent cannot be
     reproduced by rounding the raw value at all — which is precisely what
     ``_display_pct``'s ``printed`` parameter was added for in #4146, and which
     this call site never adopted.

``TestEitherCauseAlone`` is the load-bearing class: it fails a fix that swaps
the rung but keeps rounding for itself, which is the fix a reader of the issue
title would write.
"""

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.utils.feed_reasons import generate_event_reason
from app.utils.feed_scoring import format_event_data
from app.utils.graded_card import (
    duel_percents_by_side,
    rendered_duel_percents,
    rendered_percent,
)
from app.utils.prematch_reading import resolve_prematch_reading

# The production specimen, from `/api/feed` at 16:52Z.
SPECIMEN_KALSHI_HOME = 0.385  # the rung the card drew
SPECIMEN_BOOKS_HOME = 0.3908  # the rung the sentence read
SPECIMEN_HOME = "New York Giants"
SPECIMEN_AWAY = "Dallas Cowboys"


def _sentence(**overrides) -> str:
    """The specimen's call, with the card's percents handed in as the route does."""
    kwargs = dict(
        home_team=SPECIMEN_HOME,
        away_team=SPECIMEN_AWAY,
        status="completed",
        highlight_reasons=["upset"],
        opening_home_prob=SPECIMEN_BOOKS_HOME,
        home_score=28,
        away_score=20,
        prematch_percents={"home": 38, "away": 62},
    )
    kwargs.update(overrides)
    return generate_event_reason(**kwargs)


# ── A. THE SPECIMEN ───────────────────────────────────────────────────────────


class TestTheSpecimen:
    def test_the_sentence_states_the_percent_the_card_prints(self):
        """RED ON THE PARENT: "Won as 39% underdog" under a row reading 38%."""
        assert _sentence() == "New York Giants won as a 38% underdog"

    def test_the_stale_number_is_gone(self):
        assert "39%" not in _sentence()

    def test_the_line_names_its_subject(self):
        """#5567 — the only sentence claiming what happened had no subject."""
        assert _sentence().startswith("New York Giants ")


# ── B. EITHER CAUSE ALONE — the class, not the specimen ───────────────────────


class TestEitherCauseAlone:
    def test_rounding_alone_reproduces_it_when_the_rung_already_agrees(self):
        """THE HALF-FIX GUARD.

        Here the sentence and the card read the SAME probability, 0.385, so a
        fix that only swapped the rung is fully applied. It still fails without
        `printed`: independent rounding says 39, the card derives 38.
        """
        assert rendered_percent(SPECIMEN_KALSHI_HOME) == 39
        assert rendered_duel_percents(0.615, SPECIMEN_KALSHI_HOME) == [62, 38]
        assert (
            _sentence(opening_home_prob=SPECIMEN_KALSHI_HOME)
            == "New York Giants won as a 38% underdog"
        )

    def test_the_rung_alone_reproduces_it_when_the_rounding_already_agrees(self):
        """The other direction: a books opening that rounds cleanly on its own,
        against a card drawing a kalshi rung four points away."""
        assert (
            _sentence(opening_home_prob=0.30, prematch_percents={"home": 38})
            == "New York Giants won as a 38% underdog"
        )


# ── C. THE SUBJECT IS THE WINNER, NOT A POSITION ──────────────────────────────


class TestTheSubject:
    def test_an_away_winner_is_named(self):
        assert (
            _sentence(home_score=20, away_score=28)
            == "Dallas Cowboys won as a 62% underdog"
        )

    @pytest.mark.parametrize(
        "home_score,away_score,expected",
        [(28, 20, SPECIMEN_HOME), (20, 28, SPECIMEN_AWAY)],
    )
    def test_the_named_team_is_always_the_one_that_won(
        self, home_score, away_score, expected
    ):
        text = _sentence(home_score=home_score, away_score=away_score)
        assert text.startswith(f"{expected} won as a ")

    def test_the_winner_takes_its_own_side_of_the_pair(self):
        """A mirror of the percents must move the number with the team, or the
        sentence is reading a fixed index rather than the winner's side."""
        assert (
            _sentence(prematch_percents={"home": 71, "away": 29})
            == "New York Giants won as a 71% underdog"
        )


# ── D. THE PAYLOAD AND THE SENTENCE ARE ONE ANSWER ────────────────────────────


def _card(prematch_by_source, opening_home, opening_away):
    return format_event_data(
        event_id=14637256,
        external_id="x",
        sport_key="americanfootball_nfl",
        sport_name="NFL",
        home_team=SPECIMEN_HOME,
        away_team=SPECIMEN_AWAY,
        commence_time=datetime(2026, 9, 13, 21, 20, tzinfo=timezone.utc),
        status="completed",
        home_score=28,
        away_score=20,
        current_home_prob=None,
        current_away_prob=None,
        opening_home_prob=opening_home,
        opening_away_prob=opening_away,
        opening_favorite="away",
        win_probability_sources=None,
        prob_source=None,
        game_clock=None,
        period=None,
        broadcast_info=None,
        highlight_label="Recent upset",
        raw_ei=None,
        inline_tags=[],
        ended_at=None,
        prematch_by_source=prematch_by_source,
    )


class TestTheCardAndTheSentenceAgree:
    """The contract on the SERVED payload, over the shapes that differ.

    This models the route's six lines rather than running the route; the route's
    own plumbing is pinned separately in `TestTheRoutePassesThem`, because a
    payload test cannot see a caller that stops passing the arguments.
    """

    @pytest.mark.parametrize(
        "prematch_by_source,opening_home,opening_away",
        [
            # The specimen: kalshi rung, books opening a half-point away.
            ({"kalshi": (0.385, 0.615)}, SPECIMEN_BOOKS_HOME, 0.6092),
            # Polymarket rung.
            ({"polymarket": (0.445, 0.555)}, 0.47, 0.53),
            # Books only — the sentence must still take the DUEL percent.
            (None, 0.385, 0.615),
            # A pair sitting exactly on the .5 grid, both sides.
            ({"kalshi": (0.425, 0.575)}, 0.425, 0.575),
            ({"kalshi": (0.005001, 0.994999)}, 0.2, 0.8),
        ],
    )
    def test_the_winners_percent_is_the_same_integer_in_both(
        self, prematch_by_source, opening_home, opening_away
    ):
        data = _card(prematch_by_source, opening_home, opening_away)
        reading = resolve_prematch_reading(
            by_source=prematch_by_source,
            books_home=opening_home,
            books_away=opening_away,
        )
        percents = duel_percents_by_side(
            away_probability=reading["away_probability"],
            home_probability=reading["home_probability"],
        )
        text = generate_event_reason(
            home_team=SPECIMEN_HOME,
            away_team=SPECIMEN_AWAY,
            status="completed",
            highlight_reasons=["upset"],
            opening_home_prob=opening_home,
            home_score=28,
            away_score=20,
            prematch_percents=percents,
        )
        # The home side won, so the card's home percent is the one on screen.
        printed = data["prematch_odds"]["home_rendered_percent"]
        assert f" {printed}% underdog" in text, (
            f"card printed {printed}%, sentence said {text!r}"
        )


# ── E. THE ROUTE ACTUALLY HANDS THEM OVER ─────────────────────────────────────


class TestTheRoutePassesThem:
    """The plumbing half. Without this, every assertion above passes on a route
    that never supplies the percents — which is the state this ship found.
    """

    @staticmethod
    def _the_call() -> ast.Call:
        source = (
            Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"
        ).read_text()
        calls = [
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "generate_event_reason"
        ]
        assert len(calls) == 1, f"expected one call site, found {len(calls)}"
        return calls[0]

    def test_the_call_site_supplies_the_cards_percents(self):
        assert "prematch_percents" in {kw.arg for kw in self._the_call().keywords}

    def test_it_supplies_the_resolved_pair_not_a_raw_probability(self):
        """A named local, so a later edit cannot quietly pass `opening_home_prob`
        back in through the new parameter and restore the defect."""
        by_name = {kw.arg: kw.value for kw in self._the_call().keywords}
        value = by_name["prematch_percents"]
        assert isinstance(value, ast.Name) and value.id == "_prematch_percents"

    def test_that_local_is_built_by_the_keyed_helper(self):
        """The ordering hazard this ship removed: `rendered_duel_percents`
        returns ``[away, home]``, and a route that unpacked it the wrong way
        round would state the loser's percent in a sentence about the winner —
        grammatical, plausible, and wrong. `duel_percents_by_side` owns the
        order, so the route must go through it rather than unpacking the pair.
        """
        source = (
            Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"
        ).read_text()
        tree = ast.parse(source)
        builders = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "_prematch_percents"
                for t in node.targets
            )
        ]
        assert len(builders) == 1, f"expected one builder, found {len(builders)}"
        called = {
            n.func.id
            for n in ast.walk(builders[0])
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "duel_percents_by_side" in called
        assert "rendered_duel_percents" not in called

    def test_each_side_of_the_reading_goes_to_its_own_argument(self):
        """M5, the one mutant the behavioural tests above cannot reach.

        `duel_percents_by_side` makes the ORDER safe; it cannot make the route's
        two lookups safe, and `away_probability=reading["home_probability"]` is
        still a sentence about the winner carrying the loser's number. The route
        has no seam to call it through — the percents are built inside a 400-line
        loop over ORM rows — so this is asserted on the source, deliberately, and
        it is the reason the file keeps an AST class at all.
        """
        source = (
            Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"
        ).read_text()
        builder = next(
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "_prematch_percents"
                for t in node.targets
            )
        )
        call = next(
            n
            for n in ast.walk(builder)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "duel_percents_by_side"
        )
        by_name = {kw.arg: kw.value for kw in call.keywords}
        assert set(by_name) == {"away_probability", "home_probability"}
        for arg, key in (
            ("away_probability", "away_probability"),
            ("home_probability", "home_probability"),
        ):
            value = by_name[arg]
            assert isinstance(value, ast.Subscript), f"{arg} is not a lookup"
            assert isinstance(value.slice, ast.Constant) and value.slice.value == key, (
                f"{arg}= reads {ast.dump(value.slice)}, not the reading's {key!r}"
            )


class TestTheKeyedHelper:
    """`duel_percents_by_side` is where the away/home order now lives, once."""

    def test_it_keys_an_asymmetric_pair_to_the_right_sides(self):
        assert duel_percents_by_side(
            away_probability=0.615, home_probability=0.385
        ) == {"away": 62, "home": 38}

    def test_it_agrees_with_the_positional_pair_it_wraps(self):
        away_pct, home_pct = rendered_duel_percents(0.615, 0.385)
        keyed = duel_percents_by_side(away_probability=0.615, home_probability=0.385)
        assert keyed == {"away": away_pct, "home": home_pct}

    def test_an_unusable_pair_still_keys_both_sides(self):
        """`None` is a real answer — "no price" — and must not collapse a key."""
        assert duel_percents_by_side(away_probability=None, home_probability=None) == {
            "away": None,
            "home": None,
        }


# ── F. NOTHING ELSE ON A FINAL CARD MOVED ─────────────────────────────────────


class TestUnchanged:
    """CONTROLS. Every test in this class calls the function the way the PARENT
    could — no new keyword — so each one is GREEN on the parent as well as here.
    That is what makes them controls: they would not survive a fix that reached
    past the upset percent into the rest of the settled block.
    """

    @staticmethod
    def _parent_shaped(**overrides) -> str:
        kwargs = dict(
            home_team=SPECIMEN_HOME,
            away_team=SPECIMEN_AWAY,
            status="completed",
            highlight_reasons=["upset"],
            opening_home_prob=SPECIMEN_BOOKS_HOME,
            home_score=28,
            away_score=20,
        )
        kwargs.update(overrides)
        return generate_event_reason(**kwargs)

    def test_no_opening_still_yields_the_wordless_upset(self):
        assert self._parent_shaped(opening_home_prob=None) == "Upset result"

    def test_a_non_upset_final_is_still_silent(self):
        """#4094 — the card already says it three ways."""
        assert self._parent_shaped(highlight_reasons=["major_prob_swing"]) == ""

    def test_a_final_still_gets_no_live_sentence(self):
        """#5439's tense rule, untouched."""
        text = self._parent_shaped(highlight_reasons=["major_prob_swing"])
        assert "leading" not in text and "chance rose" not in text

    def test_the_word_underdog_survives_for_the_clients_styler(self):
        """`FeedCard.tsx` styles this family on `\\bunderdogs?\\b`, and the
        pattern is matched against the WHOLE sentence — so the added subject
        must not take the card's icon away. Green both sides by construction.
        """
        assert "underdog" in self._parent_shaped()


class TestTheFallbackPath:
    def test_a_caller_holding_no_card_percents_rounds_for_itself_as_before(self):
        """Not a control — it asserts the new subject too. The point is that
        dropping the percents degrades to the old NUMBER rather than to no
        sentence: `_display_pct` still falls back to `rendered_percent`.
        """
        assert (
            _sentence(prematch_percents=None)
            == "New York Giants won as a 39% underdog"
        )
