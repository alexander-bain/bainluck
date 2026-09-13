from __future__ import annotations
import json
from pathlib import Path
from scripts.evals.calibration_fingerprint_derived_map import BUILD,DEFAULT_MAP,FIX_SEQUENCING_NOTE,derive_declared,derive_map

def frozen(): return json.loads(DEFAULT_MAP.read_text())
def _rows(m): return {r["name"]:r for r in m["inputs"]}
def _moved(live,pinned):
 a,b=_rows(live),_rows(pinned)
 return sorted(set(a)^set(b))+sorted(n for n in set(a)&set(b) if a[n]!=b[n])
def _unhashed_cross_module(live,names):
 """The tier where regenerating the artifact is bookkeeping and NOT the fix.

 Same test `test_calibration_fingerprint_coverage.py` applies when it pins the
 cross-module list: not covered by value, and defined outside the build module.
 """
 rows=_rows(live)
 return [n for n in names if n in rows and not rows[n]["covered_by_value"] and not rows[n]["origin"].startswith("app.tasks.precompute_calibration")]
def divergence_message(live,pinned):
 """What an author who just reddened the ratchet needs, instead of a dict diff.

 CAL-P1142 (#997, the CERT-2788 follow-up measured rather than argued). The
 ratchet was a bare ``derive_map()==frozen()``, so a real edit to
 ``resolution_authority`` printed two 69-input dicts and "Differing items" —
 and the obvious response to that, regenerate the artifact and move on, is the
 wrong one for exactly the inputs that matter most. An input in the unhashed
 cross-module tier is not hashed by value in ``_main_input_fingerprint``, so
 the digest does NOT move: an in-flight bank stays resumable across the change
 and one published payload can carry units built from two populations. That is
 the hazard the whole census exists to make impossible, and the artifact going
 green again is what hides it.

 Both mutations were run before this was written — adding a source to
 ``LONE_CLAIM_TRUTH_ELIGIBLE_SOURCES``, and ``LONE_CLAIM_N_OUTCOMES`` 1 -> 2.
 Both redden this ratchet (so the tripwire is real, not decoration) and neither
 moves ``_main_input_fingerprint`` (so reddening is the whole of its protection).

 :data:`FIX_SEQUENCING_NOTE` is QUOTED, never restated. Two derivations of one
 fact is how this census was a hand-maintained map in the first place, and the
 note already carries both blocking constraints and the ordering.
 """
 moved=_moved(live,pinned)
 unhashed=_unhashed_cross_module(live,moved)
 lines=["derived map diverged from the pinned artifact.","inputs that moved: "+(", ".join(moved) if moved else "(none — a count, a hashed root or a by-value declaration moved instead)")]
 if unhashed:
  lines+=["","UNHASHED CROSS-MODULE TIER: "+", ".join(unhashed),"Regenerating this artifact RECORDS your change; it does not make it safe.","",FIX_SEQUENCING_NOTE]
 else:
  lines.append("No moved input is in the unhashed cross-module tier — regenerate the artifact.")
 return "\n".join(lines)
def test_generated_map_matches_real_source():
 live,pinned=derive_map(),frozen()
 assert live==pinned, divergence_message(live,pinned)
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
def test_the_message_names_the_cross_module_input_and_quotes_the_sequencing_note():
 """The D112 lone-claim edit is the specimen, because it is the one the cert parked."""
 module="app.utils.resolution_authority"
 source=(BUILD.parents[1]/"utils/resolution_authority.py").read_text()
 needle='LONE_CLAIM_N_OUTCOMES: int = 1'
 assert needle in source
 live=derive_map(module_sources={module:source.replace(needle,'LONE_CLAIM_N_OUTCOMES: int = 2',1)})
 message=divergence_message(live,frozen())
 assert "calibration_truth_eligible_sql" in message
 assert "UNHASHED CROSS-MODULE TIER" in message
 assert FIX_SEQUENCING_NOTE in message
def test_the_message_withholds_the_note_when_the_moved_input_is_not_in_that_tier():
 """The other direction, so the note means something when it IS printed.

 Dropping ``REPRESENTATIVE_TIE_AUTHORITY`` from the fingerprint un-covers a
 SAME-MODULE input: a real divergence the author should regenerate for, and
 not one where regenerating hides an unmoved digest.
 """
 mutated=BUILD.read_text().replace("        REPRESENTATIVE_TIE_AUTHORITY,\n","",1)
 message=divergence_message(derive_map(mutated),frozen())
 assert "REPRESENTATIVE_TIE_AUTHORITY" in message
 assert "UNHASHED CROSS-MODULE TIER" not in message
 assert FIX_SEQUENCING_NOTE not in message
def test_the_message_is_not_a_strawman_on_the_real_tree():
 """A green tree must produce an empty moved-list, or the two tests above pass on noise."""
 assert _moved(derive_map(),frozen())==[]
