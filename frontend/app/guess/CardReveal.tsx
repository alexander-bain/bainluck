"use client";

// The back of a card: what the world thinks, with every player's guess on the
// same line so the misses can be seen at a glance.
//
//   chance    the world's number on a 0-to-100 line
//   given     the same, plus the two numbers side by side as bars
//   rest      the same, plus the field split into the favorites and the rest
//   count     the world's count on a 0-to-max line, and the dots
//   duo       two lines, one for each number

import { duoParts } from "@/lib/guess/engine";
import type { ChanceCard, CountCard, DuoCard, PackCard } from "@/lib/guess/types";

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
            className={`absolute top-4 flex h-6 w-6 -translate-x-1/2 items-center justify-center rounded-full border-2 border-white text-[11px] font-black text-white ${mark.dot}`}
            style={{ left: at(mark.value) }}
          >
            {initial(mark.name)}
          </div>
        ))}
      </div>
      <div className="mx-3 flex justify-between text-[11px] font-semibold text-text-secondary">
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
      <span className={`w-28 shrink-0 text-xs leading-tight text-text-primary ${strong ? "font-black" : "font-semibold"}`}>{label}</span>
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
        <div className="text-xs font-bold uppercase tracking-wide text-text-secondary">The world says</div>
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
        <div className="text-xs font-bold uppercase tracking-wide text-text-secondary">The world counts</div>
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
      <div className="text-center text-xs font-bold uppercase tracking-wide text-text-secondary">The world says</div>
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

export default function CardReveal({ card, slots }: { card: PackCard; slots: RevealSlot[] }) {
  switch (card.kind) {
    case "chance":
      return <ChanceReveal card={card} slots={slots} />;
    case "count":
      return <CountReveal card={card} slots={slots} />;
    case "duo":
      return <DuoReveal card={card} slots={slots} />;
  }
}
