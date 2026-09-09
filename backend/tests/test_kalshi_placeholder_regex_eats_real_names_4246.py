"""#4246 — "Team Europe" and "Song Yadong" are names, not Kalshi placeholders.

Mystery-shopping `/sports` after #4223 deployed (standing notice 4 / D48). Three
`market_type: field` cards on the served payload ranked a QUESTION where a
contender's name belongs:

    2027 Ryder Cup Winner
      1. Will Team Europe win the Ryder Cup?    53.5%
      2. Will Team USA win the Ryder Cup?       41.5%
      3. Tie                                     6.0%

    Bantamweight Title Holder on Dec 31, 2026?
      1. Petr Yan                                                   53.8%
      ...
      5. Who will be the Bantamweight Title Holder on Dec 31, 2026?  1.4%

#4223 banned this shape one layer out, in a container FOLD. These cards never
fold: they are native Kalshi field markets, and the question is what our own
ingest chose to store in `futures_outcomes.name`.

WHAT THE VENUE ACTUALLY SERVES (read from Kalshi's own `/markets`, standing
notice 26, 2026-09-09) — every one of these markets carries the right name:

    KXPGARYDER-RC27-EUR        yes_sub_title="Team Europe"
    KXPGARYDER-RC27-USA        yes_sub_title="Team USA"
    KXPRESCUP-26-WORLD         yes_sub_title="Team World"
    KXUFCBANTAMWEIGHTTITLE-26-SYAD  yes_sub_title="Song Yadong"

So this is our bug, and the mechanism is one regex. `_GENERIC_OUTCOME_PATTERNS`
catches Kalshi's obfuscated labels ("Team A", "Option 1"). It is matched
IGNORECASE and its arms read `Team [A-Z0-9]+$` — under IGNORECASE `[A-Z0-9]+`
matches ANY single word, so "Team Europe" is a placeholder, "Team USA" is a
placeholder, and the fighter **Song Yadong** is a placeholder because "Song" is
one of the nouns. Each rejection falls through to `_kalshi_outcome_name` step 4,
which returns the market's own title — the question.

Reach measured on production the same morning: **373 outcome rows on 55 open
`field` markets** carried a name ending in `?`. The poll rewrites `name` on
conflict, so the fix drains without a backfill.

Two rules, and a third that keeps them enforceable:
  1. a placeholder suffix is a single letter or a run of digits, never a word;
  2. a name that ends in `?` can never be a contender, so step 4 refuses one;
  3. `_create_settled_market` had a second hand-inlined copy of the ladder, so a
     ban added to the helper was not a ban. One helper, one ladder.
"""

import re

import pytest

from app.services.kalshi_api import KalshiMarket
from app.tasks import kalshi as kalshi_task
from app.tasks.kalshi import (
    _is_generic_outcome_name,
    _is_question_title,
    _kalshi_outcome_name,
)


def _market(ticker: str, title: str, **kw) -> KalshiMarket:
    """A real `KalshiMarket`, so the fixture cannot drift from the parser."""
    return KalshiMarket(
        ticker=ticker,
        event_ticker=ticker.rsplit("-", 1)[0],
        title=title,
        status="active",
        **kw,
    )


# ── the four names the venue serves and we threw away ─────────────────────


@pytest.mark.parametrize(
    "name",
    ["Team Europe", "Team USA", "Team World", "Song Yadong"],
)
def test_a_real_name_is_not_a_placeholder(name):
    """Verbatim `yes_sub_title` values from Kalshi's own API, 2026-09-09."""
    assert _is_generic_outcome_name(name) is False


def test_the_ryder_cup_card_names_its_contenders():
    """Production group `kalshi:KXPGARYDER-RC27`, all three markets."""
    event_title = "2027 Ryder Cup Winner"
    served = [
        ("KXPGARYDER-RC27-EUR", "Will Team Europe win the Ryder Cup?", "Team Europe"),
        ("KXPGARYDER-RC27-USA", "Will Team USA win the Ryder Cup?", "Team USA"),
        (
            "KXPGARYDER-RC27-TIE",
            "Will Team USA and Team Europe tie in the Ryder Cup?",
            "Tie",
        ),
    ]
    names = [
        _kalshi_outcome_name(
            event_title,
            _market(ticker, title, yes_sub_title=sub, no_sub_title=sub),
            len(served),
        )
        for ticker, title, sub in served
    ]
    assert names == ["Team Europe", "Team USA", "Tie"]


def test_the_bantamweight_card_names_song_yadong():
    """The one stray on a nine-fighter card: `-SYAD`, ranked 5th at 1.4%."""
    name = _kalshi_outcome_name(
        "Bantamweight Title Holder on Dec 31, 2026?",
        _market(
            "KXUFCBANTAMWEIGHTTITLE-26-SYAD",
            "Who will be the Bantamweight Title Holder on Dec 31, 2026?",
            yes_sub_title="Song Yadong",
            no_sub_title="Song Yadong",
        ),
        9,
    )
    assert name == "Song Yadong"


def test_no_row_on_the_two_golf_cards_ends_in_a_question_mark():
    """The card read as a whole — the assertion the issue names as the guard."""
    cards = {
        "2027 Ryder Cup Winner": [
            (
                "KXPGARYDER-RC27-EUR",
                "Will Team Europe win the Ryder Cup?",
                "Team Europe",
            ),
            ("KXPGARYDER-RC27-USA", "Will Team USA win the Ryder Cup?", "Team USA"),
        ],
        "Presidents Cup Winner": [
            (
                "KXPRESCUP-26-USA",
                "Will Team USA win the Presidents Cup?",
                "Team USA",
            ),
            (
                "KXPRESCUP-26-WORLD",
                "Will Team World win the Presidents Cup?",
                "Team World",
            ),
        ],
    }
    for event_title, markets in cards.items():
        for ticker, title, sub in markets:
            name = _kalshi_outcome_name(
                event_title,
                _market(ticker, title, yes_sub_title=sub, no_sub_title=sub),
                len(markets),
            )
            assert not name.endswith("?"), f"{event_title}: {name!r}"


# ── what the rule must NOT cost ───────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Ticker D",
        "Option 1",
        "Option A",
        "Option 12",
        "Choice 1",
        "Person B",
        "Team 1",
        "Team A",
        "Player 1",
        "Candidate 1",
        "App H",
        "Song A",
        "Song 1",
        "Movie B",
        "Show C",
        "A",
        "42",
    ],
)
def test_every_obfuscated_label_the_pattern_was_written_for_is_still_generic(name):
    """Narrowing the suffix must not surrender a single original case."""
    assert _is_generic_outcome_name(name) is True


def test_a_distinct_non_question_title_is_still_used():
    """Step 4 is intact — the ban is on questions, not on titles."""
    name = _kalshi_outcome_name(
        "Best Picture 2027",
        _market("KXOSCAR-27-DUNE3", "Dune: Part Three", yes_sub_title="Option A"),
        8,
    )
    assert name == "Dune: Part Three"


def test_a_truly_generic_side_falls_to_the_ticker_not_to_the_question():
    """When the venue really has no name, the last resort is the ticker.

    This is the clause that makes the ban a ban rather than a preference: with
    no usable sub-title, step 4 used to hand back the question. It now cannot,
    whatever the sub-title was.
    """
    name = _kalshi_outcome_name(
        "2027 Ryder Cup Winner",
        _market(
            "KXPGARYDER-RC27-EUR",
            "Will Team Europe win the Ryder Cup?",
            yes_sub_title="Team A",
        ),
        3,
    )
    assert name == "Eur"


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Will Team Europe win the Ryder Cup?", True),
        ("Who will be the Bantamweight Title Holder on Dec 31, 2026?", True),
        ("Will Team Europe win the Ryder Cup?  ", True),
        ("Dune: Part Three", False),
        ("Team Europe", False),
    ],
)
def test_question_titles_are_recognised_by_the_trailing_mark(title, expected):
    assert _is_question_title(title) is expected


# ── one helper, one ladder ────────────────────────────────────────────────


def _function_source(name: str) -> str:
    """The slice of `kalshi.py` between `def <name>` and the next top-level def.

    Scoped to the FUNCTION, not the file: `_kalshi_outcome_name` itself reads
    `yes_sub_title`, and a file-wide scan would be satisfied by that.
    """
    import inspect

    src = inspect.getsource(kalshi_task)
    start = re.search(rf"^async def {re.escape(name)}\(", src, re.M)
    assert start, f"{name} not found in app/tasks/kalshi.py"
    rest = src[start.end() :]
    end = re.search(r"^(?:async )?def ", rest, re.M)
    return rest[: end.start()] if end else rest


def test_the_settled_backfill_uses_the_shared_namer():
    """It had its own copy of the ladder; a ban in the helper missed it.

    The settled-events backfill is the path a reader meets these names on as
    RESULTS. If it keeps its own ladder, every rule added here has to be added
    twice or it is not enforced — which is how this defect stayed reachable
    through #4223's fix.
    """
    body = _function_source("_create_settled_market")
    assert "_kalshi_outcome_name(" in body
    # Pinned on the LADDER's own signature, not on `yes_sub_title`: this
    # function also forwards `yes_sub_title` to the game-market namer, which is
    # a different and legitimate read. `_is_generic_outcome_name` is the rung
    # only the shared helper is allowed to call.
    assert "_is_generic_outcome_name(" not in body, (
        "_create_settled_market is re-inlining the naming ladder; call "
        "_kalshi_outcome_name instead so one ban covers both writers"
    )
