import json
from pathlib import Path
import pytest
from scripts.evals.browser_filer_privilege_residual_contract import evaluate_corpus,load_corpus
F=Path(__file__).parent/"fixtures/browser_filer_privilege_residual_contract.json"
def test_corpus():
 r=evaluate_corpus(load_corpus(F)); assert r["total"]==12 and r["passed"]==12
def test_all_critical_refusals():
 reasons={z for x in load_corpus(F)["cases"] for z in x["expected"]["reason_codes"]}
 assert {"MANIFEST_NOT_VALIDATED","TRIGGER_SHA_MISMATCH","TRIGGER_REPOSITORY_UNTRUSTED","FINGERPRINT_RACE","RECOVERY_NOT_IMPLEMENTED","FILING_DEFAULTS_DRIFT"}<=reasons
def test_clean_paths_exist(): assert sum(not x["expected"]["reason_codes"] for x in load_corpus(F)["cases"])>=4
def test_loader(tmp_path):
 c=load_corpus(F); c["schema_version"]="x"; p=tmp_path/"x"; p.write_text(json.dumps(c))
 with pytest.raises(ValueError,match="SCHEMA_VERSION_INVALID"): load_corpus(p)
def test_ids_unique():
 ids=[x["id"] for x in load_corpus(F)["cases"]]; assert len(ids)==len(set(ids))
