/**
 * UX-P234 — ONE PIN AFFORDANCE, USED IN BOTH PLACES (board items 15 + 16).
 *
 * ═══ WHAT ALEX SAW ═══
 *
 * 15. The futures DETAIL page's pin was the bare word **"Pin"**, inside a container
 *     whose own comment read *"Legacy hero kept for share/pin actions"* — leftover
 *     scaffolding that shipped.
 * 16. On the web DISCOVER feed there was **no indication a card can be pinned at all**.
 *
 * Alex's instruction is one sentence: *one affordance, used in both places.*
 *
 * ═══ ⚠️ ITEM 16'S PREMISE NEEDED A CORRECTION ═══
 *
 * The board item says *"the capability exists and is invisible."* Measured, it did
 * not exist on that card: `components/discover/FuturesCard.tsx` contained no pin
 * state, no pin handler and no reference to `usePinnedFutures`, and nothing under
 * `components/discover/` did. What existed was the hook plus a real, working pin on
 * `components/FuturesCard.tsx` — the card used by search, my-stuff and preferences.
 *
 * So Discover was not hiding an affordance. It was the ONE surface that never got
 * one while every neighbour had it on the very same market, which is exactly why
 * Alex expected it to be there.
 *
 * ═══ THE TRAP THIS FILE IS BUILT AROUND ═══
 *
 * `PinIcon` was defined THREE times, byte-for-byte, in `FuturesCard.tsx`,
 * `EventCard.tsx` and `app/events/[id]/page.tsx` — and the detail page had drifted
 * away from all three into a bare word. A fourth copy would have "fixed" item 15
 * while guaranteeing the next drift. The Discover half has the same shape one level
 * down: `FuturesCard` renders **four** ActionBars across four card variants, and a
 * pin wired into three of them is a pin that vanishes on the fourth.
 *
 * That is why the last test in this file counts.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

// The resolver this ship took off the landing page. Imported HERE, in the test,
// precisely because the shipped component must no longer import it: the guard
// needs `twMerge` to prove the component does not need it.
import { twMerge } from "tailwind-merge";

import { PinButton, pinTitle, pinAriaLabel, pinClickAction, PIN_ICON_SIZE, PIN_TONE } from "../../components/PinButton";
import { ActionBar } from "../../components/discover/shared";

/**
 * Source with comments removed.
 *
 * 🔴 THIS EXISTS BECAUSE THE GUARD FAILED ON ITS OWN FIX, TWICE. Both source-level
 * assertions below are of the form "this must no longer appear" — and the code that
 * removed each thing QUOTES it in a comment to explain what it replaced. A plain
 * `not.toContain` cannot tell a claim from a quotation of that claim, so it went red
 * on the very change it was written to prove. That is the HISTORY_CLAIM_BANS lesson
 * exactly, met here twice in one session.
 *
 * Deliberately naive: it does not understand `//` inside a string literal. Fine for
 * these two assertions, and stated rather than hidden.
 */
function codeOnly(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

/**
 * Text a reader actually sees — tags stripped, so attributes cannot satisfy it.
 *
 * 🔴 A CHARACTER SCAN, NOT `replace(/<[^>]*>/g, "")`. CodeQL flagged the regex form
 * as **high severity** `js/incomplete-multi-character-sanitization` on the branch
 * below this one, and it is right about the shape: a single-pass tag strip is the
 * classic incomplete sanitizer, because one pass over `<<a>script>` leaves a tag
 * behind. Nothing untrusted flows through here — it reads our own SSR output inside
 * a test — but a new high alert is a real CI gate, and "it is only a test" is not a
 * reason to ship the pattern people copy. A scan cannot be defeated by nesting.
 */
function visibleText(html: string): string {
  let out = "";
  let inTag = false;
  for (const ch of html) {
    if (ch === "<") inTag = true;
    else if (ch === ">") inTag = false;
    else if (!inTag) out += ch;
  }
  return out.trim();
}

function attrs(html: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of html.matchAll(/([a-zA-Z-]+)="([^"]*)"/g)) out[m[1]] = m[2];
  return out;
}

describe("UX-P234: the shared pin affordance is an affordance, not a word", () => {
  test("it renders an icon, in both variants", () => {
    for (const variant of ["icon", "labelled"] as const) {
      const html = renderToStaticMarkup(
        <PinButton pinned={false} onToggle={() => {}} variant={variant} />,
      );
      expect(html).toContain("<svg");
      expect(html).toContain('data-testid="pin-button"');
    }
  });

  test("the labelled variant keeps the word AND gains the icon", () => {
    // Item 15 is not "delete the word", it is "the word was all there was".
    //
    // ⚠️ Asserted on the VISIBLE text, not on the markup. `toContain("Pin")` also
    // matches `aria-label="Pin market"` and `title="Pin"`, so deleting the visible
    // <span> passed it — mutant E survived the first battery on exactly that.
    const off = renderToStaticMarkup(<PinButton pinned={false} onToggle={() => {}} variant="labelled" />);
    expect(off).toContain("<svg");
    expect(visibleText(off)).toBe("Pin");

    const on = renderToStaticMarkup(<PinButton pinned onToggle={() => {}} variant="labelled" />);
    expect(visibleText(on)).toBe("Pinned");
  });

  test("the icon variant carries NO visible text, so it needs its label", () => {
    const html = renderToStaticMarkup(<PinButton pinned={false} onToggle={() => {}} variant="icon" />);
    expect(visibleText(html)).toBe("");
    expect(attrs(html)["aria-label"]).toBe("Pin market");
  });

  test("pinned and unpinned are visibly DIFFERENT icons, not just different colours", () => {
    // A state change a reader can only perceive as a colour shift is not a state.
    const off = renderToStaticMarkup(<PinButton pinned={false} onToggle={() => {}} />);
    const on = renderToStaticMarkup(<PinButton pinned onToggle={() => {}} />);
    expect(off).toContain('fill="none"');
    expect(on).toContain('fill="currentColor"');
    expect(off).not.toBe(on);
  });

  test("the state is exposed to assistive tech, not only to the eye", () => {
    expect(attrs(renderToStaticMarkup(<PinButton pinned onToggle={() => {}} />))["aria-pressed"]).toBe("true");
    expect(attrs(renderToStaticMarkup(<PinButton pinned={false} onToggle={() => {}} />))["aria-pressed"]).toBe("false");
  });

  test("every state has one wording and the table is the only source of it", () => {
    expect(pinTitle(false, false)).toBe("Pin");
    expect(pinTitle(true, false)).toBe("Unpin");
    expect(pinTitle(false, true)).toBe("Max 6 pins");
    // 🔴 At the ceiling an ALREADY-pinned item must still say Unpin and stay
    // clickable — otherwise a reader at 6 pins can never get back below 6.
    expect(pinTitle(true, true)).toBe("Unpin");
    expect(pinAriaLabel(true, "event")).toBe("Unpin event");
  });

  test("the icon is actually DRAWN — it carries a size, not just an <svg> tag", () => {
    // An <svg> that is present but never painted is a bare word wearing an icon.
    // Mutant F blanked the size class and survived a mere `toContain("<svg")`.
    for (const variant of ["icon", "labelled"] as const) {
      const html = renderToStaticMarkup(
        <PinButton pinned={false} onToggle={() => {}} variant={variant} />,
      );
      expect(html).toContain(PIN_ICON_SIZE[variant]);
    }
    expect(PIN_ICON_SIZE.icon).not.toBe(PIN_ICON_SIZE.labelled);
  });

  test("a pin click inside a Discover card is SWALLOWED, not allowed to navigate", () => {
    // These cards sit inside `useSwipe` and, in some variants, a <Link>. Without
    // the swallow, pinning also opens the detail page and the pin looks like it
    // did nothing because the surface it changed is gone.
    //
    // Asserted through `pinClickAction` because this project has no
    // @testing-library/react and `renderToStaticMarkup` cannot dispatch a click.
    // The source-substring version of this guard was satisfied by the PROP NAME
    // and survived deletion of the actual calls.
    expect(pinClickAction({ disabled: false, swallow: true })).toEqual({
      preventDefault: true,
      stopPropagation: true,
      toggles: true,
    });
    // On the detail page there is nothing to swallow, and swallowing would be wrong.
    expect(pinClickAction({ disabled: false, swallow: false })).toEqual({
      preventDefault: false,
      stopPropagation: false,
      toggles: true,
    });
    // A disabled button still swallows, so a click at the ceiling does not navigate.
    expect(pinClickAction({ disabled: true, swallow: true })).toEqual({
      preventDefault: true,
      stopPropagation: true,
      toggles: false,
    });
  });

  test("at the ceiling an unpinned button is disabled and a pinned one is NOT", () => {
    const blocked = renderToStaticMarkup(<PinButton pinned={false} onToggle={() => {}} atMax />);
    expect(blocked).toContain("disabled");
    expect(attrs(blocked)["title"]).toBe("Max 6 pins");

    const escapable = renderToStaticMarkup(<PinButton pinned onToggle={() => {}} atMax />);
    expect(escapable).not.toContain("disabled");
    expect(attrs(escapable)["title"]).toBe("Unpin");
  });
});

describe("UX-P234: item 15 — the detail page uses the shared affordance", () => {
  const PAGE = readFileSync(join(__dirname, "../../app/futures/[id]/page.tsx"), "utf8");

  test("the bare-word button is gone", () => {
    expect(PAGE).not.toContain('{marketIsPinned ? "Pinned" : "Pin"}');
  });

  test("it renders the shared PinButton rather than a fourth hand-rolled one", () => {
    expect(PAGE).toContain("<PinButton");
    expect(PAGE).toContain('from "@/components/PinButton"');
  });

  test("the retired scaffolding comment went with the thing it described", () => {
    // ":629 calls its container 'Legacy hero kept for share/pin actions' —
    // leftover scaffolding that shipped." A comment describing a hero that no
    // longer exists is a false claim about the code for the next reader.
    //
    // ⚠️ Matched as the standalone JSX comment it was, NOT as a substring: the
    // replacement comment QUOTES the retired line to explain what it replaced, and
    // a naive `not.toContain` therefore failed on the very fix it was guarding.
    // A guard that cannot tell a claim from a quotation of that claim is the
    // HISTORY_CLAIM_BANS lesson, and it caught me here.
    expect(codeOnly(PAGE)).not.toContain("Legacy hero kept for share/pin actions");
  });
});

describe("UX-P234: item 16 — Discover cards can be pinned, and every variant says so", () => {
  const CARD = readFileSync(join(__dirname, "../../components/discover/FuturesCard.tsx"), "utf8");
  const SHARED = readFileSync(join(__dirname, "../../components/discover/shared.tsx"), "utf8");

  test("the Discover pin is bound to the REAL store, not a local useState", () => {
    // A pin that does not survive a reload is theatre. The binding is the page's
    // (see the architecture test below), so this asserts it at its real owner.
    //
    // ⚠️ This test USED to read `expect(CARD).toContain("usePinnedFutures()")`,
    // written when the hook lived in the card. After the binding moved it kept
    // passing — off the DOCBLOCK that explains why the hook must not be there.
    // Directly contradicting the architecture test two below it, and both green.
    // Left here as the named example: a source-substring assertion survives the
    // deletion of the thing it was about.
    const PAGE = readFileSync(join(__dirname, "../../app/discover/page.tsx"), "utf8");
    expect(codeOnly(PAGE)).toContain("usePinnedFutures()");
    // The card holds no pin state of its own — it renders the binding it is
    // handed. (It legitimately uses `useState` for context expansion and the A/B
    // variant, so the claim is about PIN state, not about state in general.)
    expect(codeOnly(CARD)).not.toMatch(/useState[^\n]*[Pp]in/);
    expect(codeOnly(CARD)).toContain("pin={pin}");
  });

  const bar = (pin?: { pinned: boolean; onToggle: () => void; atMax: boolean; noun: string }) =>
    renderToStaticMarkup(
      <ActionBar
        liked={false}
        setLiked={() => {}}
        shareUrl="https://bainluck.com/futures/1"
        shareTitle="A market"
        contentType="futures"
        itemId={1}
        pin={pin}
      />,
    );

  test("the action bar RENDERS the shared affordance when handed a binding", () => {
    // Rendered, not grepped: a source-substring guard cannot tell whether the
    // element reaches the markup.
    const html = bar({ pinned: false, onToggle: () => {}, atMax: false, noun: "market" });
    expect(html).toContain('data-testid="pin-button"');
    expect(html).toContain('data-pinned="false"');
    expect(visibleText(html)).toContain("Pin");
    // And it has not displaced the actions that were already there.
    expect(html).toContain("Like");
    expect(html).toContain("Share");
  });

  test("the action bar reflects the PINNED state it is handed", () => {
    // Mutant K hard-codes this to false: the button renders, and silently stops
    // being a state.
    const html = bar({ pinned: true, onToggle: () => {}, atMax: true, noun: "market" });
    expect(html).toContain('data-pinned="true"');
    expect(visibleText(html)).toContain("Pinned");
    // At the ceiling an already-pinned card must still be unpinnable.
    expect(html).not.toContain("disabled");
  });

  test("no binding ⇒ no pin, and the rest of the bar is untouched", () => {
    const html = bar(undefined);
    expect(html).not.toContain('data-testid="pin-button"');
    expect(html).toContain("Like");
    expect(html).toContain("Share");
  });

  test("🔴 EVERY COMPONENT A FUTURES ITEM CAN ROUTE TO IS HANDED THE PIN", () => {
    // 🔴 THE ASSERTION CERT-606 HAD TO WRITE FOR ME, AND THE ONE THAT MATTERS MOST.
    //
    // The test below counts `<ActionBar>` inside FuturesCard and requires each to
    // carry the pin. That looked exhaustive and was exhaustive within ONE
    // component — while `DiscoverCard` routes a FUTURES item to `ComparisonCard`
    // instead whenever `suggested_format === "outcome_distribution"` and there are
    // >=4 outcomes. So the SAME market showed a pin or not depending on how the
    // feed chose to format it, and every one of the 20 assertions here passed.
    //
    // The lesson is one level up from UX-P211's: enumerating the renderings INSIDE
    // a component is not enumerating the components a card type can BE. Count the
    // routing branches, not the JSX you happened to be editing.
    const DISCOVER = readFileSync(join(__dirname, "../../components/DiscoverCard.tsx"), "utf8");
    const code = codeOnly(DISCOVER);

    // Every JSX element rendered on an `item.type === "futures"` branch.
    const futuresBranch = code.slice(code.indexOf('item.type === "futures"'));
    const routed = [...futuresBranch.matchAll(/<(FuturesCard|ComparisonCard)\b[^>]*>/g)];
    expect(routed.length).toBeGreaterThanOrEqual(2); // both renderings exist

    for (const [tag] of routed) {
      expect(tag).toContain("pin={pinFor?.(");
    }
  });

  test("ComparisonCard — the missed rendering — renders the pin it is handed", () => {
    const CMP = readFileSync(join(__dirname, "../../components/discover/ComparisonCard.tsx"), "utf8");
    expect(codeOnly(CMP)).toContain("pin={pin}");
    expect(codeOnly(CMP)).not.toContain("usePinnedFutures");
  });

  test("🔴 EVERY ActionBar in the Discover futures card is handed the pin", () => {
    // THE ASSERTION THIS FILE EXISTS FOR. `FuturesCard` renders four ActionBars
    // across four card variants; a pin wired into three of them is a pin that
    // silently vanishes on the fourth, and no other test here would notice. This
    // is the same class as `PinIcon` existing three times — and as UX-P211's
    // "enumerate the renderings". If a fifth variant is added, this goes red.
    const bars = CARD.match(/<ActionBar\b/g) ?? [];
    const wired = CARD.match(/pin=\{pin\}/g) ?? [];
    expect(bars.length).toBeGreaterThanOrEqual(4);
    expect(wired).toHaveLength(bars.length);
  });

  test("🔴 the Discover card stays PRESENTATIONAL — no pin store read inside it", () => {
    // THE REGRESSION THIS TEST EXISTS FOR, and it is one I caused and fixed.
    // The first draft called `usePinnedFutures()` inside this leaf card. That
    // reaches `useAuthContext`, which THROWS outside an `AuthProvider`, and it
    // took down TEN existing suites that render this card in isolation — 71
    // failing tests. It also contradicts the convention `DiscoverCard` states in
    // its own docblock: "Cards stay presentational … never behind a storage read
    // in here."
    //
    // The page owns the store; the card is handed a binding. Same shape as
    // `components/FuturesCard.tsx`, which has always taken `isPinned` /
    // `onPinToggle` as props.
    expect(codeOnly(CARD)).not.toContain("usePinnedFutures");
    expect(CARD).toContain("pin?: ActionBarProps[\"pin\"]");
  });

  test("the PAGE owns the pin store and hands each card its binding", () => {
    const PAGE = readFileSync(join(__dirname, "../../app/discover/page.tsx"), "utf8");
    expect(PAGE).toContain("usePinnedFutures()");
    expect(PAGE).toContain("pinFor={pinForFutures}");
  });

  test("the pin is OPTIONAL on ActionBar, so unwired card types are untouched", () => {
    // Concept, comparison, tournament and event cards render an ActionBar too.
    // This ship deliberately wires futures only — the half that pairs with item
    // 15 — and they must be byte-identical rather than sprouting a dead button.
    expect(SHARED).toContain("{pin && (");
  });
});

/**
 * LAT-P211 — THIS BUTTON IS WHY THE LANDING PAGE DOWNLOADED `tailwind-merge`.
 *
 * `cn` is `twMerge(clsx(...))` and `tailwind-merge` is 26,985 raw / 7,398 brotli.
 * Eleven components use `cn`, and exactly ONE of them was in the eager import
 * graph of `/`: this file, via `components/discover/shared.tsx`. So the Discover
 * landing page shipped a Tailwind class-conflict resolver for one button.
 *
 * It was doing real work. The ActionBar passed
 * `className="text-text-muted hover:text-text-secondary"` and relied on `twMerge`
 * to drop this button's own conflicting `text-text-secondary hover:text-text-primary`
 * (and, when pinned, its `text-amber-600`) — two of the 1,299 load-bearing
 * divergences LAT-P201 counted app-wide. So the fix is NOT "drop `twMerge` and hope":
 * the override became a `tone` prop and the colours became a total lookup table, so
 * the component cannot emit two classes that fight and there is nothing to resolve.
 *
 * ═══ WHY THE INVARIANT AND NOT A SNAPSHOT OF THE COLOURS ═══
 *
 * The tempting guard is "these 16 states render exactly the strings they rendered on
 * 2026-09-02". That reds on any intended restyle, so it would be edited away the
 * first time a designer touches the pin — and the thing that actually matters would
 * go with it. The durable property is the one that makes the resolver unnecessary:
 * **`twMerge` is a no-op on everything this component emits.** That survives a colour
 * change and reds precisely when someone reintroduces a conflict — which is the
 * moment `/` would silently need `tailwind-merge` back.
 *
 * Its artifact-level twin is the `tailwind-merge` entry in
 * `__tests__/lib/emittedEntryGraph.test.ts`, which fails if the package returns to
 * the landing page's `<script>` set by any route at all. This one says why it left.
 */
describe("LAT-P211: the pin needs no class-conflict resolver", () => {
  /** Every state the component can be asked for: 2 tones × 2 variants × 2 pinned. */
  const STATES = (["default", "muted"] as const).flatMap((tone) =>
    (["icon", "labelled"] as const).flatMap((variant) =>
      [true, false].map((pinned) => ({ tone, variant, pinned })),
    ),
  );

  /**
   * The classes on the BUTTON, not on the icon inside it.
   *
   * 🔴 NOT `attrs(html).class`. `attrs` walks every `name="value"` pair in the
   * whole string into one record, so a later match overwrites an earlier one and
   * `.class` is the `<svg>`'s `w-3.5 h-3.5` — two classes, none of them the ones
   * under test. The control below is what caught it: every assertion here is
   * "twMerge changed nothing", and twMerge changes nothing about `w-3.5 h-3.5`,
   * so the real test would have passed green while reading the wrong element.
   */
  const classesOf = (html: string): string[] => {
    const tag = html.match(/<button\b[^>]*>/)?.[0] ?? "";
    return (tag.match(/\sclass="([^"]*)"/)?.[1] ?? "").split(" ").filter(Boolean);
  };

  const asSet = (classes: string[]): string =>
    [...new Set(classes)].sort().join("|");

  test("control — the assertion below can actually fail", () => {
    // Every check in this describe is "twMerge changed nothing", which is
    // vacuously true of an empty or unparsed class list. So first: prove the
    // comparison catches a class list that DOES need resolving, using exactly
    // the conflict this ship removed.
    const conflicted = "px-3 text-text-secondary hover:text-text-primary text-text-muted hover:text-text-secondary";
    expect(asSet(twMerge(conflicted).split(" "))).not.toBe(asSet(conflicted.split(" ")));

    // And that the reader below finds a real, non-trivial class list.
    const html = renderToStaticMarkup(<PinButton pinned={false} onToggle={() => {}} variant="labelled" />);
    expect(classesOf(html).length).toBeGreaterThan(5);
  });

  test("🔴 twMerge is a no-op on every state this button renders", () => {
    const offenders: string[] = [];
    for (const { tone, variant, pinned } of STATES) {
      // `disabled` is `atMax && !pinned`, so both reachable values of atMax are
      // covered here and the unreachable pinned+disabled state is not invented.
      for (const atMax of [true, false]) {
        const html = renderToStaticMarkup(
          <PinButton pinned={pinned} onToggle={() => {}} variant={variant} tone={tone} atMax={atMax} />,
        );
        const emitted = classesOf(html);
        const resolved = twMerge(emitted.join(" ")).split(" ").filter(Boolean);
        if (asSet(emitted) !== asSet(resolved)) {
          offenders.push(
            `tone=${tone} variant=${variant} pinned=${pinned} atMax=${atMax}: ` +
              `twMerge dropped [${emitted.filter((c) => !resolved.includes(c)).join(", ")}]`,
          );
        }
      }
    }
    // A non-empty list means the pin is relying on class-conflict resolution
    // again, and `/` now needs `tailwind-merge` on its first load to render this
    // button correctly. Fix the class list, do not re-import `cn`.
    expect(offenders).toEqual([]);
  });

  test("PIN_TONE is the ONLY source of colour, so a conflict cannot be hand-written back in", () => {
    // The invariant above is about the OUTPUT. This is about the shape that keeps
    // it true: every colour class comes from one table, so there is one place to
    // check. A hardcoded `text-*` beside a `PIN_TONE[...]` lookup is exactly how
    // the conflict would come back.
    for (const { tone, variant, pinned } of STATES) {
      const html = renderToStaticMarkup(
        <PinButton pinned={pinned} onToggle={() => {}} variant={variant} tone={tone} />,
      );
      const expected = PIN_TONE[`${tone}-${variant}-${pinned}`].split(" ");
      const emitted = classesOf(html);
      for (const cls of expected) expect(emitted).toContain(cls);
      // Nothing colour-shaped that the table did not put there.
      const colourish = emitted.filter((c) => /(^|:)(text-(?!sm\b|xs\b|base\b|lg\b)|bg-)/.test(c));
      expect(asSet(colourish)).toBe(asSet(expected));
    }
  });

  test("the override that used to need the resolver is gone from BOTH ends", () => {
    // The caller stopped passing a conflicting className …
    const BAR = readFileSync(join(__dirname, "../../components/discover/shared.tsx"), "utf8");
    expect(codeOnly(BAR)).toContain('tone="muted"');
    expect(codeOnly(BAR)).not.toContain('className="text-text-muted hover:text-text-secondary"');
    // … and the component no longer accepts one, so it cannot come back by prop.
    // TypeScript is the real gate here; this states the intent where it is read.
    const BUTTON = readFileSync(join(__dirname, "../../components/PinButton.tsx"), "utf8");
    expect(codeOnly(BUTTON)).not.toContain("className?: string;\n  /** Discover");
    // And the import that pulls 7,398 brotli onto whatever route renders this.
    expect(codeOnly(BUTTON)).not.toContain('from "@/lib/utils"');
  });
});
