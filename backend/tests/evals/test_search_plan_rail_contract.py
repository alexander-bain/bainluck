from __future__ import annotations
import copy
from scripts.evals.search_plan_rail_contract import check,evaluate,load_corpus
def row(i):return copy.deepcopy(next(x for x in load_corpus()["cases"] if x["id"]==i))
def test_corpus():r=evaluate(load_corpus());assert r["total"]==20 and r["passed"]==20
def test_raw_sql_and_mutation_fail():assert {"RAW_SQL_FORBIDDEN","MUTATION_RISK"}<=set(check(row("raw-mutating-sql")))
def test_auth_and_named_template():assert {"AUTH_REQUIRED","NAMED_TEMPLATE_REQUIRED"}<=set(check(row("unknown-unauth")))
def test_analyze_tighter():assert "ANALYZE_FORBIDDEN" in check(row("analyze-unbounded"))
def test_timeout_unknown():
 r=row("timeout");r["verdict"]="GREEN";assert "FALSE_SUCCESS" in check(r)
def test_secret_redaction():assert "SECRET_LEAK" in check(row("secret-error"))
def test_order_independent():
 p=load_corpus();q=copy.deepcopy(p);q["cases"].reverse();assert evaluate(p)==evaluate(q)
