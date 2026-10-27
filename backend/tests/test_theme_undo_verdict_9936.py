"""#9936 G7: a theme undo restores a member only if its rule keeps it NOW.

PILLARS TRUTH / DISCOVER / MATCHING. SHIP: an explicitly authorized correction
removes a wrong AI or Oscars member through the guarded operator, and undoing
it never restores a member the theme no longer justifies.

Pure: the real registry ``decide()`` and ``plan_container_pass`` behind
``collection_publication.theme_undo_verdict``; no database. Cases adopted from
Fable's advisory packet ``artifacts/fable-9936-theme-undo-evidence-20261025/``
(``fixtures/test_fable_theme_undo_verdict_9936.py``, manifest bb5080be…), here
run against the operator's own function instead of the packet's copy.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import theme_assembly as ta
from app.utils import theme_definitions as td
from scripts.collection_publication import theme_undo_verdict

NOW = datetime(2026, 10, 25, 23, 0, tzinfo=timezone.utc)
SETTLED_3D = NOW - timedelta(days=3)
SETTLED_20D = NOW - timedelta(days=20)


def _ai(**changes) -> ta.MemberRow:
    base = dict(id=13791997, name="OpenAI IPO before 2027?", source="polymarket",
                external_id="PM-OAI-IPO", status="open", llm_sport_category="tech")
    return ta.MemberRow(**{**base, **changes})


def _oscars(**changes) -> ta.MemberRow:
    base = dict(id=57313556, name="Best Picture Winner", source="polymarket",
                external_id="PM-OSC-BP", status="open",
                llm_sport_category="entertainment",
                market_metadata={"event_title": "Oscars 2027: Best Picture"})
    return ta.MemberRow(**{**base, **changes})


# (case, slug, row now, backed-up class, verdict, reason, the rule's own reason)
CASES = [
    ("U1 unchanged open AI member", "ai", _ai(), "side_question",
     "allowed", "rule_admits_now", "admitted_entity_signal"),
    ("U2 AI result now beyond retention", "ai",
     _ai(status="resolved", settled_at=SETTLED_20D), "side_question",
     "refused", "not_justified_now", "resolved_beyond_retention"),
    ("L1 AI resolved within retention", "ai",
     _ai(status="resolved", settled_at=SETTLED_3D), "side_question",
     "allowed", "rule_admits_now", "admitted_entity_signal"),
    ("L2 AI resolved, settle time unknown", "ai",
     _ai(status="resolved", settled_at=None), "side_question",
     "allowed", "retained_as_member", "resolved_settle_time_unknown"),
    ("L3 Oscars resolved long ago", "oscars-2027",
     _oscars(status="resolved", settled_at=NOW - timedelta(days=400)), "title",
     "allowed", "rule_admits_now", "admitted_venue_event_edition"),
    ("X1 AI category re-labelled", "ai", _ai(llm_sport_category="sports"),
     "side_question", "refused", "not_justified_now", "wrong_category"),
    ("X2 AI renamed off-subject", "ai",
     _ai(name="Will a Claude Monet painting sell for $100M?"), "side_question",
     "refused", "not_justified_now", "lexical_false_friend"),
    ("X3 Oscars event title moved to 2028", "oscars-2027",
     _oscars(market_metadata={"event_title": "Oscars 2028: Best Picture"}), "title",
     "refused", "not_justified_now", "other_edition"),
    ("X4 Oscars edition now unknown", "oscars-2027",
     _oscars(market_metadata={"event_title": "Academy Awards: Best Picture"}), "title",
     "refused", "not_justified_now", "edition_unknown"),
    ("C1 backed-up class differs from the rule's", "ai", _ai(), "title",
     "refused", "class_changed", "admitted_entity_signal"),
    ("A1 market row gone", "ai", None, "side_question",
     "refused", "market_row_absent", None),
    ("A2 collection has no current definition", "oscars-2026", _oscars(), "title",
     "refused", "rule_unavailable", None),
]


@pytest.mark.parametrize("case,slug,row,cls,verdict,reason,rule_reason", CASES,
                         ids=[c[0] for c in CASES])
def test_the_verdict_is_the_rules_own(case, slug, row, cls, verdict, reason, rule_reason):
    got = theme_undo_verdict(slug, row, cls, now=NOW)
    assert (got[0], got[1]) == (verdict, reason), got
    assert got[2].get("rule_reason") == rule_reason, got


def test_only_the_clock_moved_a_member_out_of_retention():
    """Every identity column the restore compares is equal; only time moved."""
    row = _ai(status="resolved", settled_at=SETTLED_20D)
    inside = theme_undo_verdict("ai", row, "side_question", now=SETTLED_20D + timedelta(days=13))
    assert inside[0] == "allowed"
    assert theme_undo_verdict("ai", row, "side_question", now=NOW)[1] == "not_justified_now"


def test_a_new_rule_version_is_judged_by_the_new_rule():
    stricter = dataclasses.replace(td.AI, rule_version="ai-subject@3")
    got = theme_undo_verdict("ai", _ai(), "side_question", now=NOW,
                             registry={**td.REGISTRY, "ai": stricter})
    assert got[0] == "allowed" and got[2]["rule_version"] == "ai-subject@3"


def test_an_undecidable_row_is_refused_not_admitted():
    def broken(defn, market, *, now):
        raise ValueError("rule cannot read this row")

    registry = {**td.REGISTRY, "ai": dataclasses.replace(td.AI, decider=broken)}
    got = theme_undo_verdict("ai", _ai(), "side_question", now=NOW, registry=registry)
    assert got[:2] == ("refused", "rule_undecidable")


def test_bare_readmission_cannot_return_a_settle_time_unknown_member():
    """After a bare readmit there is no standing edge, so the next pass
    EXCLUDES this member; only the exact undo (edge restored) keeps it."""
    row = _ai(status="resolved", settled_at=None)
    decision = td.AI.decide(row, now=NOW)
    bare = ta.plan_container_pass([ta.MemberDecision(row.id, decision, False)], {},
                                  inventory_complete=True, rule_version="ai-subject@2")
    exact = ta.plan_container_pass([ta.MemberDecision(row.id, decision, False)],
                                   {row.id: "side_question"}, inventory_complete=True,
                                   rule_version="ai-subject@2")
    assert bare.edge_upserts == ()
    assert bare.decision_rows[0]["reason"] == td.RESOLVED_SETTLE_TIME_UNKNOWN
    assert exact.edge_deletes == ()
    assert exact.decision_rows[0]["reason"] == td.ADMITTED_SETTLE_TIME_PENDING
