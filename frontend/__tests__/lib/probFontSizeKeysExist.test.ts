import fs from "fs";
import path from "path";

import tailwindConfig from "../../tailwind.config";

// #3749 — A `text-prob-*` CLASS WHOSE KEY IS NOT IN THE CONFIG MUST FAIL THE BUILD.
//
// `/about`'s hero card is the product's whole thesis — "60% vs 40%", not
// "-150 / +130" — and both of its numbers were written `text-prob-xl`. There is
// no `prob-xl` key in `tailwind.config.ts`; the scale is hero/lg/md/sm. Tailwind
// emits no rule for a key it does not have, so the class was inert and the two
// numbers fell through to inherited body size: smaller than the heading above
// them and barely larger than the `Celtics` / `76ers` captions below. The point
// of the card rendered as the least prominent thing in it.
//
// It survived for as long as it existed because THIS FAILURE IS SILENT BY
// CONSTRUCTION. A misspelt Tailwind key is not a type error, not a lint error
// and not a runtime error — it is a class attribute that no stylesheet matches.
// `font-black`, `font-mono` and `tracking-tight` all still applied, which is
// exactly why it read as deliberate rather than broken. Nothing in the toolchain
// was ever going to say a word. Hence a test.
//
// This is NOT #3592. That was `twMerge` eating a size that DID exist; the two
// `/about` call sites do not go through `cn`, so nothing was eaten. Opposite
// mechanism, and `cnProbFontSize.test.ts` cannot see this one.
//
// ── WHY THE SECOND HALF ──────────────────────────────────────────────────────
//
// The scale is written down in TWO places that must agree: the `fontSize` block
// in `tailwind.config.ts`, and the `font-size` class group registered with
// tailwind-merge in `lib/utils.ts`. A key present in the config but missing from
// the registration is not dead — it is worse: it renders correctly wherever the
// class is written literally, and is silently eaten wherever it goes through
// `cn`. That is #3592 exactly, and adding a fifth size is the move that brings
// it back. `cnProbFontSize.test.ts` pins the four keys by hand and so cannot
// notice a fifth. Comparing the two lists is what notices.

const PROB_KEY = /^prob-/;

/** Every source file Tailwind is pointed at, plus `lib/` — see the note below. */
function sourceFiles(): string[] {
  const roots = ["app", "components", "lib"].map((d) =>
    path.join(__dirname, "..", "..", d),
  );
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "node_modules" || entry.name === ".next") continue;
        walk(full);
      } else if (/\.(tsx?|jsx?|mdx)$/.test(entry.name)) {
        out.push(full);
      }
    }
  };
  roots.forEach(walk);
  return out;
}

function fontSizeKeys(): string[] {
  const sizes = (tailwindConfig.theme?.extend?.fontSize ?? {}) as Record<
    string,
    unknown
  >;
  return Object.keys(sizes);
}

describe("#3749 — every text-prob-* class names a key that exists", () => {
  const declared = fontSizeKeys().filter((k) => PROB_KEY.test(k));

  it("the probability scale is non-empty (the scan is not vacuous)", () => {
    // Without this, deleting the whole `fontSize` block would make the test
    // below pass by finding nothing to check.
    expect(declared.length).toBeGreaterThan(0);
    expect(declared).toEqual(expect.arrayContaining(["prob-hero", "prob-sm"]));
  });

  it("no source file uses a text-prob-* key the config does not declare", () => {
    const offenders: string[] = [];

    for (const file of sourceFiles()) {
      const text = fs.readFileSync(file, "utf8");
      const lines = text.split("\n");

      lines.forEach((line, i) => {
        // Skip comment lines: `lib/utils.ts` and this file both DISCUSS the
        // class names, and a guard that trips over prose about itself is worse
        // than no guard.
        const trimmed = line.trim();
        if (trimmed.startsWith("//") || trimmed.startsWith("*")) return;

        for (const m of line.matchAll(/\btext-(prob-[a-z0-9]+)\b/g)) {
          const key = m[1];
          if (!declared.includes(key)) {
            const rel = path.relative(path.join(__dirname, "..", ".."), file);
            offenders.push(`${rel}:${i + 1}  text-${key}`);
          }
        }
      });
    }

    expect(offenders).toEqual([]);
  });
});

describe("#3749 — the config scale and the tailwind-merge registration agree", () => {
  it("lib/utils.ts registers exactly the prob keys the config declares", () => {
    const utils = fs.readFileSync(
      path.join(__dirname, "..", "..", "lib", "utils.ts"),
      "utf8",
    );

    // The registration is `{ text: ["prob-hero", "prob-lg", ...] }`.
    const block = utils.match(/"font-size":\s*\[\{\s*text:\s*\[([^\]]*)\]/);
    expect(block).not.toBeNull();

    const registered = [...(block as RegExpMatchArray)[1].matchAll(/"([^"]+)"/g)]
      .map((m) => m[1])
      .sort();

    const declared = fontSizeKeys().filter((k) => PROB_KEY.test(k)).sort();

    // Both directions. A key in the config but not registered is #3592 again;
    // a key registered but not in the config is a dead entry that makes the
    // registration lie about what the scale is.
    expect(registered).toEqual(declared);
  });
});
