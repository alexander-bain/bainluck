"""Dependency-free disposition oracle for retired Manus evidence rails."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
FIXTURE=Path(__file__).parents[2]/"tests/evals/fixtures/manus_retirement_contract.json"

def load_corpus(path:str|Path=FIXTURE)->dict[str,Any]:
    p=json.loads(Path(path).read_text(encoding="utf-8"))
    if p.get("schema_version")!="manus-retirement/v1": raise ValueError("SCHEMA_VERSION_INVALID")
    rows=p.get("cases")
    if not isinstance(rows,list) or not rows: raise ValueError("CASES_REQUIRED")
    ids=[r.get("id") for r in rows if isinstance(r,dict)]
    if len(ids)!=len(rows) or any(not isinstance(v,str) or not v for v in ids): raise ValueError("CASE_ID_REQUIRED")
    if len(ids)!=len(set(ids)): raise ValueError("CASE_ID_DUPLICATE")
    return p

def evaluate_case(row:dict[str,Any])->dict[str,Any]:
    x=row["input"]; kind=x["kind"]; executable=x.get("executable",False); historical=x.get("historical",False)
    replacement=x.get("replacement",False); cites=x.get("cites_evidence",False)
    if historical: action="retain"
    elif executable and kind in {"required_ci","optional_workflow","api_script"}: action="delete"
    elif kind in {"health_command","issue_citation","active_doc"}: action="annotate"
    else: action="archive"
    return {"action":action,"reproduction_path":("replacement" if replacement else "unavailable"),"notice_required":cites or kind in {"health_command","active_doc"}}

def evaluate_corpus(p:dict[str,Any])->dict[str,Any]:
    details=[]
    for row in sorted(p["cases"],key=lambda r:r["id"]):
        actual=evaluate_case(row); details.append({"id":row["id"],"actual":actual,"expected":row["expected"],"passed":actual==row["expected"]})
    return {"schema_version":p["schema_version"],"total":len(details),"passed":sum(d["passed"] for d in details),"details":details}

def main()->int:
    pa=argparse.ArgumentParser(description=__doc__); pa.add_argument("--fixture",default=str(FIXTURE)); a=pa.parse_args()
    result=evaluate_corpus(load_corpus(a.fixture)); print(json.dumps(result,indent=2,sort_keys=True)); return 0 if result["passed"]==result["total"] else 1
if __name__=="__main__": raise SystemExit(main())
