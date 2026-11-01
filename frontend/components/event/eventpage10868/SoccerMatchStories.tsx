"use client";

/**
 * #10868 — the soccer match's story stream (web), with the five story cards in
 * COMPACT form, each drawn as its approved native visual (274369bc):
 *
 *   - goal milestones   TotalMilestonePresentation10868 — a milestone profile:
 *                       x the total goals, y the chance on a fixed 0–100%
 *                       scale; hollow pre-match marks on stems, filled in-game
 *                       marks only where admitted as current, the count as a
 *                       solid rule (a count, never a chance), and the strip of
 *                       every milestone under it.
 *   - exact final score ExactScoreMapPresentation10868 — a heat map, home goals
 *                       down and away goals across, shaded by each listed
 *                       score's PRE-MATCH chance on the owner's own scale;
 *                       hatched off-scale, dashed where not listed, a dark
 *                       outline on the venue's confirmed result, corner marks on
 *                       the chosen score.
 *   - both teams        BothTeamsScorePresentation10868 — a ring holding ONE
 *                       number, the chosen outcome's pre-match chance (its
 *                       remainder is geometry, never the other outcome), beside
 *                       both teams' goals; each outcome keeps its own tile.
 *   - first team        FirstScorerComparisonPresentation10868 — the chosen
 *                       outcome's named comparison above a lollipop plot of
 *                       every outcome's pre-match chance on one shared scale.
 *   - half by half      PeriodOutcomeComparisonPresentation10868 — a dot plot:
 *                       each outcome's pre-match chance per half on one scale,
 *                       lines joining one outcome's halves (never a time
 *                       series), then the chosen outcome's tile per half.
 *
 * Geometry reads only the builder's qualified raw values (probabilities,
 * quantities, the count, the owner's scale bound) — never a figure parsed back
 * out of text. A missing, stale or withheld chance draws NO mark and keeps its
 * own words; a quoted 0% is a mark at 0%. A result or a reached milestone is
 * never drawn as a chance: results are their own badge in web's one settled
 * vocabulary (`propVerdictLabel`), the count is its own rule. Nothing is
 * complemented, normalised or ranked.
 *
 * MANUAL stream: the reader moves with Previous and Next, and nothing else moves
 * the card. No playback, dwell, timer or ranking. With no offered card
 * (production today: no owner admits the story markets) the stream says so in
 * its own words and points to All props. The reader's choices (milestone,
 * outcome, half series, score market and score) are HELD here across stories
 * and refreshes; each card's chance-timing disclosure lists the chosen row's
 * readings with their full clocks and venues.
 *
 * HELD SELECTION (native `TotalMilestoneInput10868.selection`,
 * `BothTeamsScoreInput10868.selection`, `FirstScorerComparisonInput10868`,
 * `PeriodOutcomeComparisonInput10868`, `ExactScoreMapInput10868.scopeSelection`
 * / `originalSelection`, ExactScoreMapPresentation10868.swift:384-405): a choice
 * resolves by its exact id, EXACTLY ONCE. With no explicit choice the card opens
 * on the owner's default (else its first row). An explicit choice the payload no
 * longer names, or names more than once, is UNAVAILABLE: the card says so in the
 * leaf's own words and shows no other row's reading, chance, result or timing,
 * never the default or the first of the duplicates. The held id is kept, so the
 * same identity is shown again when it returns; every other row stays choosable
 * (a row whose id is not unique offers no action — it could resolve nobody).
 * The choices belong to the stream's reading scope (`stream.scope`, one per
 * event and phase): a refresh in that scope keeps them; a new event or phase
 * starts a new reading. No timer, no subscription, no key on the payload.
 *
 * Card-level Details is not in this increment: every original's exact Details
 * is in All props.
 */

import { useId, useState, type ReactNode } from "react";
import { propVerdictLabel } from "@/lib/propGrade";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import type {
  SoccerBothCard,
  SoccerCurrent,
  SoccerExactCard,
  SoccerExactOriginal,
  SoccerExactScope,
  SoccerFirstCard,
  SoccerGoalsCard,
  SoccerGoalsMilestone,
  SoccerHalfSeries,
  SoccerHalvesCard,
  SoccerLeafTitles,
  SoccerPregame,
  SoccerReadingRow,
  SoccerResult,
  SoccerStoryCard,
  SoccerStoryStream,
  SoccerTiming,
} from "@/lib/eventPage10868/soccerMatchTypes";

type Held = Record<string, string>;
type Hold = (key: string, value: string) => void;

export interface SoccerStoryColors {
  home: string;
  away: string;
}

const DEFAULT_COLORS: SoccerStoryColors = { home: "var(--series-1)", away: "var(--series-2)" };
/** The chance marks' one colour (native `DS.blue`): a design-token variable, never a hex. */
const CHANCE = "var(--series-1)";
/** The fixed chance axis every plot shares (native ticks 0 / 50 / 100%), through web's one percent rule. */
const CHANCE_TICKS = [0, 0.5, 1].map((p) => ({ p, text: formatProbabilityPercent(p) }));

const PREVIOUS = "Previous";
const NEXT = "Next";

// ─── Readings ──────────────────────────────────────────────────────────────

/** The raw qualified probability a mark is drawn at, or null: no mark. */
const pregameValue = (p: SoccerPregame): number | null => (p.kind === "value" ? p.observation.probability : null);
const currentValue = (c: SoccerCurrent | null): number | null => (c?.kind === "recorded" ? c.observation.probability : null);
/** A position on a 0–100% axis, for geometry only. */
const at = (p: number): string => `${Math.min(100, Math.max(0, p * 100))}%`;

function pregameText(p: SoccerPregame): { text: string; value: boolean } {
  return p.kind === "value" ? { text: p.observation.text, value: true } : { text: p.words, value: false };
}

function currentText(c: SoccerCurrent): { text: string; value: boolean } {
  return c.kind === "recorded" ? { text: c.observation.text, value: true } : { text: c.words, value: false };
}

/** A result in web's one settled vocabulary, or its own words when there is no admitted verdict. */
function resultText(r: SoccerResult): string {
  return r.kind === "unconfirmed" ? r.words : propVerdictLabel(r.kind === "won");
}

function Figure({ title, reading, large = false }: { title: string; reading: { text: string; value: boolean }; large?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-text-secondary">{title}</dt>
      <dd
        className={
          reading.value
            ? `${large ? "text-xl" : "text-base"} whitespace-nowrap font-bold tabular-nums text-text-primary`
            : "text-sm text-text-secondary"
        }
      >
        {reading.text}
      </dd>
    </div>
  );
}

/** A result, kept apart from every chance: its own badge with a drawn mark (no glyph text). */
function ResultBadge({ title, result }: { title: string; result: SoccerResult }) {
  const verdict = result.kind !== "unconfirmed";
  return (
    <div className="min-w-0">
      <dt className="text-xs text-text-secondary">{title}</dt>
      <dd
        data-result={result.kind}
        className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-sm ${
          verdict ? "border border-text-primary font-bold text-text-primary" : "text-text-secondary"
        }`}
      >
        {verdict && (
          <svg viewBox="0 0 12 12" className="h-3 w-3 shrink-0" aria-hidden="true">
            {result.kind === "won" ? (
              <path d="M2 6.5 L5 9.5 L10 2.5" fill="none" strokeWidth={2} className="stroke-text-primary" />
            ) : (
              <path d="M2.5 2.5 L9.5 9.5 M9.5 2.5 L2.5 9.5" fill="none" strokeWidth={2} className="stroke-text-primary" />
            )}
          </svg>
        )}
        {resultText(result)}
      </dd>
    </div>
  );
}

/** The chosen row's readings for its phase, side by side at the same size. */
function Readout({ row, titles }: { row: SoccerReadingRow; titles: SoccerLeafTitles }) {
  return (
    <dl className="flex flex-wrap gap-x-6 gap-y-2" data-readout={row.id}>
      <Figure title={titles.pregame} reading={pregameText(row.pregame)} large />
      {row.current && <Figure title={titles.current} reading={currentText(row.current)} large />}
      {row.result && !row.current && <ResultBadge title={titles.result} result={row.result} />}
    </dl>
  );
}

function Timing({ timing }: { timing: SoccerTiming }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  if (timing.lines.length === 0) return null;
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        className="min-h-11 text-left text-sm font-semibold text-text-primary underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand"
      >
        {timing.title}
      </button>
      <ul id={id} hidden={!open} className="list-disc space-y-1 pl-5 text-sm text-text-secondary">
        {timing.lines.map((line, i) => (
          <li key={`${i}:${line}`} className="break-words">
            {line}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** How a card's choice resolves against this pass's rows. */
export type SoccerSelection<T> =
  | { kind: "none" }
  | { kind: "selected"; row: T }
  /** The id names no row (withdrawn, or re-identified) or more than one row: nothing is substituted. */
  | { kind: "unavailable"; id: string; reason: "missing" | "duplicate" };

/** Exact id only, exactly once; a missing or duplicated id gets no substitute. */
export function selectExactlyOnce<T extends { id: string }>(rows: readonly T[], id: string | null): SoccerSelection<T> {
  if (id === null) return { kind: "none" };
  const matches = rows.filter((r) => r.id === id);
  if (matches.length === 1) return { kind: "selected", row: matches[0] };
  return { kind: "unavailable", id, reason: matches.length === 0 ? "missing" : "duplicate" };
}

/**
 * The id a card resolves: the reader's explicit held id whenever there is one
 * (kept even while unavailable), else — only with no explicit choice — the
 * owner's opening default, else its first row.
 */
export function soccerRequestedId(held: string | undefined, fallback: string | null, rows: readonly { id: string }[]): string | null {
  if (held !== undefined) return held;
  return fallback ?? rows[0]?.id ?? null;
}

/** A row can be chosen only when its id names exactly one row. */
const isUnique = (rows: readonly { id: string }[], id: string) => rows.filter((r) => r.id === id).length === 1;
const chosenRow = <T,>(selection: SoccerSelection<T>): T | null => (selection.kind === "selected" ? selection.row : null);

/** In place of a chosen row's readout: the leaf's own words, and nothing of any other row. */
function SelectionUnavailable({ selection, words }: { selection: SoccerSelection<unknown>; words: string }) {
  if (selection.kind !== "unavailable") return null;
  return (
    <p className="rounded-md bg-surface-deep p-2 text-sm font-semibold text-text-primary" data-soccer-selection-unavailable={selection.reason}>
      {words}
    </p>
  );
}

const CHOICE =
  "min-h-11 rounded-md border px-2 py-1 text-left text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand";
const chosenClass = (chosen: boolean) => (chosen ? "border-text-primary" : "border-surface-border");

/** A mark on a plot, centred on its point: hollow (a pre-match chance) or filled (a current one). */
function Dot({ hollow, color = CHANCE, size = 10, emphasis = false, mark }: { hollow: boolean; color?: string; size?: number; emphasis?: boolean; mark: string }) {
  return (
    <span
      data-mark={mark}
      className={`absolute block -translate-x-1/2 -translate-y-1/2 rounded-full ${hollow ? "bg-surface-card" : ""} ${
        emphasis ? "ring-2 ring-text-primary ring-offset-1 ring-offset-surface-card" : ""
      }`}
      style={{ width: size, height: size, border: `2px solid ${color}`, background: hollow ? undefined : color }}
    />
  );
}

/** The 0 / 50 / 100% gridlines and their labels, shared by every chance plot. */
function ChanceGrid() {
  return (
    <>
      {CHANCE_TICKS.map((tick) => (
        <div key={tick.p} className="absolute inset-x-0 border-t border-surface-border" style={{ bottom: at(tick.p) }}>
          <span className="absolute -left-1 -translate-x-full -translate-y-1/2 text-xs text-text-secondary">{tick.text}</span>
        </div>
      ))}
    </>
  );
}

// ─── Goals: the milestone profile (TotalMilestonePresentation10868) ────────

function GoalsCard({ card, held, hold }: { card: SoccerGoalsCard; held: Held; hold: Hold }) {
  const selection = selectExactlyOnce(card.milestones, soccerRequestedId(held.goals, card.defaultId, card.milestones));
  const chosen = chosenRow(selection);
  const count = card.actual?.kind === "count" ? card.actual : null;
  // The axis domain is the milestones and the visible count, never the selection (native).
  const top = Math.max(0, ...card.milestones.map((m) => m.quantity), count?.quantity ?? 0) + 1;
  const x = (q: number) => `${(q / top) * 100}%`;
  const drawable = card.milestones.some((m) => pregameValue(m.pregame) !== null || currentValue(m.current) !== null);
  const summary = card.milestones
    .map((m) => `${m.label}: ${pregameText(m.pregame).text}${m.current ? `, ${currentText(m.current).text}` : ""}`)
    .join("; ");
  return (
    <article className="space-y-3" data-soccer-card="goals">
      <p className="text-xs font-semibold tracking-wide text-text-secondary">{card.eyebrow}</p>
      <h4 className="text-base font-semibold">{card.title}</h4>
      {card.actual &&
        (count ? (
          <p className="text-sm">
            <span className="text-text-secondary">{`${count.title}: `}</span>
            <span className="font-bold tabular-nums">{`${count.text} ${count.unit}`}</span>
            {count.clock && <span className="text-text-secondary">{` · ${count.clock}`}</span>}
          </p>
        ) : (
          <p className="text-sm text-text-secondary">{card.actual.kind === "unavailable" ? card.actual.words : null}</p>
        ))}

      <figure className="space-y-1" data-goals-plot={drawable ? "chart" : "strip"}>
        {drawable && <figcaption className="text-xs text-text-secondary">{card.chartTitle}</figcaption>}
        <div className="pl-10 pr-2">
          <div className={`relative ${drawable ? "h-36" : "h-6"} ${count ? "mt-5" : ""}`} role="img" aria-label={`${card.chartTitle}. ${summary}`}>
            {drawable && <ChanceGrid />}
            {drawable &&
              card.milestones.map((m, i) => {
                const before = pregameValue(m.pregame);
                const now = currentValue(m.current);
                const isChosen = chosen === m;
                return (
                  <div key={`${i}:${m.id}`} className="absolute inset-y-0" style={{ left: x(m.quantity) }} data-milestone={m.id}>
                    {before !== null && (
                      <>
                        <span
                          data-mark="stem"
                          className="absolute bottom-0 block w-0.5 -translate-x-1/2 opacity-40"
                          style={{ height: at(before), background: CHANCE }}
                        />
                        <span className="absolute block" style={{ bottom: at(before) }}>
                          <Dot hollow mark="pregame" emphasis={isChosen} />
                        </span>
                      </>
                    )}
                    {now !== null && (
                      <span className="absolute block" style={{ bottom: at(now) }}>
                        <Dot hollow={false} mark="current" emphasis={isChosen} />
                      </span>
                    )}
                  </div>
                );
              })}
            {count && (
              <div className="absolute inset-y-0" style={{ left: x(count.quantity) }} data-mark="actual-rule">
                <span className="absolute inset-y-0 block w-0.5 -translate-x-1/2 bg-text-primary" />
                <span className="absolute -top-1 left-1 -translate-y-full whitespace-nowrap text-xs font-semibold">{count.ruleLabel}</span>
              </div>
            )}
          </div>
          <div className="relative mt-1 h-5">
            {card.milestones.map((m, i) => (
              <span
                key={`${i}:${m.id}`}
                className={`absolute -translate-x-1/2 whitespace-nowrap text-xs tabular-nums ${chosen === m ? "font-bold text-text-primary" : "text-text-secondary"}`}
                style={{ left: x(m.quantity) }}
              >
                {m.quantityLabel}
              </span>
            ))}
          </div>
        </div>
        <figcaption className="text-xs text-text-secondary">{card.quantityAxisTitle}</figcaption>
      </figure>

      {/* The strip: every original milestone, in owner order, with its own phase reading. */}
      <ul className="flex flex-wrap gap-2" aria-label={card.name}>
        {card.milestones.map((m, i) => (
          <MilestoneChip
            key={`${i}:${m.id}`}
            milestone={m}
            chosen={chosen === m}
            choosable={isUnique(card.milestones, m.id)}
            onChoose={() => hold("goals", m.id)}
          />
        ))}
      </ul>
      <SelectionUnavailable selection={selection} words={card.selectionUnavailable} />
      {chosen && (
        <div className="space-y-1 rounded-md bg-surface-deep p-2" data-soccer-chosen={chosen.id}>
          <p className="text-sm font-semibold">{chosen.label}</p>
          <Readout row={chosen} titles={card.titles} />
          <Timing key={chosen.id} timing={chosen.timing} />
        </div>
      )}
    </article>
  );
}

function MilestoneChip({
  milestone,
  chosen,
  choosable,
  onChoose,
}: {
  milestone: SoccerGoalsMilestone;
  chosen: boolean;
  choosable: boolean;
  onChoose: () => void;
}) {
  const before = pregameText(milestone.pregame);
  return (
    <li>
      <button type="button" aria-pressed={chosen} disabled={!choosable} onClick={onChoose} className={`${CHOICE} ${chosenClass(chosen)}`}>
        <span className="block font-semibold">{milestone.label}</span>
        <span className={`block ${before.value ? "tabular-nums" : "text-text-secondary"}`}>{before.text}</span>
        {milestone.current && <span className="block text-text-secondary">{currentText(milestone.current).text}</span>}
        {milestone.performance && <span className="block text-text-secondary">{milestone.performance}</span>}
        {milestone.result && <span className="block font-semibold">{resultText(milestone.result)}</span>}
      </button>
    </li>
  );
}

// ─── Both teams: the ring (BothTeamsScorePresentation10868) ─────────────────

const RING_R = 30;
const RING_C = 2 * Math.PI * RING_R;

function Ring({ value, label }: { value: number | null; label: string }) {
  return (
    <svg viewBox="0 0 80 80" className="h-20 w-20 shrink-0" role="img" aria-label={label} data-ring={value === null ? "empty" : "filled"}>
      <circle cx="40" cy="40" r={RING_R} fill="none" strokeWidth={8} className="stroke-surface-border" />
      {value !== null && (
        <circle
          data-mark="ring-arc"
          cx="40"
          cy="40"
          r={RING_R}
          fill="none"
          strokeWidth={8}
          strokeDasharray={`${(RING_C * Math.min(1, Math.max(0, value))).toFixed(2)} ${RING_C.toFixed(2)}`}
          transform="rotate(-90 40 40)"
          style={{ stroke: CHANCE }}
        />
      )}
    </svg>
  );
}

function BothCard({ card, held, hold }: { card: SoccerBothCard; held: Held; hold: Hold }) {
  const selection = selectExactlyOnce(card.outcomes, soccerRequestedId(held.both, card.defaultId, card.outcomes));
  const chosen = chosenRow(selection);
  const before = chosen ? pregameText(chosen.pregame) : null;
  const team = (t: SoccerBothCard["scoring"]["home"]) => (
    <div className="min-w-0">
      <dt className="break-words text-sm font-semibold">{t.name}</dt>
      <dd>
        <span className={t.value.kind === "value" ? "text-2xl font-bold tabular-nums" : "text-sm text-text-secondary"}>{t.value.text}</span>
        {t.status && <span className="block text-xs text-text-secondary">{t.status}</span>}
      </dd>
    </div>
  );
  return (
    <article className="space-y-3" data-soccer-card="both">
      <p className="text-xs font-semibold tracking-wide text-text-secondary">{card.eyebrow}</p>
      {card.beforeContext && <p className="text-sm text-text-secondary">{card.beforeContext}</p>}
      <div className="flex flex-wrap items-center gap-4">
        {chosen && before && (
          <div className="flex items-center gap-3">
            <div className="relative">
              <Ring value={pregameValue(chosen.pregame)} label={`${chosen.label} · ${card.titles.pregame}: ${before.text}`} />
              {before.value && (
                <span className="absolute inset-0 flex items-center justify-center text-base font-bold tabular-nums" aria-hidden="true">
                  {before.text}
                </span>
              )}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold">{chosen.label}</p>
              <p className="text-xs text-text-secondary">{card.titles.pregame}</p>
              {!before.value && <p className="text-sm text-text-secondary">{before.text}</p>}
            </div>
          </div>
        )}
        {/* An unavailable choice: the ring holds no number and says why (native `ring` → `.unselected`). */}
        {selection.kind === "unavailable" && (
          <div className="flex items-center gap-3">
            <Ring value={null} label={card.selectionUnavailable} />
            <SelectionUnavailable selection={selection} words={card.selectionUnavailable} />
          </div>
        )}
        <div>
          <p className="text-xs text-text-secondary">{card.scoring.title}</p>
          <dl className="mt-1 flex flex-wrap gap-x-5 gap-y-1">
            {team(card.scoring.home)}
            {team(card.scoring.away)}
          </dl>
          {card.scoring.clock && <p className="text-xs text-text-secondary">{card.scoring.clock}</p>}
        </div>
      </div>
      {/* Each outcome keeps its own figure in its own tile: never a complement of the other. */}
      <ul className="grid grid-cols-2 gap-2" aria-label={card.name}>
        {card.outcomes.map((o, i) => {
          const own = pregameText(o.pregame);
          return (
            <li key={`${i}:${o.id}`}>
              <button
                type="button"
                aria-pressed={chosen === o}
                disabled={!isUnique(card.outcomes, o.id)}
                onClick={() => hold("both", o.id)}
                className={`${CHOICE} w-full ${chosenClass(chosen === o)}`}
              >
                <span className="block font-semibold">{o.label}</span>
                <span className={`block ${own.value ? "text-base font-bold tabular-nums" : "text-text-secondary"}`}>{own.text}</span>
              </button>
            </li>
          );
        })}
      </ul>
      {chosen && (
        <div className="space-y-1 rounded-md bg-surface-deep p-2" data-soccer-chosen={chosen.id}>
          <Readout row={chosen} titles={card.titles} />
          <Timing key={chosen.id} timing={chosen.timing} />
        </div>
      )}
    </article>
  );
}

// ─── First team: the lollipop plot (FirstScorerComparisonPresentation10868) ─

function FirstCard({ card, held, hold }: { card: SoccerFirstCard; held: Held; hold: Hold }) {
  const selection = selectExactlyOnce(card.rows, soccerRequestedId(held.first, card.defaultId, card.rows));
  const chosen = chosenRow(selection);
  return (
    <article className="space-y-3" data-soccer-card="first">
      <div>
        <h4 className="text-base font-semibold">{card.title}</h4>
        {card.context && <p className="text-sm text-text-secondary">{card.context}</p>}
      </div>
      {chosen && (
        <div className="space-y-1 rounded-md bg-surface-deep p-2" data-soccer-chosen={chosen.id}>
          <p className="text-sm font-semibold">{chosen.label}</p>
          <Readout row={chosen} titles={card.titles} />
        </div>
      )}
      <SelectionUnavailable selection={selection} words={card.selectionUnavailable} />
      <figure className="space-y-2" data-first-plot="">
        <figcaption className="text-xs text-text-secondary">{card.plotTitle}</figcaption>
        <ul className="space-y-2" aria-label={card.name}>
          {card.rows.map((row, i) => {
            const before = pregameValue(row.pregame);
            const own = pregameText(row.pregame);
            const isChosen = chosen === row;
            return (
              <li key={`${i}:${row.id}`} data-first-row={row.id}>
                <button
                  type="button"
                  aria-pressed={isChosen}
                  disabled={!isUnique(card.rows, row.id)}
                  onClick={() => hold("first", row.id)}
                  className="block min-h-11 w-full text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand"
                >
                  <span className="flex items-baseline justify-between gap-2 text-sm">
                    <span className={`min-w-0 break-words ${isChosen ? "font-bold" : "font-medium"}`}>{row.label}</span>
                    <span className={own.value ? "whitespace-nowrap font-bold tabular-nums" : "text-text-secondary"}>{own.text}</span>
                  </span>
                  {/* The track: every row the same width and origin, so the scale is shared. */}
                  <span className="relative mt-1 block h-3">
                    <span className="absolute inset-x-0 top-1/2 block h-px bg-surface-border" />
                    {before !== null && (
                      <>
                        <span
                          data-mark="stem"
                          className="absolute left-0 top-1/2 block h-0.5 -translate-y-1/2"
                          style={{ width: at(before), background: CHANCE }}
                        />
                        <span className="absolute top-1/2 block" style={{ left: at(before) }}>
                          <Dot hollow={false} mark="pregame" size={10} emphasis={isChosen} />
                        </span>
                      </>
                    )}
                  </span>
                </button>
                {row.current && <p className="text-xs text-text-secondary">{`${card.titles.current}: ${currentText(row.current).text}`}</p>}
                {row.result && !row.current && (
                  <dl className="mt-1">
                    <ResultBadge title={card.titles.result} result={row.result} />
                  </dl>
                )}
              </li>
            );
          })}
        </ul>
        <div className="relative h-4 text-xs text-text-secondary">
          {CHANCE_TICKS.map((tick) => (
            <span key={tick.p} className={`absolute ${tick.p === 0 ? "" : tick.p === 1 ? "-translate-x-full" : "-translate-x-1/2"}`} style={{ left: at(tick.p) }}>
              {tick.text}
            </span>
          ))}
        </div>
      </figure>
      {card.scorePath && (
        <div data-first-checkpoints="">
          <p className="text-sm font-semibold">{card.scorePath.title}</p>
          <p className="text-xs text-text-secondary">{card.scorePath.note}</p>
          <ol className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {card.scorePath.observations.map((o) => (
              <li key={o.id} aria-label={o.spoken}>
                <span className="font-bold tabular-nums">{o.score}</span>
                <span className="text-text-secondary">{` · ${o.time}`}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
      {chosen && <Timing key={chosen.id} timing={chosen.timing} />}
    </article>
  );
}

// ─── Halves: the dot plot (PeriodOutcomeComparisonPresentation10868) ───────

type Shape = "circle" | "square" | "diamond";
/** Native `symbol`: home circle, away diamond, Draw square. */
const SHAPES: Record<string, Shape> = { home: "circle", away: "diamond", draw: "square" };

function ShapeMark({ shape, color, dim, mark }: { shape: Shape; color: string; dim: boolean; mark?: string }) {
  return (
    <svg viewBox="0 0 12 12" className={`h-3 w-3 ${dim ? "opacity-40" : ""}`} aria-hidden="true" data-mark={mark}>
      {shape === "circle" && <circle cx="6" cy="6" r="5" style={{ fill: color }} />}
      {shape === "square" && <rect x="1.5" y="1.5" width="9" height="9" style={{ fill: color }} />}
      {shape === "diamond" && <path d="M6 0.5 L11.5 6 L6 11.5 L0.5 6 Z" style={{ fill: color }} />}
    </svg>
  );
}

function HalvesCard({ card, held, hold, colors }: { card: SoccerHalvesCard; held: Held; hold: Hold; colors: SoccerStoryColors }) {
  const selection = selectExactlyOnce(card.series, soccerRequestedId(held.halves, card.defaultId, card.series));
  const series = chosenRow(selection);
  /** Only a resolved series dims the others; an unavailable choice dims nothing. */
  const dimmed = (s: SoccerHalfSeries) => series !== null && s !== series;
  const colorOf = (s: SoccerHalfSeries) => (s.id === "home" ? colors.home : s.id === "away" ? colors.away : "var(--series-3)");
  const n = card.periods.length;
  const px = (i: number) => ((i + 0.5) / n) * 100;
  const valueAt = (s: SoccerHalfSeries, periodId: string) => {
    const cell = s.cells.find((c) => c.periodId === periodId);
    return cell ? pregameValue(cell.pregame) : null;
  };
  return (
    <article className="space-y-3" data-soccer-card="halves">
      <p className="text-xs font-semibold tracking-wide text-text-secondary">{card.eyebrow}</p>
      <h4 className="text-base font-semibold">{card.title}</h4>
      <figure className="space-y-1" data-halves-plot="">
        <figcaption className="text-xs text-text-secondary">{`${card.plotTitle} · ${card.scaleCaption}`}</figcaption>
        <div className="pl-10 pr-2">
          <div className="relative h-36" role="img" aria-label={`${card.plotTitle}. ${card.pointExplanation} ${card.lineExplanation}`}>
            <ChanceGrid />
            {/* Lines join one outcome's chances in neighbouring halves; a missing chance breaks the line. */}
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible" aria-hidden="true">
              {card.series.flatMap((s, si) =>
                card.periods.slice(1).flatMap((p, i) => {
                  const a = valueAt(s, card.periods[i].id);
                  const b = valueAt(s, p.id);
                  if (a === null || b === null) return [];
                  return [
                    <line
                      key={`${si}:${s.id}:${p.id}`}
                      data-mark="half-line"
                      x1={px(i)}
                      x2={px(i + 1)}
                      y1={100 - a * 100}
                      y2={100 - b * 100}
                      vectorEffect="non-scaling-stroke"
                      strokeWidth={2}
                      opacity={dimmed(s) ? 0.3 : 1}
                      style={{ stroke: colorOf(s) }}
                    />,
                  ];
                }),
              )}
            </svg>
            {card.series.flatMap((s, si) =>
              card.periods.flatMap((p, i) => {
                const v = valueAt(s, p.id);
                if (v === null) return [];
                return [
                  <span
                    key={`${si}:${s.id}:${p.id}`}
                    className="absolute block -translate-x-1/2 translate-y-1/2"
                    style={{ left: `${px(i)}%`, bottom: at(v) }}
                    data-half-point={`${s.id}:${p.id}`}
                  >
                    <ShapeMark shape={SHAPES[s.id] ?? "circle"} color={colorOf(s)} dim={dimmed(s)} mark="pregame" />
                  </span>,
                ];
              }),
            )}
          </div>
          <div className="relative mt-1 h-5">
            {card.periods.map((p, i) => (
              <span key={p.id} className="absolute -translate-x-1/2 whitespace-nowrap text-xs text-text-secondary" style={{ left: `${px(i)}%` }}>
                {p.label}
              </span>
            ))}
          </div>
        </div>
        <p className="text-xs text-text-secondary">{card.pointExplanation}</p>
        <p className="text-xs text-text-secondary">{card.lineExplanation}</p>
      </figure>
      <div className="flex flex-wrap gap-2" role="group" aria-label={card.name}>
        {card.series.map((s, si) => (
          <button
            key={`${si}:${s.id}`}
            type="button"
            aria-pressed={series === s}
            disabled={!isUnique(card.series, s.id)}
            onClick={() => hold("halves", s.id)}
            className={`${CHOICE} inline-flex items-center gap-2 ${chosenClass(series === s)}`}
          >
            <ShapeMark shape={SHAPES[s.id] ?? "circle"} color={colorOf(s)} dim={false} />
            <span className="font-semibold">{s.label}</span>
          </button>
        ))}
      </div>
      <SelectionUnavailable selection={selection} words={card.selectionUnavailable} />
      {series && (
        <div className="space-y-2" data-soccer-chosen={series.id}>
          {card.resultsLead && <p className="text-sm font-semibold">{`${card.resultsLead} · ${series.label}`}</p>}
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {card.periods.map((p) => {
              const cell = series.cells.find((c) => c.periodId === p.id);
              return (
                <li key={p.id} className="rounded-md bg-surface-deep p-2">
                  <p className="text-sm font-semibold">{p.label}</p>
                  {cell ? (
                    <Readout row={cell} titles={card.titles} />
                  ) : (
                    <p className="text-sm text-text-secondary">{card.cellUnavailable}</p>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </article>
  );
}

// ─── Exact score: the heat map (ExactScoreMapPresentation10868) ─────────────

type Fill = { kind: "intensity"; fraction: number } | { kind: "offScale" } | { kind: "blank" };

/**
 * Native `ExactScoreMapGeometry10868.fill` + `ExactScoreMapCellArt10868.draw`
 * (ExactScoreMapPresentation10868.swift:722-724, 846-870): the PRE-MATCH chance
 * as a fraction of the owner's scale bound, drawn as the chance colour at
 * 0.55 × that fraction; a reading the scale cannot place is hatched, never
 * clamped; no reading (or no usable scale) is blank. Web's `probabilityHeat`
 * is an absolute three-band scale and cannot shade a 0–10% map, so this ports
 * native's own rule onto the design-token variable.
 */
export function exactCellFill(pregame: SoccerPregame, scale: SoccerExactScope["scale"]): Fill {
  const p = pregameValue(pregame);
  if (p === null || !scale) return { kind: "blank" };
  if (p < 0 || p > scale.upper) return { kind: "offScale" };
  return { kind: "intensity", fraction: p / scale.upper };
}

function FillLayer({ fill }: { fill: Fill }) {
  if (fill.kind === "blank") return null;
  if (fill.kind === "offScale") {
    return (
      <span
        aria-hidden="true"
        data-fill="offScale"
        className="absolute inset-0 block"
        style={{ backgroundImage: `repeating-linear-gradient(45deg, ${CHANCE} 0 1.5px, transparent 1.5px 6px)`, opacity: 0.6 }}
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      data-fill="intensity"
      data-fraction={fill.fraction.toFixed(4)}
      className="absolute inset-0 block"
      style={{ background: CHANCE, opacity: 0.55 * fill.fraction }}
    />
  );
}

/** Native corner marks on the chosen cell. */
function Corners() {
  const corner = "absolute block h-2 w-2 border-text-primary";
  return (
    <span aria-hidden="true" data-mark="selected">
      <span className={`${corner} left-0.5 top-0.5 border-l-2 border-t-2`} />
      <span className={`${corner} right-0.5 top-0.5 border-r-2 border-t-2`} />
      <span className={`${corner} bottom-0.5 left-0.5 border-b-2 border-l-2`} />
      <span className={`${corner} bottom-0.5 right-0.5 border-b-2 border-r-2`} />
    </span>
  );
}

/** What occupies one grid coordinate (native `ExactScoreMapSlot10868`). */
type ExactSlot = { kind: "original"; original: SoccerExactOriginal } | { kind: "notListed" } | { kind: "ambiguous" };

function ExactCard({ card, held, hold }: { card: SoccerExactCard; held: Held; hold: Hold }) {
  if (card.scopes.length === 0) return null;
  // Native `scopeSelection` (ExactScoreMapPresentation10868.swift:384-394): exact id, exactly once.
  const scopeSelection = selectExactlyOnce(card.scopes, soccerRequestedId(held.exactScope, card.defaultScopeId, card.scopes));
  const scope = chosenRow(scopeSelection);
  return (
    <article className="space-y-3" data-soccer-card="exact">
      <h4 className="text-base font-semibold">{card.title}</h4>
      <p className="text-sm text-text-secondary">{card.intro}</p>
      {/* The scope choices stay reachable whenever there is another to choose, or the held one is unavailable. */}
      {(card.scopes.length > 1 || scope === null) && (
        <div className="flex flex-wrap gap-2" role="group" aria-label={card.title}>
          {card.scopes.map((s, i) => (
            <button
              key={`${i}:${s.id}`}
              type="button"
              aria-pressed={s === scope}
              disabled={!isUnique(card.scopes, s.id)}
              onClick={() => hold("exactScope", s.id)}
              className={`${CHOICE} ${chosenClass(s === scope)} font-semibold`}
            >
              {s.label}
            </button>
          ))}
        </div>
      )}
      {scope ? (
        <ExactScopeMap card={card} scope={scope} held={held} hold={hold} />
      ) : (
        <SelectionUnavailable selection={scopeSelection} words={card.scopeUnavailable} />
      )}
    </article>
  );
}

function ExactScopeMap({ card, scope, held, hold }: { card: SoccerExactCard; scope: SoccerExactScope; held: Held; hold: Hold }) {
  const heldKey = `exact:${scope.id}`;
  // Native `originalSelection` (L396-405): exact id within this scope, exactly once; no default score.
  const selection = selectExactlyOnce(scope.originals, held[heldKey] ?? null);
  const chosen = chosenRow(selection);
  const slotAt = (home: number, away: number): ExactSlot => {
    const found = scope.originals.filter((o) => o.placement.kind === "grid" && o.placement.home === home && o.placement.away === away);
    if (found.length === 0) return { kind: "notListed" };
    return found.length === 1 ? { kind: "original", original: found[0] } : { kind: "ambiguous" };
  };
  // Named choices: every original the grid cannot place exactly (non-grid, off the axes, or a shared coordinate).
  const named = scope.originals.filter(
    (o) =>
      o.placement.kind === "nonGrid" ||
      !scope.rows.includes(o.placement.home) ||
      !scope.columns.includes(o.placement.away) ||
      slotAt(o.placement.home, o.placement.away).kind === "ambiguous",
  );
  const slots = scope.rows.flatMap((h) => scope.columns.map((a) => slotAt(h, a)));
  const fills = scope.originals.map((o) => exactCellFill(o.pregame, scope.scale));
  const use = {
    offScale: fills.some((f) => f.kind === "offScale"),
    notListed: slots.some((s) => s.kind === "notListed"),
    unavailable: slots.some((s) => s.kind === "ambiguous" || (s.kind === "original" && pregameValue(s.original.pregame) === null)),
    result: scope.originals.some((o) => o.result?.kind === "won"),
  };
  const spoken = (o: SoccerExactOriginal) =>
    [o.label, `${card.titles.pregame}: ${pregameText(o.pregame).text}`, o.result && o.result.kind !== "unconfirmed" ? `${card.titles.result}: ${resultText(o.result)}` : null]
      .filter(Boolean)
      .join(". ");
  const swatch = (children: ReactNode, extra = "") => (
    <span className={`relative inline-block h-4 w-4 shrink-0 overflow-hidden rounded-sm border border-surface-border bg-surface-card ${extra}`}>{children}</span>
  );
  return (
    <>
      {scope.actual && (
        <p className="text-sm" data-exact-actual="">
          <span className="text-text-secondary">{`${scope.actual.title}: `}</span>
          <span className="font-semibold">{scope.actual.text}</span>
        </p>
      )}
      {!scope.scale && <p className="text-sm text-text-secondary">{card.scaleUnavailable}</p>}

      <div className="overflow-x-auto">
        <table className="border-separate" style={{ borderSpacing: 3 }} data-exact-map={scope.id}>
          <caption className="pb-1 text-left text-xs text-text-secondary">{`${card.rowsTitle} · ${card.columnsTitle}`}</caption>
          <thead>
            <tr>
              <th scope="col">
                <span className="sr-only">{card.rowsTitle}</span>
              </th>
              {scope.columns.map((away) => (
                <th key={away} scope="col" className="text-xs font-semibold tabular-nums text-text-secondary">
                  {away}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {scope.rows.map((home) => (
              <tr key={home}>
                <th scope="row" className="pr-1 text-xs font-semibold tabular-nums text-text-secondary">
                  {home}
                </th>
                {scope.columns.map((away) => {
                  const slot = slotAt(home, away);
                  if (slot.kind === "notListed") {
                    return (
                      <td key={away} data-cell="notListed" className="h-10 w-10 rounded border border-dashed border-surface-border">
                        <span className="sr-only">{card.notListed}</span>
                      </td>
                    );
                  }
                  if (slot.kind === "ambiguous") {
                    // More than one original names it: nothing is chosen here; each is a named choice below.
                    return (
                      <td key={away} data-cell="ambiguous" className="h-10 w-10 rounded border border-surface-border text-center text-xs text-text-secondary">
                        {card.unavailableMark}
                      </td>
                    );
                  }
                  const original = slot.original;
                  const fill = exactCellFill(original.pregame, scope.scale);
                  const isChosen = chosen === original;
                  const confirmed = original.result?.kind === "won";
                  return (
                    <td key={away} className="h-10 w-10 p-0" data-cell={original.id}>
                      <button
                        type="button"
                        aria-pressed={isChosen}
                        aria-label={spoken(original)}
                        disabled={!isUnique(scope.originals, original.id)}
                        onClick={() => hold(heldKey, original.id)}
                        data-confirmed={confirmed ? "" : undefined}
                        className={`relative block h-10 w-10 overflow-hidden rounded border bg-surface-card focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand ${
                          confirmed ? "border-2 border-text-primary" : "border-surface-border"
                        }`}
                      >
                        <FillLayer fill={fill} />
                        {pregameValue(original.pregame) === null && (
                          <span aria-hidden="true" className="relative text-xs text-text-secondary">
                            {card.unavailableMark}
                          </span>
                        )}
                        {isChosen && <Corners />}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* The key: the scale's own ticks, then only the marks this scope uses. */}
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-secondary" data-exact-legend="">
        {scope.scale && (
          <li className="flex flex-wrap items-center gap-1">
            <span>{card.legend.scaleTitle}</span>
            {scope.scale.ticks.map((tick) => (
              <span key={tick.fraction} className="inline-flex items-center gap-1">
                {swatch(<FillLayer fill={{ kind: "intensity", fraction: tick.fraction }} />)}
                <span className="tabular-nums">{tick.text}</span>
              </span>
            ))}
          </li>
        )}
        {use.offScale && (
          <li className="flex items-center gap-1">
            {swatch(<FillLayer fill={{ kind: "offScale" }} />)}
            {card.legend.offScale}
          </li>
        )}
        {use.notListed && (
          <li className="flex items-center gap-1">
            {swatch(null, "border-dashed")}
            {card.legend.notListed}
          </li>
        )}
        {use.unavailable && <li>{card.legend.unavailable}</li>}
        {use.result && (
          <li className="flex items-center gap-1">
            {swatch(null, "border-2 border-text-primary")}
            {card.legend.result}
          </li>
        )}
        <li className="flex items-center gap-1">
          {swatch(<Corners />)}
          {card.legend.selection}
        </li>
      </ul>

      {named.length > 0 && (
        <div>
          <p className="text-sm font-semibold">{card.otherChoicesTitle}</p>
          <ul className="mt-1 flex flex-wrap gap-2">
            {named.map((o, i) => {
              const own = pregameText(o.pregame);
              return (
                <li key={`${i}:${o.id}`}>
                  <button
                    type="button"
                    aria-pressed={chosen === o}
                    disabled={!isUnique(scope.originals, o.id)}
                    onClick={() => hold(heldKey, o.id)}
                    className={`${CHOICE} ${chosenClass(chosen === o)}`}
                  >
                    <span className="block font-semibold">{o.label}</span>
                    <span className={`block ${own.value ? "tabular-nums" : "text-text-secondary"}`}>{own.text}</span>
                    {o.result && o.result.kind !== "unconfirmed" && <span className="block font-semibold">{resultText(o.result)}</span>}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {chosen ? (
        <div className="space-y-1 rounded-md bg-surface-deep p-2" data-soccer-exact-chosen={chosen.id}>
          <p className="text-sm font-semibold">{chosen.label}</p>
          <Readout row={chosen} titles={card.titles} />
          <Timing key={chosen.id} timing={chosen.timing} />
        </div>
      ) : selection.kind === "unavailable" ? (
        <SelectionUnavailable selection={selection} words={card.selectionUnavailable} />
      ) : (
        <p className="text-sm text-text-secondary">{card.noSelection}</p>
      )}
    </>
  );
}

// ─── The stream ────────────────────────────────────────────────────────────

function CardBody({ card, held, hold, colors }: { card: SoccerStoryCard; held: Held; hold: Hold; colors: SoccerStoryColors }) {
  switch (card.id) {
    case "goals":
      return <GoalsCard card={card} held={held} hold={hold} />;
    case "both":
      return <BothCard card={card} held={held} hold={hold} />;
    case "first":
      return <FirstCard card={card} held={held} hold={hold} />;
    case "halves":
      return <HalvesCard card={card} held={held} hold={hold} colors={colors} />;
    case "exact":
      return <ExactCard card={card} held={held} hold={hold} />;
    default:
      return null;
  }
}

/** The reader's place in one reading scope: the story they moved to and their held choices. */
interface SoccerReading {
  scope: string;
  shownId: string | null;
  held: Held;
}

const freshReading = (scope: string): SoccerReading => ({ scope, shownId: null, held: {} });

export default function SoccerMatchStories({ stream, colors = DEFAULT_COLORS }: { stream: SoccerStoryStream; colors?: SoccerStoryColors }) {
  const headingId = useId();
  const [stored, setStored] = useState<SoccerReading>(() => freshReading(stream.scope));
  // A new event or phase is a new reading: nothing of the old scope's story or
  // choices survives (native stream scope, "soccer:<event id>:<phase>"). A
  // refresh in the same scope keeps every held id, available or not. Adjusted
  // while rendering, so no frame shows the old scope's choices; no effect,
  // timer or key.
  if (stored.scope !== stream.scope) setStored(freshReading(stream.scope));
  const reading = stored.scope === stream.scope ? stored : freshReading(stream.scope);
  const { shownId, held } = reading;
  const write = (change: (current: SoccerReading) => SoccerReading) =>
    setStored((prev) => change(prev.scope === stream.scope ? prev : freshReading(stream.scope)));
  const setShownId = (id: string) => write((current) => ({ ...current, shownId: id }));
  const cards = stream.cards;
  const count = cards.length;
  // The card the reader moved to, while it is still offered; else the first.
  const index = Math.max(0, cards.findIndex((c) => c.id === shownId));
  const card = cards[index] ?? null;
  const previous = count > 1 ? cards[(index + count - 1) % count] : null;
  const next = count > 1 ? cards[(index + 1) % count] : null;
  const hold: Hold = (key, value) => write((current) => ({ ...current, held: { ...current.held, [key]: value } }));

  return (
    <section aria-labelledby={headingId} aria-roledescription="story stream" className="space-y-3" data-soccer-stories={count}>
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id={headingId} className="text-base font-semibold">
          {stream.heading}
        </h3>
        {count > 1 && card && (
          <p className="text-sm text-text-secondary" aria-live="polite">
            {`${index + 1} of ${count} · ${card.name}`}
          </p>
        )}
      </header>

      {stream.manualStatus && <p className="text-sm text-text-secondary">{stream.manualStatus}</p>}

      {card ? (
        <div className="rounded-lg border border-surface-border p-3">
          <CardBody card={card} held={held} hold={hold} colors={colors} />
        </div>
      ) : (
        <p className="rounded-lg bg-surface-deep p-3 text-sm text-text-secondary">{stream.emptyWords}</p>
      )}

      {previous && next && (
        <nav aria-label={stream.storiesLabel} className="flex flex-wrap justify-between gap-2">
          <button
            type="button"
            onClick={() => setShownId(previous.id)}
            className="min-h-11 rounded-md border border-surface-border px-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand"
          >
            {PREVIOUS}
            <span className="font-normal text-text-secondary">{` · ${previous.name}`}</span>
          </button>
          <button
            type="button"
            onClick={() => setShownId(next.id)}
            className="min-h-11 rounded-md border border-surface-border px-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand"
          >
            {NEXT}
            <span className="font-normal text-text-secondary">{` · ${next.name}`}</span>
          </button>
        </nav>
      )}
    </section>
  );
}
