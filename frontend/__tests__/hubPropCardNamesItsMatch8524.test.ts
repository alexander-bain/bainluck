/**
 * #8524 — `/hub/esports` prop cards read "Games Total: O/U 4.5" with no match.
 *
 * The backend now serves `event_title` (the venue's match name) ONLY on a card
 * whose own name names no match (`backend/app/utils/hub_prop_matchup.py`, guarded
 * by `test_hub_prop_card_names_its_match_8524.py`). This pins the other half: the
 * hub card draws it in the eyebrow, ahead of the competition, and draws the
 * eyebrow not at all when neither is served.
 */
import fs from "fs";
import path from "path";

const page = fs.readFileSync(
  path.join(__dirname, "..", "app", "hub", "[competition]", "page.tsx"),
  "utf8",
);

describe("#8524 hub prop card eyebrow", () => {
  it("renders the served match title, falling back to the competition", () => {
    expect(page).toContain("{(market.event_title || market.competition) && (");
    expect(page).toContain("{market.event_title || market.competition}");
  });

  it("no longer gates the eyebrow on the competition alone", () => {
    expect(page).not.toContain("{market.competition && (");
  });
});
