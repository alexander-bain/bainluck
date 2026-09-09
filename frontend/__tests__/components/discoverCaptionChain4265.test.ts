import fs from "fs";
import path from "path";

import { feedContextSnippet } from "../../components/discover/utils";

/**
 * #4265 — web's half of the futures caption chain, graded against the record.
 *
 * The two clients build a card's caption from the same four served strings and
 * used to resolve them differently. They cannot be compared inside one process,
 * so they are compared against a language-neutral record: this file asserts the
 * TypeScript chain reproduces every row of
 * `fixtures/discover/caption-chain-record-2026-09-09.json`, and
 * `BainLuckTests/DiscoverCaptionParityTests.swift` asserts the Swift chain
 * reproduces the same rows. (Same construction as the CAL-P043 calibration
 * record — see `calibrationSurfaceParity.contract.test.js`.)
 *
 * The record is READ here rather than duplicated, because Node can read it.
 * Swift cannot do so host-independently, so its copy is a literal table and
 * `discoverCaptionChainParity.contract.test.js` holds that copy to this file.
 */

type Row = {
  name: string;
  note?: string;
  context_summary: string | null;
  headline: string | null;
  reason: string | null;
  hook_description: string | null;
  expected: string;
};

const RECORD_PATH = path.join(
  __dirname,
  "../../../fixtures/discover/caption-chain-record-2026-09-09.json",
);

const record = JSON.parse(fs.readFileSync(RECORD_PATH, "utf8")) as {
  rows: Row[];
};

const asItem = (row: Row) => ({
  type: "futures" as const,
  context_summary: row.context_summary,
  headline: row.headline,
  reason: row.reason,
  data: { hook_description: row.hook_description },
});

describe("#4265 futures caption chain — web reproduces the shared record", () => {
  test("the record is present and has not been silently emptied", () => {
    // A parity suite that iterates zero rows passes for the wrong reason
    // (gotcha: an empty-render rig reads as a clean diff). Pin the count.
    expect(record.rows.length).toBe(12);
    expect(record.rows.filter((r) => r.name.startsWith("prod-")).length).toBe(5);
  });

  test.each(record.rows.map((r) => [r.name, r] as const))(
    "%s",
    (_name, row) => {
      expect(feedContextSnippet(asItem(row) as never)).toBe(row.expected);
    },
  );

  test("the three cards that were blank in the app are captioned here too", () => {
    // Named separately from the table so the reader-visible claim of #4265 has
    // an assertion of its own rather than living inside a parametrised loop.
    const blanks = record.rows.filter((r) =>
      r.name.endsWith("-blank-in-app"),
    );
    expect(blanks.length).toBe(3);
    for (const row of blanks) {
      expect(feedContextSnippet(asItem(row) as never)).toMatch(
        /off its opening price/i,
      );
    }
  });

  test("a settled EVENT card keeps UX-P045's order — this ship is futures-only", () => {
    // The other direction. #4265 changes the futures branch; the settled-event
    // promotion of `reason` above `headline` must survive untouched, or five of
    // fifteen finished games go back to reading "Line moving" hours after
    // full time.
    const settled = {
      type: "event" as const,
      context_summary: null,
      headline: "Line moving",
      reason: "San Diego Padres odds shifted 49% during the game",
      data: { status: "completed" },
    };
    expect(feedContextSnippet(settled as never)).toBe(
      "San Diego Padres odds shifted 49% during the game",
    );
  });
});
