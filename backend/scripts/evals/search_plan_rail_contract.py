"""Pure C120 safety contract for named, bounded search plan requests."""
from __future__ import annotations
import copy,json
from pathlib import Path
F=Path(__file__).parents[2]/"tests"/"evals"/"fixtures"/"search_plan_rail_contract.json"
def merge(a,b):
 o=copy.deepcopy(a)
 for k,v in b.items(): o[k]=merge(o[k],v) if isinstance(v,dict) and isinstance(o.get(k),dict) else copy.deepcopy(v)
 return o
def load_corpus(path=F):
 p=json.loads(Path(path).read_text()); assert p["schema_version"]=="search-plan-rail/v1"; p["cases"]=[merge(p["defaults"],x) for x in p["cases"]]; return p
def check(r):
 e=[]
 if r["auth"]!="admin":e.append("AUTH_REQUIRED")
 if r["template"] not in r["allowed_templates"]:e.append("NAMED_TEMPLATE_REQUIRED")
 if r["raw_sql"]:e.append("RAW_SQL_FORBIDDEN")
 if r["mutation"] or r["side_effect"]:e.append("MUTATION_RISK")
 if not r["read_only"]:e.append("READ_ONLY_REQUIRED")
 if not(0<r["statement_ms"]<r["request_ms"]<=10000):e.append("BUDGET_INVALID")
 if r["mode"]=="analyze" and (not r["analyze_allowed"] or r["statement_ms"]>2500):e.append("ANALYZE_FORBIDDEN")
 if r["bytes"]>r["byte_cap"] or r["depth"]>r["depth_cap"]:e.append("PLAN_TRUNCATION_REQUIRED")
 if r["status"] in {"timeout","cancelled","malformed"} and r["verdict"]!="UNKNOWN":e.append("FALSE_SUCCESS")
 if r["checked"]==0 and r["verdict"]=="GREEN":e.append("CHECKED_ZERO_GREEN")
 if r["secret_in_error"]:e.append("SECRET_LEAK")
 return sorted(e)
def evaluate(p):
 d=[]
 for r in sorted(p["cases"],key=lambda x:x["id"]):
  a=check(r);x=sorted(r["expected"]);d.append({"id":r["id"],"passed":a==x,"actual":a,"expected":x})
 return {"total":len(d),"passed":sum(x["passed"] for x in d),"details":d}
if __name__=="__main__":
 r=evaluate(load_corpus());print(json.dumps(r,indent=2));raise SystemExit(0 if r["passed"]==r["total"] else 1)
