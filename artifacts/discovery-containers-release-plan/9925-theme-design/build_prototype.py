"""Build prototype.html for #9925 from the evidence files beside it.

Every number on the prototype comes from `evidence/` (production reads taken
2026-09-30 ~20:40-20:55Z). Anything that is NOT production data is labelled
FIXTURE in the page itself. Run: python3 build_prototype.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
EV = HERE / "evidence"

served = json.loads((EV / "served-feed-bundles-2026-09-30T2039Z.json").read_text())
sections = json.loads((EV / "inventory-sections-2026-09-30.json").read_text())


def leader(text):
    if not text:
        return None, None
    m = re.match(r"^(.*)\s+([01](?:\.\d+)?)$", str(text))
    if not m:
        return str(text), None
    return m.group(1), float(m.group(2))


FOLDED_IDS = {
    r["id"]
    for stages in sections["awards"].values()
    for rows in stages.values()
    for r in rows
    if r["twin_ids"]
} | {
    t
    for stages in sections["awards"].values()
    for rows in stages.values()
    for r in rows
    for t in r["twin_ids"]
}


def served_members(story_key):
    out = []
    for m in served[story_key]["data"]["items"]:
        d = m["data"]
        out.append({
            "id": d["id"],
            "name": d["name"],
            # The row's own venue. The served `sources` list is keyed on the
            # canonical_market_key BUCKET (feed.py `_canonical_source_names_cache`),
            # which holds the Oscar beside the Grammy, so it over-claims a twin.
            "sources": [d.get("source")],
            "folded": d["id"] in FOLDED_IDS,
            "observed": d.get("price_observed_at"),
            "context": m.get("context_summary"),
            "format": (d.get("discover_card") or {}).get("suggested_format"),
            "top": [
                {"name": o["name"], "p": o["probability"], "move": o.get("movement")}
                for o in (d.get("top_outcomes") or [])[:3]
            ],
        })
    return out


def awards_rows():
    order = ["Oscars", "Grammys", "Daytime Emmys", "Latin Grammys"]
    ceremony_page = {"Oscars": "/event/awards/oscars", "Grammys": "/event/awards/grammys"}
    out = []
    for cer in order:
        stages = sections["awards"].get(cer, {})
        groups = []
        for stage, title in (("winners", "Winners"), ("nominations", "Nominations"), ("around", "Nominations")):
            for r in stages.get(stage, []):
                if "attend" in r["name"].lower():
                    continue  # does not answer "who wins" — stays on the ceremony page
                name, p = leader(r["leader"])
                row = {
                    "id": r["id"], "label": r["label"], "leader": name, "p": p,
                    "sources": r["sources"], "traded": bool(r["vol24"]),
                    "folded": len(r["twin_ids"]) > 0, "twins": r["twin_ids"],
                    "kind": "nominee" if stage != "winners" else "winner",
                }
                if stage == "around":
                    row["kind"] = "race"
                g = next((g for g in groups if g["title"] == title), None)
                if g is None:
                    g = {"title": title, "rows": []}
                    groups.append(g)
                g["rows"].append(row)
        out.append({"key": cer, "title": f"The {cer} 2027" if cer in ceremony_page else f"{cer} 2026",
                    "page": ceremony_page.get(cer), "groups": groups})
    return out


def ai_rows():
    out = []
    for h, rows in sections["ai"].items():
        if not rows:
            continue
        items = []
        for r in rows:
            name, p = leader(r["leader"])
            items.append({"id": r["id"], "label": r["name"], "leader": name, "p": p,
                          "sources": [r["source"]], "traded": bool(r["vol24"]), "res": r["res"],
                          "kind": "race"})
        out.append({"key": h, "title": h, "groups": [{"title": None, "rows": items}]})
    return out


oil = json.loads((EV / "served-feed-oil-bundle-2026-09-30T2039Z.json").read_text())
served["story:oil"] = oil

data = {
    "counts": sections["counts"],
    "oil": {"members": served_members("story:oil")},
    "awards": {"members": served_members("story:major_entertainment_events"), "sections": awards_rows()},
    "ai": {"members": served_members("story:ai"), "sections": ai_rows()},
}
template = (HERE / "prototype.template.html").read_text()
(HERE / "prototype.html").write_text(template.replace("/*__DATA__*/null", json.dumps(data)))
print("wrote prototype.html", {k: len(v["sections"]) for k, v in data.items() if "sections" in v})
