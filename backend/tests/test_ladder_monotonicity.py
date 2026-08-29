"""Guards for the generalized nested-ladder monotonicity law.

Every test whose name ends in a market name is a REGRESSION guard for a defect
that was actually measured on ``polymarket/tech`` while the grammar was being
built, not an invented edge case. The two parser defects in particular were
each live for one census run and each produced a plausible-looking family that
would have condemned real rows for the wrong reason.
"""

from __future__ import annotations

import pytest

from app.utils.ladder_monotonicity import (
    DEC,
    INC,
    LADDER_MONOTONICITY_RULE_TEXT,
    ambiguous_families,
    blanked_key,
    condemned_families,
    flat_pairs,
    ladder_is_incoherent,
    ladder_report,
    monotonicity_violations,
    name_rungs,
    outcome_ladder,
    parse_by_date,
    parse_over_under,
    parse_plus_bracket,
    parse_threshold,
    read_name_ladders,
)


# ---------------------------------------------------------------------------
# Grammar: threshold
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,value", [
    ("Will Broadcom Q2 AI revenue be above $10.5B?", 10.5e9),
    ("Will CrowdStrike Q1 net new ARR be above $225M?", 225e6),
    ("SpaceX IPO closing market cap above $3.6T?", 3.6e12),
    ("Will Lyft’s total rides in Q1 2026 be above 250m?", 250e6),
    ("Will Claude Code Commits hit (HIGH) 750.0k by June 30?", 750e3),
    ("Will the next Google Gemini model debut at a score of at least 1490?", 1490.0),
    ("Will Zoom Q1 online average monthly churn rate be at least 3.1%?", 3.1),
])
def test_threshold_magnitudes_parse_with_their_units(name, value):
    parsed = parse_threshold(name)
    assert parsed is not None, name
    assert parsed[1] == pytest.approx(value)


def test_threshold_direction_comes_from_the_word_not_the_number():
    assert parse_threshold("revenue above $10.5B?")[2] == DEC
    assert parse_threshold("revenue below $10.5B?")[2] == INC
    assert parse_threshold("Will X be under 250m?")[2] == INC
    assert parse_threshold("Will X be at most 250m?")[2] == INC


def test_high_and_low_markers_set_direction_even_though_the_verb_is_hit():
    """``hit (LOW) $15B`` is ASCENDING despite reading like an upward verb.

    Polymarket names the leg with the parenthesised marker, and the marker is
    the only thing in the string that carries the sign.
    """
    assert parse_threshold("Will Perplexity's valuation hit (LOW) $15B by December 31?")[2] == INC
    assert parse_threshold("Will Stripe's valuation hit (HIGH) $210B by June 30?")[2] == DEC


def test_measles_the_m_of_a_following_word_is_not_a_mega_suffix():
    """REGRESSION. ``at least 2000 measles`` read 2,000 as 2,000,000,000.

    The scale suffix consumed the leading ``m`` of "measles", which both
    inflated the rung by 10^6 and corrupted the family key to ``<rung> easles
    cases``, splitting the family off from its own siblings.
    """
    name = "Will there be at least 2000 measles cases in the U.S. in 2026?"
    span, value, direction = parse_threshold(name)
    assert value == 2000.0
    assert direction == DEC
    assert "measles" in blanked_key(name, span)
    assert "easles" not in blanked_key(name, span).replace("measles", "")


@pytest.mark.parametrize("suffix,expected", [
    ("2000 measles cases", 2000.0),
    ("2000 million cases", 2000.0),
    ("2000 billionaires", 2000.0),
    ("2000 tickets", 2000.0),
    ("2000 kilometres", 2000.0),
])
def test_no_bare_word_starting_with_a_scale_letter_is_ever_a_suffix(suffix, expected):
    assert parse_threshold(f"Will there be at least {suffix}?")[1] == expected


def test_government_a_direction_word_inside_another_word_is_not_a_direction():
    """REGRESSION. ``over`` matched inside "g-over-nment".

    It then bound to the ``30`` of "April 30" and invented a threshold rung on
    a market that only ever carried a date, producing the bogus family
    ``will anthropic provide mythos to the us g <rung> 2026?``.
    """
    name = "Will Anthropic provide Mythos to the US government by April 30, 2026?"
    assert parse_threshold(name) is None
    keys = [k for k, _ in name_rungs(name)]
    assert all("us g <rung>" not in key for key, _ in keys), keys
    assert len(keys) == 1 and keys[0][1] == INC


def test_the_number_must_follow_the_direction_word_immediately():
    """Slop between word and number is what let "government" reach "April 30"."""
    assert parse_threshold("above the line, 30 people showed up") is None
    assert parse_threshold("above $30") is not None


# ---------------------------------------------------------------------------
# Grammar: dates
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,value", [
    ("Will GPT-6 be released by June 30, 2026?", 20260630.0),
    ("Claude 4.7 released by April 30?", 20260430.0),
    ("ChatGPT Outage by April 17?", 20260417.0),
    ("Will a new Gemini flagship be released by July 31, 2026?", 20260731.0),
])
def test_by_date_rungs_sort_as_yyyymmdd(name, value):
    parsed = parse_by_date(name)
    assert parsed is not None and parsed[1] == value
    assert parsed[2] == INC


def test_a_bare_year_sorts_after_every_dated_rung_inside_it():
    assert parse_by_date("Will X happen by 2026?")[1] == 20261231.0
    assert parse_by_date("Will X happen by 2026?")[1] > parse_by_date("by December 30, 2026?")[1]


def test_a_date_ladder_is_always_ascending_because_later_contains_earlier():
    assert parse_by_date("released by June 5?")[2] == INC


# ---------------------------------------------------------------------------
# Family keys
# ---------------------------------------------------------------------------

def test_direction_is_part_of_the_key_so_a_high_ladder_never_merges_with_a_low_one():
    """REGRESSION. 13 valuation families merged a descending into an ascending ladder.

    The two names differ ONLY in the parenthesised marker, which sits inside
    the blanked span, so without direction in the key they collapse together
    and either sign manufactures violations across the merged family.
    """
    high = name_rungs("Will OpenAI's valuation hit (HIGH) $1.0T by December 31?")
    low = name_rungs("Will OpenAI's valuation hit (LOW) $500B by December 31?")
    high_thresh = [k for k, _ in high if k[1] == DEC]
    low_thresh = [k for k, _ in low if k[1] == INC]
    assert high_thresh and low_thresh
    assert high_thresh[0][0] == low_thresh[0][0], "blanked text is the same ..."
    assert high_thresh[0] != low_thresh[0], "... so only direction keeps them apart"


def test_a_name_with_a_threshold_and_a_date_joins_two_families_one_per_axis():
    """The two-dimensional valuation grid. Each axis holds the other literal."""
    rungs = name_rungs("Will Stripe's valuation hit (HIGH) $210B by June 30?")
    assert len(rungs) == 2
    by_dir = {k[1]: k[0] for k, _ in rungs}
    assert "june 30" in by_dir[DEC], "threshold family keeps the date literal"
    assert "210b" in by_dir[INC], "date family keeps the threshold literal"


def test_different_subjects_never_share_a_family():
    a = name_rungs("Claude 4.7 released by April 30?")[0][0]
    b = name_rungs("Claude 4.8 released by May 31?")[0][0]
    assert a != b


def test_the_same_ladder_reached_by_two_rungs_shares_one_key():
    a = name_rungs("Will Broadcom Q2 AI revenue be above $10.5B?")[0][0]
    b = name_rungs("Will Broadcom Q2 AI revenue be above $11.5B?")[0][0]
    assert a == b


def test_a_name_with_no_rung_contributes_nothing():
    assert name_rungs("Which company's AI will first hit 1550 on Chatbot Arena?") != []
    assert name_rungs("CapCut: Photo & Video Editor") == []
    assert name_rungs(None) == []
    assert name_rungs("") == []


# ---------------------------------------------------------------------------
# The law
# ---------------------------------------------------------------------------

def test_a_descending_ladder_priced_in_order_has_no_violation():
    assert monotonicity_violations({1.0: 0.9, 2.0: 0.6, 3.0: 0.3}, DEC) == []


def test_a_descending_ladder_that_rises_is_condemned_and_names_the_pair():
    out = monotonicity_violations({1.0: 0.9, 2.0: 0.4, 3.0: 0.7}, DEC)
    assert out == [(2.0, 0.4, 3.0, 0.7)]


def test_an_ascending_date_ladder_that_falls_is_condemned():
    out = monotonicity_violations({20260605.0: 0.4, 20260612.0: 0.2}, INC)
    assert out == [(20260605.0, 0.4, 20260612.0, 0.2)]


def test_an_ascending_ladder_priced_in_order_has_no_violation():
    assert monotonicity_violations({20260605.0: 0.2, 20260612.0: 0.4}, INC) == []


def test_adjacency_is_consecutive_in_sorted_order_not_a_fixed_step():
    """Irregular steps are the norm: June 5, 12, 19, 26, 30, July 31.

    ``ladder_coherence`` compares rungs exactly one unit apart and would find
    NOTHING here. The generalization is the whole point of this module.
    """
    rungs = {20260605.0: 0.10, 20260612.0: 0.20, 20260619.0: 0.15,
             20260630.0: 0.40, 20260731.0: 0.55}
    assert monotonicity_violations(rungs, INC) == [(20260612.0, 0.20, 20260619.0, 0.15)]


def test_out_of_order_input_is_sorted_before_comparison():
    forward = monotonicity_violations({3.0: 0.7, 1.0: 0.9, 2.0: 0.4}, DEC)
    assert forward == [(2.0, 0.4, 3.0, 0.7)]


def test_equality_is_not_a_violation_which_is_the_documented_weakening():
    """The O/U rule condemns an equal pair; this one CANNOT, and must not.

    Two rungs here can be a day or a rounding step apart, so equal prices are
    consistent with the law. If this test ever flips, the module has silently
    adopted the O/U strictness on a grammar that does not license it.
    """
    assert monotonicity_violations({1.0: 0.5, 2.0: 0.5}, DEC) == []
    assert monotonicity_violations({1.0: 0.5, 2.0: 0.5}, INC) == []


def test_flat_pairs_reports_what_the_law_declines_to_condemn():
    rungs = {1.0: 0.5, 2.0: 0.5, 3.0: 0.4}
    assert flat_pairs(rungs) == [(1.0, 0.5, 2.0, 0.5)]
    assert monotonicity_violations(rungs, DEC) == []


def test_a_family_of_one_rung_is_never_condemned():
    assert ladder_is_incoherent({1.0: 0.9}, DEC) is False
    assert ladder_is_incoherent({}, DEC) is False


def test_a_priceless_rung_takes_no_part_rather_than_breaking_the_chain():
    """``2600+`` carries no price on the measles market; it must not create a pair."""
    assert monotonicity_violations({1.0: 0.9, 2.0: None, 3.0: 0.8}, DEC) == []


def test_an_unknown_direction_raises_rather_than_defaulting_to_one_sign():
    with pytest.raises(ValueError):
        monotonicity_violations({1.0: 0.5, 2.0: 0.4}, "sideways")


# ---------------------------------------------------------------------------
# The OUTCOME site
# ---------------------------------------------------------------------------

def test_measles_market_57767991_is_a_cumulative_ladder_and_it_violates():
    """The live shape that motivated the outcome site.

    P(>=2450) = 0.740 while P(>=2500) = 0.865: the larger, strictly contained
    event is priced HIGHER. No model is needed to call that wrong.
    """
    outcomes = [{"name": "2400+", "price": 0.945}, {"name": "2450+", "price": 0.740},
                {"name": "2500+", "price": 0.865}, {"name": "2550+", "price": 0.500},
                {"name": "2600+", "price": None}]
    rungs = outcome_ladder(outcomes)
    assert rungs == {2400.0: 0.945, 2450.0: 0.740, 2500.0: 0.865, 2550.0: 0.500}
    assert monotonicity_violations(rungs, DEC) == [(2450.0, 0.740, 2500.0, 0.865)]


def test_bracket_market_113766_is_a_partition_and_is_never_treated_as_a_ladder():
    """Exclusive brackets sum to one; they do not nest and must not be condemned."""
    outcomes = [{"name": "<5", "price": 0.215}, {"name": "5-6", "price": 0.305},
                {"name": "7-8", "price": 0.100}, {"name": "9-10", "price": 0.220},
                {"name": "11-12", "price": 0.0535}, {"name": ">16", "price": 0.0725}]
    assert outcome_ladder(outcomes) is None


@pytest.mark.parametrize("bad_leg", [
    {"name": "5-6", "price": 0.3},
    {"name": "<5", "price": 0.3},
    {"name": "2400 or less", "price": 0.3},
    {"name": "Yes", "price": 0.3},
    {"name": "Google Gemini", "price": 0.3},
])
def test_one_non_plus_leg_disqualifies_the_whole_market(bad_leg):
    outcomes = [{"name": "2400+", "price": 0.9}, {"name": "2450+", "price": 0.8}, bad_leg]
    assert outcome_ladder(outcomes) is None


def test_a_duplicated_outcome_rung_disqualifies_the_market():
    outcomes = [{"name": "2400+", "price": 0.9}, {"name": "2400+", "price": 0.8}]
    assert outcome_ladder(outcomes) is None


def test_a_single_priced_rung_is_not_a_ladder():
    assert outcome_ladder([{"name": "2400+", "price": 0.9}]) is None
    assert outcome_ladder([{"name": "2400+", "price": 0.9},
                           {"name": "2450+", "price": None}]) is None


@pytest.mark.parametrize("text,value", [
    ("500k+", 500e3), ("700b+", 700e9), ("600B+", 600e9),
    ("5.50B+", 5.5e9), ("12+", 12.0), ("$2,400+", 2400.0),
])
def test_plus_bracket_magnitudes(text, value):
    assert parse_plus_bracket(text)[1] == pytest.approx(value)


def test_plus_bracket_is_anchored_at_both_ends():
    assert parse_plus_bracket("2400-2450+") is None
    assert parse_plus_bracket("more than 2400+ cases") is None


# ---------------------------------------------------------------------------
# Grouping, ambiguity, and the report
# ---------------------------------------------------------------------------

def _row(mid, name, price):
    return {"market_id": mid, "name": name, "yes_price": price}


def test_aws_a_relisted_question_makes_the_key_ambiguous_and_is_kept_not_dropped():
    """REGRESSION. "AWS service disrupted by March 31?" exists under three ids.

    Two rows on the same (family, value) prove the key is not identifying a
    single ladder — never that the ladder is bad — so the rule fails toward
    KEEPING, the way ``ladder_coherence`` learned to on esports.
    """
    rows = [
        _row(1, "AWS service disrupted by March 31?", 0.20),
        _row(2, "AWS service disrupted by March 31?", 0.90),
        _row(3, "AWS service disrupted by June 30?", 0.10),
    ]
    ladders = read_name_ladders(rows)
    assert ambiguous_families(ladders)
    assert condemned_families(ladders) == set()
    report = ladder_report(rows)
    assert report["drop"] == set()
    assert report["ambiguous"] == {1, 2, 3}


def test_a_clean_descending_family_lands_in_coherent():
    rows = [
        _row(1, "SpaceX IPO closing market cap above $1.8T?", 0.60),
        _row(2, "SpaceX IPO closing market cap above $3T?", 0.30),
        _row(3, "SpaceX IPO closing market cap above $3.6T?", 0.10),
    ]
    report = ladder_report(rows)
    assert report["coherent"] == {1, 2, 3}
    assert report["drop"] == set()
    assert report["census"]["families_multi_rung"] == 1
    assert report["census"]["violating_pairs"] == 0


def test_a_reversed_family_condemns_every_rung_not_only_the_violating_pair():
    """Ruling 111: the family is the unit. A violation is evidence about the
    pricing process that produced the whole family."""
    rows = [
        _row(1, "SpaceX IPO closing market cap above $1.8T?", 0.60),
        _row(2, "SpaceX IPO closing market cap above $3T?", 0.30),
        _row(3, "SpaceX IPO closing market cap above $3.6T?", 0.55),
    ]
    report = ladder_report(rows)
    assert report["drop"] == {1, 2, 3}
    assert report["coherent"] == set()
    assert report["census"]["violating_pairs"] == 1


def test_a_market_condemned_on_either_axis_is_dropped_not_rescued_by_the_other():
    """The two-dimensional grid: consistency on one axis is not a defence."""
    rows = [
        # Date axis for $210B is clean; threshold axis at June 30 is reversed.
        _row(1, "Will Stripe's valuation hit (HIGH) $210B by June 30?", 0.20),
        _row(2, "Will Stripe's valuation hit (HIGH) $250B by June 30?", 0.50),
        _row(3, "Will Stripe's valuation hit (HIGH) $210B by December 31?", 0.40),
    ]
    report = ladder_report(rows)
    assert 1 in report["drop"] and 2 in report["drop"]
    assert not (report["drop"] & report["ambiguous"])
    assert not (report["drop"] & report["coherent"])


def test_the_three_id_sets_are_always_disjoint():
    rows = [
        _row(1, "Widget above $1?", 0.9), _row(2, "Widget above $2?", 0.95),
        _row(3, "Gadget by March 31?", 0.1), _row(4, "Gadget by March 31?", 0.2),
        _row(5, "Gadget by June 30?", 0.3),
        _row(6, "Doohickey above $1?", 0.9), _row(7, "Doohickey above $2?", 0.5),
    ]
    r = ladder_report(rows)
    assert not (r["drop"] & r["ambiguous"])
    assert not (r["drop"] & r["coherent"])
    assert not (r["ambiguous"] & r["coherent"])


def test_a_row_with_no_price_takes_no_part_in_any_arm():
    rows = [_row(1, "Widget above $1?", None), _row(2, "Widget above $2?", 0.5)]
    r = ladder_report(rows)
    assert r["drop"] == set() and r["ambiguous"] == set() and r["coherent"] == set()


def test_a_singleton_family_puts_its_market_in_no_arm_at_all():
    """"Not a ladder member" and "a ladder the rule kept" are different claims."""
    r = ladder_report([_row(1, "Widget above $1?", 0.9)])
    assert r["drop"] == set() and r["coherent"] == set() and r["ambiguous"] == set()
    assert r["census"]["families_singleton"] == 1


def test_census_family_and_market_ambiguity_counts_are_reconcilable():
    """A duplicate-only family has no pair to test, so it is reported as its own
    class rather than inflating ``families_ambiguous`` past the market count."""
    rows = [_row(1, "Widget above $1?", 0.9), _row(2, "Widget above $1?", 0.8)]
    c = ladder_report(rows)["census"]
    assert c["families_ambiguous"] == 0
    assert c["families_untestable_duplicate_only"] == 1


# ---------------------------------------------------------------------------
# Standing invariants
# ---------------------------------------------------------------------------

def test_the_module_never_reads_an_outcome():
    """Leakage guard. A predicate fitted to ``is_winner`` is not a structural
    law, and a holdout on one tests nothing.

    Checked over the READ SITES the AST actually contains — attribute names,
    string subscript keys, and ``.get("...")`` keys — rather than over the
    source text. A substring scan cannot tell ``row["is_winner"]`` from the
    sentence "never mutates is_winner" in the rule's own prose, and a guard
    that cannot tell two cases apart is given evidence, not a wider band
    (ruling 083). The text scan flagged the docstring on its first run.
    """
    import ast
    import inspect

    from app.utils import ladder_monotonicity as mod

    tree = ast.parse(inspect.getsource(mod))
    reads: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            reads.add(node.attr)
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if isinstance(node.slice.value, str):
                reads.add(node.slice.value)
        elif (isinstance(node, ast.Call)
              and isinstance(node.func, ast.Attribute)
              and node.func.attr in ("get", "setdefault")
              and node.args
              and isinstance(node.args[0], ast.Constant)
              and isinstance(node.args[0].value, str)):
            reads.add(node.args[0].value)

    banned = {"is_winner", "winner", "winners", "resolution_source",
              "settled", "settlement", "result"}
    assert not (reads & banned), f"outcome read sites present: {sorted(reads & banned)}"


def test_the_module_writes_nothing():
    import inspect

    from app.utils import ladder_monotonicity as mod

    src = inspect.getsource(mod)
    for banned in ("UPDATE ", "INSERT ", "DELETE ", "session.", "commit("):
        assert banned not in src, f"{banned!r} must not appear (gotcha #21)"


def test_the_rule_text_states_the_weakening_it_carries():
    """The non-strict law is the single most misquotable thing about this rule."""
    text = LADDER_MONOTONICITY_RULE_TEXT.lower()
    assert "equality is not a reversal" in text
    assert "family of one" in text
    assert "read-side only" in text


# ---------------------------------------------------------------------------
# Rail wiring. CAL-P127/130/131/132 each registered a dimension and each had to
# be caught by a SIBLING suite going red; these guards live beside the rule so
# the registration and its proof are in one file.
# ---------------------------------------------------------------------------

def _rail():
    import importlib
    return importlib.import_module("scripts.calibration_cell_exact")


def test_mono_is_registered_as_a_per_chunk_dimension():
    cce = _rail()
    assert "mono" in cce.PER_CHUNK_DIMENSIONS
    assert "mono" not in cce.DIMENSIONS, "a pre-pass dimension is not a static one"
    assert not (set(cce.PER_CHUNK_DIMENSIONS) & set(cce.DIMENSIONS))


def test_every_per_chunk_dimension_has_a_pre_pass_registered():
    """The two tables are keyed the same on purpose.

    A dimension in one table and not the other is the failure that produces an
    EMPTY partition at the end of a 75-second fold instead of an error at
    start-up, and an empty partition reads as "the rule found nothing"
    (gotcha #53).
    """
    cce = _rail()
    assert set(cce.PER_CHUNK_DIMENSIONS) == set(cce.PER_CHUNK_CONTEXT)


def test_mono_dim_emits_the_four_arms_including_both_controls():
    cce = _rail()
    cce._MONO = {"drop": {1}, "ambiguous": {2}, "coherent": {3}}
    try:
        expr, join, pre = cce.mono_dim(0, 10)
    finally:
        cce._MONO = None
    for arm in ("a_drop_reversed", "b_ambiguous_kept",
                "c_mono_coherent", "z_not_in_a_ladder"):
        assert arm in expr
    assert join == "" and pre == ""


def test_mono_dim_refuses_to_run_before_its_pre_pass():
    cce = _rail()
    cce._MONO = None
    with pytest.raises(RuntimeError):
        cce.mono_dim(0, 10)


def test_mono_pre_pass_sql_carries_no_name_filter():
    """The deliberate difference from ``LADDER_ROWS_SQL``.

    A Postgres rendering of the rung grammar would be a second site for a
    predicate whose authority is the Python, which ``ladder_coherence`` books as
    an unproven cert obligation. This pre-pass pulls every market with a YES leg
    instead, so there is nothing to reconcile.
    """
    cce = _rail()
    sql = cce.MONO_ROWS_SQL
    assert "'yes'" in sql
    for grammar_token in ("above", "at least", "O/U", "by ", "~"):
        assert grammar_token not in sql, (
            f"{grammar_token!r} in the pre-pass SQL would make Postgres a second "
            "definition of the rung grammar")


def test_the_rail_did_not_rebind_the_ou_ambiguous_families():
    """Both modules export ``ambiguous_families`` with different key types.

    A flat ``from app.utils.ladder_monotonicity import ambiguous_families``
    would silently rebind the O/U one and change what ``--by ladder`` enforces,
    with no test failing anywhere near the edit.
    """
    from app.utils import ladder_coherence

    cce = _rail()
    assert cce.ambiguous_families is ladder_coherence.ambiguous_families
    assert cce.ladder_report is not ladder_coherence.ambiguous_families


# ---------------------------------------------------------------------------
# CAL-P134 — the Kalshi OUTCOME-site grammar and the TRUTH law.
#
# Every leg string below is copied from a real ``kalshi/economics`` market. The
# cell folded to "46 families, one condemned pair" under the pre-CAL-P134
# grammar while 4,621 of its 7,590 markets were all-cumulative ladders, so these
# guards exist to make that particular all-clear impossible to reproduce.
# ---------------------------------------------------------------------------

from app.utils.ladder_monotonicity import (  # noqa: E402
    cumulative_outcome_ladder,
    outcome_ladder_report,
    parse_cumulative_leg,
    truth_reversals,
)

_AUTH = "api_settlement"
_GUESS = "pass2_guess"


def _leg(name, price=None, win=False, src=_AUTH):
    return {"name": name, "price": price, "is_winner": win, "resolution_source": src}


@pytest.mark.parametrize("text,value,direction", [
    # 'US SPR level for the week ending April 3, 2026'
    ("Above 410M", 410_000_000.0, DEC),
    # 'Silver price on Apr 7, 2026 at 5pm EDT?'
    ("above $68.25", 68.25, DEC),
    # 'US CPI inflation for May 30, 2026'
    ("Above 2.14%", 2.14, DEC),
    # the single most common Kalshi economics leg shape, and the one no
    # grammar in this module saw before CAL-P134
    ("7,175 or above", 7175.0, DEC),
    ("$25,600 or higher", 25600.0, DEC),
    ("3.0% or more", 3.0, DEC),
    ("2400+", 2400.0, DEC),            # the pre-CAL-P134 form still parses
    ("Below 410M", 410_000_000.0, INC),
    ("2.5% or less", 2.5, INC),
    ("under $70", 70.0, INC),
])
def test_parse_cumulative_leg_reads_the_shapes_kalshi_actually_writes(
        text, value, direction):
    assert parse_cumulative_leg(text) == (value, direction)


@pytest.mark.parametrize("text", [
    "Yes", "No", "", None,
    "5-6", "2400-2450+", "$100 to $200",     # ranges partition, never nest
    "<5", ">16",                             # tail legs of a bracket market
    "Above 410M or below 400M",              # two rungs in one leg
    "Trump", "Recession in 2026",            # prose
])
def test_parse_cumulative_leg_refuses_everything_that_is_not_one_rung(text):
    assert parse_cumulative_leg(text) is None


def test_the_measles_defect_cannot_come_back_through_the_new_grammar():
    """``at least 2000 measles cases`` must not read ``m`` as MEGA.

    The name-site parser learned this the expensive way; the leg-site parser is
    anchored at both ends, so the whole-string match is what refuses it, and
    this guard asserts the refusal rather than a corrected magnitude.
    """
    assert parse_cumulative_leg("at least 2000 measles cases") is None
    assert parse_cumulative_leg("at least 2000") == (2000.0, DEC)


def test_cumulative_outcome_ladder_reads_a_real_kalshi_market():
    # market 29210105, 'AI sector performance on May 29, 2026'
    legs = [_leg("Above 64.21", 0.99, True), _leg("Above 59.71", 0.02, True),
            _leg("Above 61.21", 0.01, True), _leg("Above 62.71", 0.01, True)]
    ordered, direction = cumulative_outcome_ladder(legs)
    assert direction == DEC
    assert [v for v, _ in ordered] == [59.71, 61.21, 62.71, 64.21]


@pytest.mark.parametrize("legs", [
    # a bracket market: partitions, never nests, and condemning it would be wrong
    [_leg("<5"), _leg("5-6"), _leg(">16")],
    # ONE prose leg disqualifies the whole market rather than being skipped
    [_leg("Above 410M"), _leg("Above 411M"), _leg("Other")],
    # opposite-signed legs are not one ladder
    [_leg("Above 410M"), _leg("Below 400M")],
    # a duplicate rung value is the outcome-site form of a key grouping two ladders
    [_leg("Above 410M"), _leg("above $410M")],
    [_leg("Above 410M")],                      # one leg is never a ladder
    [],
])
def test_cumulative_outcome_ladder_refuses_anything_that_is_not_one_ladder(legs):
    assert cumulative_outcome_ladder(legs) is None


def test_a_priceless_leg_does_not_disqualify_the_ladder():
    """Pricing is the caller's problem. Dropping an unpriced leg HERE would let
    a ladder qualify on a subset of its own legs and silently change population."""
    legs = [_leg("Above 1"), _leg("Above 2", 0.5), _leg("Above 3", 0.4)]
    ordered, direction = cumulative_outcome_ladder(legs)
    assert [v for v, _ in ordered] == [1.0, 2.0, 3.0]


# --- the truth law ---------------------------------------------------------

def test_truth_reversals_accepts_the_only_shape_a_realized_value_can_produce():
    """V settles every rung at once, so DEC truth is True…True False…False."""
    assert truth_reversals([(1.0, True), (2.0, True), (3.0, False)], DEC) == []
    assert truth_reversals([(1.0, True), (2.0, True)], DEC) == []
    assert truth_reversals([(1.0, False), (2.0, False)], DEC) == []


def test_truth_reversals_names_the_pair_a_cert_has_to_argue_about():
    # market 30784010, 'S&P price on Jun 2, 2026 at 4pm EDT?' — settled data
    assert truth_reversals([(7000.0, False), (7025.0, True)], DEC) == [(7000.0, 7025.0)]


def test_truth_reversals_flips_with_direction():
    below = [(1.0, True), (2.0, False)]
    assert truth_reversals(below, INC) == [(1.0, 2.0)]
    assert truth_reversals(below, DEC) == []


def test_truth_reversals_refuses_a_direction_it_was_not_given():
    with pytest.raises(ValueError):
        truth_reversals([(1.0, True), (2.0, False)], "sideways")


def test_the_truth_law_is_documented_as_NOT_leakage_free():
    """The one sentence that must never be dropped when this result is quoted.

    Every other law in this module is a function of names and prices. This one
    reads ``is_winner``, so a rule built on it is a truth-eligibility finding of
    the pass2_loser kind, not an exclusion rule in the CAL-P133 class.
    """
    doc = truth_reversals.__doc__ or ""
    assert "LEAKAGE-FREE AND THIS ONE IS NOT" in doc
    assert "is_winner" in doc


def test_outcome_ladder_report_splits_by_resolution_authority():
    """The split IS the finding: measured 0.3% auth vs 22.2% guess-containing."""
    markets = {
        # authoritative and impossible: the easier rung lost, the harder one won
        1: [_leg("Above 10", 0.6, False, _AUTH), _leg("Above 20", 0.5, True, _AUTH)],
        # the same shape, but a guess is in the ladder
        2: [_leg("Above 10", 0.6, False, _GUESS), _leg("Above 20", 0.5, True, _AUTH)],
        # truth sound, prices reversed
        3: [_leg("Above 10", 0.4, True, _AUTH), _leg("Above 20", 0.9, False, _AUTH)],
        # clean
        4: [_leg("Above 10", 0.9, True, _AUTH), _leg("Above 20", 0.4, False, _AUTH)],
        # not a ladder at all
        5: [_leg("Yes", 0.5, True, _AUTH), _leg("No", 0.5, False, _AUTH)],
    }
    r = outcome_ladder_report(markets)
    assert r["truth_broken"] == {1, 2}
    assert r["price_broken"] == {3}
    assert r["clean"] == {4}
    c = r["census"]
    assert c["markets_scanned"] == 5
    assert c["markets_not_a_ladder"] == 1
    assert c["ladders_truth_broken_auth"] == 1
    assert c["ladders_truth_broken_guess"] == 1
    assert c["ladders_auth"] == 3 and c["ladders_guess"] == 1


def test_the_three_outcome_site_arms_are_disjoint_so_a_caller_can_add_them():
    markets = {
        1: [_leg("Above 10", 0.4, False, _AUTH), _leg("Above 20", 0.9, True, _AUTH)],
    }
    r = outcome_ladder_report(markets)
    # truth AND price are both broken here; severity order puts it in truth only
    assert r["truth_broken"] == {1}
    assert r["price_broken"] == set() and r["clean"] == set()


def test_an_ungraded_leg_takes_no_part_because_is_winner_defaults_to_false():
    """``is_winner`` is nullable DEFAULT false, so False is ambiguous. Only a leg
    carrying a resolution_source may be read as a graded result."""
    markets = {
        1: [_leg("Above 10", 0.6, False, None), _leg("Above 20", 0.5, True, None)],
    }
    r = outcome_ladder_report(markets)
    assert r["truth_broken"] == set()
    assert r["census"]["ladders_under_two_graded_legs"] == 1


def test_a_bracket_market_is_never_condemned_by_the_outcome_site():
    """The whole safety argument. Brackets sum to one rather than falling, and a
    monotonicity law applied to them would delete a correctly priced market."""
    markets = {1: [_leg("<5", 0.2, False), _leg("5-6", 0.5, True),
                   _leg(">16", 0.3, False)]}
    r = outcome_ladder_report(markets)
    assert r["truth_broken"] == r["price_broken"] == r["clean"] == set()
    assert r["census"]["markets_not_a_ladder"] == 1


def test_truth_is_registered_as_a_per_chunk_dimension():
    cce = _rail()
    assert "truth" in cce.PER_CHUNK_DIMENSIONS
    assert "truth" in cce.PER_CHUNK_CONTEXT
    assert "truth" not in cce.DIMENSIONS, "a pre-pass dimension is not a static one"


def test_every_per_chunk_dimension_has_its_own_context_slot():
    """The if/else that routed context by name held exactly TWO branches.

    A third dimension took the ``else`` and overwrote ``_MONO`` — an empty
    partition at the end of a fifteen-minute fold rather than an error at the
    start. This asserts the slot table covers every registered dimension.
    """
    cce = _rail()
    slots = {"ladder": "_LADDER", "mono": "_MONO", "truth": "_TRUTH"}
    assert set(slots) == set(cce.PER_CHUNK_DIMENSIONS)
    for name in slots.values():
        assert hasattr(cce, name), f"{name} is not a module global"


def test_the_truth_pre_pass_sql_carries_no_rung_grammar():
    """Python stays the only definition of a rung, so there is nothing to
    reconcile against a Postgres rendering later — the reason MONO_ROWS_SQL has
    no name filter, applied to the leg-site pull."""
    cce = _rail()
    sql = cce.TRUTH_ROWS_SQL
    for grammar_token in ("above", "at least", "or above", "O/U", "~", "+'"):
        assert grammar_token not in sql, (
            f"{grammar_token!r} in the pre-pass SQL would make Postgres a second "
            "definition of the rung grammar")
    # It must read the outcome columns the truth law needs, or the law silently
    # grades every leg False (is_winner is nullable DEFAULT false).
    assert "is_winner" in sql and "resolution_source" in sql


def test_the_truth_dimension_names_its_own_leakage_status():
    """A reader must not be able to quote this arm as if it were CAL-P133's."""
    cce = _rail()
    doc = cce.truth_dim.__doc__ or ""
    assert "NOT a leakage-free arm" in doc


# ---------------------------------------------------------------------------
# Grammar: the O/U compound, and the sign inversion it exists to fix.
#
# Every name below is copied from a real polymarket market in one of the four
# cells CAL-P135 censused (baseball, esports, soccer, basketball).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,value", [
    ("Trujillanos FC vs. Monagas SC: O/U 3.5", 3.5),
    ("Liverpool FC vs. Club Atlético de Madrid: O/U 4.5", 4.5),
    ("Paris Saint-Germain FC vs. ŠK Slovan Bratislava: O/U 0.5", 0.5),
    ("Mexico vs. Colombia: O/U 160.5", 160.5),
    ("Aguada Santeros vs. Vaqueros de Bayamon: O/U 170.5", 170.5),
    ("Map 1 Total Rounds: Over/Under 24.5", 24.5),
    ("Map 3 Total Rounds: Over/Under 21.5", 21.5),
    ("Games Total: O/U 2.5", 2.5),
    ("O/U 52.5", 52.5),
])
def test_over_under_lines_parse_as_rungs(name, value):
    parsed = parse_over_under(name)
    assert parsed is not None, f"{name!r} is the grammar the sports book writes"
    assert parsed[1] == value


@pytest.mark.parametrize("name", [
    "Trujillanos FC vs. Monagas SC: O/U 3.5",
    "Map 1 Total Rounds: Over/Under 24.5",
])
def test_an_over_under_line_is_descending_because_the_priced_side_is_over(name):
    """The sign is the whole point of this grammar.

    "total over 4.5" is contained in "total over 3.5", so the Over price can
    only fall as the line rises. Measured: soccer and baseball O/U markets carry
    ``Over``/``Under`` legs and no ``Yes`` leg at all.
    """
    assert parse_over_under(name)[2] == DEC
    assert name_rungs(name)[0][0][1] == DEC


def test_over_under_does_not_also_yield_the_under_half_as_an_ascending_rung():
    """🔴 THE REGRESSION THIS GRAMMAR EXISTS FOR.

    ``_NUM`` permits only whitespace between a direction word and its number, so
    in "Over/Under 24.5" the ``Over`` cannot bind (a ``/`` follows it) and the
    ``Under`` can. THRESHOLD_RE therefore matched the WRONG HALF of the compound
    and filed the rung as ascending — the exact inverse of the truth — under a
    key that had swallowed the word "Over" (``map 1 total rounds: over/ <RUNG>``).

    Measured on polymarket/esports: 19,766 names took that path.
    """
    rungs = name_rungs("Map 1 Total Rounds: Over/Under 24.5")
    assert len(rungs) == 1, f"one line must yield one rung, got {rungs}"
    (key, direction), value = rungs[0]
    assert direction == DEC
    assert value == 24.5
    assert "over/" not in key, (
        f"the key kept a fragment of the compound: {key!r}")
    assert INC not in {d for (_, d), _ in rungs}


def test_two_rungs_of_one_total_share_a_family_key():
    """Blanking the whole compound is what makes the family work; blanking only
    the number would leave "over/" in the key on one form and not the other."""
    a = name_rungs("Trujillanos FC vs. Monagas SC: O/U 1.5")[0][0]
    b = name_rungs("Trujillanos FC vs. Monagas SC: O/U 3.5")[0][0]
    assert a == b


def test_two_different_matches_never_share_an_over_under_family():
    a = name_rungs("Trujillanos FC vs. Monagas SC: O/U 3.5")[0][0]
    b = name_rungs("Liverpool FC vs. Club Atlético de Madrid: O/U 3.5")[0][0]
    assert a != b


def test_a_context_free_name_DOES_collapse_across_matches_and_that_is_measured():
    """A known limit, pinned so nobody reads the census as an all-clear.

    Polymarket names sub-markets without their match ("Map 1 Total Rounds:
    Over/Under 21.5" is written identically for every match), so the NAME site
    alone CANNOT identify one ladder in these cells. Measured by CAL-P135:
    49.2% of basketball's O/U keys and 100% of esports' span more than one
    event. A caller folding these cells must scope the family key to an event
    identity; ``read_name_ladders`` on names alone must not be trusted there.
    """
    a = name_rungs("Map 1 Total Rounds: Over/Under 21.5")[0][0]
    b = name_rungs("Map 1 Total Rounds: Over/Under 24.5")[0][0]
    assert a == b, (
        "these two names are indistinguishable, which is the finding — if this "
        "ever stops being true the collapse census needs re-running")


def test_a_valuation_grid_still_contributes_to_both_of_its_axes():
    """The containment suppression must drop FRAGMENTS, never disjoint spans."""
    rungs = name_rungs("Will OpenAI valuation hit (HIGH) $210B by June 30?")
    assert len(rungs) == 2
    assert {d for (_, d), _ in rungs} == {DEC, INC}


@pytest.mark.parametrize("name", [
    "Will Anthropic provide Mythos to the US government by April 30, 2026?",
    "at least 2000 measles cases",
    "Will Broadcom Q2 AI revenue be above $10.5B?",
])
def test_the_over_under_grammar_does_not_disturb_the_existing_ones(name):
    """The two guarded parser defects and a plain threshold are unchanged."""
    assert parse_over_under(name) is None
    assert name_rungs(name) == _rungs_without_over_under(name)


def _rungs_without_over_under(name):
    """What the pre-CAL-P135 grammar set produced, recomputed from the parts."""
    out = []
    for grammar in (parse_threshold, parse_by_date):
        parsed = grammar(name)
        if parsed is None:
            continue
        span, value, direction = parsed
        out.append(((blanked_key(name, span), direction), value))
    return out
