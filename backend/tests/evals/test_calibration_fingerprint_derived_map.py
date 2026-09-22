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

 🔴 AND NOT A HASHED ROOT (#6275, CERT-2902's repair found this). The two
 conjuncts above were a complete test of "the digest will not move" only while
 every hashed root lived in the build module. `identity_quarantine_ctes` is the
 first that does not: it is cross-module and it is not covered by value, but
 `_main_input_fingerprint` hashes its SOURCE, so editing it moves the digest —
 measured, `c0a825a6…` -> `80a180b0…` on the repair that prompted this line.
 Without this conjunct the ratchet told the author of that repair "regenerating
 this artifact RECORDS your change; it does not make it safe" and quoted two
 blocking constraints, about a change the digest had already caught. A warning
 that fires on the safe case is how the unsafe one stops being read.
 """
 rows=_rows(live)
 roots=set(live["hashed_roots"])
 return [n for n in names if n in rows and n not in roots and not rows[n]["covered_by_value"] and not rows[n]["origin"].startswith("app.tasks.precompute_calibration")]
def _moved_roots(live,pinned):
 """The hashed roots whose own source moved — i.e. the ones that cost the bank.

 The tier ABOVE :func:`_unhashed_cross_module`, and the opposite hazard. There,
 the digest does NOT move and regenerating hides a bank that can straddle two
 populations. Here the digest DOES move, the straddle is impossible, and the
 cost lands somewhere the artifact never mentioned: deploying discards every
 banked unit and restarts a multi-day convergence from zero.
 """
 a=live.get("hashed_root_sha16") or {}; b=pinned.get("hashed_root_sha16") or {}
 return sorted(n for n in set(a)|set(b) if a.get(n)!=b.get(n))
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
 roots=_moved_roots(live,pinned)
 unhashed=_unhashed_cross_module(live,moved)
 # The "instead" list is narrowed by what the per-root digests now rule out: a
 # reader two lines above "no hashed root moved" should not be told one might have.
 nothing_moved="(none — a count, a hashed root or a by-value declaration moved instead)" if roots else "(none — a count, a by-value declaration, or source outside every hashed root moved instead)"
 lines=["derived map diverged from the pinned artifact.","inputs that moved: "+(", ".join(moved) if moved else nothing_moved)]
 if roots:
  # CAL-P1336 (#6868). This branch is the reset side of the ship that made the
  # beat faster: the accuracy page has to walk ~4 days of beats to publish, and
  # a fingerprint move resets that walk to zero. Before this the ratchet told
  # the author of such a change to "regenerate the artifact" and nothing more,
  # so the largest cost in the whole convergence was the one cost it never
  # named. It is not an instruction to abandon the change — it is the one fact
  # that decides WHEN it lands.
  lines+=["","HASHED ROOT MOVED: "+", ".join(roots),
   "`_main_input_fingerprint` hashes the source of these functions, so this edit",
   "moves the digest. Deploying it DISCARDS every banked unit and restarts the",
   "convergence from zero — days of beats, not hours. Regenerate the artifact,",
   "and land it immediately after a successful publish, never mid-convergence."]
 if unhashed:
  lines+=["","UNHASHED CROSS-MODULE TIER: "+", ".join(unhashed),"Regenerating this artifact RECORDS your change; it does not make it safe.","",FIX_SEQUENCING_NOTE]
 elif moved or roots:
  lines.append("No moved input is in the unhashed cross-module tier — regenerate the artifact.")
 else:
  lines.append("No input and no hashed root moved: the digest does not move and the in-flight bank survives this change — regenerate the artifact.")
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
def test_a_cross_module_hashed_root_is_not_reported_as_unhashed():
 """#6275 / CERT-2902. `identity_quarantine_ctes` is the specimen and the only
 member of its shape: hashed as a ROOT, defined outside the build module, not
 covered by value. Editing it MOVES the digest, so the unhashed tier's warning
 and the sequencing note are both false for it — they are about an input the
 digest CANNOT see. (CAL-P1336 amends the "and nothing else" this line used to
 carry: moving the digest discards the in-flight bank, so the HASHED ROOT block
 does print here, and correctly. The two strings asserted below are unchanged.)

 Mutated rather than asserted off the pinned row, because the row would go on
 satisfying a classifier that had stopped consulting `hashed_roots`.
 """
 module="app.utils.market_identity"
 source=(BUILD.parents[1]/"utils/market_identity.py").read_text()
 needle="Step 1: the date token"
 assert needle in source, "the mutation site moved — re-aim it inside identity_quarantine_ctes"
 live=derive_map(module_sources={module:source.replace(needle,"Step 1: the mutated date token",1)})
 moved=_moved(live,frozen())
 assert "identity_quarantine_ctes" in moved, "the mutation did not move the input, so this proves nothing"
 assert _unhashed_cross_module(live,moved)==[], (
  "a cross-module HASHED ROOT was reported in the unhashed tier. Its source is "
  "hashed by `_main_input_fingerprint`, so the digest moves and an in-flight "
  "bank cannot straddle the change — the note's premise is false for it."
 )
 message=divergence_message(live,frozen())
 assert "UNHASHED CROSS-MODULE TIER" not in message
 assert FIX_SEQUENCING_NOTE not in message
def test_the_message_is_not_a_strawman_on_the_real_tree():
 """A green tree must produce an empty moved-list, or the two tests above pass on noise."""
 assert _moved(derive_map(),frozen())==[]
 assert _moved_roots(derive_map(),frozen())==[]
def test_hashed_root_digest_is_the_bytes_the_fingerprint_hashes():
 """The whole per-root tier is worth nothing if its digest is merely plausible.

 `_main_input_fingerprint` concatenates `inspect.getsource(root)` for six roots
 and hashes that. So the artifact's digest is checked against those exact bytes
 on the live objects — not against another AST walk, which would agree with the
 generator by construction and prove nothing about the real digest.
 """
 import hashlib, inspect
 from app.tasks import precompute_calibration as build
 live=derive_map()
 digests=live["hashed_root_sha16"]
 assert sorted(digests)==sorted(live["hashed_roots"]), "a root is declared but carries no digest"
 for name in live["hashed_roots"]:
  expected=hashlib.sha256(inspect.getsource(getattr(build,name)).strip().encode()).hexdigest()[:16]
  assert digests[name]==expected, f"{name}: the artifact digest is not a digest of the hashed bytes"
def test_an_edit_inside_a_hashed_root_names_it_and_says_the_bank_is_discarded():
 """CAL-P1336 (#6868). A COMMENT inside a root is the specimen, on purpose.

 `inspect.getsource` returns a function's text comments and all, so a comment
 inside a root moves the production digest and discards the bank, while a
 comment outside every root (the test below) does not. Nothing about the size
 or the semantics of an edit predicts which side of that line it falls on —
 only where it sits — which is exactly why an author cannot be expected to
 work it out and the ratchet has to say it.
 """
 source=BUILD.read_text()
 needle="# Queue 300D Item 2 refused this combination outright, because"
 assert source.count(needle)==1, "the mutation site moved — re-aim it inside _main_futures_sql"
 live=derive_map(source.replace(needle,needle+" (mutation probe)",1))
 assert _moved_roots(live,frozen())==["_main_futures_sql"]
 message=divergence_message(live,frozen())
 assert "HASHED ROOT MOVED: _main_futures_sql" in message
 assert "DISCARDS every banked unit" in message
 assert "the in-flight bank survives" not in message
def test_a_comment_outside_every_hashed_root_says_the_bank_survives():
 """The other direction, so the warning above means something when it IS printed.

 `_main_input_fingerprint`'s own docstring is not hashed by anything (it is not
 a root, and hashing a function's source never covers its caller), yet editing
 it moves `source_sha256` and reddens this ratchet. That is the case the
 generator's comment-only correction hit, and the honest answer to it is
 "regenerate, the bank is fine" — which the message could not say until the
 per-root digests existed to rule the other branch out.
 """
 source=BUILD.read_text()
 needle="Everything a carried phase output depends on, in one 32-char digest."
 assert source.count(needle)==1, "the mutation site moved — re-aim it outside every hashed root"
 live=derive_map(source.replace(needle,needle[:-1]+" (mutation probe).",1))
 assert live!=frozen(), "the mutation did not move the artifact, so this proves nothing"
 assert _moved_roots(live,frozen())==[]
 message=divergence_message(live,frozen())
 assert "HASHED ROOT MOVED" not in message
 assert "the in-flight bank survives this change" in message
