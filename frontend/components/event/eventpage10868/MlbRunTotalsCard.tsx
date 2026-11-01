"use client";

/**
 * #10868 — THE MLB RUN-TOTAL CARD, FINAL LEAF (web). Native:
 * `MLBTotalTargetsCardView11284` over `MLBTotalTargetsPresentation11284`
 * (MLBTotalTargetsPresentation11284.swift).
 *
 * PILLARS: FORMATTING / DISCOVER / TRUTH. SHIP: a baseball fan sees the final
 * run total against the offered lines, with the pregame chance and source
 * result kept distinct from performance.
 *
 * What it draws, from the built `MlbFinalTotals` only (`mlbRunTotals.ts`):
 * the final total, large, and the selected line's pregame chance or
 * "Unavailable"; the team split as keys; the selected line's name and the
 * SPORTING comparison ("Final 10 runs · above this line"); the final total as
 * a stacked home/away bar on a zero-based runs axis, every offered line as a
 * tick on that axis whichever is selected, and the selected line as a hollow
 * diamond on a stem; the source's result on that line in web's one settled
 * vocabulary (`propVerdictLabel`), or "Result unavailable"; then every line in
 * a wrapping strip of buttons. The comparison is the score against the number;
 * the source result is the venue's grade; neither is derived from the other.
 *
 * SELECTION: the only state is the chosen option key, held per `scope`
 * (`mlb:<event id>:<phase>`). With no choice the card opens on native's
 * default (the highest line the total cleared, else the lowest). A held key
 * the lines no longer carry exactly once says "Selected line unavailable" and
 * shows no chance, diamond, comparison or result — never the default or a
 * neighbour; it returns when the key is offered again. A new scope starts a
 * new reading inside this component (adjusted while rendering); no parent
 * `key` is needed.
 *
 * CONTROLLED SELECTION (optional, B1). A host that must keep the chosen line
 * while the card itself is absent (native `BaseballStoriesAdapter10868`
 * holds `selectedOptionKey` outside the card) passes `selection`: its `held`
 * key (null = no choice yet, so the default) replaces the internal one, and
 * each deliberate tap calls `onSelect(optionKey)` exactly once; the card never
 * selects by itself. The same resolution applies: a held key the lines do not
 * carry exactly once is "Selected line unavailable", never the default. With
 * no `selection` the card behaves exactly as above.
 *
 * BEFORE FIRST PITCH AND DURING PLAY (S2b). Given `mlbRunMilestones`' input
 * (`kind: "milestones"`), the card draws S2a's `CountMilestoneCard` — the
 * approved milestone visual — instead of the final leaf, inside the same
 * `data-mlb-run-totals` wrapper. The chosen line is the SAME held option key
 * (the host's `selection`, else the internal per-scope state): no held key is
 * passed as `undefined`, never a made-up id, so with no shown pregame chance
 * nothing is chosen. Each tap routes once (to `onSelect`, or to the internal
 * state). Details stay off inside the wrapper. The final input draws exactly
 * the final leaf below.
 *
 * LAYOUT (optional, reader I1, Design R-F2). `layout="page"` (the default) is
 * the markup above, unchanged. `layout="expanded"` — what the full-size reader
 * (`MlbRunTotalsReader`) asks for — gives ONLY the final plot more height, in
 * native's proportion (`MLBTotalTargetsPresentation11284` chart frame
 * `expanded ? 132 : 108`). Native's frame holds the marks and the axis labels;
 * the web twin is the `data-run-plot` block: the marks area (6rem) plus the
 * axis-label row (0.25rem gap + 1.25rem) = 7.5rem. Expanded, that block is
 * 7.5rem × 132 / 108 = 9.1667rem; the label row keeps its size and type (as
 * native's axis labels do), so the marks area alone takes the added room:
 * 7.5rem × 132 / 108 − 1.5rem = 7.6667rem. Every mark inside it is placed in
 * percentages of that area, so the bar, ticks, stem and diamond keep their
 * proportions; every horizontal position, the diamond's size, every reading,
 * word and control are the same as on the page. No Details control is added
 * (native expanded draws one; web Details stay owed). The milestones leaf
 * has no expanded form (native has none) and ignores `layout`. No pixel
 * parity is claimed before a browser check.
 *
 * The axis never depends on the selection, so choosing a line never rescales
 * the bar. No chart library, fetch, timer or subscription; tokens and the
 * host's team colours only. The plot is hidden from screen readers: every
 * figure it shows is also in words.
 */

import { useId, useState } from "react";
import { propVerdictLabel } from "@/lib/propGrade";
import {
  MLB_RUN_TOTAL_WORDS as W,
  mlbRunComparison,
  mlbRunSelected,
  type MlbRunTotalsInput,
} from "@/lib/eventPage10868/mlbRunTotals";
import { CountMilestoneCard } from "./SoccerMatchStories";

/** The host's team colours (its own contrast-checked tints, else series tokens). */
export interface MlbRunTotalsColors {
  home: string;
  away: string;
}

const DEFAULT_COLORS: MlbRunTotalsColors = { home: "var(--series-1)", away: "var(--series-2)" };

/** A host-held selection: the chosen option key (null = none yet) and the tap callback. */
export interface MlbRunTotalsSelection {
  held: string | null;
  onSelect: (optionKey: string) => void;
}

/** Where the card is drawn: on the page (default), or full size in the reader (see LAYOUT). */
export type MlbRunTotalsLayout = "page" | "expanded";

/**
 * The final plot's marks-area height per layout (see LAYOUT): page 6rem (`h-24`);
 * expanded = the 7.5rem plot block × 132 / 108, less the unchanged 1.5rem axis-label row.
 */
export const MLB_RUN_PLOT_HEIGHT: Record<MlbRunTotalsLayout, string> = {
  page: "h-24",
  expanded: "h-[calc(7.5rem*132/108_-_1.5rem)]",
};

/** The source's verdict in web's one settled vocabulary, or the documented partial. */
const resultWords = (result: boolean | null): string => (result === null ? W.resultUnavailable : propVerdictLabel(result));

const axisText = (value: number): string => (Number.isInteger(value) ? String(value) : value.toFixed(1));

export default function MlbRunTotalsCard({
  totals,
  scope,
  colors = DEFAULT_COLORS,
  selection,
  layout = "page",
}: {
  /**
   * THIS event's built input: `mlbFinalTotals(…)` after the final, or
   * `mlbRunMilestones(…)` before first pitch and during play.
   */
  totals: MlbRunTotalsInput;
  /** `mlb:<event id>:<phase>`: a change resets the held line. */
  scope: string;
  colors?: MlbRunTotalsColors;
  /** Optional host-held selection (see CONTROLLED SELECTION); absent = the card holds it itself. */
  selection?: MlbRunTotalsSelection;
  /** Optional: "expanded" gives only the final plot more height (see LAYOUT); default "page". */
  layout?: MlbRunTotalsLayout;
}) {
  const titleId = useId();
  const stripId = useId();
  const [stored, setStored] = useState<{ scope: string; held: string | null }>(() => ({ scope, held: null }));
  // A new event or phase is a new reading: adjusted while rendering, so no frame shows the old choice.
  if (stored.scope !== scope) setStored({ scope, held: null });
  const held = selection ? selection.held : stored.scope === scope ? stored.held : null;
  const choose = (key: string) => (selection ? selection.onSelect(key) : setStored({ scope, held: key }));

  if (totals.kind === "milestones") {
    // Before / live: S2a's wrapper over the approved milestone visual, on the same held key (none = undefined).
    // `layout` is not read here: the milestones leaf has no expanded form.
    return (
      <div className="min-w-0" data-mlb-run-totals={scope} data-mlb-run-milestones={totals.phase}>
        <CountMilestoneCard card={totals.card} heldId={held === null ? undefined : held} onChoose={choose} />
      </div>
    );
  }

  const selected = mlbRunSelected(totals, held);
  const { total, bar, axis } = totals;
  const comparison = selected ? mlbRunComparison(total, selected) : null;
  // Every line and the total are at or under `axis.upper`, so every position is on the plot.
  const at = (value: number) => `${(value / axis.upper) * 100}%`;
  const segments =
    bar.kind === "stacked"
      ? [
          { id: "home", from: 0, to: bar.home, color: colors.home },
          { id: "away", from: bar.home, to: bar.home + bar.away, color: colors.away },
        ].filter((s) => s.to > s.from)
      : [];
  const last = axis.labels.length - 1;

  return (
    <section aria-labelledby={titleId} className="min-w-0 space-y-3" data-mlb-run-totals={scope}>
      <div>
        <p className="text-xs font-semibold tracking-wide text-text-secondary">{W.eyebrow(totals.lines.length)}</p>
        <h3 id={titleId} className="break-words text-base font-semibold">
          {W.title}
        </h3>
      </div>

      {/* The final total and the selected line's pregame chance, side by side; they stack when there is no room. */}
      <dl className="flex flex-wrap gap-x-8 gap-y-2">
        <div className="flex min-w-0 flex-col-reverse">
          <dt className="text-sm text-text-secondary">{W.actualLabel}</dt>
          <dd
            data-run-total={total ?? "unavailable"}
            className={total === null ? "text-xl font-semibold text-text-secondary" : "text-3xl font-bold tabular-nums text-text-primary"}
          >
            {total === null ? W.unavailable : total}
          </dd>
        </div>
        <div className="flex min-w-0 flex-col-reverse">
          <dt className="break-words text-sm text-text-secondary">{selected ? `${W.pregameLabel} · ${selected.label}` : W.pregameLabel}</dt>
          <dd
            data-run-pregame=""
            className={
              selected && selected.pregame !== null ? "text-3xl font-bold tabular-nums text-text-primary" : "text-xl font-semibold text-text-secondary"
            }
          >
            {selected ? selected.pregameText : W.unavailable}
          </dd>
        </div>
      </dl>

      {(bar.kind === "stacked" || selected) && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs" data-run-keys="">
          {bar.kind === "stacked" && (
            <>
              <li className="flex min-w-0 items-center gap-1.5 break-words text-text-primary" data-run-key="home">
                <span aria-hidden="true" className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: colors.home }} />
                {`${totals.homeName} ${bar.home}`}
              </li>
              <li className="flex min-w-0 items-center gap-1.5 break-words text-text-primary" data-run-key="away">
                <span aria-hidden="true" className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: colors.away }} />
                {`${totals.awayName} ${bar.away}`}
              </li>
            </>
          )}
          {selected && (
            <li aria-hidden="true" className="flex items-center gap-1.5 text-text-secondary" data-run-key="marker">
              <span className="inline-block h-2 w-2 shrink-0 rotate-45 border-2 border-text-primary bg-surface-card" />
              {W.markerKey(selected.lineText)}
            </li>
          )}
        </ul>
      )}

      <div data-run-selected={selected?.optionKey ?? "unavailable"}>
        <p className={`break-words text-base font-semibold ${selected ? "text-text-primary" : "text-text-secondary"}`} data-run-heading="">
          {selected ? selected.label : W.selectedUnavailable}
        </p>
        {comparison && (
          <p className="text-sm text-text-secondary" data-run-comparison="">
            {comparison}
          </p>
        )}
      </div>

      {/* The bar, every line's tick and the selected diamond, on one zero-based runs axis. */}
      <div aria-hidden="true" className="px-3" data-run-plot={layout === "expanded" ? "expanded" : ""}>
        <div className={`relative ${MLB_RUN_PLOT_HEIGHT[layout]}`}>
          <div className="absolute inset-x-0 top-[40%] h-[28%] rounded-sm bg-surface-deep" />
          {segments.map((s) => (
            <div
              key={s.id}
              data-run-segment={s.id}
              data-run-from={s.from}
              data-run-to={s.to}
              className="absolute top-[40%] h-[28%]"
              style={{ left: at(s.from), width: `${((s.to - s.from) / axis.upper) * 100}%`, background: s.color }}
            />
          ))}
          {totals.lines.map((l) => (
            <span
              key={l.optionKey}
              data-run-tick={l.line}
              className="absolute bottom-0 h-[22%] w-px -translate-x-1/2 bg-text-secondary"
              style={{ left: at(l.line) }}
            />
          ))}
          {selected && (
            <>
              <span
                data-run-stem={selected.line}
                className="absolute bottom-0 top-[12%] w-0.5 -translate-x-1/2 bg-text-primary"
                style={{ left: at(selected.line) }}
              />
              <span
                data-run-marker={selected.line}
                className="absolute top-[12%] h-3 w-3 -translate-x-1/2 -translate-y-1/2 rotate-45 border-2 border-text-primary bg-surface-card"
                style={{ left: at(selected.line) }}
              />
            </>
          )}
        </div>
        <div className="relative mt-1 h-5 text-xs tabular-nums text-text-secondary">
          {axis.labels.map((value, i) => (
            <span
              key={value}
              data-run-axis-label={value}
              className={`absolute top-0 whitespace-nowrap ${i === 0 ? "" : i === last ? "-translate-x-full" : "-translate-x-1/2"}`}
              style={{ left: at(value) }}
            >
              {axisText(value)}
            </span>
          ))}
        </div>
      </div>

      {selected && (
        <p className="text-sm" data-run-source="">
          <span className="text-text-secondary">{`${W.sourceResult} `}</span>
          <span className="font-semibold">{resultWords(selected.result)}</span>
        </p>
      )}

      <div className="space-y-2">
        <p id={stripId} className="text-sm font-semibold">
          {W.strip}
        </p>
        <ul className="flex flex-wrap gap-2" aria-labelledby={stripId}>
          {totals.lines.map((l) => {
            const chosen = selected === l;
            return (
              <li key={l.optionKey}>
                <button
                  type="button"
                  aria-pressed={chosen}
                  aria-label={`${l.label}. ${W.sourceResult} ${resultWords(l.result)}.`}
                  onClick={() => choose(l.optionKey)}
                  data-run-choice={l.optionKey}
                  className={`min-h-11 min-w-[3.25rem] rounded-md border px-2 text-base tabular-nums focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand ${
                    chosen ? "border-2 border-text-primary bg-surface-deep font-bold" : "border-surface-border"
                  }`}
                >
                  {l.lineText}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
