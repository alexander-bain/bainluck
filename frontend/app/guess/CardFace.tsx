"use client";

// The front of a card: its picture and the slider a player answers with.
//
// EVERY CARD IS A SLIDER (429: A). What changes from card to card is the
// picture above the slider, because playtesting asked for "more visual
// diversity between cards":
//
//   straight  a big picture of the subject
//   given     the number you are told, drawn as a bar, above the one you guess
//   rest      the three favorites crossed out, and "anyone else" lit up
//   count     a dot for every team, filling as you slide
//   duo       two sliders, one for each number

import { duoParts, isValidGuess, packDuo, startGuess } from "@/lib/guess/engine";
import type { ChanceCard, CountCard, DuoCard, PackCard } from "@/lib/guess/types";

export interface TopicTint {
  panel: string;
  chip: string;
}

const TINTS: Record<string, TopicTint> = {
  Sports: { panel: "bg-emerald-50 border-emerald-200", chip: "bg-emerald-100 text-emerald-900" },
  "Screen and games": { panel: "bg-fuchsia-50 border-fuchsia-200", chip: "bg-fuchsia-100 text-fuchsia-900" },
  "Stars and sky": { panel: "bg-sky-50 border-sky-200", chip: "bg-sky-100 text-sky-900" },
};

export function tintFor(topic: string): TopicTint {
  return TINTS[topic] ?? { panel: "bg-surface-elevated border-surface-border", chip: "bg-surface-elevated text-text-primary" };
}

interface FaceProps {
  card: PackCard;
  value: number;
  onChange: (value: number) => void;
}

/** A number, the buttons that nudge it, and the slider under it. */
function Dial({
  value,
  max,
  suffix,
  steps,
  label,
  testId,
  onChange,
}: {
  value: number;
  max: number;
  suffix: string;
  steps: number[];
  label: string;
  testId: string;
  onChange: (value: number) => void;
}) {
  const set = (next: number) => onChange(Math.max(0, Math.min(max, next)));
  const step = (by: number) => (
    <button
      key={by}
      type="button"
      onClick={() => set(value + by)}
      aria-label={`${by > 0 ? "Up" : "Down"} ${Math.abs(by)}`}
      className="min-h-[44px] min-w-[44px] rounded-2xl border-2 border-surface-border bg-surface-card text-sm font-black text-text-primary active:scale-95"
    >
      {by > 0 ? `+${by}` : `−${Math.abs(by)}`}
    </button>
  );
  return (
    <div>
      <div className="flex items-center justify-between gap-1">
        <div className="flex gap-1">{steps.filter((s) => s < 0).map(step)}</div>
        <div className="text-5xl font-black tabular-nums text-text-primary" data-testid={testId}>
          {value}
          {suffix}
        </div>
        <div className="flex gap-1">{steps.filter((s) => s > 0).map(step)}</div>
      </div>
      <input
        type="range"
        min={0}
        max={max}
        step={1}
        value={value}
        onChange={(e) => set(Number(e.target.value))}
        aria-label={label}
        data-testid={`${testId}-slider`}
        className="h-10 w-full accent-accent-brand"
      />
    </div>
  );
}

function PercentScale() {
  return (
    <div className="flex justify-between text-xs font-semibold text-text-secondary">
      <span>0% never</span>
      <span>50% coin flip</span>
      <span>100% certain</span>
    </div>
  );
}

function ChancePicture({ card }: { card: ChanceCard }) {
  const tint = tintFor(card.topic);

  if (card.given) {
    return (
      <div className={`rounded-3xl border-2 p-3 ${tint.panel}`} data-testid="given">
        <div className="flex items-center gap-3">
          <span className="text-4xl" aria-hidden="true">
            {card.emoji}
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[11px] font-black uppercase tracking-wide text-text-secondary">A number to go on</div>
            <div className="text-sm font-bold leading-snug text-text-primary">{card.given.text}</div>
          </div>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <span className="block h-3 flex-1 overflow-hidden rounded-full bg-surface-card">
            <span className="block h-full rounded-full bg-text-primary" style={{ width: `${card.given.percent}%` }} />
          </span>
          <span className="shrink-0 text-base font-black tabular-nums text-text-primary">{card.given.percent}%</span>
        </div>
      </div>
    );
  }

  if (card.parts) {
    return (
      <div className={`grid grid-cols-4 gap-1.5 rounded-3xl border-2 p-2 ${tint.panel}`} data-testid="favorites">
        {card.parts.map((part) => (
          <div key={part.label} className="flex min-h-[64px] flex-col items-center justify-center rounded-2xl bg-surface-card px-1 text-center opacity-70">
            <span className="text-lg" aria-hidden="true">
              🚫
            </span>
            <span className="text-xs font-bold text-text-secondary line-through">{part.label}</span>
          </div>
        ))}
        <div className="flex min-h-[64px] flex-col items-center justify-center rounded-2xl border-2 border-text-primary bg-surface-card px-1 text-center">
          <span className="text-2xl" aria-hidden="true">
            {card.emoji}
          </span>
          <span className="text-xs font-black text-text-primary">Anyone else</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`relative flex h-20 items-center justify-center overflow-hidden rounded-3xl border-2 ${tint.panel}`} aria-hidden="true">
      <span className="absolute left-8 top-2 -rotate-12 text-3xl">{card.extras[0]}</span>
      <span className="text-5xl">{card.emoji}</span>
      <span className="absolute bottom-2 right-8 rotate-12 text-3xl">{card.extras[1]}</span>
    </div>
  );
}

function ChanceFace({ card, value, onChange }: { card: ChanceCard; value: number; onChange: (value: number) => void }) {
  return (
    <div className="space-y-2">
      <ChancePicture card={card} />
      <Dial
        value={value}
        max={100}
        suffix="%"
        steps={[-5, -1, 1, 5]}
        label="Your guess, from 0 to 100 percent"
        testId="guess-number"
        onChange={onChange}
      />
      <PercentScale />
    </div>
  );
}

function CountFace({ card, value, onChange }: { card: CountCard; value: number; onChange: (value: number) => void }) {
  const tint = tintFor(card.topic);
  const perRow = card.max > 20 ? Math.ceil(card.max / 2) : card.max;
  return (
    <div className="space-y-2">
      <div className={`rounded-3xl border-2 p-3 ${tint.panel}`}>
        <div className="grid gap-1" style={{ gridTemplateColumns: `repeat(${perRow}, minmax(0, 1fr))` }} aria-hidden="true" data-testid="count-dots">
          {Array.from({ length: card.max }, (_, i) => (
            <span
              key={i}
              className={`aspect-square rounded-full border-2 ${i < value ? "border-text-primary bg-text-primary" : "border-surface-border bg-surface-card"}`}
            />
          ))}
        </div>
        <div className="mt-2 flex items-center justify-center gap-2 text-sm font-bold text-text-primary">
          <span className="text-xl" aria-hidden="true">
            {card.emoji}
          </span>
          One dot for each of the {card.max} {card.noun}.
        </div>
      </div>
      <Dial
        value={value}
        max={card.max}
        suffix=""
        steps={[-1, 1]}
        label={`Your guess, from 0 to ${card.max} ${card.noun}`}
        testId="guess-number"
        onChange={onChange}
      />
      <div className="flex justify-between text-xs font-semibold text-text-secondary">
        <span>0 none</span>
        <span>{Math.round(card.max / 2)} half</span>
        <span>{card.max} all</span>
      </div>
    </div>
  );
}

function DuoFace({ card, value, onChange }: { card: DuoCard; value: number; onChange: (value: number) => void }) {
  const tint = tintFor(card.topic);
  const both = duoParts(value);
  const set = (which: number, next: number) => {
    const clean = Math.max(0, Math.min(100, next));
    onChange(which === 0 ? packDuo(clean, both[1]) : packDuo(both[0], clean));
  };
  const step = (which: number, by: number) => (
    <button
      type="button"
      onClick={() => set(which, both[which] + by)}
      aria-label={`${by > 0 ? "Up" : "Down"} ${Math.abs(by)}`}
      className="min-h-[44px] min-w-[44px] shrink-0 rounded-2xl border-2 border-surface-border bg-surface-card text-sm font-black text-text-primary active:scale-95"
    >
      {by > 0 ? `+${by}` : `−${Math.abs(by)}`}
    </button>
  );
  // Two sliders have to fit one phone screen, so each keeps its number beside
  // its sentence and its nudge buttons at the ends of the slider.
  return (
    <div className="space-y-2">
      {card.parts.map((part, i) => (
        <div key={part.label} className={`rounded-3xl border-2 px-3 py-2 ${i === 0 ? tint.panel : "border-surface-border bg-surface-elevated"}`}>
          <div className="flex items-center gap-2">
            <span className="text-2xl" aria-hidden="true">
              {part.emoji}
            </span>
            <span className="min-w-0 flex-1 text-sm font-black leading-snug text-text-primary">{part.label}</span>
            <span className="shrink-0 text-3xl font-black tabular-nums text-text-primary" data-testid={`guess-number-${i + 1}`}>
              {both[i]}%
            </span>
          </div>
          <div className="mt-1 flex items-center gap-2">
            {step(i, -1)}
            <input
              type="range"
              min={0}
              max={100}
              step={1}
              value={both[i]}
              onChange={(e) => set(i, Number(e.target.value))}
              aria-label={`${part.label}: your guess, from 0 to 100 percent`}
              data-testid={`guess-number-${i + 1}-slider`}
              className="h-10 min-w-0 flex-1 accent-accent-brand"
            />
            {step(i, 1)}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function CardFace({ card, value, onChange }: FaceProps) {
  // A guess left over from another card never reaches a slider.
  const safe = isValidGuess(card, value) ? value : startGuess(card);
  switch (card.kind) {
    case "chance":
      return <ChanceFace card={card} value={safe} onChange={onChange} />;
    case "count":
      return <CountFace card={card} value={safe} onChange={onChange} />;
    case "duo":
      return <DuoFace card={card} value={safe} onChange={onChange} />;
  }
}
