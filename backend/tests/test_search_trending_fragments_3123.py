"""#3123 — Trending must not be one stranger's keystrokes.

WHAT A PERSON SAW, on a freshly erased simulator against production
(native/017, D48 mystery-shop of the Search tab)::

    Trending
      Stanford    Sta    Stan    Stanfo    Stanf

Five chips, one word. `/typeahead` fires as a reader types and
`record_query` counts every prefix at or above `MIN_QUERY_CHARS`, so one person
typing "stanford" votes five times — once for each rung on the way. Trending has
five slots, and Trending is the only part of the Search empty state that claims
to be about OTHER PEOPLE. It was noise presented as signal, it crowded out real
trends, and it showed every reader the shape of one person's typing.

WHERE THE FIX IS, AND THE ONE IT DELIBERATELY IS NOT. `read_window` has exactly
two callers: this route, and `typeahead_warmer.resolve_head`, which picks what
the warmer warms. `search_trending.py`'s own header closes by warning that
changing what the endpoint counts "changes what the warmer heads from too, so it
is one decision, not two". So the collapse runs at the READ, composed by the
public endpoint, and `read_window` is untouched — the warmer still heads from the
uncollapsed window, and that stays a separate decision for the lane that owns it.
`test_the_warmers_window_is_not_collapsed` below is the pin on that promise.

WHY THE RULE IS THE CONSERVATIVE ONE. A row is a fragment when a strictly longer
row it prefixes scored AT LEAST AS HIGH. Under per-keystroke counting a prefix's
score is the number of people who typed THROUGH it, so it can only be >= the
score of anything it prefixes — equality means nobody stopped there. The
strictly-greater case is a real query and is KEPT. Over-collapsing costs a real
trend; under-collapsing costs a slot; only one of those is a lie.

🔴 **THE TIE-BREAK, which is why the route over-reads.** A fragment only ever
drops against a row scoring at least as high, and on a real `ZREVRANGE` such a
row ranks at or above it even on a tie — Redis breaks equal scores in REVERSE
lexicographic order, and a prefix sorts below the phrase extending it, so the
completion comes first. That is a Redis ordering guarantee the route would
otherwise silently depend on. This file refuses to depend on it: every endpoint
assertion runs against BOTH tie-break directions and requires the same five.
`test_a_one_times_read_is_not_enough_under_the_other_tie_break` is the mutation
that shows the over-read is load-bearing rather than decorative — and the
ascending direction it uses is not hypothetical, it is what the #2072 file's own
`FakeRedis` does today.
"""

from __future__ import annotations

import pytest

from app.utils import search_trending as st

# ---------------------------------------------------------------------------
# PART 1 — the rule, as a pure function. No Redis, no clock, no fake: the whole
# of `collapse_typing_fragments` is a list in and a list out, and a double
# standing between the assertion and the logic would only add a second thing
# that could be wrong.
# ---------------------------------------------------------------------------

#: The ladder from the issue's screenshot, at the one vote each a single walk
#: produces. Written longest-first and shortest-first in different tests
#: because the rule must not care what order it meets a chain in.
LADDER = [
    ("sta", 1.0),
    ("stan", 1.0),
    ("stanf", 1.0),
    ("stanfo", 1.0),
    ("stanford", 1.0),
]


def _queries(rows):
    return [q for q, _ in rows]


def test_the_screenshot_collapses_to_the_one_word_it_was() -> None:
    """Five chips, one walk, one vote each -> the phrase that was typed."""
    assert _queries(st.collapse_typing_fragments(LADDER)) == ["stanford"]


def test_the_chain_collapses_from_either_direction() -> None:
    """Order in must not decide the answer: a chain is a chain read backwards."""
    forward = st.collapse_typing_fragments(LADDER)
    backward = st.collapse_typing_fragments(list(reversed(LADDER)))
    assert _queries(forward) == _queries(backward) == ["stanford"]


def test_a_popular_prefix_outranking_its_completion_SURVIVES() -> None:
    """The guard against over-collapsing, and the reason the rule uses `<=`.

    Seven of those eight readers stopped at the two words they meant. Deleting
    "red sox" because one person went on to type "red sox yankees" would remove
    the single most real thing in the window.
    """
    rows = [("red sox", 8.0), ("red sox yankees", 1.0)]
    assert _queries(st.collapse_typing_fragments(rows)) == [
        "red sox",
        "red sox yankees",
    ]


def test_the_fragment_production_was_publishing() -> None:
    """🔴 THE SPECIMEN. `GET /api/events/search/trending`, read 2026-09-19 20:48Z,
    and photographed the same minute in the web search dropdown at 1280px
    (`artifacts-lane1b-408/01-trending-BEFORE.png`) — a reader could see this::

        red sox 8 · stanford 3 · yankes 2 ·
        stanford cardinal at duke blue devils 2 · stanfo 1

    `stanfo` is not a word. It is the fourth keystroke of `stanford`, which is
    sitting two chips to its left with three votes, and it was published as a
    thing other people are interested in. That is the whole of #3123 in one row.

    Everything else here stays, and that is the point of the inequality: `yankes`
    is a typo nobody completed in this window, and `stanford` at 3 outranks its
    own six-word completion at 2, so a reader who stopped at the school keeps
    their trend.
    """
    rows = [
        ("red sox", 8.0),
        ("stanford", 3.0),
        ("yankes", 2.0),
        ("stanford cardinal at duke blue devils", 2.0),
        ("stanfo", 1.0),
    ]
    assert st.collapse_typing_fragments(rows) == rows[:4]


def test_an_earlier_read_of_the_same_window_needed_no_change() -> None:
    """The same endpoint twenty minutes earlier, 2026-09-19 20:28Z. No rung had
    tied its completion yet, so the conservative rule correctly did nothing.

    Kept as a control: a collapse that fires on every window is not a collapse,
    it is a truncation, and this is the window that proves the difference.
    """
    rows = [
        ("red sox", 8.0),
        ("yankes", 2.0),
        ("stanford", 2.0),
        ("stanford cardinal at duke blue devils", 1.0),
        ("new york yankees", 1.0),
    ]
    assert st.collapse_typing_fragments(rows) == rows


def test_scores_are_never_merged() -> None:
    """Folding a fragment's count into its completion would double-count the
    completion's own typers — the same arithmetic error facing the other way."""
    out = st.collapse_typing_fragments(LADDER)
    assert out == [("stanford", 1.0)]


def test_relative_order_is_preserved() -> None:
    rows = [("celtics", 9.0), ("red", 4.0), ("red sox", 4.0), ("world cup", 2.0)]
    assert _queries(st.collapse_typing_fragments(rows)) == [
        "celtics",
        "red sox",
        "world cup",
    ]


def test_a_shared_prefix_that_nobody_typed_through_is_untouched() -> None:
    """ "stan" prefixes neither: unrelated words that merely look alike stay."""
    rows = [("stanford", 3.0), ("stanley cup", 3.0)]
    assert st.collapse_typing_fragments(rows) == rows


@pytest.mark.parametrize("rows", [[], [("nba", 5.0)]])
def test_degenerate_inputs(rows) -> None:
    assert st.collapse_typing_fragments(rows) == rows


def test_the_three_character_floor_was_not_raised() -> None:
    """#3123 suggested dropping "anything below a plausible length". It was not
    taken: `nba`, `ufc` and `mlb` are three characters and are real queries, so
    a higher floor would delete trends in order to hide typing."""
    assert st.MIN_QUERY_CHARS == 3


# ---------------------------------------------------------------------------
# PART 2 — the route. A fake whose tie-break direction is a PARAMETER, because
# the tie-break is the thing the over-read exists to not depend on.
# ---------------------------------------------------------------------------
class FakeRedis:
    """Enough Redis to answer `read_window`, with the tie-break made explicit.

    `reverse_lex_ties=True` is what a real server does on `ZREVRANGE`: equal
    scores come back in reverse lexicographic order. `False` is the ascending
    variant — not a strawman, it is what `test_search_trending_window_2072.py`'s
    own double does, so it is the shape a future reader is most likely to write.
    """

    def __init__(self, scores: dict[str, float], *, reverse_lex_ties: bool):
        self.scores = dict(scores)
        self.reverse_lex_ties = reverse_lex_ties
        self.read_sizes: list[int] = []

    def zunionstore(self, dest, keys, aggregate=None):
        return len(self.scores)

    def expire(self, key, seconds):
        return True

    def zrevrange(self, key, start, stop, withscores=False):
        ordered = sorted(
            self.scores.items(),
            key=lambda kv: (-kv[1], kv[0]),
            reverse=False,
        )
        if self.reverse_lex_ties:
            ordered = sorted(self.scores.items(), key=lambda kv: kv[0], reverse=True)
            ordered.sort(key=lambda kv: -kv[1])
        end = None if stop == -1 else stop + 1
        self.read_sizes.append(-1 if end is None else end - start)
        page = ordered[start:end]
        if withscores:
            return [(m.encode(), s) for m, s in page]
        return [m.encode() for m in page]


#: One person's walk toward "stanford" sitting beside one genuinely popular
#: query. This is the issue's situation exactly: the ladder is IN the top five,
#: so the reader loses four slots to it.
ONE_PERSONS_TYPING = {
    "red sox": 8.0,
    "sta": 1.0,
    "stan": 1.0,
    "stanf": 1.0,
    "stanfo": 1.0,
    "stanford": 1.0,
}


async def _serve(monkeypatch, rc) -> list[dict]:
    """Call the real route function with the client swapped underneath it."""
    from app.routes import events as ev
    from app.tasks import redis_state

    monkeypatch.setattr(redis_state, "get_redis_client", lambda: rc)
    payload = await ev.get_trending_searches()
    return payload["trending"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reverse_lex_ties", [True, False], ids=["real-redis", "ascending"]
)
async def test_the_endpoint_serves_the_word_not_the_keystrokes(
    monkeypatch, reverse_lex_ties
) -> None:
    """THE HEADLINE. Both tie-break directions, one answer, no fragments."""
    rc = FakeRedis(ONE_PERSONS_TYPING, reverse_lex_ties=reverse_lex_ties)
    served = await _serve(monkeypatch, rc)

    assert [row["query"] for row in served] == ["red sox", "stanford"]
    assert served[0]["count"] == 8
    assert served[1]["count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reverse_lex_ties", [True, False], ids=["real-redis", "ascending"]
)
async def test_the_endpoint_still_serves_five_when_five_are_real(
    monkeypatch, reverse_lex_ties
) -> None:
    """The collapse must not cost slots that were never the ladder's.

    Truncation happens AFTER the collapse, so a window with six real queries
    still fills all five — a route that sliced first and collapsed second would
    serve four here.
    """
    real = {
        "red sox": 9.0,
        "celtics": 8.0,
        "world cup": 7.0,
        "yankees": 6.0,
        "patriots": 5.0,
        "world series": 4.0,
    }
    served = await _serve(
        monkeypatch, FakeRedis(real, reverse_lex_ties=reverse_lex_ties)
    )
    assert [row["query"] for row in served] == [
        "red sox",
        "celtics",
        "world cup",
        "yankees",
        "patriots",
    ]


@pytest.mark.asyncio
async def test_the_route_over_reads_before_collapsing(monkeypatch) -> None:
    """The route asks for more than it serves, or the collapse sees a slice that
    has already thrown the completion away."""
    rc = FakeRedis(ONE_PERSONS_TYPING, reverse_lex_ties=True)
    await _serve(monkeypatch, rc)
    assert rc.read_sizes == [5 * st.FRAGMENT_SCAN_MULTIPLIER]
    assert st.FRAGMENT_SCAN_MULTIPLIER > 1


@pytest.mark.asyncio
async def test_a_one_times_read_is_not_enough_under_the_other_tie_break(
    monkeypatch,
) -> None:
    """🔴 THE MUTATION THAT PROVES THE OVER-READ IS LOAD-BEARING.

    Pin the multiplier to 1 and the route reads exactly the five it serves.
    Under the ascending tie-break the slice is `red sox, sta, stan, stanf,
    stanfo` — "stanford" never arrives, so the longest rung IN THE SLICE has
    nothing to drop against and **"stanfo" is published to a reader**. This test
    asserts that failure, so that if anyone ever lowers `FRAGMENT_SCAN_MULTIPLIER`
    the suite says what it costs instead of going quietly green.
    """
    monkeypatch.setattr(st, "FRAGMENT_SCAN_MULTIPLIER", 1)
    rc = FakeRedis(ONE_PERSONS_TYPING, reverse_lex_ties=False)
    served = await _serve(monkeypatch, rc)

    assert [row["query"] for row in served] == ["red sox", "stanfo"]


@pytest.mark.asyncio
async def test_an_unreadable_window_still_answers(monkeypatch) -> None:
    """Fail-open is unchanged: trending is never worth a 500."""

    class Broken:
        def zunionstore(self, *a, **k):
            raise RuntimeError("redis down")

    from app.routes import events as ev
    from app.tasks import redis_state

    monkeypatch.setattr(redis_state, "get_redis_client", lambda: Broken())
    assert await ev.get_trending_searches() == {"trending": []}


# ---------------------------------------------------------------------------
# PART 3 — the promise this fix made to the lane next door.
# ---------------------------------------------------------------------------
def test_the_warmers_window_is_not_collapsed() -> None:
    """`resolve_head` is `read_window`'s other caller and it must still see the
    window as counted. The collapse is the endpoint's composition, not
    `read_window`'s behaviour — "one decision, not two", per the module header.

    If someone ever moves the collapse inside `read_window`, this fails, and the
    failure is the conversation that should happen first.
    """
    rc = FakeRedis(ONE_PERSONS_TYPING, reverse_lex_ties=True)
    rows = st.read_window(rc, 40, now=1_786_998_600.0)
    assert "sta" in _queries(rows)
    assert "stanfo" in _queries(rows)
