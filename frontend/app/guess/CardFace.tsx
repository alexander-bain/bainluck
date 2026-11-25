"use client";

// The front of a card: its picture and the control a player answers with.
// Each kind of card looks and works differently on purpose. Three rounds of
// playtesting asked for "more visual diversity between cards", and a card that
// compares two things should not look like a card that asks for one number.

import { useState } from "react";

import { ORDER_PERMS } from "@/lib/guess/engine";
import type { CardOption, PackCard } from "@/lib/guess/types";

export interface TopicTint {
  panel: string;
  chip: string;
}

const TINTS: Record<string, TopicTint> = {
  Sports: { panel: "bg-emerald-50 border-emerald-200", chip: "bg-emerald-100 text-emerald-900" },
  "Screen and games": { panel: "bg-fuchsia-50 border-fuchsia-200", chip: "bg-fuchsia-100 text-fuchsia-900" },
  "Space and science": { panel: "bg-sky-50 border-sky-200", chip: "bg-sky-100 text-sky-900" },
  "Odd ones": { panel: "bg-amber-50 border-amber-200", chip: "bg-amber-100 text-amber-900" },
};

export function tintFor(topic: string): TopicTint {
  return TINTS[topic] ?? { panel: "bg-surface-elevated border-surface-border", chip: "bg-surface-elevated text-text-primary" };
}

interface FaceProps {
  card: PackCard;
  value: number | null;
  onChange: (value: number | null) => void;
}

const SELECTED = "border-text-primary bg-surface-card shadow-md ring-2 ring-text-primary";
const IDLE = "border-surface-border bg-surface-card";

function Tile({
  option,
  selected,
  tall,
  onPick,
}: {
  option: CardOption;
  selected: boolean;
  tall: boolean;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onPick}
      aria-pressed={selected}
      className={`flex w-full flex-col items-center justify-center rounded-3xl border-2 text-center transition-transform active:scale-95 ${
        selected ? SELECTED : IDLE
      } ${tall ? "min-h-[150px] gap-2 px-3 py-4" : "min-h-[96px] gap-1 px-2 py-2"}`}
    >
      <span className={tall ? "text-5xl" : "text-2xl"} aria-hidden="true">
        {option.emoji}
      </span>
      <span className="text-sm font-bold leading-snug text-text-primary">{option.label}</span>
    </button>
  );
}

function ChanceFace({ card, value, onChange }: FaceProps & { card: Extract<PackCard, { kind: "chance" }> }) {
  const shown = value ?? 50;
  const nudge = (by: number) => onChange(Math.max(0, Math.min(100, shown + by)));
  const tint = tintFor(card.topic);
  const step = (by: number) => (
    <button
      key={by}
      type="button"
      onClick={() => nudge(by)}
      aria-label={`${by > 0 ? "Up" : "Down"} ${Math.abs(by)}`}
      className="min-h-[44px] min-w-[44px] rounded-2xl border-2 border-surface-border bg-surface-card text-sm font-black text-text-primary active:scale-95"
    >
      {by > 0 ? `+${by}` : `−${Math.abs(by)}`}
    </button>
  );
  return (
    <div className="space-y-2">
      <div className={`relative flex h-24 items-center justify-center overflow-hidden rounded-3xl border-2 ${tint.panel}`} aria-hidden="true">
        <span className="absolute left-8 top-3 -rotate-12 text-3xl">{card.extras[0]}</span>
        <span className="text-6xl">{card.emoji}</span>
        <span className="absolute bottom-3 right-8 rotate-12 text-3xl">{card.extras[1]}</span>
      </div>
      <div className="flex items-center justify-between gap-1">
        <div className="flex gap-1">{[-5, -1].map(step)}</div>
        <div className="text-5xl font-black tabular-nums text-text-primary" data-testid="guess-number">
          {shown}%
        </div>
        <div className="flex gap-1">{[1, 5].map(step)}</div>
      </div>
      <input
        type="range"
        min={0}
        max={100}
        step={1}
        value={shown}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label="Your guess, from 0 to 100 percent"
        className="h-10 w-full accent-accent-brand"
      />
      <div className="flex justify-between text-xs font-semibold text-text-secondary">
        <span>0% never</span>
        <span>50% coin flip</span>
        <span>100% certain</span>
      </div>
    </div>
  );
}

function CountFace({ card, value, onChange }: FaceProps & { card: Extract<PackCard, { kind: "count" }> }) {
  const tint = tintFor(card.topic);
  return (
    <div className="space-y-4">
      <div className={`grid grid-cols-2 gap-2 rounded-3xl border-2 p-3 ${tint.panel}`}>
        {card.items.map((item) => (
          <div key={item.label} className="flex items-center gap-2 rounded-2xl bg-surface-card px-3 py-2">
            <span className="text-xl" aria-hidden="true">
              {item.emoji}
            </span>
            <span className="text-sm font-bold leading-tight text-text-primary">{item.label}</span>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1.5" role="group" aria-label="How many">
        {Array.from({ length: card.max + 1 }, (_, n) => (
          <button
            key={n}
            type="button"
            onClick={() => onChange(n)}
            aria-pressed={value === n}
            className={`min-h-[52px] rounded-2xl border-2 text-xl font-black tabular-nums active:scale-95 ${
              value === n ? "border-text-primary bg-text-primary text-white" : "border-surface-border bg-surface-card text-text-primary"
            }`}
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  );
}

function PickFace({ card, value, onChange }: FaceProps & { card: Extract<PackCard, { kind: "pick" }> }) {
  const pair = card.options.length === 2;
  return (
    <div className="relative grid grid-cols-2 gap-3">
      {card.options.map((option, index) => (
        <Tile key={option.label} option={option} selected={value === index} tall={pair} onPick={() => onChange(index)} />
      ))}
      {pair && (
        <span
          className="pointer-events-none absolute left-1/2 top-1/2 flex h-10 w-10 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-text-primary text-xs font-black text-white"
          aria-hidden="true"
        >
          OR
        </span>
      )}
    </div>
  );
}

function LadderFace({ card, value, onChange }: FaceProps & { card: Extract<PackCard, { kind: "ladder" }> }) {
  const tint = tintFor(card.topic);
  return (
    <div className={`relative space-y-2 rounded-3xl border-2 p-3 ${tint.panel}`}>
      {card.options.map((option, index) => (
        // Each rung starts further in, so the list reads as steps in time.
        <div key={option.label} style={{ paddingLeft: `${index * 22}px` }}>
          <button
            type="button"
            onClick={() => onChange(index)}
            aria-pressed={value === index}
            className={`block min-h-[46px] w-full rounded-2xl border-2 px-4 text-left text-lg font-black active:scale-95 ${
              value === index ? "border-text-primary bg-text-primary text-white" : "border-surface-border bg-surface-card text-text-primary"
            }`}
          >
            {option.label}
          </button>
        </div>
      ))}
      <span className="pointer-events-none absolute bottom-3 left-3 text-4xl" aria-hidden="true">
        {card.emoji}
      </span>
    </div>
  );
}

function OrderFace({ card, onChange }: FaceProps & { card: Extract<PackCard, { kind: "order" }> }) {
  const [picked, setPicked] = useState<number[]>([]);
  const tap = (item: number) => {
    if (picked.includes(item)) return;
    const next = [...picked, item];
    // Two taps settle all three: the one left over goes last.
    const full = next.length === 2 ? [...next, [0, 1, 2].find((i) => !next.includes(i)) as number] : next;
    setPicked(full);
    if (full.length === 3) {
      onChange(ORDER_PERMS.findIndex((perm) => perm.every((value, i) => value === full[i])));
    }
  };
  const clear = () => {
    setPicked([]);
    onChange(null);
  };
  return (
    <div className="space-y-2">
      {card.items.map((item, index) => {
        const rank = picked.indexOf(index);
        return (
          <button
            key={item.label}
            type="button"
            onClick={() => tap(index)}
            aria-label={rank >= 0 ? `${item.label}, number ${rank + 1}` : item.label}
            className={`flex min-h-[60px] w-full items-center gap-3 rounded-3xl border-2 px-4 py-2 text-left active:scale-95 ${
              rank >= 0 ? SELECTED : IDLE
            }`}
          >
            <span
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-base font-black ${
                rank >= 0 ? "bg-text-primary text-white" : "border-2 border-dashed border-surface-border text-text-muted"
              }`}
            >
              {rank >= 0 ? rank + 1 : ""}
            </span>
            <span className="text-2xl" aria-hidden="true">
              {item.emoji}
            </span>
            <span className="text-sm font-bold leading-snug text-text-primary">{item.label}</span>
          </button>
        );
      })}
      <div className="flex items-center justify-between px-1 text-xs font-semibold text-text-secondary">
        <span>Tap the surest first.</span>
        {picked.length > 0 && (
          <button type="button" onClick={clear} className="min-h-[32px] font-bold text-text-primary underline underline-offset-2">
            Start again
          </button>
        )}
      </div>
    </div>
  );
}

export default function CardFace({ card, value, onChange }: FaceProps) {
  switch (card.kind) {
    case "chance":
      return <ChanceFace card={card} value={value} onChange={onChange} />;
    case "count":
      return <CountFace card={card} value={value} onChange={onChange} />;
    case "pick":
      return <PickFace card={card} value={value} onChange={onChange} />;
    case "ladder":
      return <LadderFace card={card} value={value} onChange={onChange} />;
    case "order":
      return <OrderFace card={card} value={value} onChange={onChange} />;
  }
}
