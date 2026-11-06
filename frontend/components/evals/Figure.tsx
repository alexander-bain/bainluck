"use client";

import { createContext, useContext, type ReactNode } from "react";

import TruthChip from "@/components/evals/TruthChip";
import type { MeasuredTruth, RepoRef } from "@/lib/evals/truth";

/**
 * THE ONLY WAY A NUMBER REACHES /evals (#12102).
 *
 * A figure needs three things, and the props make each one required: a truth
 * kind (LIVE or LAST RUN — PLANNED has no figure, so it is not a legal value),
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

export interface FigureProps {
  /** The figure as the reader sees it, e.g. "24 of 25". */
  children: string;
  truth: MeasuredTruth;
  /** The raw value for a probe, e.g. "24/25", so a check never parses prose. */
  value?: string;
  className?: string;
}

export function figureProblem(insidePlanned: boolean, truth: MeasuredTruth): string | null {
  if (insidePlanned) return "a PLANNED item renders no figure";
  if (!truth.asOf) return "a figure needs the time it is true as of";
  if (!truth.source?.href) return "a figure needs a link to where it came from";
  return null;
}

export default function Figure({ children, truth, value, className = "" }: FigureProps) {
  const insidePlanned = useContext(PlannedContext);
  const problem = figureProblem(insidePlanned, truth);
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
      className={`font-mono tabular-nums ${className}`}
    >
      {children}
    </span>
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
