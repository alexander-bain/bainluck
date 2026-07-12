// #999 L2-65: shared market/tournament → event-key helper.

import {
  cleanSlug,
  isWinnerMarketName,
  marketEventKey,
  combatCardKey,
  tournamentEventKey,
  eventPath,
  hubLabel,
  hubPath,
  conceptDisplayLabel,
  awardsEventKey,
  awardsCeremonyName,
} from "../../lib/eventKey";

describe("cleanSlug", () => {
  test("mirrors backend clean_slug", () => {
    expect(cleanSlug("2026 Women's Wimbledon Winner")).toBe("2026-women-s-wimbledon-winner");
    expect(cleanSlug("The Open Championship")).toBe("the-open-championship");
    expect(cleanSlug("  --Weird__Name!!  ")).toBe("weird-name");
    expect(cleanSlug(null)).toBe("");
  });
});

describe("isWinnerMarketName", () => {
  test("winner fields, not matchups", () => {
    expect(isWinnerMarketName("2026 Women's Wimbledon Winner")).toBe(true);
    expect(isWinnerMarketName("Wimbledon Men's Champion")).toBe(true);
    expect(isWinnerMarketName("Gauff vs Sabalenka")).toBe(false);
    expect(isWinnerMarketName("Alcaraz def. Sinner")).toBe(false);
    expect(isWinnerMarketName(null)).toBe(false);
  });
});

describe("marketEventKey", () => {
  test("tennis winner market → tennis event key", () => {
    expect(
      marketEventKey({ name: "2026 Women's Wimbledon Winner", llm_sport_category: "tennis" }),
    ).toBe("event:tennis:2026-women-s-wimbledon-winner");
  });
  test("null for non-adapter category, non-winner, or match markets", () => {
    expect(marketEventKey({ name: "The Open Winner", llm_sport_category: "golf" })).toBeNull(); // golf → server event_concept_key / tournament card path
    expect(marketEventKey({ name: "Gauff vs Sabalenka", llm_sport_category: "tennis" })).toBeNull();
    expect(marketEventKey({ name: "Fed Rate Decision", llm_sport_category: "economics" })).toBeNull();
  });
  test("L2-91: combat fight ticker → card concept (any category)", () => {
    expect(
      marketEventKey({ name: "McGregor vs. Holloway", external_id: "kalshi:KXUFCFIGHT-26JUL11MCGHOL", llm_sport_category: "mma" }),
    ).toBe("event:ufc:26jul11");
    expect(
      marketEventKey({ name: "Mason vs Bell", external_id: "KXBOXING-26JUL04MASONBELL", llm_sport_category: "boxing" }),
    ).toBe("event:boxing:26jul04");
  });
  test("L2-91: combat prop ticker → null (not a fight)", () => {
    expect(
      marketEventKey({ name: "Method of victory", external_id: "KXUFCMOV-26JUL11MCG", llm_sport_category: "mma" }),
    ).toBeNull();
  });
  test("L2-91: F1 GP winner → f1 event key, submarkets/non-GP → null", () => {
    expect(
      marketEventKey({ name: "British Grand Prix Winner", llm_sport_category: "motorsports" }),
    ).toBe("event:f1:british-grand-prix-winner");
    expect(
      marketEventKey({ name: "British Grand Prix Sprint Winner", llm_sport_category: "motorsports" }),
    ).toBeNull();
    expect(
      marketEventKey({ name: "Any Group Winner", llm_sport_category: "motorsports" }),
    ).toBeNull(); // no "grand prix" → miscategorization guard
  });
});

describe("combatCardKey (L2-91)", () => {
  test("date-token off a fight ticker; null for props / non-combat", () => {
    expect(combatCardKey({ external_id: "kalshi:KXUFCFIGHT-26JUL11MCGHOL" })).toBe("event:ufc:26jul11");
    expect(combatCardKey({ external_id: "KXBOXING-26JUL04MASONBELL" })).toBe("event:boxing:26jul04");
    expect(combatCardKey({ external_id: "KXUFCMOV-26JUL11MCG" })).toBeNull();
    expect(combatCardKey({ external_id: "KXNBA-CHAMP" })).toBeNull();
    expect(combatCardKey({})).toBeNull();
  });
});

describe("hub helpers + conceptDisplayLabel (L2-91)", () => {
  test("hubLabel / hubPath", () => {
    expect(hubLabel("mma")).toBe("MMA");
    expect(hubLabel("golf")).toBe("Golf");
    expect(hubLabel("nba")).toBeNull();
    expect(hubLabel(null)).toBeNull();
    expect(hubPath("mma")).toBe("/hub/mma");
  });
  test("conceptDisplayLabel: ceremony, fight card, winner-suffix stripped", () => {
    expect(conceptDisplayLabel("event:awards:oscars", "Best Picture")).toBe("The Oscars");
    expect(conceptDisplayLabel("event:ufc:26jul11", "McGregor vs Holloway")).toBe("the full fight card");
    expect(conceptDisplayLabel("event:f1:british-grand-prix-winner", "British Grand Prix Winner")).toBe("British Grand Prix");
    expect(conceptDisplayLabel(null, "Whatever")).toBeNull();
  });
});

describe("awardsEventKey (L2-88)", () => {
  test("ticker stem → ceremony key (mirrors backend derive_awards_concept)", () => {
    expect(awardsEventKey({ external_id: "KXOSCARPIC-27" })).toBe("event:awards:oscars");
    expect(awardsEventKey({ external_id: "kalshi:KXEMMYDSERIES-26SEP14" })).toBe("event:awards:emmys");
    expect(awardsEventKey({ external_id: "KXTONYAWARDS-26BM" })).toBe("event:awards:tonys");
    expect(awardsEventKey({ external_id: "KXGRAMAOTY-69" })).toBe("event:awards:grammys");
  });
  test("name fallback when no ticker", () => {
    expect(awardsEventKey({ name: "Oscar winner: Best Picture" })).toBe("event:awards:oscars");
    expect(awardsEventKey({ name: "Emmy Award for Drama Series" })).toBe("event:awards:emmys");
    expect(awardsEventKey({ name: "Tony Award for Best Play?" })).toBe("event:awards:tonys");
  });
  test("null for non-awards", () => {
    expect(awardsEventKey({ external_id: "KXPGATOUR-GESO26", name: "Scottish Open Winner" })).toBeNull();
    expect(awardsEventKey({ name: "2026 Men's Wimbledon Winner" })).toBeNull();
    expect(awardsEventKey({})).toBeNull();
  });
});

describe("awardsCeremonyName", () => {
  test("maps a ceremony key to its display name (edition-tolerant)", () => {
    expect(awardsCeremonyName("event:awards:oscars")).toBe("The Oscars");
    expect(awardsCeremonyName("event:awards:oscars-2027")).toBe("The Oscars");
    expect(awardsCeremonyName("event:awards:tonys")).toBe("The Tony Awards");
    expect(awardsCeremonyName("event:tennis:wimbledon")).toBeNull();
    expect(awardsCeremonyName(null)).toBeNull();
  });
});

describe("marketEventKey — awards branch (L2-88)", () => {
  test("an awards market links up to its ceremony page", () => {
    expect(
      marketEventKey({ name: "Oscar for Best Director?", external_id: "KXOSCARDIR-26", llm_sport_category: "entertainment" }),
    ).toBe("event:awards:oscars");
  });
});

describe("tournamentEventKey", () => {
  test("prefers an existing event key", () => {
    expect(tournamentEventKey({ key: "event:golf:the-open-championship" })).toBe(
      "event:golf:the-open-championship",
    );
  });
  test("uses slug, then name, then underscored key", () => {
    expect(tournamentEventKey({ key: "the_open", slug: "the-open-championship" })).toBe(
      "event:golf:the-open-championship",
    );
    expect(tournamentEventKey({ key: "the_open", name: "The Open Championship" })).toBe(
      "event:golf:the-open-championship",
    );
    expect(tournamentEventKey({ key: "the_open" })).toBe("event:golf:the-open");
  });
  test("null when nothing resolvable", () => {
    expect(tournamentEventKey({})).toBeNull();
  });
});

describe("eventPath", () => {
  test("single-encodes the key for the route", () => {
    expect(eventPath("event:golf:the-open-championship")).toBe(
      "/event/event%3Agolf%3Athe-open-championship",
    );
  });
});
