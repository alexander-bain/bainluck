/**
 * #6440 — the finished-game age rule exists in TWO runtimes, so it is two rules
 * the moment one of them is edited.
 *
 * Web ages a finished card out at 8h from the whistle (14h for a marquee final
 * Discover kept on purpose); the backend composes `mode=sports`' first page
 * KNOWING the client deletes those rows (`client_deletes_finished_card`, pinned
 * to this file by `backend/tests/test_client_deletion_mirror_3836.py`). The
 * phone was the third implementation and had two different answers — 8h from
 * KICKOFF on Discover, no age term at all on the Sports tab — so on 2026-09-15
 * it rendered four finals aged 17.3–20.2h that bainluck.com/sports did not have
 * in its document.
 *
 * Same mechanism as `settledQuoteParity`: a jest test READS the other runtime's
 * source and asserts the values match, because only jest can see both files.
 * The Swift side carries its own behavioural suite
 * (`ios/Bain Luck/BainLuckTests/SportsFinishedAgeOut6440Tests.swift`); this is
 * the part neither suite can check alone.
 */

import { readFileSync } from "fs";
import { join } from "path";

import {
  COMPLETED_EVENT_MAX_AGE_HOURS,
  MARQUEE_FINAL_MAX_AGE_HOURS,
  finishedEventAgeAnchor,
  finishedEventMaxAgeHours,
} from "@/lib/discover/feedFreshness";

const SWIFT = readFileSync(
  join(__dirname, "../../../ios/Bain Luck/Bain Luck/Models/FeedModels.swift"),
  "utf8",
);

/** `static let name: Double = 8` → 8. */
function swiftDouble(name: string): number {
  const m = SWIFT.match(new RegExp(`static let ${name}:\\s*Double\\s*=\\s*([0-9.]+)`));
  if (!m) throw new Error(`FeedModels.swift has no Double constant named ${name}`);
  return Number(m[1]);
}

/** The body of `static func name(...) -> T { ... }` up to the closing brace column. */
function swiftFunc(name: string): string {
  const start = SWIFT.indexOf(`static func ${name}(`);
  if (start < 0) throw new Error(`FeedModels.swift has no function named ${name}`);
  const end = SWIFT.indexOf("\n    }", start);
  return SWIFT.slice(start, end);
}

describe("finished-card age parity: TypeScript ↔ Swift", () => {
  test("the ordinary window is one number", () => {
    expect(swiftDouble("completedEventMaxAgeHours")).toBe(COMPLETED_EVENT_MAX_AGE_HOURS);
  });

  test("the marquee-final window is one number, and it is the longer one", () => {
    expect(swiftDouble("marqueeFinalMaxAgeHours")).toBe(MARQUEE_FINAL_MAX_AGE_HOURS);
    expect(MARQUEE_FINAL_MAX_AGE_HOURS).toBeGreaterThan(COMPLETED_EVENT_MAX_AGE_HOURS);
  });

  test("both runtimes age from the whistle, and fall back to the kickoff", () => {
    // Field order is the rule: `ended_at` first, `commence_time` only when the
    // payload carries no whistle. A Swift anchor that read `commenceTime` first
    // would charge every finished card for its own duration again (#4776).
    const anchor = swiftFunc("finishedEventAgeAnchor");
    const ended = anchor.indexOf("endedAt");
    const commence = anchor.indexOf("commenceTime");
    expect(ended).toBeGreaterThan(-1);
    expect(commence).toBeGreaterThan(ended);

    expect(
      finishedEventAgeAnchor({
        ended_at: "2026-09-15T04:47:26.482663+00:00",
        commence_time: "2026-09-15T00:40:00+00:00",
      } as never),
    ).toBe("2026-09-15T04:47:26.482663+00:00");
    expect(
      finishedEventAgeAnchor({ commence_time: "2026-09-15T00:40:00+00:00" } as never),
    ).toBe("2026-09-15T00:40:00+00:00");
  });

  test("both runtimes take the long window on `true` and nothing looser", () => {
    // Absent and `false` are the ordinary 8 hours on both sides: an absent flag
    // means the payload came from a surface that does not select marquee finals
    // (`mode=sports` is one), and unknown provenance is not evidence.
    expect(finishedEventMaxAgeHours({ discover_marquee_final: true } as never)).toBe(
      MARQUEE_FINAL_MAX_AGE_HOURS,
    );
    for (const flag of [false, undefined, null, "true", 1]) {
      expect(
        finishedEventMaxAgeHours({ discover_marquee_final: flag } as never),
      ).toBe(COMPLETED_EVENT_MAX_AGE_HOURS);
    }
    expect(swiftFunc("finishedEventMaxAgeHours")).toContain(
      "discoverMarqueeFinal == true",
    );
  });

  test("both runtimes render the card that is exactly at the threshold", () => {
    // Strict `>` on both sides. `>=` would delete a card web keeps, and the
    // disagreement would only ever be visible for one second per card.
    const ts = readFileSync(
      join(__dirname, "../../lib/discover/feedFreshness.ts"),
      "utf8",
    );
    expect(ts).toContain("hoursAgo > finishedEventMaxAgeHours(ed)");
    expect(swiftFunc("finishedEventIsExpired")).toContain(
      "> finishedEventMaxAgeHours(e) * 3600",
    );
  });
});
