"use client";

/**
 * #10868 — the soccer match's three-outcome headline (web): home win, Draw,
 * away win, always in that order and never sorted. The web twin of native
 * `SoccerThreeOutcomeHeadline11449` (body L90-105, columns L122-146, blocks
 * L166-188, headings L212-233).
 *
 * TWO ARRANGEMENTS, tried in order, the first that fits whole being drawn
 * (native `ViewThatFits(in: .horizontal) { columns; blocks }`):
 *
 *   1. COLUMNS — three equal, aligned outcome columns: the outcome names on one
 *      row, then each reading row under its own full-width heading (title, then
 *      its dated source context), so the primary and comparison rows line up
 *      across the three outcomes and each heading is said once.
 *   2. BLOCKS — one fully labelled block per outcome: the headings (with their
 *      contexts) once at the top, then each outcome's name with every reading
 *      under its own heading title.
 *
 * An accessibility text size goes straight to blocks (native
 * `typeSize.isAccessibilitySize`). "Fits" is measured, not assumed — the
 * hockey matrix's rule (`HockeyJourneyMatrix.tsx`): before paint, the columns'
 * frame and every column cell are measured, and a cell whose content is wider
 * than its equal third (a figure, or a WORD of a name or of the absence words —
 * nothing wraps inside a word, as native's `WholeWordsText11449`) steps to
 * blocks. The search restarts whenever its key changes: the content
 * (`soccerHeadlineFitContent`), the frame's width or the text size. Type never
 * shrinks: figures are the same size in both arrangements.
 *
 * A missing reading prints that slot's own words ("Draw chance unavailable"),
 * never a dash, a zero or a figure derived from the other two. A team's figure
 * wears its own colour only when that colour clears the card-surface contrast
 * floor (`tint`); the page sets the colour variables (`teamColorStyle`).
 */

import { useId, useRef, useState } from "react";
import type {
  SoccerMatchHeadline as Headline,
  SoccerOutcomeSlot,
  SoccerReadingHeading,
  SoccerSlot,
} from "@/lib/eventPage10868/soccerMatchTypes";
import { useFrameMeasure, useIsomorphicLayoutEffect } from "./useFrameMeasure";

export type SoccerHeadlineArrangement = "columns" | "blocks";

/** The arrangements to try, in order (native body L90-105). */
export function soccerHeadlineArrangements(accessibilitySize: boolean): SoccerHeadlineArrangement[] {
  return accessibilitySize ? ["blocks"] : ["columns", "blocks"];
}

/** Everything that can change the columns' width: names, printed readings, headings. */
export function soccerHeadlineFitContent(headline: Headline): string {
  return JSON.stringify([
    headline.outcomes.map((o) => [o.label, o.primary.text, o.comparison?.text ?? null]),
    headline.primaryHeading,
    headline.comparisonHeading,
  ]);
}

/** A box's content is wider than the box: a figure or a single word does not fit. */
function overflows(el: Element): boolean {
  return el.scrollWidth > el.clientWidth + 1;
}

function figureStyle(outcome: SoccerOutcomeSlot): { color: string } | undefined {
  if (!outcome.tint) return undefined;
  return { color: outcome.key === "home" ? "rgb(var(--team-home-primary))" : "rgb(var(--team-away-primary))" };
}

const FIGURE = "whitespace-nowrap text-2xl font-bold tabular-nums leading-tight";
const WORDS = "text-sm text-text-secondary";

interface ReadingRow {
  heading: SoccerReadingHeading;
  slot: (outcome: SoccerOutcomeSlot) => SoccerSlot | null;
}

function SlotText({ slot, outcome }: { slot: SoccerSlot; outcome: SoccerOutcomeSlot }) {
  return slot.kind === "value" ? (
    <span className={`${FIGURE} ${outcome.tint ? "" : "text-text-primary"}`} style={figureStyle(outcome)}>
      {slot.text}
    </span>
  ) : (
    <span className={WORDS}>{slot.text}</span>
  );
}

function HeadingLines({ heading, id }: { heading: SoccerReadingHeading; id?: string }) {
  return (
    <span id={id} className="block text-left" data-soccer-heading="">
      <span className="block text-sm font-semibold">{heading.title}</span>
      {heading.context && <span className="block text-sm font-normal text-text-secondary">{heading.context}</span>}
    </span>
  );
}

/** Native `columns` (L122-146): names, then each heading row and its aligned readings. */
function Columns({ headline, rows, ids }: { headline: Headline; rows: ReadingRow[]; ids: string }) {
  return (
    <table className="w-full table-fixed border-collapse" data-soccer-headline-columns="">
      <thead>
        <tr>
          {headline.outcomes.map((outcome) => (
            <th
              key={outcome.key}
              id={`${ids}-o-${outcome.key}`}
              scope="col"
              data-fit-cell=""
              data-soccer-outcome={outcome.key}
              className="overflow-hidden px-1 pb-1 text-left align-bottom text-base font-semibold first:pl-0 last:pr-0"
            >
              {outcome.label}
            </th>
          ))}
        </tr>
      </thead>
      {rows.map((row, r) => (
        <tbody key={`${r}:${row.heading.title}`}>
          <tr>
            <th colSpan={3} scope="colgroup" className="pb-1 pt-2 font-normal">
              <HeadingLines heading={row.heading} id={`${ids}-h-${r}`} />
            </th>
          </tr>
          <tr>
            {headline.outcomes.map((outcome) => {
              const slot = row.slot(outcome);
              return (
                <td
                  key={outcome.key}
                  headers={`${ids}-o-${outcome.key} ${ids}-h-${r}`}
                  data-fit-cell=""
                  data-soccer-reading={`${r}:${outcome.key}`}
                  className="overflow-hidden px-1 align-top first:pl-0 last:pr-0"
                >
                  {slot && <SlotText slot={slot} outcome={outcome} />}
                </td>
              );
            })}
          </tr>
        </tbody>
      ))}
    </table>
  );
}

/** Native `blocks` (L166-188): headings once, then one labelled block per outcome. */
function Blocks({ headline, rows }: { headline: Headline; rows: ReadingRow[] }) {
  return (
    <div className="space-y-4" data-soccer-headline-blocks="">
      <div className="space-y-2">
        {rows.map((row, r) => (
          <HeadingLines key={`${r}:${row.heading.title}`} heading={row.heading} />
        ))}
      </div>
      <ul className="space-y-3" aria-label="Match outcomes">
        {headline.outcomes.map((outcome) => (
          <li key={outcome.key} className="min-w-0" data-soccer-outcome={outcome.key}>
            <p className="break-words text-base font-semibold">{outcome.label}</p>
            <dl className="mt-1 space-y-1">
              {rows.map((row, r) => {
                const slot = row.slot(outcome);
                return slot ? (
                  <div key={`${r}:${row.heading.title}`} className="min-w-0">
                    <dt className="text-sm text-text-secondary">{row.heading.title}</dt>
                    <dd>
                      <SlotText slot={slot} outcome={outcome} />
                    </dd>
                  </div>
                ) : null;
              })}
            </dl>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function SoccerMatchHeadline({ headline }: { headline: Headline }) {
  const ids = useId();
  const frame = useRef<HTMLDivElement>(null);
  const { width, accessibilitySize } = useFrameMeasure(frame);
  // What the fit search is for; a step found for another key is never reused.
  const fitKey = `${soccerHeadlineFitContent(headline)}|${width}|${accessibilitySize ? "large" : "standard"}`;
  const [fit, setFit] = useState({ key: fitKey, step: 0 });
  const step = fit.key === fitKey ? fit.step : 0;
  const order = soccerHeadlineArrangements(accessibilitySize);
  const arrangement = order[Math.min(step, order.length - 1)];

  // Before paint: the columns step to blocks when the frame or any column cell overflows.
  useIsomorphicLayoutEffect(() => {
    const el = frame.current;
    if (!el || arrangement !== "columns") return;
    if (overflows(el) || Array.from(el.querySelectorAll("[data-fit-cell]")).some(overflows)) {
      setFit({ key: fitKey, step: step + 1 });
    }
  }, [arrangement, fitKey, step]);

  const rows: ReadingRow[] = [
    { heading: headline.primaryHeading, slot: (o) => o.primary },
    ...(headline.comparisonHeading ? [{ heading: headline.comparisonHeading, slot: (o: SoccerOutcomeSlot) => o.comparison }] : []),
  ];

  return (
    <div className="rounded-lg bg-surface-deep p-3" data-soccer-headline="">
      <div ref={frame} className="w-full overflow-hidden" data-arrangement={arrangement}>
        {arrangement === "columns" ? <Columns headline={headline} rows={rows} ids={ids} /> : <Blocks headline={headline} rows={rows} />}
      </div>
    </div>
  );
}
