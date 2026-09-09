"""#4146 — a card's sentence states the number the card prints.

On production Discover, 2026-09-08 22:5x PT (`GET /api/feed?limit=60`), ELEVEN of
forty-five cards printed one probability twice, a point apart, three millimetres
apart on the same row:

    This Sep 2026 is the hottest September ever?   hero 37%   caption "36% chance"
    Fed rate hike in 2026?                         row  71%   caption "70% chance"
    Which party will win the U.S. House?           row  85%   caption "leads at 84%"

Every one sat exactly on a .5 boundary, and that names the cause. The card's
number comes from `graded_card.rendered_percent`, which is **deliberately not**
`round()`: Python's built-in is banker's rounding (`round(70.5) == 70`) while
`Math.round` on web and `.rounded()` on Swift are half-up, so the canonical
implementation is `floor(x + 0.5)` and all three runtimes are driven through
`contracts/rendered_percent.json` under ruling 021 — share the DECISION, not the
ingredient. `feed_reasons.py` composed its own percent with the built-in, making
it a fourth runtime of the same decision that disagreed with the other three at
exactly the boundary the contract exists to pin.

🔴 THE INVARIANT IS NOT "USE HALF-UP", IT IS "SAY WHAT THE CARD SAYS". Those are
different, and #4146's body names the specimen that separates them: on a
two-sided card the pair rule (#2060) normalizes, rounds the LEADER once, and
DERIVES the other side as `100 - leader`, so a 0.505 affirmative can legitimately
print 49 while half-up on the raw probability says 51. There the sentence must
follow the card, not the rounder. A fix that merely swapped `round` for
`rendered_percent` would fix ten of the eleven and quietly keep the eleventh.

So the guards below stand in three places:

* at the ROUTE (`_score_futures`), where the invariant is checked against the
  card's OWN served `rendered_percent` values and nothing is hand-picked — the
  lesson CERT-2326 taught this lane: a producer-level census cannot see what an
  `or` or a later serializer does to the string;
* at the COMPOSERS, driven through every contract row that discriminates
  banker's rounding from half-up, so the sentence joins the contract the other
  three runtimes are already held to;
* at BOTH ROUTE SITES structurally, because the /sports futures rail
  (`_score_sports_mode_futures`) is a hand-maintained near-copy of
  `_score_futures` that the live guard's fixtures cannot reach, and a near-copy
  is exactly where a fix applied once survives as a bug.
"""

import ast
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Imported as MODULES, not as names: `test_the_route_guard_can_fail` monkeypatches
# attributes on both, and a module cannot be both `import`ed and `import from`ed
# without CodeQL's py/import-and-import-from (a note, but an avoidable one).
import app.routes.feed as feed_route
import app.utils.feed_reasons as fr
from app.utils.graded_card import rendered_percent
from app.utils.personalization import PersonalizationContext

CONTRACT = json.loads(
    (
        Path(__file__).resolve().parents[2] / "contracts" / "rendered_percent.json"
    ).read_text()
)

#: The rows where Python's built-in `round` and the contract disagree. These are
#: the only rows that can catch this bug; a run over the other eighteen is green
#: on the broken code.
DISCRIMINATING = [
    c
    for c in CONTRACT["cases"]
    if c.get("discriminates") and c.get("probability") is not None
]

#: The subset the FEED will actually admit and print. A card whose leader sits
#: at 1% (or at 12% across a wide field) is demoted by the feed's own quality
#: gates and never served, so a fixture built on one asserts nothing at all —
#: the "was it served" denominator below turns that into a loud failure rather
#: than a silent pass. The composer-level guards run every contract row; only
#: the route pass needs a card a reader could actually see.
ROUTE_CASES = [c for c in DISCRIMINATING if c["probability"] >= 0.5]
assert len(ROUTE_CASES) >= 3, (
    "fewer than three discriminating rows are servable; the route guard below "
    "is being defanged by the table it reads"
)

PERCENT_IN_TEXT = re.compile(r"(\d+)%")

CANONICAL_KEY = "sentence-states-the-printed-percent"


def _bankers(probability: float) -> int:
    """What the built-in gives — the number these guards must never see."""
    return round(probability * 100)


# ── 1. AT THE ROUTE: every percent in a served sentence is one the card prints ──


class _Outcome:
    def __init__(self, id, name, probability):
        self.id = id
        self.name = name
        self.external_id = None
        self.current_probability = probability
        self.probability_change_24h = 0.0
        self.opening_probability = None
        self.rank = None
        self.rank_change_24h = None
        self.team_id = None
        self.calibration_probability = None
        self.current_yes_bid = None
        self.current_yes_ask = None


class _Market:
    """A real object so `__dict__.get(...)` reads work, as in #250's harness."""

    def __init__(self, id, name, *, outcomes, category="politics"):
        now = datetime.now(timezone.utc)
        self.id = id
        self.name = name
        self.source = "polymarket"
        self.external_id = f"poly-{id}"
        self.sport_id = None
        self.sport = None
        self.category = category
        self.llm_sport_category = category
        self.market_tier = 1
        self.canonical_market_key = CANONICAL_KEY
        self.group_id = None
        self.group_type = None
        self.image_url = None
        self.hook_description = None
        self.hook_generated_at = None
        self.hook_leader_at_generation = None
        self.market_metadata = {}
        self.curation_score_adj = 0
        self.volume_24h = 250000
        self.updated_at = now
        self.commence_time = now - timedelta(days=1)
        self.resolution_date = now + timedelta(days=30)
        self.status = "open"
        self.created_at = now - timedelta(days=10)
        self.llm_league = None
        self.llm_gender = None
        self.llm_level = None
        self.outcomes = outcomes


def _mock_db(markets):
    db = AsyncMock()

    def make_result(*a, **k):
        r = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [m.id for m in markets]
        unique = MagicMock()
        unique.all.return_value = markets
        scalars.unique.return_value = unique
        r.scalars.return_value = scalars
        r.all.return_value = []
        return r

    db.execute = AsyncMock(side_effect=make_result)
    return db


async def _serve(markets, *, source_count: int = 2):
    with (
        patch(
            "app.routes.feed._external_curator_recall_market_ids",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.routes.feed._get_canonical_source_counts",
            new=AsyncMock(return_value={CANONICAL_KEY: source_count}),
        ),
        patch(
            "app.tasks.redis_state.get_async_redis_client",
            side_effect=Exception("no redis in test"),
        ),
    ):
        return await feed_route._score_futures(
            _mock_db(markets),
            datetime.now(timezone.utc),
            None,
            PersonalizationContext(),
        )


def _served_sentences(item: dict) -> dict[str, str]:
    return {
        slot: item.get(slot) or "" for slot in ("headline", "reason", "context_summary")
    }


def _printed_percents(item: dict) -> set[int]:
    """Every whole percent this card actually shows a reader.

    Taken off the served payload — `top_outcomes[*].rendered_percent` is the
    number the row prints — rather than recomputed here, because recomputing it
    in the test is the same mistake the code under test made.
    """
    printed = set()
    for outcome in (item.get("data") or {}).get("top_outcomes") or []:
        if outcome.get("rendered_percent") is not None:
            printed.add(int(outcome["rendered_percent"]))
    return printed


def _field_outcomes(leader_probability: float) -> list[_Outcome]:
    """A leader plus a field, deliberately NOT a complement pair.

    A two-outcome card goes down #2060's pair path — normalize, round the leader,
    derive the other — so the boundary under test would never reach
    `rendered_percent` and the row would prove nothing. A field of three or more
    renders each outcome independently, which is the shape all six live
    `leads at` misses had (`2028 Democratic presidential nominee`, `Brazil
    Presidential Election`, the US Open winner card).
    """
    remainder = 1 - leader_probability
    parts = int(remainder / leader_probability) + 1
    each = round(remainder / parts, 6)
    outcomes = [_Outcome(101, "Gavin Newsom", leader_probability)]
    outcomes += [_Outcome(102 + i, f"Candidate {i + 1}", each) for i in range(parts)]
    assert all(
        o.current_probability < leader_probability for o in outcomes[1:]
    ), "the fixture's 'leader' is not the leader"
    return outcomes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    ROUTE_CASES,
    ids=[str(c["probability"]) for c in ROUTE_CASES],
)
async def test_a_served_sentence_never_states_a_percent_the_card_does_not_print(case):
    """The live defect, at the route, on the boundaries that catch it.

    The assertion compares the sentence against the card's OWN served numbers,
    so it cannot be satisfied by a second correct rounder — only by the sentence
    reading what the card prints.
    """
    probability = case["probability"]
    market = _Market(
        1,
        "2028 Democratic presidential nominee",
        outcomes=_field_outcomes(probability),
    )
    items = await _serve([market])
    futures = [i for i in items if i["type"] == "futures"]

    # Eligible denominator, both halves: the card was admitted AND it printed at
    # least one percent. Without these a dropped fixture or an empty card would
    # pass this test having proved nothing (#4169's lesson).
    assert len(futures) == 1, f"the fixture card was not served: {items}"
    printed = _printed_percents(futures[0])
    assert printed, f"the card printed no percent at all: {futures[0]}"

    offenders = {}
    for slot, text in _served_sentences(futures[0]).items():
        for stated in PERCENT_IN_TEXT.findall(text):
            if int(stated) not in printed:
                offenders[slot] = (text, int(stated))
    assert not offenders, (
        f"p={probability}: card prints {sorted(printed)}, but the sentence says "
        f"otherwise — {offenders}. Half-up gives {case['percent']}, "
        f"banker's gives {_bankers(probability)}."
    )


@pytest.mark.asyncio
async def test_the_route_guard_can_fail(monkeypatch):
    """The guard above is only worth its runtime if a regression reds it.

    Re-creates the defect exactly as it was written — the route does not hand the
    composer the printed percent, so the composer derives one, with the built-in
    — and asserts the route-level invariant catches it. Note WHICH knob has to be
    turned: after the fix the served path never rounds at all, so breaking the
    rounder alone is not enough to reproduce the bug. That is the fix, stated as
    a test.
    """
    monkeypatch.setattr(feed_route, "_printed_leader_percent", lambda rows: None)
    monkeypatch.setattr(
        feed_route, "_printed_affirmative_percent", lambda rows, names: None
    )
    monkeypatch.setattr(
        fr, "rendered_percent", lambda probability: round((probability or 0) * 100)
    )

    # 0.625 -> half-up 63, banker's 62.
    market = _Market(
        2,
        "2028 Democratic presidential nominee",
        outcomes=_field_outcomes(0.625),
    )
    items = await _serve([market])
    futures = [i for i in items if i["type"] == "futures"]
    assert len(futures) == 1

    printed = _printed_percents(futures[0])
    stated = {
        int(p)
        for text in _served_sentences(futures[0]).values()
        for p in PERCENT_IN_TEXT.findall(text)
    }
    assert printed, "the card printed no percent, so this proves nothing"
    assert stated, "no sentence stated a percent, so this proves nothing"
    assert stated - printed, (
        "re-creating the defect did NOT produce a sentence disagreeing with the "
        f"card (card {sorted(printed)}, sentences {sorted(stated)}), so the guard "
        "above cannot fail and is not evidence"
    )


# ── 2. AT THE COMPOSERS: the contract's own rows, every template ────────────


def _futures_kwargs(probability: float) -> dict:
    return dict(
        highlight_reasons=[],
        leader_name="Democrats",
        leader_probability=probability,
        market_name="Which party will win the U.S. House?",
        source_count=2,
    )


@pytest.mark.parametrize(
    "case",
    DISCRIMINATING,
    ids=[str(c["probability"]) for c in DISCRIMINATING],
)
def test_the_leads_at_templates_follow_the_contract(case):
    """`<name> leads at N%` — six of the eleven live misses were this family.

    #4146's body scoped the defect to the `N% chance` sentences; the `leads at`
    templates are the same defect in a different template and were measured at
    six of thirty-one on the same page.
    """
    probability, expected = case["probability"], case["percent"]
    wrong = _bankers(probability)
    assert expected != wrong, "this row does not discriminate; the table moved"

    for name, sentence in (
        ("headline", fr.generate_futures_headline(**_futures_kwargs(probability))),
        (
            "context_summary",
            fr.generate_futures_context_summary(
                headline="", **_futures_kwargs(probability)
            ),
        ),
        ("reason", fr.generate_futures_reason(**_futures_kwargs(probability))),
    ):
        stated = PERCENT_IN_TEXT.findall(sentence)
        assert stated, f"{name} stated no percent for p={probability}: {sentence!r}"
        assert int(stated[0]) == expected, (
            f"{name} says {stated[0]}% for p={probability}; the card prints "
            f"{expected}% (banker's rounding gives {wrong}%): {sentence!r}"
        )


@pytest.mark.parametrize(
    "case",
    DISCRIMINATING,
    ids=[str(c["probability"]) for c in DISCRIMINATING],
)
def test_the_percent_chance_template_follows_the_contract(case):
    """`N% chance` — the family #4146's body measured at six of twelve."""
    probability, expected = case["probability"], case["percent"]
    # `highlight_reasons=["resolving_soon_7d"]`, not `[]`. #4056 emptied the
    # no-signal terminal of `compose_binary_card_copy` — a card with no story now
    # says nothing rather than restating its own hero number — so `[]` no longer
    # produces an `N% chance` sentence for this contract to check. The row's own
    # control at the bottom is what caught that, exactly as intended.
    #
    # `resolving_soon_7d` is the nearest branch that still USES the `N% chance`
    # template ("15% chance, resolving this week"), so the rounding contract under
    # test is unchanged and still discriminates banker's from half-up.
    copy = fr.compose_binary_card_copy(
        market_name="Will the U.S. invade Iran before 2027?",
        highlight_reasons=["resolving_soon_7d"],
        affirmative_probability=probability,
    )
    for slot, text in copy._asdict().items():
        stated = PERCENT_IN_TEXT.findall(text)
        if not stated:
            continue
        assert int(stated[0]) == expected, (
            f"{slot} says {stated[0]}% for p={probability}; the card prints "
            f"{expected}% (banker's gives {_bankers(probability)}): {text!r}"
        )
    assert PERCENT_IN_TEXT.search(copy.context_summary), (
        "the bare-probability sentence stated no percent, so this row asserted "
        "nothing"
    )


def test_the_sentence_follows_the_card_when_the_pair_rule_derives_the_complement():
    """The miss NO ROUNDER CAN FIX, transcribed from the live card.

    Production `c7cf9898`, 2026-09-08 23:2x PT — `Will New Jersey Devils advance
    to the Second Round of the 2027 Stanley Cup Playoffs?`:

        Not New Jersey Devils   p=0.505   card prints 51
        New Jersey Devils       p=0.495   card prints 49
        caption                                "50% chance"

    The caption describes the AFFIRMATIVE, which is the 0.495 row. Note what
    that makes the arithmetic:

    * banker's `round(49.5)` = **50**
    * half-up `rendered_percent(0.495)` = **50**
    * what the card prints for that row = **49**

    Both rounders agree, and both are wrong, because #2060's pair rule never
    rounds this side at all — it rounds the LEADER once (0.505 -> 51) and
    DERIVES the complement as `100 - 51`. So no rounding of the affirmative
    probability can reproduce 49, and a fix that swapped `round` for the half-up
    rounder would have left this card saying 50 beside a row saying 49.

    The only thing that gets it right is reading the row. That is the whole
    thesis of #4146, and this is the specimen that proves the weaker reading
    ("just use half-up") insufficient rather than merely inelegant.
    """
    # #4056 — `["resolving_soon_7d"]` not `[]`; see the note on the contract test
    # above. The pair-rule specimen this test exists for is untouched.
    copy = fr.compose_binary_card_copy(
        market_name="Will New Jersey Devils advance to the Second Round?",
        highlight_reasons=["resolving_soon_7d"],
        affirmative_probability=0.495,
        rendered_affirmative_percent=49,
    )
    stated = PERCENT_IN_TEXT.findall(copy.context_summary)
    assert stated, f"no percent in {copy.context_summary!r}"
    assert int(stated[0]) == 49, (
        "the sentence re-derived the percent instead of stating the one the card "
        f"prints: {copy.context_summary!r}"
    )
    # The two rounders this fixture must out-run, asserted rather than asserted
    # ABOUT — if either ever yields 49, this test stops discriminating and the
    # docstring above has gone stale.
    assert _bankers(0.495) == 50 and rendered_percent(0.495) == 50, (
        "both rounders no longer agree on 50 for the affirmative side; this "
        "specimen no longer separates 'say what the card says' from 'use half-up'"
    )
    # And the half-up fallback still exists for callers that have no served row yet.
    # #4056 — this used to read `highlight_reasons=[]`, which now yields the empty
    # terminal and would have made the assertion vacuous in the other direction.
    assert PERCENT_IN_TEXT.findall(
        fr.compose_binary_card_copy(
            market_name="Will the U.S. invade Iran before 2027?",
            highlight_reasons=["resolving_soon_7d"],
            affirmative_probability=0.145,
        ).context_summary
    ) == ["15"], "without a served percent the composer must still be half-up"


def test_the_contract_still_has_rows_that_catch_this():
    """The parametrization above is only as good as the table it reads.

    Deleting the discriminating rows would make every test in this file pass
    vacuously while the bug returned — the exact way a table-driven guard dies.
    """
    assert len(DISCRIMINATING) >= 5, (
        f"only {len(DISCRIMINATING)} discriminating rows remain in "
        "contracts/rendered_percent.json; this file's guards are being defanged"
    )
    for case in DISCRIMINATING:
        assert rendered_percent(case["probability"]) != _bankers(case["probability"])


# ── 3. BOTH ROUTE SITES, not just the one the live guard can reach ──────────


#: The composers that put a percent in a sentence, spelled as `routes/feed.py`
#: calls them — these are matched against `ast.Name` ids in THAT file, so they are
#: bare names, not this module's `fr.` aliases. `compose_binary_card_copy` is not
#: here: the route never calls it directly — it is reached THROUGH these three,
#: which forward the affirmative percent they are given.
_SENTENCE_COMPOSERS = {
    "generate_futures_headline",
    "generate_futures_reason",
    "generate_futures_context_summary",
}

#: The two places a futures card's sentences are composed. Discover goes through
#: `_score_futures`; the /sports page's futures rail goes through
#: `_score_sports_mode_futures`, which is a near-copy — and a near-copy is
#: exactly where a fix applied once survives as a bug.
_ROUTE_SCORERS = ("_score_futures", "_score_sports_mode_futures")


def _composer_calls_in(function_name: str) -> list[tuple[int, str, set[str]]]:
    source = (
        Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py"
    ).read_text()
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ):
            return [
                (call.lineno, call.func.id, {k.arg for k in call.keywords})
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id in _SENTENCE_COMPOSERS
            ]
    raise AssertionError(f"{function_name} is gone from routes/feed.py")


@pytest.mark.parametrize("scorer", _ROUTE_SCORERS)
def test_every_route_site_hands_the_composers_the_printed_percent(scorer):
    """The live guard above drives `_score_futures`. This one reaches both.

    Structural on purpose, and honest about it: a served-payload guard for the
    /sports futures rail needs a whole second fixture universe (a real Sport, a
    sport_id, the sports-mode admission gates), and CERT-2326's lesson is that a
    guard which cannot reach a branch reports it clean. The reachable, cheap and
    decisive fact is that BOTH scorers pass the card's own percents to every
    composer they call — because the defect returns the moment one of them
    stops, and the two functions are near-copies maintained by hand.

    Deleting a kwarg at the sports-mode site reds this; adding a fourth call
    site without the kwargs reds this.
    """
    calls = _composer_calls_in(scorer)
    assert len(calls) == 3, (
        f"{scorer} makes {len(calls)} sentence-composer calls, expected 3 "
        f"(headline, reason, context_summary): {[(c[0], c[1]) for c in calls]}"
    )
    assert {
        c[1] for c in calls
    } == _SENTENCE_COMPOSERS, (
        f"{scorer} no longer calls each composer exactly once: {calls}"
    )
    for lineno, name, kwargs in calls:
        for required in ("rendered_leader_percent", "rendered_affirmative_percent"):
            assert required in kwargs, (
                f"{scorer} calls {name} at feed.py:{lineno} without {required}, so "
                "that sentence derives its own percent again and can disagree "
                "with the card beside it"
            )


def test_the_composers_still_accept_the_printed_percent():
    """The kwargs above must be real parameters, not silently swallowed.

    `generate_futures_*` do not take `**kwargs`, so a rename in `feed_reasons`
    would raise at the route — but this states the coupling as an assertion
    rather than leaving it to the live guard's fixtures to trip over.
    """
    import inspect

    for composer in (
        fr.generate_futures_headline,
        fr.generate_futures_reason,
        fr.generate_futures_context_summary,
    ):
        params = inspect.signature(composer).parameters
        for required in ("rendered_leader_percent", "rendered_affirmative_percent"):
            assert required in params, f"{composer.__name__} dropped {required}"
    assert (
        "rendered_affirmative_percent"
        in inspect.signature(fr.compose_binary_card_copy).parameters
    )
