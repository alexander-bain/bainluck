/**
 * #6579 — the Discover movement chip holds its line beside a truncated name.
 *
 * Seen on production Discover at 390px, 2026-09-16 16:00Z (lane1b/292, frame
 * `lane1b-6536/discover-390-valid-chips-control.png`, the "next government of
 * Sweden" card): row 1's chip rendered as a two-line pink oval — `▼ 7` over
 * `pts` — squeezed against `Swedish Social Democrati…`, while rows 3 and 4 of the
 * SAME card drew `▲ 7 pts` inline. The values were correct; the container was not.
 *
 * ## What this file can and cannot prove
 *
 * This project's jest runs on `testEnvironment: 'node'` with no jsdom and no
 * layout engine, so nothing here can measure a wrap — and any px claim written
 * here would be invented. The provable thing is the CLASS COMBINATION, and that is
 * also the actual defect: inside `flex items-center gap-1.5`, an item with neither
 * `shrink-0` nor `whitespace-nowrap` beside a `min-w-0 truncate` sibling WILL be
 * squeezed past its one-line width at some sibling length — the only question is
 * which name. Same doctrine, and the same house precedent, as
 * `futuresCardFitsAt390_4244_4245.test.tsx`.
 *
 * Both sides are asserted, because "make everything unshrinkable" is a different
 * and worse fix: the chip must not yield, AND the name must still be the one that
 * does.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { MovementBadge } from "@/components/discover/shared";

function classesOf(html: string, tag = "span"): string[] {
  const m = html.match(new RegExp(`<${tag}[^>]*class="([^"]*)"`));
  return m ? m[1].split(/\s+/).filter(Boolean) : [];
}

describe("#6579 — the movement chip is the item that does NOT yield", () => {
  // 7 points down, the production specimen's own reading.
  const html = renderToStaticMarkup(<MovementBadge m={-0.07} prob={0.92} />);

  test("its text can never break across two lines", () => {
    expect(classesOf(html)).toContain("whitespace-nowrap");
  });

  test("it is not squeezed by a long sibling in the first place", () => {
    // `whitespace-nowrap` alone would stop the wrap and let the chip overflow its
    // row instead; `shrink-0` is what sends the squeeze to the sibling that has an
    // ellipsis to announce it. `TrendBadge` in the same module already carries this
    // `shrink-0` half — it needs no nowrap because its text has no interior break
    // to be squeezed onto, and "7 pts" does.
    expect(classesOf(html)).toContain("shrink-0");
  });

  test("the badge still says what it said — this is a container fix only", () => {
    expect(html).toContain("7 pts");
    expect(html).toContain('aria-label="Down 7 points in the last 24h"');
  });

  test("CONTROL — a move under the floor still renders nothing at all", () => {
    expect(renderToStaticMarkup(<MovementBadge m={0.01} prob={0.5} />)).toBe("");
  });
});

describe("#6579 — the OTHER side: the outcome name is still the item that yields", () => {
  test("the Discover futures row keeps a shrinkable, truncating name cell", () => {
    // Read off the source rather than a render, because the claim is about the
    // pair of siblings in one flex row: a fix that made BOTH unshrinkable would
    // pass every assertion above and push the percentage column off the card.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const src: string = require("fs").readFileSync(
      require("path").join(process.cwd(), "components/discover/FuturesCard.tsx"),
      "utf8",
    );
    const row = src.match(
      /<div className="flex items-center gap-1\.5">[\s\S]{0,900}?<MovementBadge/,
    );
    expect(row).not.toBeNull();
    expect(row![0]).toContain("min-w-0 truncate");
  });
});
