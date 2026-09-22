/**
 * #7992 — A HOCKEY CHART'S `OT` MARKER STOOD WHERE OVERTIME ENDED.
 *
 * `normalizePeriodLabel` computes `isEnd` from the `^end\s+(?:of\s+)?` prefix and
 * honoured it in three branches — quarter, period, half — and dropped it in the
 * overtime branch. So `"End of OT"` and `"Overtime"` both normalized to `OT`:
 * the same label for the two opposite edges of the period, where every other
 * period type on the strip distinguishes them with a `/` prefix.
 *
 * ═══ WHY IT SURVIVED, AND WHERE THE SILENCE BREAKS ═══
 *
 * `derivePeriodBoundaries` dedups by EXACT label, first-seen wins, so on a game
 * carrying both edges the end marker is absorbed by the start and nothing is
 * visible. That is a fact about COLLISIONS, and it says nothing about the
 * singleton case — which is where the wrong survivor wins by default.
 *
 * `/events/15312790` is the singleton. MEASURED on its real payload: 35
 * `period_markers`, and the ONLY overtime row in ANY of its three channels is
 * `End of OT` at 01:57:49Z — there is no start-of-overtime row at all. So the
 * absorbed duplicate was the only `OT` the chart had, standing at the moment
 * overtime FINISHED and reading like every other marker beside it: the period
 * began here.
 *
 * ═══ REACH, MEASURED BEFORE BUILDING ═══
 *
 * ux/1433's 70-event / 7-sport corpus, real function, before vs after
 * (`artifacts/ux-1435/reach-7992-{BEFORE,AFTER}.json`):
 *
 *   6 `End of OT` rows — 3 NFL, 3 NHL — across exactly 2 events
 *   1 of 70 charts changes:  P1 /P1 P2 P3 [OT -> /OT]
 *   LABELS GAINED: NONE
 *
 * The NFL game (`14780544`) carries both edges and does NOT gain a marker: its
 * `period_markers` supplies the real `Overtime` start, its `End of OT` lives
 * only in the fallback channels, and `fillMissingPeriods` refuses it because
 * `periodIdentity("/OT") === "OT"` is already claimed. That is #7917's helper
 * doing exactly the job it was built for, and it is pinned below — the issue
 * asked whether the label packer would have room for a gained `/OT`, and the
 * answer is that nothing gains one.
 */
import { readFileSync } from "fs";
import { join } from "path";
import { derivePeriodBoundaries, normalizePeriodLabel } from "@/lib/periodMarkers";

/**
 * The real payload of `/events/15312790`, trimmed to the period fields on its
 * three populated channels — timestamps and period strings verbatim. TRACKED,
 * because a test that reads an untracked capture path does not fail on CI, it
 * fails to START.
 */
const NHL = JSON.parse(
  readFileSync(
    join(__dirname, "../fixtures/periodMarkersOvertimeEnd.15312790.nhl-ot.json"),
    "utf8",
  ),
) as {
  sport: string;
  period_markers: Array<{ timestamp: string; period: string }>;
  espn_history: Array<{ timestamp: string; period: string }>;
  win_prob_history: Record<string, Array<{ timestamp: string; game_state: { period: string } }>>;
};

const nhlBoundaries = () =>
  derivePeriodBoundaries(
    NHL.espn_history as never,
    NHL.win_prob_history as never,
    undefined,
    NHL.period_markers,
    NHL.sport,
  );

describe("#7992 — the overtime branch honours `isEnd` like every other period type", () => {
  it("THE DEFECT: the specimen's only overtime row is an END, and it no longer reads as a start", () => {
    // The fixture's own shape is the premise of the whole issue, so it is
    // asserted rather than assumed: if a future capture gains a start-of-OT row
    // this specimen stops being the singleton case and this test should say so.
    const otRows = NHL.period_markers.filter((m) => /overtime|\bot\b/i.test(m.period));
    expect(otRows.map((m) => m.period)).toEqual(["End of OT"]);

    const labels = nhlBoundaries().map((b) => b.label);
    expect(labels).toEqual(["P1", "/P1", "P2", "P3", "/OT"]);
    // The convicting assertion, stated as the reader's question: the strip must
    // not carry a bare `OT` standing at the moment overtime ended.
    expect(labels).not.toContain("OT");
  });

  it("the end marker keeps overtime's own evidenced time — this relabels, it does not move", () => {
    const ot = nhlBoundaries().find((b) => b.label === "/OT");
    expect(ot?.timestamp).toBe("2026-09-22T01:57:49.933346+00:00");
    // And it stays last: a relabel must not reorder the strip.
    expect(nhlBoundaries().at(-1)?.label).toBe("/OT");
  });

  it("REACH: a game with a real overtime START is untouched and gains nothing", () => {
    // `14780544`'s shape, reduced to the channels that decide it: the curated
    // `period_markers` names the start, the fallback carries the end. This is
    // the arm that answers the issue's label-packer question.
    const markers = [
      { timestamp: "2026-09-08T01:00:00Z", period: "4th Quarter" },
      { timestamp: "2026-09-08T02:00:00Z", period: "Overtime" },
    ];
    const fallback = {
      espn: [
        { timestamp: "2026-09-08T02:00:30Z", game_state: { period: "Overtime" } },
        { timestamp: "2026-09-08T02:10:00Z", game_state: { period: "End of OT" } },
      ],
    };
    const labels = derivePeriodBoundaries(
      undefined,
      fallback as never,
      undefined,
      markers,
      "americanfootball_nfl",
    ).map((b) => b.label);

    expect(labels).toEqual(["Q4", "OT"]);
    expect(labels).not.toContain("/OT");
  });

  describe("the label rule itself", () => {
    it("distinguishes the two edges of overtime", () => {
      expect(normalizePeriodLabel("Overtime")).toBe("OT");
      expect(normalizePeriodLabel("OT")).toBe("OT");
      expect(normalizePeriodLabel("End of OT")).toBe("/OT");
      expect(normalizePeriodLabel("End of Overtime")).toBe("/OT");
      expect(normalizePeriodLabel("End OT")).toBe("/OT");
    });

    it("reads the same way the three branches that always honoured `isEnd` do", () => {
      // The consistency this ship is really about: one grammar for every period
      // type, so a reader learns the `/` once.
      expect(normalizePeriodLabel("End of 1st Quarter")).toBe("/Q1");
      expect(normalizePeriodLabel("End of 1st Period")).toBe("/P1");
      expect(normalizePeriodLabel("End of 1st Half")).toBe("/1H");
      expect(normalizePeriodLabel("End of OT")).toBe("/OT");
    });

    it("NUMBERED overtimes, both spellings, agree — a zero-reach consistency arm", () => {
      // Zero occurrences in the 70-event corpus, fixed anyway: the reach of a
      // FORM is not the reach of the RULE. #7982's `"End 8"` arm is the
      // precedent — leaving one spelling behind is how two spellings of one
      // marker come to disagree, which was that ship's whole finding.
      expect(normalizePeriodLabel("2nd Overtime")).toBe("OT2");
      expect(normalizePeriodLabel("End of 2nd Overtime")).toBe("/OT2");
      expect(normalizePeriodLabel("OT2")).toBe("OT2");
      expect(normalizePeriodLabel("End of OT2")).toBe("/OT2");
    });

    it("still uppercases a lowercase already-short overtime", () => {
      // `OT\d?` was removed from the "already short" alternation because the
      // overtime branch now consumes every spelling and a live-looking branch
      // that can never run is what misled two readers in #7982. This pins the
      // one behaviour that alternation was still buying.
      expect(normalizePeriodLabel("ot3")).toBe("OT3");
      expect(normalizePeriodLabel("ot")).toBe("OT");
    });

    it("does not invent an end marker where there is no end prefix", () => {
      // The `/` must be earned by the word, not by the shape.
      expect(normalizePeriodLabel("Start of OT")).toBe("OT");
      expect(normalizePeriodLabel("5:00 - OT")).toBe("OT");
      expect(normalizePeriodLabel("10:00 - OT")).toBe("OT");
    });
  });
});
