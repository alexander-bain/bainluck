/**
 * UX-P248 — "for you" says something TRUE about this reader and this card.
 *
 * Alex, 2026-09-01 (D-D): personalization made visible.
 *
 * 🔴 THE DEFECT THIS SUITE EXISTS TO PREVENT is the one-line version of the
 * feature: `{item.personalized && <ForYou/>}`. The payload's `personalized`
 * flag is `bool(reasons)` and `reasons` counts PENALTIES, so that version puts
 * "for you" on cards the reader's own swipes pushed DOWN. Half the assertions
 * below are that case, from a different angle each time, because it is the
 * only way this feature can be actively worse than not shipping it.
 */

import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import {
  FOR_YOU_UPRANK_IDS,
  forYouCue,
  parsePersonalizationReason,
} from "@/lib/discover/forYouCue";
import { ForYouChip } from "@/components/discover/shared";

type Item = Parameters<typeof forYouCue>[0];

const boosted = (reasons: string[], multiplier = 1.35): Item => ({
  personalized: true,
  multiplier,
  personalization_reasons: reasons,
});

describe("a boost the reader can be told about", () => {
  it("names the class, not a bare 'for you'", () => {
    expect(forYouCue(boosted(["your_team:0.35"]))).toEqual({
      label: "One of your teams",
      reasonId: "your_team",
    });
  });

  it("prefers the most SPECIFIC true statement when several apply", () => {
    // A pinned card, for a team you follow, in a sport you follow. All three
    // are true; "you pinned this" is the one the reader can act on.
    const cue = forYouCue(boosted(["sport_boost:0.20", "your_team:0.35", "pinned:0.50"]));
    expect(cue?.reasonId).toBe("pinned");
  });

  it("reads the futures-side token spellings too", () => {
    expect(forYouCue(boosted(["your_team_futures:0.30"]))?.label).toBe("One of your teams");
    expect(forYouCue(boosted(["alma_mater_futures:0.25"]))?.label).toBe("Your alma mater");
  });
});

describe("🔴 a DOWNRANKED card is never labelled 'for you'", () => {
  it("no cue on a card personalized only by penalties", () => {
    // `personalized: true` and a multiplier BELOW 1 — the exact shape the
    // naive implementation gets wrong.
    expect(
      forYouCue({
        personalized: true,
        multiplier: 0.7,
        personalization_reasons: ["sport_nah:-0.30"],
      })
    ).toBeNull();
  });

  it.each([
    ["sport_suppress:-0.50"],
    ["minor_pro:-0.20"],
    ["discover_dismiss:-0.15"],
    ["discover_feature_dislike:category:golf:-0.10"],
  ])("no cue for penalty reason %s", (reason) => {
    expect(
      forYouCue({ personalized: true, multiplier: 0.8, personalization_reasons: [reason] })
    ).toBeNull();
  });

  it("🔴 NO CUE WHEN A REAL BOOST IS OUTWEIGHED — the boost is true and the sentence is not", () => {
    // `your_team` fires, so a vocabulary-only check would show the badge. The
    // card still finished lower than it started, and "we put this in front of
    // you" is false about a card we pushed down.
    const cue = forYouCue({
      personalized: true,
      multiplier: 0.9,
      personalization_reasons: ["your_team:0.35", "sport_suppress:-0.50"],
    });
    expect(cue).toBeNull();
  });

  it("no cue at a multiplier of exactly 1 — nothing moved", () => {
    expect(forYouCue(boosted(["your_team:0.35"], 1))).toBeNull();
  });

  it("no cue when the multiplier is ABSENT — an absent number is not a boost", () => {
    expect(
      forYouCue({ personalized: true, personalization_reasons: ["your_team:0.35"] })
    ).toBeNull();
  });

  it("no cue for an anonymous reader", () => {
    expect(forYouCue({})).toBeNull();
    expect(forYouCue({ personalized: false, multiplier: 1.4 })).toBeNull();
  });

  it("no cue for an uprank we cannot phrase — an unknown token is silent, not wrong", () => {
    expect(forYouCue(boosted(["brand_new_backend_signal:0.40"]))).toBeNull();
  });
});

describe("the reason parser", () => {
  it("takes the value from the LAST segment, not the second", () => {
    // `discover_feature_interest:<token>:<value>` — and the token itself has a
    // colon in it. Reading `parts[1]` yields NaN for the feature reasons and
    // for nothing else, which is why it would survive a casual test.
    expect(parsePersonalizationReason("discover_feature_interest:category:golf:0.12")).toEqual({
      id: "discover_feature_interest",
      value: 0.12,
    });
    expect(parsePersonalizationReason("your_team:0.35")).toEqual({
      id: "your_team",
      value: 0.35,
    });
  });

  it("rejects a token with no value rather than reading it as zero", () => {
    expect(parsePersonalizationReason("your_team")).toBeNull();
    expect(parsePersonalizationReason("your_team:not_a_number")).toBeNull();
  });

  it("a feature-interest reason still produces its cue end to end", () => {
    expect(
      forYouCue(boosted(["discover_feature_interest:category:golf:0.12"]))?.reasonId
    ).toBe("discover_feature_interest");
  });
});

/**
 * 🔴 THE GUARD THAT KEEPS THIS HONEST ACROSS THE STACK.
 *
 * Every id in the vocabulary is a string the BACKEND emits. A rename in
 * `personalization.py` would otherwise retire a cue in complete silence — the
 * feature would keep working, just never for alma maters again, and no test in
 * either language would notice. So the source of truth is read.
 */
describe("the vocabulary matches the reasons the backend actually emits", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "..", "..", "..", "backend", "app", "utils", "personalization.py"),
    "utf8"
  );

  it("the source really is the personalization module (not vacuous)", () => {
    expect(source).toContain("class PersonalizationResult");
    expect(source).toContain("reasons.append");
  });

  it.each(FOR_YOU_UPRANK_IDS.map((id) => [id]))(
    "backend still emits the reason token %s",
    (id) => {
      // The tokens are built as f-strings: `f"your_team:{team_bonus:.2f}"`, and
      // the two category/feature ones as `f"discover_interest:{value:.2f}"`.
      expect(source.includes(`"${id}:`)).toBe(true);
    }
  );
});

describe("the chip renders what the decision returned", () => {
  it("renders nothing at all when there is no cue — no empty element", () => {
    // ⚠️ Asserting "no visible text" would pass on an empty <span> that still
    // takes layout and still carries the test id. The markup has to be empty.
    expect(renderToStaticMarkup(<ForYouChip cue={null} />)).toBe("");
  });

  it("prints the label and carries the reason for analytics", () => {
    const html = renderToStaticMarkup(
      <ForYouChip cue={{ label: "One of your teams", reasonId: "your_team" }} />
    );
    expect(html).toContain('data-testid="for-you-cue"');
    expect(html).toContain('data-for-you-reason="your_team"');
    expect(html).toContain("In your feed because: one of your teams");
    expect(html.replace(/<[^>]*>/g, "").trim()).toBe("One of your teams");
  });

  it("the on-image skin is a different skin, not a different sentence", () => {
    const plain = renderToStaticMarkup(
      <ForYouChip cue={{ label: "Your alma mater", reasonId: "alma_mater" }} />
    );
    const onImage = renderToStaticMarkup(
      <ForYouChip cue={{ label: "Your alma mater", reasonId: "alma_mater" }} tone="onImage" />
    );
    const text = (h: string) => h.replace(/<[^>]*>/g, "").trim();
    expect(text(plain)).toBe(text(onImage));
    expect(onImage).toContain("text-white/90");
    expect(plain).not.toContain("text-white/90");
  });
});
