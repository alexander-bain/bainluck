"use client";

// The back of a card: what the world thinks, drawn the way that suits the card.
// A number on a line for a chance, bars for a pick, steps for a ladder, a tally
// for a count, a ranked list for an order.

import { rightOrder } from "@/lib/guess/engine";
import type { CardOption, PackCard } from "@/lib/guess/types";

/** One player's answer on this card, with the color they wear everywhere on the page. */
export interface RevealSlot {
  name: string;
  guess: number;
  points: number;
  dot: string;
  house: boolean;
}

function initial(name: string): string {
  return name.replace(/^The /, "").slice(0, 1).toUpperCase();
}

function Dots({ slots }: { slots: RevealSlot[] }) {
  if (slots.length === 0) return null;
  return (
    <span className="flex flex-wrap gap-1">
      {slots.map((slot) => (
        <span
          key={slot.name}
          title={slot.name}
          className={`flex h-6 min-w-[24px] items-center justify-center rounded-full px-1 text-[11px] font-black text-white ${slot.dot}`}
        >
          {initial(slot.name)}
        </span>
      ))}
    </span>
  );
}

function Bar({ percent, strong }: { percent: number | null; strong: boolean }) {
  return (
    <span className="block h-2.5 w-full overflow-hidden rounded-full bg-surface-elevated">
      <span
        className={`block h-full rounded-full ${strong ? "bg-accent-brand" : "bg-text-muted"}`}
        style={{ width: `${Math.max(2, percent ?? 0)}%` }}
      />
    </span>
  );
}

function ChanceReveal({ card, slots }: { card: Extract<PackCard, { kind: "chance" }>; slots: RevealSlot[] }) {
  return (
    <div>
      <div className="text-center">
        <div className="text-xs font-bold uppercase tracking-wide text-text-secondary">The world says</div>
        <div className="text-6xl font-black tabular-nums text-text-primary" data-testid="world-number">
          {card.answer}%
        </div>
      </div>
      <div className="relative mx-3 mt-3 h-14" aria-hidden="true">
        <div className="absolute left-0 right-0 top-6 h-2 rounded-full bg-surface-elevated" />
        <div className="absolute top-2 h-10 w-1 -translate-x-1/2 rounded bg-text-primary" style={{ left: `${card.answer}%` }} />
        {slots.map((slot) => (
          <div
            key={slot.name}
            className={`absolute top-4 flex h-6 w-6 -translate-x-1/2 items-center justify-center rounded-full border-2 border-white text-[11px] font-black text-white ${slot.dot}`}
            style={{ left: `${slot.guess}%` }}
          >
            {initial(slot.name)}
          </div>
        ))}
      </div>
      <div className="mx-3 flex justify-between text-[11px] font-semibold text-text-secondary">
        <span>0%</span>
        <span>50%</span>
        <span>100%</span>
      </div>
    </div>
  );
}

function OptionRow({
  option,
  answer,
  pickers,
  rank,
}: {
  option: CardOption;
  answer: boolean;
  pickers: RevealSlot[];
  rank?: number;
}) {
  return (
    <div className={`rounded-2xl border-2 px-3 py-2 ${answer ? "border-accent-brand bg-accent-brand/10" : "border-surface-border bg-surface-card"}`}>
      <div className="flex items-center gap-2">
        {rank !== undefined && (
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-text-primary text-xs font-black text-white">{rank}</span>
        )}
        {option.emoji && (
          <span className="text-xl" aria-hidden="true">
            {option.emoji}
          </span>
        )}
        <span className="min-w-0 flex-1 text-sm font-bold leading-snug text-text-primary">{option.label}</span>
        <span className="shrink-0 text-base font-black tabular-nums text-text-primary">{option.percent === null ? "" : `${option.percent}%`}</span>
        {answer && (
          <span className="shrink-0 text-base font-black text-accent-brand" aria-label="the answer">
            ✓
          </span>
        )}
      </div>
      {option.percent !== null && (
        <div className="mt-1.5">
          <Bar percent={option.percent} strong={answer} />
        </div>
      )}
      {pickers.length > 0 && (
        <div className="mt-1.5">
          <Dots slots={pickers} />
        </div>
      )}
    </div>
  );
}

function PickReveal({ card, slots }: { card: Extract<PackCard, { kind: "pick" | "ladder" }>; slots: RevealSlot[] }) {
  const headline =
    card.kind === "ladder"
      ? card.options[card.answer].percent === null
        ? "The world does not get past even"
        : `The world gets past even ${card.options[card.answer].label.toLowerCase()}`
      : card.flavor === "match"
        ? `Nearest to ${card.target}%`
        : card.flavor === "longshot"
          ? "The longest shot"
          : "The world says";
  return (
    <div className="space-y-2">
      <div className="text-center text-xs font-bold uppercase tracking-wide text-text-secondary">{headline}</div>
      {card.options.map((option, index) => (
        <OptionRow key={option.label} option={option} answer={index === card.answer} pickers={slots.filter((s) => s.guess === index)} />
      ))}
    </div>
  );
}

function CountReveal({ card }: { card: Extract<PackCard, { kind: "count" }> }) {
  return (
    <div className="space-y-2">
      <div className="text-center">
        <div className="text-xs font-bold uppercase tracking-wide text-text-secondary">The world counts</div>
        <div className="text-6xl font-black tabular-nums text-text-primary" data-testid="world-number">
          {card.answer}
        </div>
      </div>
      {card.items.map((item) => {
        const over = (item.percent ?? 0) >= 50;
        return (
          <div key={item.label} className="flex items-center gap-2 rounded-2xl border-2 border-surface-border bg-surface-card px-3 py-2">
            <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-black text-white ${over ? "bg-accent-brand" : "bg-text-muted"}`}>
              {over ? "✓" : "✕"}
            </span>
            <span className="min-w-0 flex-1 text-sm font-bold text-text-primary">{item.label}</span>
            <span className="w-24 shrink-0">
              <Bar percent={item.percent} strong={over} />
            </span>
            <span className="w-11 shrink-0 text-right text-base font-black tabular-nums text-text-primary">{item.percent}%</span>
          </div>
        );
      })}
    </div>
  );
}

function OrderReveal({ card }: { card: Extract<PackCard, { kind: "order" }> }) {
  return (
    <div className="space-y-2">
      <div className="text-center text-xs font-bold uppercase tracking-wide text-text-secondary">The world&apos;s order</div>
      {rightOrder(card).map((item, position) => (
        <OptionRow key={card.items[item].label} option={card.items[item]} answer={false} pickers={[]} rank={position + 1} />
      ))}
    </div>
  );
}

export default function CardReveal({ card, slots }: { card: PackCard; slots: RevealSlot[] }) {
  switch (card.kind) {
    case "chance":
      return <ChanceReveal card={card} slots={slots} />;
    case "count":
      return <CountReveal card={card} />;
    case "pick":
    case "ladder":
      return <PickReveal card={card} slots={slots} />;
    case "order":
      return <OrderReveal card={card} />;
  }
}
