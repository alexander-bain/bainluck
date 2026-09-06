import { cn } from "../../lib/utils";

// #3592 — `cn` must not eat a custom font size.
//
// `cn` is `twMerge(clsx(...))`. `text-prob-*` are custom `fontSize` entries in
// `tailwind.config.ts`; tailwind-merge has no way to know that on its own, so
// it filed them under `text-color` next to `text-text-primary` and kept only
// the last class written. Every `EventCard` chip therefore rendered with no
// size class, and the favourite/underdog hierarchy was silently gone.
//
// `lib/utils.ts` now registers the scale in the `font-size` group. These tests
// pin BOTH halves of that: the custom sizes survive a colour, and real
// `text-*` conflicts still collapse the way tailwind-merge is here to make
// them collapse. The second half is the one that matters for a shared helper —
// a fix that made every `text-*` class survive would pass the first half.

describe("cn — custom probability font sizes survive a colour class", () => {
  it.each([
    ["prob-hero", "text-text-primary"],
    ["prob-lg", "text-text-primary"],
    ["prob-md", "text-text-primary"],
    ["prob-sm", "text-text-secondary"],
  ])("keeps text-%s alongside %s", (size, colour) => {
    const out = cn("font-mono tabular-nums", `text-${size} ${colour}`);
    expect(out).toContain(`text-${size}`);
    expect(out).toContain(colour);
  });

  it("keeps the size when the colour is written first, too", () => {
    expect(cn("text-text-primary text-prob-md")).toContain("text-prob-md");
    expect(cn("text-text-primary text-prob-md")).toContain("text-text-primary");
  });
});

describe("cn — real text-* conflicts still collapse", () => {
  it("keeps only the last font size among stock sizes", () => {
    expect(cn("text-sm text-lg")).toBe("text-lg");
  });

  it("keeps only the last font size among the custom scale", () => {
    // Two members of one group: the LAST one still wins. Registering the
    // scale must not turn these into two classes fighting in the stylesheet.
    expect(cn("text-prob-md text-prob-sm")).toBe("text-prob-sm");
  });

  it("treats a custom size and a stock size as the same group", () => {
    expect(cn("text-prob-md text-sm")).toBe("text-sm");
    expect(cn("text-sm text-prob-md")).toBe("text-prob-md");
  });

  it("keeps only the last text colour", () => {
    expect(cn("text-red-500 text-blue-500")).toBe("text-blue-500");
    expect(cn("text-text-primary text-text-secondary")).toBe("text-text-secondary");
  });

  it("leaves alignment alone — a third, unrelated text-* group", () => {
    const out = cn("text-center text-prob-md text-text-primary");
    expect(out).toContain("text-center");
    expect(out).toContain("text-prob-md");
    expect(out).toContain("text-text-primary");
  });
});
