"""Adversarial contract for privileged browser-audit manifest consumer."""
from __future__ import annotations
import argparse,json
from pathlib import Path
F=Path(__file__).parents[2]/"tests/evals/fixtures/browser_filer_privilege_residual_contract.json"
def load_corpus(path=F):
 p=json.loads(Path(path).read_text()); c=p.get("cases")
 if p.get("schema_version")!="browser-filer-privilege-residual/v1": raise ValueError("SCHEMA_VERSION_INVALID")
 if not isinstance(c,list) or not c: raise ValueError("CASES_REQUIRED")
 return p
def evaluate_case(r):
 x=r["input"]; reasons=[]
 if not x.get("validator_passed"): reasons.append("MANIFEST_NOT_VALIDATED")
 if not x.get("trigger_sha") or x.get("manifest_sha")!=x.get("trigger_sha"): reasons.append("TRIGGER_SHA_MISMATCH")
 if not x.get("canonical_repo"): reasons.append("TRIGGER_REPOSITORY_UNTRUSTED")
 if x.get("verdict")=="FAIL" and not x.get("fingerprint_claim_serialized"): reasons.append("FINGERPRINT_RACE")
 if x.get("verdict")=="PASS" and x.get("open_issue") and not x.get("recovery_state_applied"): reasons.append("RECOVERY_NOT_IMPLEMENTED")
 if x.get("labels") and not {"priority:p2","needs-triage","alert-intake"}.issubset(set(x["labels"])): reasons.append("FILING_DEFAULTS_DRIFT")
 return {"action":"REFUSE" if reasons else ("FILE_OR_COMMENT" if x.get("verdict")=="FAIL" else "RECOVER_OR_NOOP"),"reason_codes":sorted(reasons)}
def evaluate_corpus(p):
 d=[]
 for r in p["cases"]:
  a=evaluate_case(r); d.append({"id":r["id"],"actual":a,"expected":r["expected"],"passed":a==r["expected"]})
 return {"total":len(d),"passed":sum(x["passed"] for x in d),"details":d}
def main():
 pa=argparse.ArgumentParser(); pa.add_argument("--fixture",default=str(F)); a=pa.parse_args(); r=evaluate_corpus(load_corpus(a.fixture)); print(json.dumps(r,indent=2)); return 0 if r["passed"]==r["total"] else 1
if __name__=="__main__": raise SystemExit(main())
