"""#7844 half two — how many SERVED BOARDS lose their podium.

Replays the banked served edition (`/api/feed?limit=200`, 2026-09-21 17:40Z,
`artifacts/d387-7844/feed-200-1740Z.json`) against the banked exclusivity map
(`excl-1740Z.json`, the `mutually_exclusive` column for all 71 futures markets
in that edition) and reproduces, in order:

  1. `_card_field_is_a_race` — the route's own resolution: flag is False AND the
     PRINTED percents (`top_outcomes[].rendered_percent`, the same annotations
     the copy is decided on) sum past 100.
  2. `DiscoverCard.tsx`'s fork — `top_outcomes.length >= 4` sends the card to
     `ComparisonCard`, which has no rank column and no remainder row, so those
     cards are out of the board arm's reach whatever their flag says.
  3. `FuturesCard.tsx`'s gate — `suggested_format === "outcome_distribution"`
     AND the priced `distribution_outcomes` clearing `distributionMinRows`.

⚠️ THIS IS A REPLAY OF A PAYLOAD, NOT A CALL OF THE FUNCTIONS THAT BUILT IT.
It can say how many cards the change reaches and which ones; it cannot prove the
rendered markup, which is what the jest guard is for. The caption arm (half one)
reached 8 of the 20 non-exclusive cards; the board arm is a different gate and
is measured here rather than inherited from that number.
"""

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
BANK = HERE.parent / "d387-7844"

feed = json.loads((BANK / "feed-200-1740Z.json").read_text())
items = feed["items"] if isinstance(feed, dict) and "items" in feed else feed

excl_doc = json.loads((BANK / "excl-1740Z.json").read_text())
cols = excl_doc["columns"]
EXCLUSIVE = {
    row[cols.index("id")]: row[cols.index("mutually_exclusive")]
    for row in excl_doc["rows"]
}


def prints_a_percent(probability):
    """`lib/discover/leaderOrder.printsAPercent`, as the component applies it."""
    return isinstance(probability, (int, float)) and probability > 0


def card_field_is_a_race(market_id, top_outcomes):
    flag = EXCLUSIVE.get(market_id)
    if flag is not False:
        return True
    printed = [
        int(o["rendered_percent"])
        for o in top_outcomes
        if o.get("rendered_percent") is not None
    ]
    if len(printed) < 2:
        return True
    return sum(printed) <= 100


futures = [i for i in items if i.get("type") == "futures"]
non_exclusive = []
draws_a_board = []
loses_the_podium = []
keeps_the_podium = []

for item in futures:
    data = item["data"]
    dc = data.get("discover_card") or {}
    top = data.get("top_outcomes") or []
    all_rows = dc.get("distribution_outcomes") or []
    priced = [r for r in all_rows if prints_a_percent(r.get("probability"))]

    if EXCLUSIVE.get(data["id"]) is False:
        non_exclusive.append(data["id"])

    # The wrapper's fork, then the leaf's gate.
    reaches_comparison_card = len(top) >= 4
    dropped_below_the_bar = len(all_rows) >= 4 and len(priced) < 4
    min_rows = 2 if (dc.get("ladder_treatment_refused") or dropped_below_the_bar) else 4
    is_a_board = (
        not reaches_comparison_card
        and dc.get("suggested_format") == "outcome_distribution"
        and len(priced) >= min_rows
    )
    if not is_a_board:
        continue

    draws_a_board.append(data["id"])
    shown = sorted(priced, key=lambda r: r.get("probability") or 0, reverse=True)[:4]
    remainder = dc.get("remaining_outcome_count", 0) + max(0, len(all_rows) - len(shown))
    row = {
        "id": data["id"],
        "name": data["name"],
        "printed_sum": sum(
            int(o["rendered_percent"])
            for o in top
            if o.get("rendered_percent") is not None
        ),
        "rows_drawn": len(shown),
        "remainder_row": remainder,
        "mutually_exclusive": EXCLUSIVE.get(data["id"]),
    }
    (keeps_the_podium if card_field_is_a_race(data["id"], top) else loses_the_podium).append(row)

print(f"futures cards in the edition ......... {len(futures)}")
print(f"  flagged NOT mutually exclusive ..... {len(non_exclusive)}")
print(f"  drawn by FuturesCard as a board .... {len(draws_a_board)}")
print(f"  BOARD ARM — lose the podium ........ {len(loses_the_podium)}")
print(f"  controls — keep it ................. {len(keeps_the_podium)}")
print()
for row in sorted(loses_the_podium, key=lambda r: -r["printed_sum"]):
    tail = f"{row['remainder_row']} more" if row["remainder_row"] else "no remainder row"
    print(f"  {row['printed_sum']:>4}%  {row['name'][:72]:<72}  {tail}")

(HERE / "board_arm_reach.json").write_text(
    json.dumps(
        {
            "edition": "feed-200-1740Z",
            "futures": len(futures),
            "non_exclusive": len(non_exclusive),
            "boards": len(draws_a_board),
            "loses_the_podium": loses_the_podium,
            "keeps_the_podium": keeps_the_podium,
        },
        indent=2,
    )
)
