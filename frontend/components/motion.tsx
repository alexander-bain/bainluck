"use client";

import { LazyMotion, m } from "framer-motion";
import { forwardRef } from "react";
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

const loadDomAnimation = () => import("@/lib/motionFeatures").then((mod) => mod.default);

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
  return (
    <MotionProvider>
      <m.div ref={ref} {...props} />
    </MotionProvider>
  );
});

const MotionSpan = forwardRef<HTMLSpanElement, MotionSpanProps>(function MotionSpan(props, ref) {
  return (
    <MotionProvider>
      <m.span ref={ref} {...props} />
    </MotionProvider>
  );
});

const MotionButton = forwardRef<HTMLButtonElement, MotionButtonProps>(function MotionButton(
  props,
  ref,
) {
  return (
    <MotionProvider>
      <m.button ref={ref} {...props} />
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
