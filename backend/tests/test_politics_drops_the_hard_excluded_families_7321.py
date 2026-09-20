"""#7321 — /politics stops rendering the families Alex hard-excluded.

Production LOOK at 390px on 2026-09-20, against the served bank behind it
(`GET /api/politics`, `updated_at 04:25:02Z`): **18 of the 60 cards the page
renders were margin-of-victory, voter-turnout or vote-percent ladders** — the
families Alex hard-excluded from Discover on 2026-06-24 (#968, #971) with the
words *"hard to imagine a time when these would ever be interesting to any
audience."* The `other` theme was 6 of 6; `gubernatorial` 6 of 10.

What a reader saw, in order, down the Gubernatorial section:

    Nevada Governor election: Joe Lombardo vote percent   At least 56%    2%
    Tim Walz out as Governor of Minnesota?                Before 2027     5%
    Rhode Island Governor election: Dan McKee vote percent At least 50%   6%
    How much government spending will Trump cut before 2027?  250bn       7%
    Iowa Governor margin of victory                       Lahn, 6+ pts   12%
    Arizona Governor margin of victory                    Biggs, 1+ pts  10%

Six consecutive cards whose headline number is <=12%, not one of which says
who is going to be governor.

WHY THEY LEAD RATHER THAN TRAIL, because the cause is not the one it looks
like. #7251 sorts every section most-OPEN-first, and `_decidedness` clamps to
0 for any multi-outcome market whose leading rung sits below the flat line
(100/n). That clamp is deliberate and correct for a genuinely flat field —
`test_a_leader_beneath_a_flat_field_is_open_not_negatively_decided` in the
#7251 file pins it on purpose. But a CUMULATIVE ladder whose every rung is
1-2% is not an open question, it is an all-but-settled one, and it scores
identically. So the sort promotes exactly the cards with the least to say.

⚠️  THE FIX IS SUPPRESSION, NOT A WIDER `_decidedness`, and the distinction is
the whole point. Teaching the metric to tell a flat field from a dead ladder
would re-rank these cards; it would not remove them, and they do not belong on
the page at any rank. Nothing in this file touches the sort.

⚠️  THE SCOPE QUESTION #7321 ASKED WAS ANSWERED BY MEASUREMENT, NOT BY CHOICE.
The issue worried that dropping all six cards would leave the `other` section
empty, reading "6 rendered of 3,957" as six available. Six is the CAP —
`build_section(themed.get("other", []), 6)`. Measured on the served bank,
every section renders exactly at its cap (10/10/12/10/12/6) against pools of
889/333/146/36/458/3961, so the slice is binding everywhere and what is
dropped here backfills from the same sorted pool.

Both directions are pinned per gotcha #43: the mechanical families go AND
every shape of real race stays. The structural arm is what makes the rest mean
anything — `build_section` is a DB-bound closure (see the #7251 file's own
note), so a gate that is never reached does not raise, it just keeps serving
the ladders.
"""

import ast
import inspect

import pytest

from app.routes import politics as politics_module
from app.utils.feed_market_quality import (
    classify_market_quality,
    hard_excluded_family,
)

# The reasons `classify_market_quality` records for this class. The helper and
# the classifier must never disagree about what a FAMILY is.
FAMILY_REASONS = {
    "margin_turnout_excluded",
    "stream_count_excluded",
    "vote_percent_excluded",
    "house_district_excluded",
    "payrolls_excluded",
}


# --------------------------------------------------------------------------
# The ship: the cards a reader actually saw, verbatim from the served bank
# --------------------------------------------------------------------------

SHOPPED = [
    ("Nevada Governor election: Joe Lombardo vote percent", "KXNVGOVPCT-26"),
    ("Rhode Island Governor election: Dan McKee vote percent", "KXRIGOVPCT-26"),
    ("Iowa Governor margin of victory", "KXIAGOVMARGIN-26"),
    ("Arizona Governor margin of victory", "KXAZGOVMARGIN-26"),
    ("Ohio Governor margin of victory", "KXOHGOVMARGIN-26"),
    ("Nebraska Senate margin of victory", "KXNESENMARGIN-26"),
    ("Michigan Senate margin of victory", "KXMISENMARGIN-26"),
    ("Iowa Senate margin of victory", "KXIASENMARGIN-26"),
    ("West Virginia Senate General Election: voter turnout", "KXWVTURNOUT-26"),
    ("Tennessee Senate General Election: voter turnout", "KXTNTURNOUT-26"),
    ("California Governor Election: Turnout", "KXCAGOVTURNOUT-26"),
    ("Iowa's 1st District margin of victory", "KXIA01MARGIN-26"),
    ("Iowa's 3rd District margin of victory", "KXIA03MARGIN-26"),
    ("Texas's 23rd District margin of victory", "KXTX23MARGIN-26"),
    ("NY-17 House election: Effie Phillips-Staley vote percent", "KXNY17PCT-26"),
    ("NY-01 House election: Jordan Maggio vote percent", "KXNY01PCT-26"),
    ("CO-04 House election: Wayne Thornton vote percent", "KXCO04PCT-26"),
]


@pytest.mark.parametrize("name,ticker", SHOPPED)
def test_every_shopped_card_is_named_by_the_family_gate(name, ticker):
    assert hard_excluded_family(name, ticker) is not None, (
        f"{name!r} is still eligible for /politics — it is one of the 18 cards "
        "the LOOK found"
    )


# --------------------------------------------------------------------------
# The other direction: the races a reader goes to /politics FOR
# --------------------------------------------------------------------------

KEEP = [
    # Chamber control — the carve-out is by construction (no district code, no
    # "vote percent"), and it is the single most important market on the page.
    "Which party will win the U.S. House?",
    "Which party will control the Senate after the 2026 midterms?",
    # Major races, every shape the page renders them in.
    "Nevada Governor election winner?",
    "Georgia Attorney General winner?",
    "Missouri State Senate District 30 winner?",
    "New York Democratic Senate nominee in 2028?",
    "Alabama Lieutenant Governor winner?",
    "2028 Democratic presidential nominee",
    # Policy / SCOTUS / international, which were 0-for-0 in the census and
    # must stay that way.
    "Will SCOTUS bar unpled affirmative defenses at summary judgment?",
    "Will a bill that directly funds HSAs/FSAs become law?",
    "When will a farm bill become law?",
    "Israel Election: Yisrael Beiteinu # of seats?",
    "Will Trump run for a third term?",
    "Ruben Gallego out as Senator?",
]


@pytest.mark.parametrize("name", KEEP)
def test_a_real_race_is_not_touched(name):
    assert hard_excluded_family(name, "KXREAL-26") is None, (
        f"{name!r} is a race the page exists to show and the gate dropped it"
    )


def test_the_us_presidential_turnout_carve_out_survives():
    """Alex's one carve-out inside the turnout family (2026-06-24)."""
    assert hard_excluded_family("US Presidential Election voter turnout") is None
    # ...and it is US-specific, so a foreign presidential turnout still goes.
    assert (
        hard_excluded_family("Zambia Presidential Election voter turnout")
        == "margin_turnout_excluded"
    )


def test_the_gate_reads_the_ticker_when_the_title_is_innocent():
    """A title can hide the family; the ticker is the second signal."""
    assert (
        hard_excluded_family("TN-09 winner?", "KXHOUSERACE-TN09")
        == "house_district_excluded"
    )
    assert (
        hard_excluded_family("Primary result?", "KXVOTEPRIMARY-26")
        == "vote_percent_excluded"
    )


def test_empty_and_missing_inputs_are_not_a_family():
    """Fail OPEN: an unknown market is a real market, never silently dropped."""
    assert hard_excluded_family(None, None) is None
    assert hard_excluded_family("", "") is None


# --------------------------------------------------------------------------
# Anti-drift: the helper and the classifier read the same patterns
# --------------------------------------------------------------------------


class TestHardExcludedFamilyAgreesWithClassifier:
    """The helper reuses the classifier's compiled patterns, but composes the
    booleans itself. This is the arm that notices if the two ever drift — the
    hazard the classifier's own comment names ("the two surfaces must agree
    about what is unreadable").
    """

    CORPUS = [name for name, _ in SHOPPED] + KEEP + [
        "US Presidential Election voter turnout",
        "Zambia Presidential Election voter turnout",
        "Rihanna Streams in 2026",
        "Nonfarm payrolls in September 2026",
        "What will US GDP be in 2026?",
    ]

    @pytest.mark.parametrize("name", CORPUS)
    def test_the_two_agree_on_every_corpus_row(self, name):
        family = hard_excluded_family(name, "KXAGREE-26")
        recorded = set(
            classify_market_quality(name, None, None, "KXAGREE-26").reasons
        ) & FAMILY_REASONS

        if family is None:
            assert recorded == set(), (
                f"the classifier hard-excludes {name!r} as {recorded} and the "
                "helper lets it through — /politics would render what Discover "
                "suppresses"
            )
        else:
            assert family in recorded, (
                f"the helper calls {name!r} {family!r} and the classifier "
                f"records {recorded or 'nothing'} — the two have drifted"
            )


# --------------------------------------------------------------------------
# Structural: the gate is actually spent, and spent in the right place
# --------------------------------------------------------------------------


def _politics_endpoint_loop() -> ast.For:
    """The loop that fills `spotlight_eligible` and `themed`."""
    tree = ast.parse(inspect.getsource(politics_module))
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        body = ast.unparse(node)
        if "spotlight_eligible.append" in body and "themed[theme].append" in body:
            return node
    raise AssertionError(
        "could not find the /politics eligibility loop — this guard is aimed "
        "at a shape that no longer exists and every arm below is vacuous"
    )


def test_the_family_gate_is_spent_in_the_eligibility_loop():
    """A gate nobody calls does not raise; it keeps serving the ladders."""
    loop = _politics_endpoint_loop()
    calls = [
        n
        for n in ast.walk(loop)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "hard_excluded_family"
    ]
    assert calls, (
        "`hard_excluded_family` is not called in the /politics eligibility "
        "loop — #7321's 18 cards are back"
    )


def test_the_gate_runs_BEFORE_the_append_because_the_coupling_is_positional():
    """The route's own comment says a new gate goes above the append.

    Below it, the market is already in `spotlight_eligible` and in
    `themed[theme]`, so the page renders it and the spotlight can headline it.
    """
    loop = _politics_endpoint_loop()

    gate_index = append_index = None
    for i, stmt in enumerate(loop.body):
        src = ast.unparse(stmt)
        if gate_index is None and "hard_excluded_family" in src:
            gate_index = i
        if append_index is None and "spotlight_eligible.append" in src:
            append_index = i

    assert gate_index is not None, "the family gate left the loop body"
    assert append_index is not None, "the append left the loop body"
    assert gate_index < append_index, (
        "the family gate runs AFTER the market is already eligible — it is "
        "inert, and the cards render exactly as #7321 found them"
    )
