/**
 * #8562, second half — a date ladder with a mover still drew no bars after the
 * wide slot was sized from its ink.
 *
 * Measured in the production DOM on web `2ae5c500ad` (the first half live),
 * Discover at 1280, where a grid card's row is 254px:
 *
 *     "Trump publicly insults Warsh?"   December 31 · ▲22.0 pts · track 11px · 43%  (fill 5px)
 *     "Astra removed from public access?" October 31 · ▲3.4 pts  · track  9px · 7%
 *     "How high will Google (GOOGL)…"   $320        · ▼4.4 pts  · track 73px · 90%  (fixed)
 *
 * A prose label cannot shrink like "$320" did, so a ladder whose label and
 * badge cannot share the row with a bar prints the badge UNDER the label and
 * drops the badge column. Decided per ladder, so one track width per ladder
 * (#1574 c) still holds.
 *
 * `testEnvironment: node` — these pin the structure the pixels follow from.
 */
import { renderToStaticMarkup } from "react-dom/server";
import QuantityGroup, { type QuantityRung } from "@/components/QuantityGroup";

/** The Warsh card as served (Discover index 47). */
const warsh: QuantityRung[] = [
  { key: "oct", label: "October 31", probability: 0.14, value: 1, movement: 0.045 },
  { key: "nov", label: "November 30", probability: 0.16, value: 2 },
  { key: "dec", label: "December 31", probability: 0.43, value: 3, movement: 0.22, highlighted: true },
];

/** The Google week card as served (Discover index 83) — the first half's specimen. */
const google: QuantityRung[] = [
  { key: "320", label: "$320", probability: 0.9, value: 320, movement: -0.044, highlighted: true },
  { key: "325", label: "$325", probability: 0.9, value: 325, movement: -0.075 },
  { key: "330", label: "$330", probability: 0.86, value: 330, movement: -0.078 },
  { key: "340", label: "$340", probability: 0.72, value: 340 },
];

const render = (rungs: QuantityRung[]) =>
  renderToStaticMarkup(<QuantityGroup bare compact wideLabels sort={false} maxRungs={8} rungs={rungs} />);
const slotWidths = (html: string) => [...html.matchAll(/width:(calc\([^"]*\))"/g)].map((m) => m[1]);
const labelWidths = (html: string) => [...html.matchAll(/width:(clamp[^"]*)"/g)].map((m) => m[1]);
const stackedCells = (html: string) => html.match(/class="shrink-0 flex flex-col gap-0.5"/g) ?? [];

describe("#8562 a date ladder's badge moves under its label", () => {
  test("the Warsh ladder reserves no badge column: the track gets that width back", () => {
    const html = render(warsh);
    expect(slotWidths(html)).toEqual([]);
    expect(stackedCells(html)).toHaveLength(3);
  });

  test("the badges still print, with their unit and their spoken form", () => {
    const html = render(warsh);
    expect(html).toContain("▲4.5 pts");
    expect(html).toContain("▲22.0 pts");
    expect(html).toContain('aria-label="up 22.0 points"');
    // the un-moved rung prints no badge line at all
    expect(html.match(/▲/g)).toHaveLength(2);
  });

  test("ONE label width on every rung, wide enough for the badge line under it", () => {
    const widths = labelWidths(render(warsh));
    expect(widths).toEqual(
      Array(3).fill("clamp(2.75rem, max(calc(11ch + 0.75rem), calc(9ch + 0.5rem)), 45%)"),
    );
  });

  test("the width sits on the stacked CELL, not the label inside it", () => {
    // On the label span, the 45% cap resolved against the auto-width cell and
    // each rung sized to its own text: the first local render measured tracks
    // of 171 / 156 / 158px on the Warsh card. The cell's parent is the row.
    const html = render(warsh);
    const cells = html.match(/<span style="width:clamp[^"]*" class="shrink-0 flex flex-col gap-0.5">/g) ?? [];
    expect(cells).toHaveLength(3);
    expect(labelWidths(html)).toHaveLength(3);
  });
});

describe("#8562 controls — the ladders the first half fixed stay inline", () => {
  test("CONTROL: the Google card keeps its badge column on every rung", () => {
    const html = render(google);
    expect(stackedCells(html)).toEqual([]);
    const slots = slotWidths(html);
    expect(slots).toHaveLength(4);
    expect(new Set(slots)).toEqual(new Set(["calc(8ch + 0.5rem)"]));
    expect(labelWidths(html)).toEqual(Array(4).fill("clamp(2.75rem, calc(4ch + 0.75rem), 45%)"));
  });

  test("CONTROL: a date ladder with no mover is untouched", () => {
    const html = render(warsh.map((r) => ({ ...r, movement: null })));
    expect(stackedCells(html)).toEqual([]);
    expect(slotWidths(html)).toEqual([]);
    expect(labelWidths(html)).toEqual(Array(3).fill("clamp(2.75rem, calc(11ch + 0.75rem), 45%)"));
  });

  test("CONTROL: a numeric (not wide-label) ladder never stacks", () => {
    const html = renderToStaticMarkup(
      <QuantityGroup sort={false} rungs={warsh.map((r) => ({ ...r, label: `Above ${r.value}0 goals` }))} />,
    );
    expect(stackedCells(html)).toEqual([]);
    expect(slotWidths(html).length).toBeGreaterThan(0);
  });
});
