from __future__ import annotations
import json
from pathlib import Path
from scripts.evals.calibration_fingerprint_derived_map import BUILD,DEFAULT_MAP,derive_declared,derive_map

def frozen(): return json.loads(DEFAULT_MAP.read_text())
def test_generated_map_matches_real_source(): assert derive_map()==frozen()
def test_declared_authority_is_parsed_from_real_fingerprint():
 roots,values=derive_declared(BUILD.read_text())
 assert roots==set(frozen()["hashed_roots"]); assert values==set(frozen()["covered_by_value"])
def test_every_input_has_actionable_classification():
 m=frozen(); assert m["input_count"]==len(m["inputs"])
 assert all(r["covered_by_value"] or r["used_in"] for r in m["inputs"])
def test_mutating_external_uncovered_definition_moves_checked_artifact():
 module="app.utils.resolution_authority"
 path=BUILD.parents[1]/"utils/resolution_authority.py"; source=path.read_text()
 needle='    "api_settlement",'
 assert needle in source
 mutated=source.replace(needle,needle+'\n    "mutation_probe",',1)
 assert derive_map(module_sources={module:mutated})!=frozen()
def test_adding_real_hashed_root_diverges_without_map_edit():
 source=BUILD.read_text(); needle="+ inspect.getsource(_main_futures_sql)"
 mutated=source.replace(needle,needle+"\n            + inspect.getsource(_coverage_bridge_ctes)",1)
 assert derive_map(mutated)["hashed_roots"]!=frozen()["hashed_roots"]
def test_removing_by_value_coverage_diverges():
 source=BUILD.read_text(); mutated=source.replace("        REPRESENTATIVE_TIE_AUTHORITY,\n","",1)
 assert derive_map(mutated)["covered_by_value"]!=frozen()["covered_by_value"]
