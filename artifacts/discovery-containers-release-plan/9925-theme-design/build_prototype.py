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
# Lifetime + 24h volume for every candidate row, read 2026-09-30 21:03Z. Used to
# keep three volume states apart instead of reading an empty 24h figure as
# "not traded" (correction 2026-09-30, see README "Corrections").
_vol = json.loads((EV / "volume-lifetime-2026-09-30T2103Z.json").read_text())
VOL = {r[0]: dict(zip(_vol["columns"], r)) for r in _vol["rows"]}
_aw = json.loads((EV / "awards-candidates-216.json").read_text())
AWARD_ROW = {r[0]: dict(zip(_aw["columns"], r)) for r in _aw["rows"]}


def vol_state(vol24, row_id):
    """traded | zero24h | unknown24h. Only a MEASURED 0 is "no trades in 24h".

    NULL is not zero: the Kalshi writer stores a summed 0 as NULL
    (`backend/app/tasks/kalshi.py` `sum(...) or None`), so an empty 24h figure
    means "not reported", and 49 of the 84 empty awards rows have lifetime
    volume > 0 (they HAVE traded).
    """
    if vol24 is not None and float(vol24) > 0:
        return "traded"
    if vol24 is not None:
        return "zero24h"
    return "unknown24h"


def traded_ever(row_id):
    life = (VOL.get(row_id) or {}).get("volume")
    return None if life is None else float(life) > 0


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


def served_also(row_id):
    """Every OTHER venue copy of a served member's question, each under its own
    venue name and price — whether the served row is the fold's representative
    or one of its twins."""
    for stages in sections["awards"].values():
        for rows in stages.values():
            for r in rows:
                family = [(r["id"], r["leader"])] + list(zip(r["twin_ids"], r["twin_leaders"]))
                if row_id in {i for i, _ in family} and len(family) > 1:
                    out = []
                    for i, lt in family:
                        if i == row_id:
                            continue
                        n, pr = leader(lt)
                        out.append({"source": AWARD_ROW[i]["source"], "leader": n, "p": pr})
                    return out
    return []


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
            "outcome_count": d.get("outcome_count"),
            "also": served_also(d["id"]),
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
                # The price shown is the representative row's OWN venue price.
                # A folded twin keeps its own venue label and its own price; the
                # two are never blended or merged into one source list.
                also = []
                for tid, tl in zip(r["twin_ids"], r["twin_leaders"]):
                    tn, tp = leader(tl)
                    also.append({"source": AWARD_ROW[tid]["source"], "leader": tn, "p": tp})
                row = {
                    "id": r["id"], "label": r["label"], "leader": name, "p": p,
                    "sources": [AWARD_ROW[r["id"]]["source"]], "also": also,
                    "vol": vol_state(r["vol24"], r["id"]), "traded_ever": traded_ever(r["id"]),
                    "folded": len(r["twin_ids"]) > 0, "twins": r["twin_ids"],
                    "kind": "nomination" if stage != "winners" else "winner",
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
                          "sources": [r["source"]], "also": [],
                          "vol": vol_state(r["vol24"], r["id"]), "traded_ever": traded_ever(r["id"]),
                          "res": r["res"], "kind": "race"})
        out.append({"key": h, "title": h, "groups": [{"title": None, "rows": items}]})
    return out


oil = json.loads((EV / "served-feed-oil-bundle-2026-09-30T2039Z.json").read_text())
served["story:oil"] = oil

# Every awards row the prototype shows, and the twins the PROPOSED fold hides.
_shown = [r for sec in awards_rows() for g in sec["groups"] for r in g["rows"]]
counts = dict(sections["counts"])
counts["awards_proposed_fold"] = len(_shown)  # 133: assumes P2, not served
counts["awards_without_fold"] = len(_shown) + sum(len(r["twins"]) for r in _shown)  # 152
counts["vol_states"] = {
    k: sum(1 for r in _shown if r["vol"] == k) for k in ("traded", "zero24h", "unknown24h")
}
counts["awards_unknown24h_traded_ever"] = sum(1 for r in _shown if r["vol"] == "unknown24h" and r["traded_ever"])
counts["awards_unknown24h_no_volume_figure"] = sum(1 for r in _shown if r["vol"] == "unknown24h" and r["traded_ever"] is None)

data = {
    "counts": counts,
    "oil": {"members": served_members("story:oil")},
    "awards": {"members": served_members("story:major_entertainment_events"), "sections": awards_rows()},
    "ai": {"members": served_members("story:ai"), "sections": ai_rows()},
}
template = (HERE / "prototype.template.html").read_text()
(HERE / "prototype.html").write_text(template.replace("/*__DATA__*/null", json.dumps(data)))
print("wrote prototype.html", {k: len(v["sections"]) for k, v in data.items() if "sections" in v}, counts)
