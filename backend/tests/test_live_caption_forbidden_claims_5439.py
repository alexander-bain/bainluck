"""T10-1 (#5439) — the forbidden-claim regression set for LIVE captions.

PILLAR: TRUTH · SHIP: a live Discover card never says "Lead change" or
"Momentum shift" unless the scoreboard shows it.

THE DEFECT, measured on production 2026-09-12 02:00Z (`GET /api/feed?limit=50`,
HTTP 200, 50 items): **"Momentum shift" appeared ten times on one page** — five
live MLB cards × two fields (`headline` and `data.highlight.label`), every one
of them the identical string with `sublabel: None`:

    Marlins 2 - Dodgers 6      Yankees 6 - Mets 4      Twins 1 - Guardians 2
    Cardinals 2 - White Sox 1  Brewers 17 - Reds 0

The same three syllables over a one-run game and a seventeen-run rout. The label
describes nothing, because its predicate was "the price moved a lot AND the game
is not level" — two numbers that cannot establish a sequence of sporting events
at any threshold. Its sibling "Lead change" was worse: produced by
`TimeSeriesMetrics.lead_changes`, which counts **probability crossings of 50%**.
Nobody scored; the favourite swapped. Reachable on the event page, where
`routes/events.py` computes the metrics (`routes/feed.py` passes none).

EVERY CASE BELOW IS PAIRED. A rejection test that is not paired with a positive
control is how a truth fix becomes a silence fix: deleting all the copy passes
100% of a forbidden-claim set. Ruling 146 — suppress the sentence, never the
card — is only checkable if something asserts what SURVIVES.

TWO CASES FROM THE DIRECTIVE'S LIST ARE **NOT** COVERED HERE, AND THE ABSENCE IS
DELIBERATE AND NAMED (see `TestWhatThisSetCannotCheck` at the bottom):

* a STALE scoreboard, and
* the GENUINE SCORE CHANGE claim ("Boston took the lead in the eighth").

Both need the same thing, which does not exist on this path: a score observation
with a TIMESTAMP. `Event.home_score`/`away_score` are bare integers with no
`score_updated_at` column beside them, and `score_snapshots` — which has both
`captured_at` and the ordered history — is loaded by no caption path. Stubbing
either would have produced a field with a reader and no writer, which is exactly
the defect #5453 had just finished repairing.
"""

from datetime import datetime, timedelta, timezone

import pytest

# One import form for `app.routes.feed`, module-level: the AST guards below need
# the module object for `inspect.getsource`, and mixing `import x` with
# `from x import y` in one file is a CodeQL `py/import-and-import-from` note.
import app.routes.feed as feed_module

from app.utils.feed_reasons import compose_live_claim, generate_event_reason
from app.utils.highlights import (
    EventFlags,
    HighlightResult,
    compute_highlight,
    get_highlight_label,
    select_live_claim,
    underdog_leads,
)

NOW = datetime(2026, 9, 12, 2, 0, tzinfo=timezone.utc)

#: Claims a caption may not make from price evidence. Matched case-insensitively
#: as substrings, because the ban is on the CLAIM, not on one spelling of it:
#: "Momentum surge" and "Momentum shift" are the same false assertion.
FORBIDDEN_CLAIM_SUBSTRINGS = ("momentum", "lead change")


def _label_of(**flags) -> str:
    return get_highlight_label(HighlightResult(flags=EventFlags(**flags))) or ""


def _live(
    *,
    home_score,
    away_score,
    opening_home_prob=0.62,
    current_home_prob=0.44,
    status="live",
):
    """A real `compute_highlight` run, so a classification move breaks this too."""
    return compute_highlight(
        status=status,
        commence_time=NOW - timedelta(minutes=40),
        sport_key="baseball_mlb",
        opening_home_prob=opening_home_prob,
        opening_away_prob=1 - opening_home_prob,
        opening_favorite="home" if opening_home_prob > 0.5 else "away",
        current_home_prob=current_home_prob,
        current_away_prob=1 - current_home_prob,
        home_score=home_score,
        away_score=away_score,
        completed_at=(NOW - timedelta(hours=1)) if status != "live" else None,
        now=NOW,
    )


def _reason(
    *,
    home_score,
    away_score,
    opening_home_prob=0.62,
    home_probability=0.44,
    status="live",
    highlight_reasons=("favorite_switched", "major_prob_swing"),
):
    return generate_event_reason(
        home_team="Milwaukee Brewers",
        away_team="Cincinnati Reds",
        status=status,
        highlight_reasons=list(highlight_reasons),
        home_probability=home_probability,
        away_probability=1 - home_probability,
        opening_home_prob=opening_home_prob,
        home_score=home_score,
        away_score=away_score,
    )


# ── A. MOMENTUM FROM A PRICE MOVE ─────────────────────────────────────────────


class TestMomentumIsNotClaimedFromAMove:
    """The specimens reach the branch by NOT switching favourite.

    0.80 -> 0.62 is an 18-point swing that never crosses 0.50, so
    `favorite_switched` stays False and the ladder falls past the upset arm to
    the major-swing arm — which is where "Momentum shift" lived. A specimen
    that crosses over returns "Odds moved" one rung earlier and would pass
    every assertion below without ever touching the code this ship changed.
    """

    def _rout(self):
        return _live(
            home_score=17, away_score=0, opening_home_prob=0.80,
            current_home_prob=0.62,
        )

    def _one_run(self):
        return _live(
            home_score=2, away_score=1, opening_home_prob=0.80,
            current_home_prob=0.62,
        )

    def test_the_specimens_reach_the_branch_this_ship_changed(self):
        """Without this the four assertions below are vacuous."""
        for result in (self._rout(), self._one_run()):
            assert result.flags.favorite_switched is False
            assert result.flags.probability_swing == "major"
            assert result.flags.someone_is_leading is True

    def test_the_seventeen_nil_rout_does_not_say_momentum(self):
        """FORBIDDEN. Brewers 17 - Reds 0, the actual production card."""
        assert "momentum" not in (get_highlight_label(self._rout()) or "").lower()

    def test_the_one_run_game_does_not_say_momentum_either(self):
        """FORBIDDEN, and the point of the pair: the old predicate could not
        tell these two cards apart, and printed the same sentence on both."""
        assert "momentum" not in (get_highlight_label(self._one_run()) or "").lower()

    def test_the_rout_and_the_one_run_game_are_still_not_silenced(self):
        """CONTROL (ruling 146). The price move is real and is still said."""
        rout = get_highlight_label(self._rout()) or ""
        tight = get_highlight_label(self._one_run()) or ""
        assert rout, "the card lost its caption instead of losing its false claim"
        assert tight
        assert "odds" in rout.lower()

    def test_an_unchanged_scoreboard_never_bought_momentum_and_still_does_not(self):
        """FORBIDDEN + the #4580 case, which this ship generalises."""
        assert "momentum" not in _label_of(
            is_live=True, probability_swing="major", someone_is_leading=None
        ).lower()

    def test_the_accelerating_arm_makes_no_momentum_claim(self):
        """FORBIDDEN. `momentum_acceleration` is the second derivative of the
        PRICE; it reads no scoreboard at all, so it claimed even less."""
        result = HighlightResult(
            flags=EventFlags(is_live=True), reasons=["momentum_accelerating"]
        )
        label = get_highlight_label(result) or ""
        assert "momentum" not in label.lower()

    def test_the_accelerating_arm_still_says_the_true_thing(self):
        """CONTROL."""
        result = HighlightResult(
            flags=EventFlags(is_live=True), reasons=["momentum_accelerating"]
        )
        assert get_highlight_label(result) == "Odds moving faster"


# ── B. A LEAD CHANGE THAT NOBODY SCORED ───────────────────────────────────────


class TestALeadChangeNeedsTheScoreboard:
    def test_a_probability_crossing_is_not_a_lead_change(self):
        """FORBIDDEN. `has_lead_changes` counts 50% crossings, nothing else."""
        assert "lead change" not in _label_of(
            is_live=True, is_close_matchup=True, has_lead_changes=True
        ).lower()

    def test_the_crossing_is_still_reported_as_what_it_is(self):
        """CONTROL. The signal survives; the subject moves to the market."""
        assert (
            _label_of(is_live=True, is_close_matchup=True, has_lead_changes=True)
            == "Odds flipped"
        )

    def test_no_live_shape_at_all_can_produce_the_forbidden_claims(self):
        """FORBIDDEN, swept rather than sampled.

        Every combination of the live flags that can reach a label, so a future
        branch cannot reintroduce either claim behind a condition this file
        happened not to name.
        """
        seen = []
        for swing in ("major", "minor", "stable"):
            for leading in (True, False, None):
                for lead_changes in (True, False):
                    for switched in (True, False):
                        for extra in ([], ["momentum_accelerating"]):
                            label = get_highlight_label(
                                HighlightResult(
                                    flags=EventFlags(
                                        is_live=True,
                                        probability_swing=swing,
                                        someone_is_leading=leading,
                                        underdog_is_leading=leading,
                                        has_lead_changes=lead_changes,
                                        favorite_switched=switched,
                                    ),
                                    reasons=list(extra),
                                )
                            )
                            seen.append(label or "")
        assert seen, "the sweep built no labels — the guard would be vacuous"
        for label in seen:
            for banned in FORBIDDEN_CLAIM_SUBSTRINGS:
                assert banned not in label.lower(), f"{banned!r} survives in {label!r}"

    @pytest.mark.parametrize(
        "was_served", ["Momentum shift", "Momentum surge", "Lead change"]
    )
    def test_the_sweeps_predicate_catches_what_it_is_for(self, was_served):
        """THE SWEEP'S RED CHECK. A ban list that matches nothing passes every
        sweep it is pointed at. These are the three labels the ladder returned
        before this ship — fed to the sweep's own predicate, each must fail it.
        """
        assert any(
            banned in was_served.lower() for banned in FORBIDDEN_CLAIM_SUBSTRINGS
        )


# ── C. THE FIELD SENTENCE, AND THE 0-0 CARD ───────────────────────────────────


class TestTheSentenceOnlyNamesTheFieldWhenItCanSeeIt:
    @pytest.mark.parametrize(
        "home_score,away_score,why",
        [
            (0, 0, "0-0 is a known 'nobody leads', not a missing answer"),
            (2, 2, "tied at 2-2, same reason"),
            (None, None, "41 of 64 live rows carry no score"),
            (3, None, "half a scoreboard is not a scoreboard"),
        ],
    )
    def test_no_lead_is_claimed_without_one(self, home_score, away_score, why):
        """FORBIDDEN."""
        text = _reason(home_score=home_score, away_score=away_score)
        assert "leading" not in text, why
        assert "underdog" not in text

    def test_the_0_0_card_still_says_the_true_thing(self):
        """CONTROL. The price moved 18 points; that is sayable, and said."""
        assert _reason(home_score=0, away_score=0) == (
            "Cincinnati Reds chance rose from 38% to 56%"
        )

    def test_the_underdog_actually_ahead_names_the_side_and_the_baseline(self):
        """CONTROL, and the ship: the number the claim rests on is handed over."""
        assert _reason(home_score=1, away_score=3) == (
            "Cincinnati Reds leading after starting at 38%"
        )

    def test_the_mirror_side_is_named_correctly(self):
        """CONTROL. A hard-coded side would pass the test above alone."""
        assert _reason(home_score=3, away_score=1, opening_home_prob=0.38) == (
            "Milwaukee Brewers leading after starting at 38%"
        )

    def test_the_favourite_ahead_is_never_called_an_underdog(self):
        """FORBIDDEN."""
        assert "underdog" not in _reason(home_score=3, away_score=1)
        assert "leading" not in _reason(home_score=3, away_score=1)

    def test_the_price_co_gate_is_gone(self):
        """THE BEHAVIOURAL PROOF THAT THE SELECTOR IS WIRED IN.

        The underdog sentence used to require `"favorite_switched" in reasons` —
        a PRICE event — before it would state a FIELD fact. A live card where
        the underdog is ahead but the market has not yet come round (the common
        early-game shape) fell through to "Tight game".

        With no highlight reasons at all there is nothing but the selector left
        to produce this sentence, so this cannot pass against the old gate and
        cannot pass against a selector that is imported but never called.
        """
        assert _reason(
            home_score=1, away_score=3, highlight_reasons=[]
        ) == "Cincinnati Reds leading after starting at 38%"


# ── D. TENSE: A FINAL IS NOT LIVE, AND A DECIDED GAME IS NOT BREWING ──────────


class TestTense:
    def test_a_final_card_gets_no_live_sentence(self):
        """FORBIDDEN. The live tense on a settled card."""
        text = _reason(home_score=1, away_score=3, status="completed")
        assert "leading" not in text
        assert "chance rose" not in text

    def test_a_settled_upset_still_says_what_happened(self):
        """CONTROL — settled means settled, and the result is still stated."""
        assert _reason(
            home_score=1,
            away_score=3,
            status="completed",
            highlight_reasons=["upset"],
        ) == "Won as 38% underdog"

    @pytest.mark.parametrize("status", ["scheduled", "completed", "closed", None])
    def test_the_selector_answers_nothing_off_a_live_card(self, status):
        """FORBIDDEN, at the selector rather than at one of its renderers."""
        assert (
            select_live_claim(
                status=status,
                opening_home_prob=0.62,
                current_home_prob=0.20,
                home_score=1,
                away_score=3,
            )
            is None
        )

    def test_the_selector_answers_on_a_live_card(self):
        """CONTROL for the parametrisation above — otherwise it passes on a
        selector that returns None for everything."""
        assert (
            select_live_claim(
                status="live",
                opening_home_prob=0.62,
                current_home_prob=0.20,
                home_score=1,
                away_score=3,
            )
            == "underdog_lead"
        )

    def test_a_near_certain_upset_is_underway_not_brewing(self):
        """CONTROL (#5047). Near-100% reads as decided, not as a possibility."""
        assert get_highlight_label(
            _live(home_score=1, away_score=9, opening_home_prob=0.62,
                  current_home_prob=0.03)
        ) == "Upset underway"

    def test_a_live_upset_with_real_doubt_is_still_brewing(self):
        """CONTROL, the other side of the same threshold."""
        assert get_highlight_label(
            _live(home_score=1, away_score=3, opening_home_prob=0.62,
                  current_home_prob=0.40)
        ) == "Upset brewing"


# ── E. THE CAPTION IS RECOMPUTED, NOT REMEMBERED ──────────────────────────────


class TestAScoreCorrectionReachesTheReader:
    def test_a_corrected_score_changes_the_sentence(self):
        """A caption that survived a score correction would be the same lie in
        a slower form. Both producers are pure functions of the row, so the
        correction lands the moment the row does — asserted, not assumed."""
        wrong = _reason(home_score=1, away_score=3)
        corrected = _reason(home_score=3, away_score=1)
        assert wrong != corrected
        assert "leading" in wrong
        assert "leading" not in corrected

    def test_a_corrected_score_changes_the_label(self):
        assert get_highlight_label(_live(home_score=1, away_score=3)) == (
            "Upset brewing"
        )
        assert get_highlight_label(_live(home_score=3, away_score=1)) == "Odds moved"


# ── F. #4596 — THE PILL AND THE CAPTION CANNOT DESCRIBE DIFFERENT EVENTS ──────


class TestThePillAndTheCaptionAgree:
    """`headline` and `data.highlight.label` are both `get_highlight_label`; the
    caption is `generate_event_reason`. Before T10-1 the two ladders read the
    same rows and reached their own conclusions. Now both route the field claim
    through `underdog_leads`/`select_live_claim`, so the invariant below holds by
    construction rather than by coincidence.
    """

    @pytest.mark.parametrize("home_score,away_score", [
        (0, 0), (2, 2), (1, 3), (3, 1), (17, 0), (None, None), (0, 1),
    ])
    @pytest.mark.parametrize("opening_home_prob", [0.38, 0.62])
    @pytest.mark.parametrize("current_home_prob", [0.20, 0.44, 0.56, 0.80])
    def test_an_upset_pill_always_has_a_leading_sentence_under_it(
        self, home_score, away_score, opening_home_prob, current_home_prob
    ):
        result = _live(
            home_score=home_score,
            away_score=away_score,
            opening_home_prob=opening_home_prob,
            current_home_prob=current_home_prob,
        )
        label = get_highlight_label(result) or ""
        text = _reason(
            home_score=home_score,
            away_score=away_score,
            opening_home_prob=opening_home_prob,
            home_probability=current_home_prob,
        )
        if "upset" in label.lower():
            assert "leading" in text, (
                f"pill {label!r} claims the underdog is ahead and the caption "
                f"{text!r} does not — the two ladders have drifted apart again"
            )
        if "leading" in text:
            assert underdog_leads(opening_home_prob, home_score, away_score) is True

    def test_the_matrix_actually_produces_both_kinds_of_card(self):
        """The invariant above is vacuous if no shape in the matrix reaches an
        upset pill, so prove at least one does and at least one does not."""
        with_upset = get_highlight_label(
            _live(home_score=1, away_score=3, opening_home_prob=0.62,
                  current_home_prob=0.40)
        )
        without = get_highlight_label(
            _live(home_score=0, away_score=0, opening_home_prob=0.62,
                  current_home_prob=0.44)
        )
        assert "upset" in (with_upset or "").lower()
        assert "upset" not in (without or "").lower()


# ── G. THE RETIRED CLAIMS CANNOT BE WRITTEN BACK BY ACCIDENT ──────────────────


def _served_string_literals(module_name: str) -> set[str]:
    """Every string literal a module can actually EMIT.

    Parsed, not grepped, for two reasons that both bit this file on its first
    run: comments are not in the AST at all, and the prose above each retired
    branch quotes the label it retired — a `"Momentum shift" not in source`
    scan fails on its own explanation. Docstrings are excluded for the same
    reason; the one below names all three retired labels.
    """
    import ast
    import importlib
    import inspect

    tree = ast.parse(inspect.getsource(importlib.import_module(module_name)))
    docstring_nodes = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstring_nodes.add(id(body[0].value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstring_nodes
    }


class TestTheRetiredStringsAreGone:
    @pytest.mark.parametrize(
        "module", ["app.utils.highlights", "app.utils.feed_reasons"]
    )
    @pytest.mark.parametrize(
        "retired", ["Momentum shift", "Momentum surge", "Lead change"]
    )
    def test_no_producer_can_return_the_retired_label(self, module, retired):
        """A removal is the one claim a source scan CAN settle: a string literal
        that is not in the module cannot be returned from it. (The converse —
        that a present string RUNS — is what a source scan cannot prove, which
        is why every other class in this file drives the functions.)"""
        assert retired not in _served_string_literals(module)

    def test_the_extractor_finds_the_labels_that_are_still_served(self):
        """RED CHECK. An extractor that returns an empty set passes the three
        assertions above against a module that still serves all three."""
        literals = _served_string_literals("app.utils.highlights")
        for still_served in ("Odds moved", "Odds flipped", "Odds moving faster",
                             "Upset brewing", "Recent upset"):
            assert still_served in literals


# ── H. THE CAPTION SLOT (#4596) — AND THE RANK THAT MUST NOT MOVE WITH IT ────


def _feed_item_dict_node():
    """The `{"type": "event", ...}` literal `routes/feed.py` serves.

    Selected by its `"type": "event"` constant, not by "the first dict with
    these keys" — the two futures item literals in the same module carry the
    same five keys and one of them comes first in a walk.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(feed_module))
    matches = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        pairs = {
            k.value: v
            for k, v in zip(node.keys, node.values)
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
        if {"reason", "headline", "data", "_rank_score"} <= set(pairs):
            type_node = pairs.get("type")
            if (
                isinstance(type_node, ast.Constant)
                and type_node.value == "event"
            ):
                matches.append(node)
    assert len(matches) == 1, (
        f"expected exactly one event feed item literal, found {len(matches)} — "
        "retarget this guard rather than deleting it (#4596/#5439)"
    )
    return matches[0]


class TestTheCaptionSlotIsWired:
    """A backend caption nobody renders is not a ship.

    `feedContextSnippet` reads `item.headline || item.reason` on an unsettled
    card, so before this ship the specific sentence in `reason` reached no
    reader on a live card — 11 of 11 on #4596's census. These pin the two
    halves of the fix: the caption takes the CLAIM, and the pill does not move.
    """

    def test_feed_composes_the_claim_with_the_scoreboard(self):
        """The #4580 wiring guard's shape: an optional argument left off does
        not raise, it silently makes every card claimless."""
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(feed_module))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "compose_live_claim"
        ]
        assert calls, "routes/feed.py no longer composes a live claim (#5439)"
        for call in calls:
            passed = {kw.arg for kw in call.keywords}
            assert {
                "home_score",
                "away_score",
                "opening_home_prob",
                "home_probability",
                "status",
            } <= passed, f"compose_live_claim is under-fed at line {call.lineno}"

    def test_the_caption_slot_no_longer_serves_the_bare_bucket_label(self):
        """FORBIDDEN (#4596). `"headline": get_highlight_label(result)` is the
        line that threw the sentence away."""
        import ast

        node = _feed_item_dict_node()
        headline_value = next(
            v
            for k, v in zip(node.keys, node.values)
            if isinstance(k, ast.Constant) and k.value == "headline"
        )
        assert not (
            isinstance(headline_value, ast.Call)
            and isinstance(headline_value.func, ast.Name)
            and headline_value.func.id == "get_highlight_label"
        ), "the caption is back to the bucket label — #4596 has regressed"
        assert "_live_claim" in ast.dump(headline_value)

    def test_the_pill_still_carries_the_bucket_label(self):
        """CONTROL, and the other half of #4596's option 1: label AND sentence.
        A fix that moved the sentence into both slots would print it twice."""
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(feed_module))
        pill_args = [
            kw.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            for kw in node.keywords
            if kw.arg == "highlight_label"
        ]
        assert pill_args, "nothing sets the pill any more (#5439)"
        for value in pill_args:
            assert (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "get_highlight_label"
            ), "the pill stopped being the bucket label"

    def test_a_claim_sentence_is_not_the_pill_text(self):
        """The two slots must actually differ, or the split bought nothing."""
        result = _live(home_score=1, away_score=3)
        claim = compose_live_claim(
            home_team="Milwaukee Brewers",
            away_team="Cincinnati Reds",
            status="live",
            home_probability=0.44,
            away_probability=0.56,
            opening_home_prob=0.62,
            home_score=1,
            away_score=3,
        )
        assert claim is not None
        assert claim.sentence != get_highlight_label(result)


class TestTheDemotionExceptionDidNotMoveWithTheCaption:
    """The rank guard on the caption change.

    `_is_discover_event_demotion_exception`'s keyword arm matched
    "upset"/"playoff"/"championship" in `item["headline"]`. The caption now
    holds a sentence that does not contain the word "upset", so the read was
    retargeted to the pill. These pin that the retarget is behaviour-preserving
    in BOTH shapes — a live underdog card must keep its exception, or a truth
    fix has silently capped every one of them at 35 (gotcha #24, notice 37).
    """

    def _item(self, *, headline, label=None):
        """Score 65 isolates the KEYWORD arm.

        The two arms above it fire at 85 (any) and 80 (major league), so a
        score of 82 makes every fixture exceptional for a reason that has
        nothing to do with the words — which is how the first draft of this
        class passed against both the old and the new read.
        """
        data = {
            "id": 1,
            "sport": "baseball_mlb",
            "status": "live",
            "event_tags": ["tier:1"],
        }
        if label is not None:
            data["highlight"] = {"label": label}
        return {"type": "event", "score": 65, "headline": headline, "data": data}

    def test_the_new_payload_shape_keeps_its_exception(self):
        """Post-ship: pill "Upset brewing", caption the claim sentence."""
        item = self._item(
            headline="Cincinnati Reds leading after starting at 38%",
            label="Upset brewing",
        )
        assert feed_module._is_discover_event_demotion_exception(item) is True

    def test_the_old_payload_shape_still_keeps_its_exception(self):
        """Pre-ship shape, and every fixture written against it."""
        assert feed_module._is_discover_event_demotion_exception(
            self._item(headline="Upset brewing")
        ) is True

    def test_a_claim_sentence_alone_is_not_an_exception(self):
        """RED CHECK. Had the read stayed on `headline`, this is the card that
        would have lost 47 points of score for saying something true."""
        assert feed_module._is_discover_event_demotion_exception(
            self._item(headline="Cincinnati Reds leading after starting at 38%")
        ) is False

    def test_an_ordinary_live_card_is_still_demotable(self):
        """CONTROL — the retarget did not make everything exceptional."""
        assert feed_module._is_discover_event_demotion_exception(
            self._item(headline="Tight game", label="Coin flip")
        ) is False


# ── WHAT THIS SET DELIBERATELY DOES NOT CHECK ────────────────────────────────


class TestWhatThisSetCannotCheck:
    """Named so the gap is a decision on the record, not an oversight."""

    def test_no_score_observation_carries_a_timestamp_on_this_path(self):
        """The directive asks for a STALE-scoreboard case and for a GENUINE
        SCORE CHANGE claim. Both need a dated score observation.

        `generate_event_reason` and `compute_highlight` are handed bare
        integers: there is no `score_updated_at` on `Event` and no observation
        instant in either signature, so "is this scoreboard fresh?" and "when
        did they take the lead?" are not merely unanswered here — they are
        unanswerable, and a freshness gate written at this layer would be a
        guess wearing a check's clothes.

        The rail that answers both is `score_snapshots` (`captured_at` plus the
        ordered history), which no caption path loads. This asserts the shape of
        the gap so that the day a timestamp does arrive in one of these
        signatures, this test fails and points at the two claims waiting for it.
        """
        import inspect

        for func in (generate_event_reason, compute_highlight):
            params = set(inspect.signature(func).parameters)
            assert not {
                p for p in params if "score" in p and ("at" in p or "time" in p)
            }, (
                f"{func.__name__} now takes a dated score observation — the "
                f"stale-scoreboard gate and the GENUINE SCORE CHANGE claim are "
                f"buildable; see #5439."
            )
