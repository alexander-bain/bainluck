"""#989 CLOB winner->outcome mapper — unit tests for the binding-spec mapping.

Pure logic, no network/DB. Covers each market shape from
`.claude/handoff/clob_mapper_spec.md` and the integrity guards.
"""

from app.tasks.clob_resolve import (
    map_clob_to_outcome,
    _name_concordance_ok,
    _date_sanity_ok,
    _suffix_of,
    _ordinal_side,
    _vintage_bucket,
    _next_cursor_decision,
)


def _clob(t0, w0, t1, w1, **extra):
    m = {"tokens": [{"outcome": t0, "winner": w0},
                    {"outcome": t1, "winner": w1}]}
    m.update(extra)
    return m


def _outs(cond, yes_name, no_name):
    return [
        {"id": 1, "name": yes_name, "external_id": f"{cond}_yes"},
        {"id": 2, "name": no_name, "external_id": f"{cond}_no"},
    ]


COND = "0xabc"


# ---- rule 1: binary yes/no props ----

def test_rule1_binary_yes_wins():
    r = map_clob_to_outcome(_clob("Yes", True, "No", False),
                            _outs(COND, "Yes", "No"), False)
    assert r["tier"] == "resolved_direct"
    assert r["winner_id"] == 1 and r["loser_id"] == 2


def test_rule1_binary_no_wins():
    r = map_clob_to_outcome(_clob("Yes", False, "No", True),
                            _outs(COND, "Yes", "No"), False)
    assert r["tier"] == "resolved_direct"
    assert r["winner_id"] == 2 and r["loser_id"] == 1


# ---- rule 3: totals ----

def test_rule3_totals_named_direction():
    r = map_clob_to_outcome(_clob("Over", False, "Under", True),
                            _outs(COND, "Over 180.5", "Under 180.5"), False)
    assert r["tier"] == "resolved_direct"
    assert r["winner_id"] == 2  # Under won -> the _no outcome named "Under 180.5"


def test_rule3_totals_stored_yesno_is_ambiguous():
    # esports totals: CLOB Over/Under but our names are Yes/No -> forbidden to derive
    r = map_clob_to_outcome(_clob("Over", False, "Under", True),
                            _outs(COND, "Yes", "No"), False)
    assert r["skip"] == "ambiguous_skipped"
    assert r["why"] == "totals_stored_yesno"


# ---- rule 2 / 4a: team-name outcomes ----

def test_rule2_team_name_match():
    r = map_clob_to_outcome(
        _clob("Los Angeles Lakers", True, "Boston Celtics", False),
        _outs(COND, "Los Angeles Lakers", "Boston Celtics"), False)
    assert r["tier"] == "resolved_name_match"
    assert r["winner_id"] == 1


def test_rule2_team_label_unmatched_is_integrity_skip():
    r = map_clob_to_outcome(
        _clob("Team Alpha", True, "Team Beta", False),
        _outs(COND, "Completely Different", "Also Different"), False)
    assert r["skip"] == "integrity_skipped"


# ---- rule 4b: spread/handicap stored Yes/No — the dangerous class ----

def test_rule4b_spread_yesno_not_gamelinked_is_ambiguous():
    r = map_clob_to_outcome(
        _clob("Leviatán Esports", True, "XLG Gaming", False),
        _outs(COND, "Yes", "No"), False)
    assert r["skip"] == "ambiguous_skipped"
    assert r["why"] == "spread_yesno_nogame"


def test_rule4b_spread_yesno_gamelinked_is_score_based():
    r = map_clob_to_outcome(
        _clob("Team A", True, "Team B", False),
        _outs(COND, "Yes", "No"), True)
    assert r["skip"] == "resolved_score_based"


# ---- void / ambiguous structure ----

def test_void_no_winner():
    r = map_clob_to_outcome(_clob("Yes", False, "No", False),
                            _outs(COND, "Yes", "No"), False)
    assert r["skip"] == "void"


def test_void_two_winners():
    r = map_clob_to_outcome(_clob("Yes", True, "No", True),
                            _outs(COND, "Yes", "No"), False)
    assert r["skip"] == "void"


def test_non_binary_clob_is_ambiguous():
    m = {"tokens": [{"outcome": "A", "winner": True},
                    {"outcome": "B", "winner": False},
                    {"outcome": "C", "winner": False}]}
    r = map_clob_to_outcome(m, _outs(COND, "Yes", "No"), False)
    assert r["skip"] == "ambiguous_skipped"
    assert r["why"] == "not_binary_clob"


def test_missing_suffix_is_ambiguous():
    outs = [{"id": 1, "name": "Yes", "external_id": "plain_id_1"},
            {"id": 2, "name": "No", "external_id": "plain_id_2"}]
    r = map_clob_to_outcome(_clob("Yes", True, "No", False), outs, False)
    assert r["skip"] == "ambiguous_skipped"
    assert r["why"] == "no_binary_suffix"


# ---- integrity guards ----

def test_name_concordance_pass_and_fail():
    # Real data: the CLOB `question` matches our stored name closely (observed
    # identical for the WNBA O/U market). A gross mislink (Fed vs WNBA) must fail.
    assert _name_concordance_ok(
        "Toronto Tempo vs. Indiana Fever: O/U 180.5",
        "Toronto Tempo vs. Indiana Fever: O/U 180.5")
    assert not _name_concordance_ok(
        "Toronto Tempo vs. Indiana Fever: O/U 180.5",
        "Will the Federal Reserve cut interest rates in December 2026")


def test_name_concordance_empty_question_passes():
    assert _name_concordance_ok("Anything", "")


def test_date_sanity():
    clob = {"end_date_iso": "2026-06-16T00:00:00Z"}
    assert _date_sanity_ok("2026-06-16T00:00:00+00:00", clob)
    assert _date_sanity_ok("2026-06-20T00:00:00+00:00", clob)  # within 14d
    assert not _date_sanity_ok("2026-08-16T00:00:00+00:00", clob)  # >14d
    assert _date_sanity_ok(None, clob)  # can't compare -> pass


def test_suffix_of():
    assert _suffix_of("0xabc_yes") == "_yes"
    assert _suffix_of("0xabc_no") == "_no"
    assert _suffix_of("0xabc") is None
    assert _suffix_of(None) is None


# ---- Amendment 1: ordinal tier ----

def test_ordinal_disabled_keeps_spec_skip():
    # default (spec-conformant): Yes/No-stored handicap -> ambiguous
    r = map_clob_to_outcome(_clob("Leviatán Esports", True, "XLG Gaming", False),
                            _outs(COND, "Yes", "No"), False)
    assert r["skip"] == "ambiguous_skipped"


def test_ordinal_enabled_spread_resolves_by_index():
    # token[0] wins -> _yes side (id 1)
    r = map_clob_to_outcome(_clob("Leviatán Esports", True, "XLG Gaming", False),
                            _outs(COND, "Yes", "No"), False, enable_ordinal=True)
    assert r["tier"] == "resolved_ordinal"
    assert r["winner_id"] == 1 and r["loser_id"] == 2
    assert r["ordinal_why"] == "spread_yesno_nogame"


def test_ordinal_enabled_spread_index1_resolves_no_side():
    # token[1] wins -> _no side (id 2)
    r = map_clob_to_outcome(_clob("Leviatán Esports", False, "XLG Gaming", True),
                            _outs(COND, "Yes", "No"), False, enable_ordinal=True)
    assert r["tier"] == "resolved_ordinal"
    assert r["winner_id"] == 2 and r["loser_id"] == 1


def test_ordinal_enabled_totals_stored_yesno():
    r = map_clob_to_outcome(_clob("Over", False, "Under", True),
                            _outs(COND, "Yes", "No"), False, enable_ordinal=True)
    assert r["tier"] == "resolved_ordinal"
    assert r["winner_id"] == 2  # Under won == token[1] == _no side


def test_ordinal_gamelinked_stays_score_based():
    # game-linked yes/no-vs-line stays score-based even with ordinal on
    r = map_clob_to_outcome(_clob("Team A", True, "Team B", False),
                            _outs(COND, "Yes", "No"), True, enable_ordinal=True)
    assert r["skip"] == "resolved_score_based"


def test_ordinal_agree_true_on_aligned_direct():
    # resolved_direct where label winner == ordinal winner (token[0])
    r = map_clob_to_outcome(_clob("Yes", True, "No", False),
                            _outs(COND, "Yes", "No"), False)
    assert r["tier"] == "resolved_direct"
    assert r["ordinal_agree"] is True


def test_ordinal_agree_false_flags_misaligned_vintage():
    # CLOB token order reversed vs our _yes/_no: label picks _yes ('Yes'), but
    # 'Yes' is at index 1 -> ordinal picks _no. Disagreement = broken invariant.
    r = map_clob_to_outcome(_clob("No", False, "Yes", True),
                            _outs(COND, "Yes", "No"), False)
    assert r["tier"] == "resolved_direct"
    assert r["winner_id"] == 1  # label match: 'Yes' outcome
    assert r["ordinal_agree"] is False  # ordinal would pick token[1]=_no=id2


def test_ordinal_side_helper():
    assert _ordinal_side({"clob_winner": "Over",
                          "clob_tokens": ["Over", "Under"]}) == "_yes"
    assert _ordinal_side({"clob_winner": "Under",
                          "clob_tokens": ["Over", "Under"]}) == "_no"
    assert _ordinal_side({"clob_winner": None, "clob_tokens": []}) is None


def test_vintage_bucket():
    assert _vintage_bucket("2026-07-06T00:00:00Z") == "2026-Q3"
    assert _vintage_bucket("2025-02-01T00:00:00Z") == "2025-Q1"
    assert _vintage_bucket(None) == "unknown"


# ---- #989 Item 1: drain cursor must not advance past rate-limited markets ----

def test_cursor_clean_full_batch_advances_to_min():
    # No errors, full batch (rows_len == limit): advance to the min id seen.
    assert _next_cursor_decision(1000, [], 300, 300) == ("set", 1000)


def test_cursor_clean_partial_batch_wraps():
    # No errors, batch smaller than limit == fully drained -> wraparound.
    assert _next_cursor_decision(1000, [], 120, 300) == ("delete", None)


def test_cursor_errors_hold_above_highest_error():
    # Errors present -> resume just ABOVE the highest errored id, so every
    # errored market is re-fetched next run (retry-in-place).
    assert _next_cursor_decision(1000, [2500, 4000, 3100], 300, 300) == ("set", 4001)


def test_cursor_errors_override_wraparound():
    # Even on a partial (final) batch, errors must NOT trigger a wraparound —
    # otherwise the tail's rate-limited markets are lost.
    assert _next_cursor_decision(1000, [1500], 50, 300) == ("set", 1501)


def test_cursor_error_below_min_still_reloads():
    # A single errored id lower than other work: resume above it.
    assert _next_cursor_decision(2000, [1200], 300, 300) == ("set", 1201)


def test_cursor_noop_when_nothing_processed():
    assert _next_cursor_decision(None, [], 0, 300) == ("noop", None)
    assert _next_cursor_decision(None, [123], 0, 300) == ("noop", None)
