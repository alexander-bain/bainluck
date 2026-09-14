"""#6219 — a card's sentence is about a row the card actually draws.

On production Discover, 2026-09-14 20:55Z, at 390px, the National Rugby League
Champion card read:

    National Rugby League Champion
    Canberra Raiders down 46.5 points since Feb 19;
    Canterbury-Bankstown Bulldogs at 49%
    ────────────────────────────────────────────
     1  C. Bulldogs                          49%
     2  N. Queensland Cowboys                49%
     3  South Sydney Rabbitohs               49%
     4  Penrith Panthers                     41%
     5  Field and remaining outcomes         +13

Canberra Raiders is rank 8 of 17, at 3%, inside that collapsed field row. The
card spent its one sentence telling a reader a team had fallen 46.5 points and
then gave that reader no way to find the team, its number, or its standing.

Three of the twenty-one ladder cards serving a movement sentence were this, the
worst being `Korea KBO Champion` leading with SSG Landers — rank 10 of 10, the
single least likely outcome in its own market.

🔴 THE SELECTOR MAKES THIS THE NORMAL CASE, NOT AN EDGE ONE. A movement sentence
takes the biggest absolute move over EVERY outcome, and in a championship field
the biggest lifetime move is almost always a collapsed former favourite — which
is near 0% precisely BECAUSE it collapsed, and is therefore exactly the outcome
that cannot be among the four rows the card draws. The defect is produced by the
mechanism, not by bad data.

🔴 AND THE NEAR MISS IS PART OF THE SPECIMEN. `Where will it rain on Sep 15,
2026?` names Seattle and Seattle IS drawn — row 4, 42%, with a `▲ 18 pts` pill.
A first pass measured against the 3-row `top_outcomes` key and called it a
defect; the rendered card draws FOUR rows, so the proxy was wrong. It is correct
copy and `test_a_subject_the_card_draws_still_speaks` pins it, because a
refusal that also swallowed the true sentences would be the same defect wearing
the other sign.

The guards stand in three places, the same shape as #4146 and #6187:

* at the HELPER, where printedness decides whether a subject may be named;
* at the COMPOSERS, both of them — `generate_futures_headline` produced the
  string the reader actually read, so a fix reaching only `reason` would have
  left the defect on screen;
* at ALL THREE ROUTE SITES structurally, because the flag's default is silent
  (`None` keeps today's wording) and an unadopted call site is therefore a live
  defect here, not a loud one.
"""

import ast
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.routes.feed import CARD_DRAWN_OUTCOME_ROWS, _outcome_is_drawn_on_card
from app.utils.feed_reasons import (
    generate_futures_headline,
    generate_futures_reason,
    movement_subject_is_printable,
)

# The production specimen, by name. Probabilities are the ones read back from
# `GET /api/futures/186930` on 2026-09-14, not invented for the fixture.
NRL_OUTCOMES = [
    {"name": "Canterbury-Bankstown Bulldogs", "probability": 0.49},
    {"name": "North Queensland Cowboys", "probability": 0.49},
    {"name": "South Sydney Rabbitohs", "probability": 0.49},
    {"name": "Penrith Panthers", "probability": 0.41},
    {"name": "Melbourne Storm", "probability": 0.20},
    {"name": "Brisbane Broncos", "probability": 0.08},
    {"name": "Sydney Roosters", "probability": 0.05},
    {"name": "Canberra Raiders", "probability": 0.03},
]

SURPRISE_REASONS = ["major_surprise"]


def _reason(**over):
    kwargs = dict(
        market_name="National Rugby League Champion",
        highlight_reasons=SURPRISE_REASONS,
        top_surprise_name="Canberra Raiders",
        top_surprise_change=-0.465,
        top_surprise_opened_at=datetime(2026, 2, 19, tzinfo=timezone.utc),
        now=datetime(2026, 9, 14, tzinfo=timezone.utc),
        leader_name="Canterbury-Bankstown Bulldogs",
        leader_probability=0.49,
    )
    kwargs.update(over)
    return generate_futures_reason(**kwargs)


def _headline(**over):
    kwargs = dict(
        market_name="National Rugby League Champion",
        highlight_reasons=SURPRISE_REASONS,
        top_surprise_name="Canberra Raiders",
        top_surprise_change=-0.465,
        top_surprise_opened_at=datetime(2026, 2, 19, tzinfo=timezone.utc),
        now=datetime(2026, 9, 14, tzinfo=timezone.utc),
        leader_name="Canterbury-Bankstown Bulldogs",
        leader_probability=0.49,
    )
    kwargs.update(over)
    return generate_futures_headline(**kwargs)


# ── 1. THE DEFECT, BOTH COMPOSERS ───────────────────────────────────────────


def test_the_reason_does_not_name_a_subject_the_card_never_draws():
    """The reason slot's half of the NRL specimen."""
    said = _reason(top_surprise_is_printed=False)
    assert (
        "Canberra Raiders" not in said
    ), "the card's sentence names a team that is not on the card: " + repr(said)
    assert "46.5" not in said, (
        "the move survived with the name stripped off it — #4640's refusal was "
        "written precisely against that shape: " + repr(said)
    )


def test_the_headline_does_not_name_a_subject_the_card_never_draws():
    """The slot the reader ACTUALLY read on production.

    `generate_futures_headline` produced 'Canberra Raiders down 46.5 points
    since Feb 19'. A fix that reached only `generate_futures_reason` would have
    passed its own tests and changed nothing on screen.
    """
    said = _headline(top_surprise_is_printed=False)
    assert "Canberra Raiders" not in said, said
    assert "46.5" not in said, said


def test_the_card_still_gets_a_sentence_about_a_row_it_draws():
    """Falling through is only correct if something true takes the slot."""
    said = _reason(top_surprise_is_printed=False)
    assert said, "the card lost its sentence entirely"
    assert (
        "Canterbury-Bankstown Bulldogs" in said
    ), "the fallback should speak about the leader, which the card draws: " + repr(said)


@pytest.mark.parametrize("reason_key", ["major_movement_24h", "moderate_movement_24h"])
def test_a_today_move_is_gated_on_the_same_question(reason_key):
    """The 24h branch has the same freedom and needs the same gate.

    Honest scope note: no live specimen existed in this branch on 2026-09-14 —
    all six same-day movers were drawn rows. It is guarded anyway because the
    mechanism is identical (`_biggest_move_from_opening`'s own docstring already
    records that the "today" branch shares the blindness), and fixing one of two
    identical branches leaves the reverse population live.
    """
    mover = dict(
        highlight_reasons=[reason_key],
        top_mover_name="Canberra Raiders",
        top_mover_change=-0.465,
        top_mover_is_printed=False,
        top_surprise_name=None,
        top_surprise_change=None,
    )
    assert "Canberra Raiders" not in _reason(**mover)
    # Both composers, for the reason this test exists at all. Written after a
    # mutant that stripped the gate from the HEADLINE's two mover branches
    # survived the first draft of this file: the reason-only assertion above
    # left exactly the slot the reader reads unguarded, which is the same
    # one-of-two-branches mistake the docstring warns about.
    assert "Canberra Raiders" not in _headline(**mover)


@pytest.mark.parametrize("reason_key", ["major_movement_24h", "moderate_movement_24h"])
def test_a_drawn_today_mover_still_speaks_in_both_composers(reason_key):
    mover = dict(
        highlight_reasons=[reason_key],
        top_mover_name="Canberra Raiders",
        top_mover_change=-0.465,
        top_mover_is_printed=True,
        top_surprise_name=None,
        top_surprise_change=None,
    )
    assert "Canberra Raiders" in _reason(**mover)
    assert "Canberra Raiders" in _headline(**mover)


# ── 2. IT MUST NOT WIDEN ────────────────────────────────────────────────────


def test_a_subject_the_card_draws_still_speaks():
    """The rain card: Seattle is row 4 at 42%, so the sentence is correct copy.

    A refusal that swallowed the true sentences would be the same defect with
    the sign flipped. Eight of the twenty-one live cards were this shape.
    """
    said = _reason(top_surprise_is_printed=True)
    assert "Canberra Raiders" in said, said
    assert "46.5" in said, said


def test_a_headline_subject_the_card_draws_still_speaks():
    said = _headline(top_surprise_is_printed=True)
    assert "Canberra Raiders" in said, said


def test_an_uninformed_caller_keeps_todays_wording():
    """`None` is 'the caller has not been taught', and must not become a guess.

    Same convention as `lead_is_printable` and `leader_is_team`. If this flipped
    to fail-closed, every caller in the codebase that has not adopted the kwarg
    would silently lose its movement sentences.
    """
    assert _reason() == _reason(top_surprise_is_printed=True)
    assert "Canberra Raiders" in _reason()


def test_unknown_and_absent_are_different_states():
    assert movement_subject_is_printable("Canberra Raiders", None) is True
    assert movement_subject_is_printable("Canberra Raiders", True) is True
    assert movement_subject_is_printable("Canberra Raiders", False) is False
    # A caller that knows its rows but has no subject to name cannot say yes.
    assert movement_subject_is_printable(None, True) is False
    assert movement_subject_is_printable("   ", True) is False
    # ...but an uninformed caller is still left alone, subject or not.
    assert movement_subject_is_printable(None, None) is True


# ── 3. THE CUT IS THE CARD'S CUT ────────────────────────────────────────────


def test_the_drawn_rows_are_the_four_the_card_prints():
    assert _outcome_is_drawn_on_card("Canterbury-Bankstown Bulldogs", NRL_OUTCOMES)
    assert _outcome_is_drawn_on_card("Penrith Panthers", NRL_OUTCOMES)  # rank 4, in
    assert not _outcome_is_drawn_on_card("Melbourne Storm", NRL_OUTCOMES)  # rank 5, out
    assert not _outcome_is_drawn_on_card("Canberra Raiders", NRL_OUTCOMES)
    assert not _outcome_is_drawn_on_card("Nobody At All", NRL_OUTCOMES)
    assert not _outcome_is_drawn_on_card(None, NRL_OUTCOMES)


def test_the_cut_does_not_depend_on_the_order_the_list_arrives_in():
    """The client sorts before slicing (#1526), so the backend must not assume.

    `slice(0, 4)` on an unsorted array drops the leader — that was the Fed
    September card. The same reasoning applies to this gate: it is defined by
    probability order, not by the order a serving path happened to build in.
    """
    shuffled = list(reversed(NRL_OUTCOMES))
    assert _outcome_is_drawn_on_card("Canterbury-Bankstown Bulldogs", shuffled)
    assert not _outcome_is_drawn_on_card("Canberra Raiders", shuffled)


def test_a_missing_probability_cannot_sort_its_way_onto_the_card():
    rows = [{"name": "No Price", "probability": None}] + NRL_OUTCOMES
    assert not _outcome_is_drawn_on_card("No Price", rows)
    assert _outcome_is_drawn_on_card("Penrith Panthers", rows)


def test_the_backend_cut_and_the_client_cut_are_the_same_number():
    """Two records of one capability, so ASSERT the gap rather than trust it.

    `FuturesCard.tsx` decides how many rows a reader sees. This constant decides
    which subjects may be named. If the client ever draws five rows and this
    still says four, the gate silences a sentence about a row the reader CAN
    see — a regression with no other alarm on it.
    """
    tsx = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "components"
        / "discover"
        / "FuturesCard.tsx"
    )
    source = tsx.read_text()
    found = re.search(r"leaderFirstSlice\(\s*distributionRows\s*,\s*(\d+)\s*\)", source)
    assert found, (
        "FuturesCard.tsx no longer slices distributionRows the way "
        f"{Path(__file__).name} assumes — re-derive CARD_DRAWN_OUTCOME_ROWS "
        "against whatever replaced it"
    )
    assert int(found.group(1)) == CARD_DRAWN_OUTCOME_ROWS, (
        f"the card draws {found.group(1)} rows but the backend gate assumes "
        f"{CARD_DRAWN_OUTCOME_ROWS}"
    )


# ── 4. EVERY ROUTE SITE, BECAUSE THE DEFAULT IS SILENT ──────────────────────

#: The two composers that can name a movement subject. `context_summary` is not
#: here on purpose: its lifetime branch returns "Shifted since <date>", which
#: names no outcome and therefore cannot orphan one.
_MOVEMENT_COMPOSERS = {"generate_futures_headline", "generate_futures_reason"}

#: All three places a futures card's sentences are composed. `_score_futures` is
#: Discover; `_score_sports_mode_futures` is the /sports rail, a hand-maintained
#: near-copy; `_score_market_trace` is the admin trace, which Q480 requires to
#: agree with the card it explains — a debug view that still names the dropped
#: row sends the next reader hunting something the feed does not serve.
_ROUTE_SCORERS = ("_score_futures", "_score_sports_mode_futures", "_score_market_trace")


def _movement_calls_in(function_name: str) -> list[tuple[int, str, set[str]]]:
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
                and call.func.id in _MOVEMENT_COMPOSERS
            ]
    raise AssertionError(f"{function_name} is gone from routes/feed.py")


@pytest.mark.parametrize("scorer", _ROUTE_SCORERS)
def test_every_route_site_says_whether_the_subject_is_drawn(scorer):
    """An unadopted call site restores the live defect instead of failing loudly.

    Adding a fourth serving path without the kwargs reds this; deleting one
    kwarg at the sports-mode site reds this.
    """
    calls = _movement_calls_in(scorer)
    assert {
        c[1] for c in calls
    } == _MOVEMENT_COMPOSERS, (
        f"{scorer} no longer calls both movement composers: {calls}"
    )
    for lineno, name, kwargs in calls:
        for required in ("top_surprise_is_printed", "top_mover_is_printed"):
            assert required in kwargs, (
                f"{scorer} calls {name} at feed.py:{lineno} without {required}, so "
                "that sentence can name an outcome the card does not draw again"
            )


def test_the_composers_still_accept_the_flags():
    """The kwargs above must be real parameters, not swallowed by **kwargs."""
    import inspect

    for composer in (generate_futures_headline, generate_futures_reason):
        params = inspect.signature(composer).parameters
        for required in ("top_surprise_is_printed", "top_mover_is_printed"):
            assert required in params, f"{composer.__name__} dropped {required}"
