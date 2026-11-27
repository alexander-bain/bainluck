"use client";

// The back of a card: what the world thinks, with every player's guess beside
// it so the hits and misses can be seen at a glance.
//
// A tap card lists what could be tapped, marks the right one, and puts each
// player's initial on the one they tapped:
//
//   side      the world's number, then "above 50%" and "below 50%"
//   versus    the two things, each with its number as a bar
//   four      the world's number, then the four numbers that were offered
//   leader    the four names, strongest first, each with its number as a bar
//
// A slider card puts every guess on one line:
//
//   chance    the world's number on a 0-to-100 line
//   given     the same, plus the two numbers side by side as bars
//   rest      the same, plus the field split into the favorites and the rest
//   count     the world's count on a 0-to-max line, and the dots
//   duo       two lines, one for each number

import { duoParts, fullGuess } from "@/lib/guess/engine";
import type { ChanceCard, CountCard, DuoCard, FourCard, LeaderCard, PackCard, SideCard, VersusCard } from "@/lib/guess/types";

/** One player's answer on this card, with the color they wear everywhere on the page. */
export interface RevealSlot {
  name: string;
  guess: number;
  points: number;
  dot: string;
  house: boolean;
}

interface Mark {
  name: string;
  value: number;
  dot: string;
}

function initial(name: string): string {
  return name.replace(/^The /, "").slice(0, 1).toUpperCase();
}

/** A line from 0 to `max` with the world's answer as a bar and each player as a dot. */
function Track({ answer, max, marks, ends }: { answer: number; max: number; marks: Mark[]; ends: [string, string, string] }) {
  const at = (value: number) => `${(Math.max(0, Math.min(max, value)) / max) * 100}%`;
  return (
    <div>
      <div className="relative mx-3 h-14" aria-hidden="true">
        <div className="absolute left-0 right-0 top-6 h-2 rounded-full bg-surface-elevated" />
        <div className="absolute top-2 h-10 w-1 -translate-x-1/2 rounded bg-text-primary" style={{ left: at(answer) }} />
        {marks.map((mark) => (
          <div
            key={mark.name}
            className={`absolute top-4 flex h-6 w-6 -translate-x-1/2 items-center justify-center rounded-full border-2 border-white text-xs font-black text-white ${mark.dot}`}
            style={{ left: at(mark.value) }}
          >
            {initial(mark.name)}
          </div>
        ))}
      </div>
      <div className="mx-3 flex justify-between text-xs font-semibold text-text-secondary">
        <span>{ends[0]}</span>
        <span>{ends[1]}</span>
        <span>{ends[2]}</span>
      </div>
    </div>
  );
}

const PERCENT_ENDS: [string, string, string] = ["0%", "50%", "100%"];

function BarRow({ label, percent, strong }: { label: string; percent: number; strong: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span className={`w-28 shrink-0 text-sm leading-tight text-text-primary ${strong ? "font-black" : "font-semibold"}`}>{label}</span>
      <span className="block h-3 min-w-0 flex-1 overflow-hidden rounded-full bg-surface-elevated">
        <span className={`block h-full rounded-full ${strong ? "bg-accent-brand" : "bg-text-muted"}`} style={{ width: `${Math.max(2, percent)}%` }} />
      </span>
      <span className="w-10 shrink-0 text-right text-sm font-black tabular-nums text-text-primary">{percent}%</span>
    </div>
  );
}

function ChanceReveal({ card, slots }: { card: ChanceCard; slots: RevealSlot[] }) {
  return (
    <div className="space-y-2">
      <div className="text-center">
        <div className="text-sm font-bold uppercase tracking-wide text-text-secondary">The world says</div>
        <div className="text-5xl font-black tabular-nums text-text-primary" data-testid="world-number">
          {card.answer}%
        </div>
      </div>
      <Track answer={card.answer} max={100} marks={slots.map((s) => ({ name: s.name, value: s.guess, dot: s.dot }))} ends={PERCENT_ENDS} />
      {card.given && (
        <div className="space-y-1.5 rounded-2xl border-2 border-surface-border bg-surface-card p-3" data-testid="given-bars">
          <BarRow label={card.given.label} percent={card.given.percent} strong={false} />
          <BarRow label={card.given.answerLabel} percent={card.answer} strong />
        </div>
      )}
      {card.parts && (
        <div className="space-y-1.5 rounded-2xl border-2 border-surface-border bg-surface-card p-3" data-testid="field-bars">
          {card.parts.map((part) => (
            <BarRow key={part.label} label={part.label} percent={part.percent} strong={false} />
          ))}
          <BarRow label="Anyone else" percent={card.answer} strong />
        </div>
      )}
    </div>
  );
}

function CountReveal({ card, slots }: { card: CountCard; slots: RevealSlot[] }) {
  const perRow = card.max > 20 ? Math.ceil(card.max / 2) : card.max;
  return (
    <div className="space-y-3">
      <div className="text-center">
        <div className="text-sm font-bold uppercase tracking-wide text-text-secondary">The world counts</div>
        <div className="text-5xl font-black tabular-nums text-text-primary" data-testid="world-number">
          {card.answer}
        </div>
        <div className="text-sm font-bold text-text-secondary">
          of {card.max} {card.noun}
        </div>
      </div>
      <div className="mx-3 grid gap-1" style={{ gridTemplateColumns: `repeat(${perRow}, minmax(0, 1fr))` }} aria-hidden="true">
        {Array.from({ length: card.max }, (_, i) => (
          <span
            key={i}
            className={`aspect-square rounded-full border-2 ${i < card.answer ? "border-accent-brand bg-accent-brand" : "border-surface-border bg-surface-card"}`}
          />
        ))}
      </div>
      <Track
        answer={card.answer}
        max={card.max}
        marks={slots.map((s) => ({ name: s.name, value: s.guess, dot: s.dot }))}
        ends={["0", String(Math.round(card.max / 2)), String(card.max)]}
      />
    </div>
  );
}

function DuoReveal({ card, slots }: { card: DuoCard; slots: RevealSlot[] }) {
  return (
    <div className="space-y-3">
      <div className="text-center text-sm font-bold uppercase tracking-wide text-text-secondary">The world says</div>
      {card.parts.map((part, i) => (
        <div key={part.label} className="rounded-2xl border-2 border-surface-border bg-surface-card px-1 pb-2 pt-3">
          <div className="flex items-center gap-2 px-2">
            <span className="text-2xl" aria-hidden="true">
              {part.emoji}
            </span>
            <span className="min-w-0 flex-1 text-sm font-bold leading-snug text-text-primary">{part.label}</span>
            <span className="shrink-0 text-3xl font-black tabular-nums text-text-primary" data-testid={`world-number-${i + 1}`}>
              {part.answer}%
            </span>
          </div>
          <Track
            answer={part.answer}
            max={100}
            marks={slots.map((s) => ({ name: s.name, value: duoParts(s.guess)[i], dot: s.dot }))}
            ends={PERCENT_ENDS}
          />
        </div>
      ))}
    </div>
  );
}

// ---- tap cards --------------------------------------------------------------

interface ChoiceRow {
  place: number;
  label: string;
  emoji?: string;
  /** The world's percent for this choice, or null when the choice is not a percent of its own. */
  percent: number | null;
}

/** What could be tapped, the right one marked, and who tapped what. */
function ChoiceRows({ rows, right, slots }: { rows: ChoiceRow[]; right: number; slots: RevealSlot[] }) {
  return (
    <ul className="space-y-1.5" data-testid="choices">
      {rows.map((row) => {
        const won = row.place === right;
        const who = slots.filter((s) => s.guess === row.place);
        return (
          <li
            key={row.place}
            data-right={won ? "yes" : undefined}
            className={`rounded-2xl border-2 bg-surface-card px-3 py-2 ${won ? "border-text-primary" : "border-surface-border"}`}
          >
            <div className="flex items-center gap-2">
              {row.emoji && (
                <span className="text-xl" aria-hidden="true">
                  {row.emoji}
                </span>
              )}
              <span className={`min-w-0 flex-1 text-sm leading-snug text-text-primary ${won ? "font-black" : "font-semibold"}`}>
                {row.label}
                {won && <span className="ml-1.5 whitespace-nowrap text-sm font-black text-text-primary">✓ right</span>}
              </span>
              {row.percent !== null && <span className="shrink-0 text-base font-black tabular-nums text-text-primary">{row.percent}%</span>}
            </div>
            {row.percent !== null && (
              <span className="mt-1 block h-2 overflow-hidden rounded-full bg-surface-elevated" aria-hidden="true">
                <span className={`block h-full rounded-full ${won ? "bg-accent-brand" : "bg-text-muted"}`} style={{ width: `${Math.max(2, row.percent)}%` }} />
              </span>
            )}
            {who.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {who.map((s) => (
                  <span key={s.name} className="flex items-center gap-1 rounded-full bg-surface-elevated py-0.5 pl-1 pr-2 text-xs font-bold text-text-primary">
                    <span className={`flex h-4 w-4 items-center justify-center rounded-full text-xs font-black text-white ${s.dot}`} aria-hidden="true">
                      {initial(s.name)}
                    </span>
                    {s.name}
                  </span>
                ))}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function WorldNumber({ percent }: { percent: number }) {
  return (
    <div className="text-center">
      <div className="text-sm font-bold uppercase tracking-wide text-text-secondary">The world says</div>
      <div className="text-5xl font-black tabular-nums text-text-primary" data-testid="world-number">
        {percent}%
      </div>
    </div>
  );
}

function SideReveal({ card, slots }: { card: SideCard; slots: RevealSlot[] }) {
  return (
    <div className="space-y-2">
      <WorldNumber percent={card.answer} />
      <ChoiceRows
        right={fullGuess(card)}
        slots={slots}
        rows={[
          { place: 1, label: "Above 50%", emoji: "⬆️", percent: null },
          { place: 0, label: "Below 50%", emoji: "⬇️", percent: null },
        ]}
      />
    </div>
  );
}

function VersusReveal({ card, slots }: { card: VersusCard; slots: RevealSlot[] }) {
  return (
    <div className="space-y-2">
      <div className="text-center text-sm font-bold uppercase tracking-wide text-text-secondary">The world says</div>
      <ChoiceRows
        right={fullGuess(card)}
        slots={slots}
        rows={card.options.map((option, place) => ({ place, label: option.label, emoji: option.emoji, percent: option.percent }))}
      />
    </div>
  );
}

function FourReveal({ card, slots }: { card: FourCard; slots: RevealSlot[] }) {
  const right = fullGuess(card);
  return (
    <div className="space-y-2">
      <WorldNumber percent={card.answer} />
      <ul className="grid grid-cols-4 gap-1.5" data-testid="choices">
        {card.options.map((percent, place) => {
          const won = place === right;
          const who = slots.filter((s) => s.guess === place);
          return (
            <li
              key={percent}
              data-right={won ? "yes" : undefined}
              className={`flex min-h-[64px] flex-col items-center rounded-2xl border-2 px-1 py-1.5 ${
                won ? "border-text-primary bg-text-primary text-white" : "border-surface-border bg-surface-card text-text-primary"
              }`}
            >
              <span className="text-lg font-black tabular-nums">{percent}%</span>
              <span className="mt-1 flex flex-wrap justify-center gap-0.5">
                {who.map((s) => (
                  <span
                    key={s.name}
                    title={s.name}
                    className={`flex h-5 w-5 items-center justify-center rounded-full border border-white text-xs font-black text-white ${s.dot}`}
                  >
                    {initial(s.name)}
                  </span>
                ))}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function LeaderReveal({ card, slots }: { card: LeaderCard; slots: RevealSlot[] }) {
  const rows = card.options
    .map((option, place) => ({ place, label: option.label, emoji: option.emoji, percent: option.percent }))
    .sort((a, b) => b.percent - a.percent);
  return (
    <div className="space-y-2">
      <div className="text-center text-sm font-bold uppercase tracking-wide text-text-secondary">The world says</div>
      <ChoiceRows right={fullGuess(card)} slots={slots} rows={rows} />
      {card.independent && <p className="text-center text-sm font-semibold text-text-secondary">Each is its own chance. More than one can happen.</p>}
    </div>
  );
}

export default function CardReveal({ card, slots }: { card: PackCard; slots: RevealSlot[] }) {
  switch (card.kind) {
    case "side":
      return <SideReveal card={card} slots={slots} />;
    case "versus":
      return <VersusReveal card={card} slots={slots} />;
    case "four":
      return <FourReveal card={card} slots={slots} />;
    case "leader":
      return <LeaderReveal card={card} slots={slots} />;
    case "chance":
      return <ChanceReveal card={card} slots={slots} />;
    case "count":
      return <CountReveal card={card} slots={slots} />;
    case "duo":
      return <DuoReveal card={card} slots={slots} />;
  }
}
