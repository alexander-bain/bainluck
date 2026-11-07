"use client";

import { createContext, useContext, type ReactNode } from "react";

import TruthChip from "@/components/evals/TruthChip";
import type { FigureTruth, RepoRef } from "@/lib/evals/truth";

/**
 * THE ONLY WAY A NUMBER REACHES /evals (#12102).
 *
 * A figure needs three things, and the props make each one required: a truth
 * kind (LIVE, LAST RUN, or LAST REVIEWED for a count read off a list we keep by
 * hand — PLANNED has no figure, so it is not a legal value),
 * the time the number is true as of, and a link to where it came from. The text
 * itself arrives already formatted by a lib helper reading a committed record or
 * a live payload; nothing in a component types a number.
 *
 * Two rules are checked at render, because a type cannot see them:
 *
 *   • A figure inside a PLANNED item is an error — a PLANNED item renders no
 *     figure (the plan's truth rule 4).
 *   • A figure with an empty as-of or an empty source link is an error.
 *
 * Outside production either one throws, so the page test and `next dev` fail
 * loudly; in production the figure is dropped instead of shown without its
 * label. Fail closed: a missing number is honest, an unlabelled one is not.
 */

export const PlannedContext = createContext(false);

/** Inside an `Example`: an illustration of how something works, never a measurement. */
export const ExampleContext = createContext(false);

export interface FigureProps {
  /** The figure as the reader sees it, e.g. "24 of 25". */
  children: string;
  truth: FigureTruth;
  /** The raw value for a probe, e.g. "24/25", so a check never parses prose. */
  value?: string;
  className?: string;
}

export function figureProblem(insidePlanned: boolean, truth: FigureTruth, insideExample = false): string | null {
  if (insidePlanned) return "a PLANNED item renders no figure";
  if (insideExample) return "an example renders no measured figure";
  if (!truth.asOf) return "a figure needs the time it is true as of";
  if (!truth.source?.href) return "a figure needs a link to where it came from";
  return null;
}

export default function Figure({ children, truth, value, className = "" }: FigureProps) {
  const insidePlanned = useContext(PlannedContext);
  const insideExample = useContext(ExampleContext);
  const problem = figureProblem(insidePlanned, truth, insideExample);
  if (problem) {
    if (process.env.NODE_ENV !== "production") {
      throw new Error(`/evals Figure "${children}": ${problem}`);
    }
    return null;
  }
  return (
    <span
      data-evals-figure=""
      data-truth={truth.kind}
      data-as-of={truth.asOf}
      data-source={truth.source.href}
      data-value={value ?? children}
      className={`tabular-nums ${className}`}
    >
      {children}
    </span>
  );
}

/**
 * A chart or other drawn exhibit: many numbers (axis ticks, counts) drawn from
 * one record. It takes the same three things a `Figure` does and obeys the
 * same two rules, and the whole exhibit counts as one figure for the page's
 * digit scan — its numbers are the record's, drawn, not typed.
 */
export function Exhibit({
  truth,
  label,
  children,
}: {
  truth: FigureTruth;
  /** What the exhibit shows, for screen readers. */
  label: string;
  children: ReactNode;
}) {
  const insidePlanned = useContext(PlannedContext);
  const insideExample = useContext(ExampleContext);
  const problem = figureProblem(insidePlanned, truth, insideExample);
  if (problem) {
    if (process.env.NODE_ENV !== "production") {
      throw new Error(`/evals Exhibit "${label}": ${problem}`);
    }
    return null;
  }
  return (
    <figure
      data-evals-figure=""
      data-evals-exhibit=""
      data-truth={truth.kind}
      data-as-of={truth.asOf}
      data-source={truth.source.href}
      aria-label={label}
    >
      {children}
    </figure>
  );
}

/**
 * Work that is not built: a PLANNED chip naming what it waits on, and a scope
 * in which no `Figure` may render.
 */
export function PlannedItem({
  waitingOn,
  repoRef,
  children,
}: {
  waitingOn: string;
  repoRef?: RepoRef;
  children: ReactNode;
}) {
  return (
    <PlannedContext.Provider value={true}>
      <div data-planned-item="" className="space-y-1.5">
        {children}
        <div>
          <TruthChip truth={{ kind: "planned", waitingOn, ref: repoRef }} />
        </div>
      </div>
    </PlannedContext.Provider>
  );
}

/**
 * An illustration of how something works, such as one view written two ways
 * becoming one probability. It always says "For example", the truth scan skips
 * its digits (`scanEvalsDom`), and no `Figure` or `Exhibit` may render inside
 * it: a measured number belongs outside, under its own label.
 */
export function Example({ caption, label, children }: { caption: string; label: string; children: ReactNode }) {
  return (
    <ExampleContext.Provider value={true}>
      <figure data-evals-example="" aria-label={label} className="space-y-2">
        <figcaption className="text-micro font-semibold uppercase tracking-wide text-text-secondary">{caption}</figcaption>
        {children}
      </figure>
    </ExampleContext.Provider>
  );
}
