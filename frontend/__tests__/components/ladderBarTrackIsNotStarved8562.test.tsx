/**
 * #8562 — a ladder card with a mover drew NO bars, and its leading rung drew a short one.
 *
 * Measured in the production DOM on web `16d8f734`, "How high will Meta (META) close on
 * September 25?" (id 62196137, Discover feed index 21):
 *
 *     1280: row 254 = label 107/114/114 + move 67 + track 0/0/0   + pct 40 + gaps
 *      390: row 300 = label 128/135/135 + move 67 + track 13/22/22 + pct 40 + gaps
 *
 * Two causes. (1) The wide label slot was a flat 45% whatever it held — 114px for "$730" —
 * and since #5659 the badge slot reads "▲56.0 pts", so nothing was left for the `flex-1`
 * track. (2) The leading rung is inset `px-2 -mx-2`; at `w-full` that padding came out of its
 * content box, so the 93% rung's track was 16px shorter than the 92% rung's below it.
 *
 * `testEnvironment: node` — no pixels here; these pin the structure the pixels follow from.
 */
import { renderToStaticMarkup } from "react-dom/server";
import QuantityGroup, { type QuantityRung } from "@/components/QuantityGroup";

/** The Meta card as served: three dollar rungs, the leader highlighted, one mover. */
const meta: QuantityRung[] = [
  { key: "730", label: "$730", probability: 0.93, value: 730, highlighted: true },
  { key: "740", label: "$740", probability: 0.92, value: 740 },
  { key: "750", label: "$750", probability: 0.91, value: 750, movement: 0.56 },
];

const widths = (html: string) => [...html.matchAll(/style="width:(clamp[^"]*)"/g)].map((m) => m[1]);
const rowClasses = (html: string) =>
  [...html.matchAll(/<div class="(flex items-center gap-3 [^"]*)" aria-label=/g)].map((m) => m[1]);

describe("#8562 the wide label slot is sized from its ink, capped at 45%", () => {
  test("a short dollar ladder reserves what '$730' needs, not 45% of the card", () => {
    const html = renderToStaticMarkup(<QuantityGroup bare compact wideLabels sort={false} rungs={meta} />);
    expect(widths(html)).toEqual(Array(3).fill("clamp(2.75rem, calc(4ch + 0.75rem), 45%)"));
    expect(html).not.toContain("w-[45%]");
    // the mover is still there — the fix makes room beside it, it does not drop it
    expect(html).toContain("▲56.0 pts");
  });

  test("ONE width per ladder: every rung, leader included, carries the same label width", () => {
    const html = renderToStaticMarkup(
      <QuantityGroup
        wideLabels
        sort={false}
        rungs={[
          { key: "a", label: "$7", probability: 0.9, value: 7, highlighted: true },
          { key: "b", label: "$1,250", probability: 0.4, value: 1250 },
        ]}
      />,
    );
    // sized by the LONGEST label, not per row (#1574 c)
    expect(widths(html)).toEqual(Array(2).fill("clamp(2.75rem, calc(6ch + 0.75rem), 45%)"));
  });

  test("CONTROL: a long label still hits the 45% cap — the slot can never grow past it", () => {
    const html = renderToStaticMarkup(
      <QuantityGroup
        wideLabels
        rungs={[{ key: "a", label: "Above 20 million short tons of coal", probability: 0.5, value: 1 }]}
      />,
    );
    const [w] = widths(html);
    expect(w).toMatch(/, 45%\)$/);
  });
});

describe("#8562 the leading rung's track is as long as its siblings'", () => {
  test("the inset (highlighted) row is widened by the 1rem its negative margins give back", () => {
    const rows = rowClasses(renderToStaticMarkup(<QuantityGroup bare compact wideLabels sort={false} rungs={meta} />));
    expect(rows).toHaveLength(3);
    expect(rows[0]).toContain("px-2 -mx-2");
    expect(rows[0]).toContain("w-[calc(100%+1rem)]");
    expect(rows[0]).not.toMatch(/\bw-full\b/);
    for (const r of rows.slice(1)) {
      expect(r).toMatch(/\bw-full\b/);
      expect(r).not.toContain("-mx-2");
    }
  });

  test("a graded rung is inset the same way and gets the same compensation", () => {
    const rows = rowClasses(
      renderToStaticMarkup(
        <QuantityGroup
          sort={false}
          rungs={[
            { key: "w", label: "≥ 60", probability: 1, value: 60, verdict: "won" },
            { key: "l", label: "≥ 95", probability: 0, value: 95, verdict: "lost" },
          ]}
        />,
      ),
    );
    for (const r of rows) {
      expect(r).toContain("-mx-2");
      expect(r).toContain("w-[calc(100%+1rem)]");
    }
  });
});
