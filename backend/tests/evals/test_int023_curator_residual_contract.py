import json
from pathlib import Path
import pytest
from scripts.evals.int023_curator_residual_contract import evaluate_corpus,load_corpus
F=Path(__file__).parent/"fixtures/int023_curator_residual_contract.json"
def test_corpus():
 r=evaluate_corpus(load_corpus(F)); assert r["total"]==10 and r["passed"]==10
def test_residual_classes():
 reasons={z for x in load_corpus(F)["cases"] for z in x["expected"]["reason_codes"]}
 assert reasons=={"NOT_EXPLICITLY_ACCEPTED","SOURCE_EVIDENCE_STALE","WILDCARD_UNESCAPED","IDENTITY_UNPROVED","REVOCATION_NOT_APPLIED","PARTIAL_GENERATION_PUBLISHED"}
def test_clean_decoys(): assert sum(x["expected"]["verdict"]=="PASS" for x in load_corpus(F)["cases"])>=3
def test_loader(tmp_path):
 c=load_corpus(F); c["schema_version"]="x"; p=tmp_path/"x"; p.write_text(json.dumps(c))
 with pytest.raises(ValueError,match="SCHEMA_VERSION_INVALID"): load_corpus(p)
def test_unique_ids():
 ids=[x["id"] for x in load_corpus(F)["cases"]]; assert len(ids)==len(set(ids))
