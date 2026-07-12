// #999 L2-65: shared market/tournament → event-key helper.

import {
  cleanSlug,
  isWinnerMarketName,
  marketEventKey,
  tournamentEventKey,
  eventPath,
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
    expect(marketEventKey({ name: "The Open Winner", llm_sport_category: "golf" })).toBeNull(); // golf → tournament card path
    expect(marketEventKey({ name: "Gauff vs Sabalenka", llm_sport_category: "tennis" })).toBeNull();
    expect(marketEventKey({ name: "Fed Rate Decision", llm_sport_category: "economics" })).toBeNull();
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
