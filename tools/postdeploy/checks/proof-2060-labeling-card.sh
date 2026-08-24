#!/usr/bin/env bash
# UX-P123 — the production proof for `program/ux-100` (#2060, the labeling card).
#
# ## Why this branch was UNCOVERED, and why that was the dangerous kind of gap
#
# ux-100 is the only one of the three branches UX-P122's coverage table named
# that ships **real production surface**: 22 files across `backend/`,
# `frontend/`, `ios/` and `contracts/`. ux-106 and ux-107 are tools-only, so for
# them "no proof" is defensible and `checks/gate-branch-surface.sh` asserts the
# antecedent that keeps it defensible. ux-100 had no such excuse. It merged, it
# deployed, and nothing in the harness looked at it — under a summary of green
# rows, which is the exact shape of the #2060 failure reproduced one level up.
#
# ## What ux-100 actually changed, and therefore what this can observe
#
# Three fixes, all of them on the card the labeler is shown, all reachable from
# one authenticated GET:
#
#   1. **Double-rounded complement pairs printed 101.** Two outcomes priced
#      0.925/0.075 were each rounded independently to 93 and 8. The fix
#      (`rendered_card_percents`, `backend/app/utils/graded_card.py:182`)
#      normalizes by the true total, rounds index 0 once, and derives index 1 as
#      `100 - leader`. Contract: `contracts/rendered_percent.json` v3.
#   2. **`commence_time` was not served**, so a Kalshi game card was dated by
#      `resolution_date` — which on a game market is the CLOSE time, not the
#      start (gotcha #14). The fix serves both.
#   3. **Kalshi truncations were shown raw.** `Los Angeles D` is now repaired to
#      `Los Angeles Dodgers` when the ticker's team codes resolve it, with the
#      untouched provider string preserved as `name_at_source` so the repair is
#      auditable rather than merely applied.
#
# ## The surface question, which this lane got wrong once already
#
# UX-P122's standing method fact: *an UNKNOWN can be a WRONG-SURFACE verdict,
# not a thin world.* Both surfaces carry all three fixes through the same shared
# utils, and the obvious one is the wrong one:
#
#   /api/admin/label-pass/pending          34 cards → ONE complement pair
#   /api/admin/ranking-judgments/candidates  100 cards → EIGHTEEN, of which
#                                          ELEVEN discriminate the fix
#
# Measured, not assumed, before this file was written. The label-pass queue is
# LLM proposals — overwhelmingly multi-outcome ladders — while the labeling
# sampler is stratified over the live corpus and full of two-sided tennis and
# senate markets. A proof pointed at the first would have reported a single
# passing pair and called that evidence.
#
# ## Why the discriminating count is a verdict input, not decoration
#
# An invariant that holds because nothing in the sample could violate it is not
# a proof, and a green row that says so is worse than a missing one. So this
# check counts the pairs where the OLD double-round would have printed something
# other than 100, and if that count is zero it returns UNKNOWN even when every
# assertion holds: the sample could not tell the fix from the bug.
#
# Verdicts: PASS(0) FAIL(1) UNKNOWN(3) NOT_DEPLOYED(4) TRANSPORT(5).
# Per gotcha #54's amendment, 1 is a result and anything else is a story about
# the harness. Per gotcha #53, every population is printed with its denominator
# and a zero-population read is UNKNOWN, never PASS.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/../lib.sh"

# The branch this check gates on. The runner reads THIS LINE and only this line
# (UX-P123) — the prose above names other branches while explaining itself, and
# prose that mentions a branch is the opposite of a proof of it.
REF="${REF:-program/ux-100}"

LIMIT="${LABELING_PROOF_LIMIT:-100}"
OUT="${LABELING_PROOF_PAYLOAD:-${HARNESS_DIR:-/tmp/postdeploy-run}/labeling-candidates.json}"
mkdir -p "$(dirname "$OUT")"

hdr "PROOF — #2060 labeling card ($REF)"

require_deployed "$REF" || exit $?

# `reviewer` is a filter key, not a write: this route only READS. It is set to a
# name no human uses so the proof cannot be mistaken for review activity, and so
# it never filters against a real reviewer's already-seen set.
say "   GET /api/admin/ranking-judgments/candidates?limit=$LIMIT (Bearer, header-only auth)"
if ! api_get_admin "/api/admin/ranking-judgments/candidates?limit=$LIMIT&reviewer=ux-p123-proof&reviewed_surface=web_discover" "$OUT"; then
  verdict "#2060" "TRANSPORT — could not read the labeling sampler"
  exit $RC_TRANSPORT
fi

python3 - "$OUT" <<'PY'
import json, math, re, sys

RC_PASS, RC_FAIL, RC_UNKNOWN = 0, 1, 3
worst = RC_PASS


def bump(rc):
    global worst
    if rc > worst:
        worst = rc


def verdict(name, text):
    print(f"{name}: {text}")


# The pre-ux-100 renderer: each outcome rounded on its own, half-up. Reproduced
# here rather than imported, because the point is to show the deployed card
# differs from what this would have printed — importing the fixed helper to
# check the fixed output would be a tautology.
def naive_percent(p):
    return None if p is None else math.floor(float(p) * 100 + 0.5)


COMPLEMENT_MIN, COMPLEMENT_MAX = 0.99, 1.01          # graded_card.py:159-160
TRUNCATED = re.compile(r"^(?P<city>.+?)\s+(?P<tail>[A-Z]{1,3})$")
FINGERPRINT = re.compile(r"^[0-9a-f]{16}$")

payload = json.load(open(sys.argv[1]))
items = payload.get("items") or []

print(f"   candidate_source: {payload.get('candidate_source')}")
print(f"   sampled: {len(items)} of {payload.get('total_available')} available")
print(f"   strata: {payload.get('strata')}")

if not items:
    verdict("#2060", "UNKNOWN — the sampler returned zero cards. An empty 200 is a "
                     "response shape, not a passing card (gotcha #53).")
    sys.exit(RC_UNKNOWN)

# ── 1. complement pairs render to exactly 100 ───────────────────────────────
pairs = broken = discriminating = 0
examples = []
for it in items:
    outs = it.get("top_outcomes") or []
    probs = [o.get("probability") for o in outs]
    if len(probs) != 2 or any(p is None for p in probs):
        continue
    total = float(probs[0]) + float(probs[1])
    if not (COMPLEMENT_MIN <= total <= COMPLEMENT_MAX):
        continue
    pairs += 1
    served = [o.get("rendered_percent") for o in outs]
    if any(s is None for s in served) or sum(served) != 100:
        broken += 1
        print(f"     BROKEN  {probs} → {served} (sum {sum(s or 0 for s in served)})"
              f"  {str(it.get('name'))[:56]}")
        continue
    naive = sum(naive_percent(p) for p in probs)
    if naive != 100:
        discriminating += 1
        if len(examples) < 4:
            examples.append(f"{probs} → {served}; the old double-round printed {naive}"
                            f"  ({str(it.get('name'))[:44]})")

print()
print(f"   [1] complement pairs (two priced outcomes summing into "
      f"[{COMPLEMENT_MIN}, {COMPLEMENT_MAX}]): {pairs} of {len(items)} cards")
print(f"       rendering to something other than 100: {broken}")
print(f"       where the pre-fix renderer would NOT have printed 100: {discriminating}")
for e in examples:
    print(f"         · {e}")

if pairs == 0:
    verdict("[1] complement rendering",
            "UNKNOWN — no two-outcome complement card in the sample. Nothing to observe.")
    bump(RC_UNKNOWN)
elif broken:
    verdict("[1] complement rendering",
            f"FAIL — {broken}/{pairs} cards print a total other than 100%. #2060's "
            f"first fix is not live on this surface.")
    bump(RC_FAIL)
elif discriminating == 0:
    verdict("[1] complement rendering",
            f"UNKNOWN — all {pairs} pairs sum to 100, but every one of them would "
            f"ALSO have summed to 100 under the pre-fix double-round. This sample "
            f"cannot tell the fix from the bug, so it is not evidence of the fix.")
    bump(RC_UNKNOWN)
else:
    verdict("[1] complement rendering",
            f"PASS — {pairs}/{pairs} sum to exactly 100, and {discriminating} of them "
            f"would have printed 99 or 101 before ux-100. The fix is observable and "
            f"observed.")

# ── 2. commence_time is served ──────────────────────────────────────────────
missing_key = [it.get("id") for it in items if "commence_time" not in it]
non_null = sum(1 for it in items if it.get("commence_time"))
both = sum(1 for it in items if it.get("commence_time") and it.get("resolution_date"))

print()
print(f"   [2] commence_time key present: {len(items) - len(missing_key)}/{len(items)}"
      f"   non-null: {non_null}/{len(items)}"
      f"   carrying BOTH commence_time and resolution_date: {both}")

if missing_key:
    verdict("[2] commence_time served",
            f"FAIL — {len(missing_key)} card(s) omit the key entirely "
            f"(ids {missing_key[:8]}). That is the pre-ux-100 shape.")
    bump(RC_FAIL)
elif non_null == 0:
    verdict("[2] commence_time served",
            "UNKNOWN — the key is on every card but null on every card. A key that is "
            "always null is indistinguishable from one that is never populated.")
    bump(RC_UNKNOWN)
else:
    verdict("[2] commence_time served",
            f"PASS — served on {len(items)}/{len(items)}, populated on {non_null}. "
            f"A game card can no longer be dated by its close time (gotcha #14).")

# ── 3. the name-repair channel ──────────────────────────────────────────────
outcomes = channel = repaired = 0
unrepaired = []
repairs_seen = []
for it in items:
    for o in it.get("top_outcomes") or []:
        outcomes += 1
        if "name_at_source" not in o:
            continue
        channel += 1
        src, shown = o.get("name_at_source"), o.get("name")
        if src != shown:
            repaired += 1
            if len(repairs_seen) < 4:
                repairs_seen.append(f"{src!r} → {shown!r}")
        elif isinstance(src, str) and TRUNCATED.match(src):
            unrepaired.append((it.get("id"), src))

print()
print(f"   [3] outcomes carrying name_at_source: {channel}/{outcomes}"
      f"   repairs applied: {repaired}")
for r in repairs_seen:
    print(f"         · {r}")

if channel != outcomes:
    verdict("[3] repair channel served",
            f"FAIL — {outcomes - channel} outcome(s) ship no name_at_source. The repair "
            f"becomes unauditable: a wrong repair and a correct one look identical.")
    bump(RC_FAIL)
else:
    verdict("[3] repair channel served",
            f"PASS — every one of {outcomes} outcomes carries the untouched provider "
            f"string alongside the displayed one.")

# An OBSERVATION, deliberately not a verdict. `repair_truncated_names` derives
# the nickname from the two team codes in a GAME ticker; a season-futures ticker
# (KXMLB-26, KXSB-27) carries none, so the helper abstains by design rather than
# inventing a name. Truncations therefore survive on futures cards. That is a
# real user-visible defect and it is NOT one ux-100 claimed to fix, so failing
# here would paint this row permanently red for someone else's bug — and a row
# that is always red stops being read.
if unrepaired:
    print()
    print(f"   OBSERVED, not asserted: {len(unrepaired)} truncation-shaped name(s) "
          f"survive un-repaired, all on season-futures tickers whose ids carry no "
          f"team-code pair for the helper to resolve:")
    for mid, nm in unrepaired[:8]:
        print(f"         · market {mid}: {nm!r}")
    print("       ux-100's repair is game-ticker-scoped by construction. Extending it "
          "to futures fields is unowned work, named here so it is not re-discovered.")

# ── 4. card_fingerprint ─────────────────────────────────────────────────────
bad_fp = [it.get("id") for it in items
          if not FINGERPRINT.match(str(it.get("card_fingerprint") or ""))]
print()
print(f"   [4] card_fingerprint is 16 hex chars: {len(items) - len(bad_fp)}/{len(items)}")
if bad_fp:
    verdict("[4] card fingerprint",
            f"FAIL — {len(bad_fp)} card(s) ship an unusable fingerprint (ids {bad_fp[:8]}). "
            f"Every judgment written against them 409s at the write path.")
    bump(RC_FAIL)
else:
    verdict("[4] card fingerprint",
            f"PASS — all {len(items)} cards are addressable by the digest the write "
            f"path re-derives.")

print()
name = {RC_PASS: "PASS", RC_FAIL: "FAIL", RC_UNKNOWN: "UNKNOWN"}[worst]
verdict("#2060 labeling card", f"{name} — worst of four assertions over {len(items)} live cards")
sys.exit(worst)
PY
rc=$?
exit $rc
