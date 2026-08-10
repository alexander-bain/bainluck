"use client";

import { LazyMotion, m } from "framer-motion";
import { forwardRef, useRef } from "react";
import type { FeatureBundle } from "framer-motion";
import type { ComponentPropsWithoutRef, ReactNode } from "react";

/**
 * Animation primitives that keep framer-motion's feature bundle out of First Load JS (#1631).
 *
 * THE PROBLEM. Importing the full `motion` component ships every animation feature to every
 * route that renders one. Measured on the cycle-38 production build, that is chunk `7611` —
 * 125 kB raw / **40.7 kB gzip** — on `/sports`, `/search`, `/my-stuff`, `/preferences`,
 * `/futures`, `/futures/[id]` and `/sports/[key]`: ~31% of `/sports`'s route-own weight, paid
 * before the page can paint a single game.
 *
 * THE FIX. `m` is the same component with no features baked in; `LazyMotion` supplies them.
 * Passing features as a `() => import(...)` thunk puts them in an async chunk, so the route
 * pays for the component shell up front and the features arrive after paint.
 *
 * WHY THE PRIMITIVES CARRY THEIR OWN PROVIDER. `m` renders nothing without a `LazyMotion`
 * ancestor, so a provider that has to be remembered is a provider that will eventually be
 * forgotten — and the failure is silent: the element renders, it just never animates. Binding
 * the provider to the primitive makes that unrepresentable. `LazyMotion` emits no DOM, so
 * wrapping costs no markup and cannot disturb a flex/grid parent.
 *
 * WHY NOT THE ROOT LAYOUT. A provider in the shared layout would move framer-motion core into
 * the 160 kB baseline that every route pays, so the **70 routes that currently pull none of it
 * would start paying** — a net loss dressed up as a bundle fix.
 *
 * `domAnimation` covers animations, variants, exit animations and tap/hover/focus gestures —
 * everything this codebase uses. `domMax` is only needed for layout animations and drag/pan,
 * and `__tests__/lib/motionBundle.test.ts` fails if we ever start using those.
 */

/**
 * ENHANCE FROM VISIBLE — the C229 P1 repair.
 *
 * `m` renders its `initial` state immediately but cannot run the animation to `animate` until
 * the feature chunk arrives. Converted call sites declare `initial={{opacity: 0}}` /
 * `initial="hidden"`, so before this repair a slow chunk left ready data painted at opacity 0,
 * and a FAILED chunk left it that way permanently: a successful feed rendering as an empty
 * page. That put the north-star "first visible card" behind an optional decoration download.
 *
 * The rule now: **content paints visible without features, and animation is the enhancement.**
 * An element that mounts before the features exist is handed `initial={false}`, which tells
 * framer-motion to start at its `animate` state — visible, untransformed, no entrance
 * animation. Elements that mount after the chunk lands animate normally.
 *
 * This also fixes the server render, which is the case that mattered most: SSR always sees
 * "not ready", so the HTML now ships visible instead of carrying an inline `opacity: 0` that
 * only JavaScript could clear. Client and server agree on the first render, so there is no
 * hydration mismatch.
 *
 * Chunk failure degrades to static, never to hidden: `featuresReady` simply never flips, and
 * every element keeps its visible fallback.
 */
let featurePromise: Promise<FeatureBundle> | null = null;
let featuresReady = false;
let featureLoadFailed = false;
let featureLoadCount = 0;

const loadDomAnimation = (): Promise<FeatureBundle> => {
  // Memoised at module scope, so N providers share ONE import call and ONE resolution. This is
  // what makes per-element providers safe to fan out, and `__motionFeatureLoadCount` exists so
  // a test can PROVE the dedup rather than asserting it from module-cache folklore (C229 P2).
  if (!featurePromise) {
    featureLoadCount += 1;
    featurePromise = import("@/lib/motionFeatures")
      .then((mod) => {
        featuresReady = true;
        return mod.default;
      })
      .catch((err) => {
        // Leave `featuresReady` false: every element keeps painting its visible fallback.
        featureLoadFailed = true;
        throw err;
      });
  }
  return featurePromise;
};

/** True once the optional feature chunk has resolved. False on the server, always. */
export function motionFeaturesReady(): boolean {
  return featuresReady;
}

/** True if the optional chunk failed. Content stays visible; animation is simply absent. */
export function motionFeaturesFailed(): boolean {
  return featureLoadFailed;
}

/** Test-only: how many times the dynamic import was actually initiated. */
export function __motionFeatureLoadCount(): number {
  return featureLoadCount;
}

/** Test-only: reset the module-scope loader state between cases. */
export function __resetMotionFeaturesForTest(): void {
  featurePromise = null;
  featuresReady = false;
  featureLoadFailed = false;
  featureLoadCount = 0;
}

/**
 * Freeze the enhance-from-visible decision at MOUNT.
 *
 * `initial` only has meaning on an element's first render, so the answer must not change
 * underneath a mounted element — otherwise a chunk landing mid-life could re-apply a hidden
 * initial to something already on screen. A ref, not state: no subscription, no re-render, and
 * the server and the first client render necessarily agree.
 */
function useInitialPaintsVisible(): boolean {
  const paintsVisible = useRef<boolean | null>(null);
  if (paintsVisible.current === null) paintsVisible.current = !featuresReady;
  return paintsVisible.current;
}

/**
 * `strict` turns a stray full-`motion` call site into a loud development error instead of a
 * silent 40 kB regression. It is off in production so the guard can never surface as a
 * user-visible crash; the durable guard is the source-level test.
 */
const STRICT = process.env.NODE_ENV !== "production";

/** Supplies the lazily-loaded feature set to any `m` components beneath it. */
export function MotionProvider({ children }: { children: ReactNode }) {
  return (
    <LazyMotion features={loadDomAnimation} strict={STRICT}>
      {children}
    </LazyMotion>
  );
}

type MotionDivProps = ComponentPropsWithoutRef<typeof m.div>;
type MotionSpanProps = ComponentPropsWithoutRef<typeof m.span>;
type MotionButtonProps = ComponentPropsWithoutRef<typeof m.button>;

const MotionDiv = forwardRef<HTMLDivElement, MotionDivProps>(function MotionDiv(props, ref) {
  const paintsVisible = useInitialPaintsVisible();
  return (
    <MotionProvider>
      <m.div ref={ref} {...props} initial={paintsVisible ? false : props.initial} />
    </MotionProvider>
  );
});

const MotionSpan = forwardRef<HTMLSpanElement, MotionSpanProps>(function MotionSpan(props, ref) {
  const paintsVisible = useInitialPaintsVisible();
  return (
    <MotionProvider>
      <m.span ref={ref} {...props} initial={paintsVisible ? false : props.initial} />
    </MotionProvider>
  );
});

const MotionButton = forwardRef<HTMLButtonElement, MotionButtonProps>(function MotionButton(
  props,
  ref,
) {
  const paintsVisible = useInitialPaintsVisible();
  return (
    <MotionProvider>
      <m.button ref={ref} {...props} initial={paintsVisible ? false : props.initial} />
    </MotionProvider>
  );
});

/**
 * Drop-in replacement for framer-motion's `motion`, limited to the elements this app animates.
 *
 * Call sites are unchanged — `<motion.div animate={...}>` still reads exactly the same. Only
 * the import moves, from `"framer-motion"` to `"@/components/motion"`.
 *
 * Variant propagation from a parent to a child still works: `LazyMotion` supplies features via
 * its own context and does not touch the motion context variants inherit through.
 */
export const motion = {
  div: MotionDiv,
  span: MotionSpan,
  button: MotionButton,
};
