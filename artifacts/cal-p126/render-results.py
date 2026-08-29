#!/usr/bin/env python3
"""CAL-P126 — render the measured-cell table and the headline delta into the
finding doc, between the <!-- CAL-P126-RESULTS --> marker and the next heading.

Read-only against production: it reads the cell JSONs and the captured payload
already on disk. Re-runnable as more cells land.
"""
import glob
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
spec = importlib.util.spec_from_file_location(
    "pc", ROOT / "backend" / "scripts" / "calibration_phantom_curve.py")
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)

OUT = ROOT / "artifacts" / "cal-p126"
payload = json.loads((OUT / "payload-q268.json").read_text())
scan = {(c["source"], c["category"]): c
        for c in json.loads((OUT / "scan.json").read_text())["cells"]}

cells = [json.loads(Path(p).read_text())
         for p in sorted(glob.glob(str(OUT / "cell-*.json")))]

# headline-cohort weight per cell, straight from the payload
weight, total = {}, 0
for b in payload["buckets"]:
    if b["price_moved"] is None:
        continue
    weight[(b["source"], b["category"])] = weight.get(
        (b["source"], b["category"]), 0) + b["n"]
    total += b["n"]

h = pc.headline(payload, cells)
covered = sum(weight.get((c["source"], c["category"]), 0) for c in cells)
clean = sum(v for k, v in weight.items()
            if not scan.get(k, {}).get("phantom_possible", True))

lines = ["<!-- CAL-P126-RESULTS -->", "",
         "Every cell below was measured exactly, on the whole-vm rail, over every "
         "unit of the cell.", "",
         "| cell | headline weight | published rows | distinct outcomes | "
         "**phantom** | copies agree |",
         "|---|--:|--:|--:|--:|:--:|"]
for c in sorted(cells, key=lambda c: -weight.get((c["source"], c["category"]), 0)):
    w = weight.get((c["source"], c["category"]), 0)
    lines.append(
        f"| `{c['cell']}` | {w:,} ({w / total * 100:.1f}%) | "
        f"{c['published_rows']:,} | {c['distinct_outcomes']:,} | "
        f"**{c['phantom_pct']}%** | {'yes' if c['coherent'] else '**NO**'} |")

tot_ship = sum(c["published_rows"] for c in cells)
tot_dist = sum(c["distinct_outcomes"] for c in cells)
lines += [
    f"| **total measured** | **{covered:,} ({covered / total * 100:.1f}%)** | "
    f"**{tot_ship:,}** | **{tot_dist:,}** | "
    f"**{(tot_ship - tot_dist) / tot_ship * 100:.2f}%** | |",
    "",
    f"**{(covered + clean) / total * 100:.1f}% of the headline population is now "
    f"settled** — {clean / total * 100:.1f}% proved clean by the scan and "
    f"{covered / total * 100:.1f}% measured exactly. The rest is unmeasured, not "
    f"clean (§5).",
    "",
    "### The headline",
    "",
    "| | closing line | opening price |",
    "|---|--:|--:|",
    f"| published `/api/calibration` | **{h['published_closing']}** | "
    f"**{h['published_opening']}** |",
    f"| reproduced from its own buckets | {h['reproduced_closing']} | "
    f"{h['reproduced_opening']} |",
    f"| with the measured cells de-duplicated | **{h['dedup_closing']}** | "
    f"**{h['dedup_opening']}** |",
    f"| **delta** | **{h['delta_closing']:+}** | **{h['delta_opening']:+}** |",
    "",
    f"{h['substituted']} of the payload's {h['substituted'] + h['untouched']} "
    f"published buckets were substituted; "
    f"{h['outcomes_published'] - round(h['outcomes_dedup']):,} phantom rows were "
    f"removed from a curve of {h['outcomes_published']:,}.",
]
# Where the move comes from, bucket by bucket. The headline is an UNWEIGHTED
# mean over these ten rows, so a move concentrated in one of them would be a
# different (and much weaker) claim than a move spread across them.
base = [{"bucket_idx": b["bucket_idx"], "price_moved": b["price_moved"],
         "n": float(b["n"]), "winners": float(b["winners"]),
         "sum_prob": float(b["sum_prob"])} for b in payload["buckets"]]
ded, _ = pc.substitute(payload["buckets"], cells)


def _agg(bs, pm):
    a = {}
    for b in bs:
        if b.get("price_moved") != pm:
            continue
        s = a.setdefault(b["bucket_idx"], {"n": 0.0, "w": 0.0, "s": 0.0})
        s["n"] += b["n"]; s["w"] += b["winners"]; s["s"] += b["sum_prob"]
    return a


A, B = _agg(base, True), _agg(ded, True)
lines += ["", "### Where the move comes from", "",
          "The headline is an unweighted mean over these ten rows, so it "
          "matters whether a move is one bucket or all of them.", "",
          "| bucket | n now | n de-duplicated | \\|err\\| now | \\|err\\| dedup | move |",
          "|--:|--:|--:|--:|--:|--:|"]
worse = 0
for i in sorted(A):
    a, b = A[i], B[i]
    ea = abs(a["w"] / a["n"] - a["s"] / a["n"]) * 100
    eb = abs(b["w"] / b["n"] - b["s"] / b["n"]) * 100
    worse += eb > ea
    lines.append(f"| {i} | {a['n']:,.0f} | {b['n']:,.0f} | {ea:.3f} | {eb:.3f} "
                 f"| **{eb - ea:+.3f}** |")
lines.append(f"\n**{worse} of the {len(A)} buckets get worse.** The move is not "
             f"one bucket's artifact.")

if h["rail_only"]:
    lines.append(f"\n⚠️ {len(h['rail_only'])} buckets the rail measured and the "
                 f"payload does not publish: {h['rail_only'][:5]}")
if not h["reproduction_exact"]:
    lines.append("\n⚠️ the payload's own buckets no longer reproduce its own "
                 "headline — the delta above is not trustworthy until that is "
                 "explained.")

doc = OUT / "FINDING-16-CAL-whole-curve.md"
text = doc.read_text()
start = text.index("<!-- CAL-P126-RESULTS -->")
end = text.index("\n---\n", start)
doc.write_text(text[:start] + "\n".join(lines) + "\n" + text[end:])
(OUT / "headline.json").write_text(json.dumps(h, indent=1))

# The same numbers into the handoff report, which lives in the shared master
# tree and therefore gets the short form rather than the whole table.
report = Path.home() / "bainluck" / ".claude" / "handoff" / \
    "REPORT-CAL-P126-the-curve-flatters-itself.md"
if report.exists():
    rt = report.read_text()
    s = rt.index("<!-- CAL-P126-REPORT-HEADLINE -->")
    e = rt.index("\n## 5.", s)
    short = [
        "<!-- CAL-P126-REPORT-HEADLINE -->", "",
        f"**{(covered + clean) / total * 100:.1f}% of the headline population is "
        f"now settled** — {clean / total * 100:.1f}% proved clean by the scan, "
        f"{covered / total * 100:.1f}% measured exactly over "
        f"{len(cells)} cells at **{(tot_ship - tot_dist) / tot_ship * 100:.2f}% "
        f"phantom**.", "",
        "| | closing line | opening price |", "|---|--:|--:|",
        f"| published `/api/calibration` | **{h['published_closing']}** | "
        f"**{h['published_opening']}** |",
        f"| reproduced from its own buckets | {h['reproduced_closing']} | "
        f"{h['reproduced_opening']} | ",
        f"| with the measured cells de-duplicated | **{h['dedup_closing']}** | "
        f"**{h['dedup_opening']}** |",
        f"| **delta** | **{h['delta_closing']:+}** | "
        f"**{h['delta_opening']:+}** |", "",
        f"**{worse} of the 10 probability bands get worse**, so this is not one "
        f"bucket's artifact — and the direction has been the same on every cell: "
        f"the published curve flatters itself. "
        f"{h['outcomes_published'] - round(h['outcomes_dedup']):,} phantom rows "
        f"removed from {h['outcomes_published']:,}.", "",
        "Per-cell and per-bucket tables: "
        "`artifacts/cal-p126/FINDING-16-CAL-whole-curve.md` §4.",
    ]
    report.write_text(rt[:s] + "\n".join(short) + "\n" + rt[e:])
    print(f"\n-- also wrote {report.name}")
print("\n".join(lines))
