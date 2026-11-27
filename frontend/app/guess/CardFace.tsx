"use client";

// The front of a card: its picture and the thing a player answers with.
//
// A TAP CARD (430: A) is answered with one tap, then locked in:
//
//   side      a picture of the subject, and two buttons: below 50%, above 50%
//   versus    two things, one above the other: tap the more likely
//   four      a picture of the subject, and four numbers: tap the world's
//   leader    four names: tap the favorite
//
// A SLIDER CARD (429: A) changes its picture from card to card, because
// playtesting asked for "more visual diversity between cards":
//
//   straight  a big picture of the subject
//   given     the number you are told, drawn as a bar, above the one you guess
//   rest      the three favorites crossed out, and "anyone else" lit up
//   count     a dot for every team, filling as you slide
//   duo       two sliders, one for each number

import { duoParts, isValidGuess, packDuo, startGuess } from "@/lib/guess/engine";
import type { ChanceCard, CountCard, DuoCard, FourCard, LeaderCard, PackCard, SideCard, VersusCard } from "@/lib/guess/types";

export interface TopicTint {
  panel: string;
  chip: string;
}

const TINTS: Record<string, TopicTint> = {
  Sports: { panel: "bg-emerald-50 border-emerald-200", chip: "bg-emerald-100 text-emerald-900" },
  "Screen and games": { panel: "bg-fuchsia-50 border-fuchsia-200", chip: "bg-fuchsia-100 text-fuchsia-900" },
  "Stars and sky": { panel: "bg-sky-50 border-sky-200", chip: "bg-sky-100 text-sky-900" },
  Stars: { panel: "bg-fuchsia-50 border-fuchsia-200", chip: "bg-fuchsia-100 text-fuchsia-900" },
  "Odd stuff": { panel: "bg-sky-50 border-sky-200", chip: "bg-sky-100 text-sky-900" },
};

export function tintFor(topic: string): TopicTint {
  return TINTS[topic] ?? { panel: "bg-surface-elevated border-surface-border", chip: "bg-surface-elevated text-text-primary" };
}

interface FaceProps {
  card: PackCard;
  /** The guess being made. `null` on a tap card until something is tapped. */
  value: number | null;
  onChange: (value: number) => void;
}

// ---- tap cards --------------------------------------------------------------

const TAP_BASE = "min-h-[64px] w-full rounded-3xl border-2 px-3 py-2 text-left transition-transform active:scale-95";
const TAP_ON = "border-text-primary bg-text-primary text-white";
const TAP_OFF = "border-surface-border bg-surface-card text-text-primary";

/** One thing to tap. The one tapped turns solid; nothing is sent until Lock in. */
function Tap({
  place,
  value,
  onChange,
  label,
  children,
  center,
}: {
  place: number;
  value: number | null;
  onChange: (value: number) => void;
  label: string;
  children: React.ReactNode;
  center?: boolean;
}) {
  const on = value === place;
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={label}
      onClick={() => onChange(place)}
      data-testid={`tap-${place}`}
      className={`${TAP_BASE} ${on ? TAP_ON : TAP_OFF} ${center ? "text-center" : ""}`}
    >
      {children}
    </button>
  );
}

/** The subject, drawn large, as on a plain slider card. */
function SubjectPicture({ topic, emoji, extras }: { topic: string; emoji: string; extras: string[] }) {
  const tint = tintFor(topic);
  return (
    <div className={`relative flex h-20 items-center justify-center overflow-hidden rounded-3xl border-2 ${tint.panel}`} aria-hidden="true">
      <span className="absolute left-8 top-2 -rotate-12 text-3xl">{extras[0]}</span>
      <span className="text-5xl">{emoji}</span>
      <span className="absolute bottom-2 right-8 rotate-12 text-3xl">{extras[1]}</span>
    </div>
  );
}

function SideFace({ card, value, onChange }: { card: SideCard; value: number | null; onChange: (value: number) => void }) {
  return (
    <div className="space-y-2">
      <SubjectPicture topic={card.topic} emoji={card.emoji} extras={card.extras} />
      <div className="grid grid-cols-2 gap-2">
        <Tap place={0} value={value} onChange={onChange} label="Below 50 percent" center>
          <span className="block text-2xl" aria-hidden="true">
            ⬇️
          </span>
          <span className="block text-lg font-black">Below 50%</span>
          <span className={`block text-sm font-semibold ${value === 0 ? "text-white" : "text-text-secondary"}`}>less likely than not</span>
        </Tap>
        <Tap place={1} value={value} onChange={onChange} label="Above 50 percent" center>
          <span className="block text-2xl" aria-hidden="true">
            ⬆️
          </span>
          <span className="block text-lg font-black">Above 50%</span>
          <span className={`block text-sm font-semibold ${value === 1 ? "text-white" : "text-text-secondary"}`}>more likely than not</span>
        </Tap>
      </div>
    </div>
  );
}

function VersusFace({ card, value, onChange }: { card: VersusCard; value: number | null; onChange: (value: number) => void }) {
  return (
    <div className="space-y-1.5">
      {card.options.map((option, i) => (
        <div key={option.label}>
          {i === 1 && (
            <div className="py-0.5 text-center text-sm font-black uppercase tracking-wide text-text-secondary" aria-hidden="true">
              or
            </div>
          )}
          <Tap place={i} value={value} onChange={onChange} label={option.label}>
            <span className="flex items-center gap-3">
              <span className="text-4xl" aria-hidden="true">
                {option.emoji}
              </span>
              <span className="min-w-0 flex-1 text-base font-black leading-snug">{option.label}</span>
            </span>
          </Tap>
        </div>
      ))}
    </div>
  );
}

function FourFace({ card, value, onChange }: { card: FourCard; value: number | null; onChange: (value: number) => void }) {
  return (
    <div className="space-y-2">
      <SubjectPicture topic={card.topic} emoji={card.emoji} extras={card.extras} />
      <div className="grid grid-cols-4 gap-1.5" data-testid="four-numbers">
        {card.options.map((percent, i) => (
          <Tap key={percent} place={i} value={value} onChange={onChange} label={`${percent} percent`} center>
            <span className="block text-2xl font-black tabular-nums">{percent}%</span>
          </Tap>
        ))}
      </div>
      <p className="text-center text-sm font-semibold text-text-secondary">One of these four is what the world says.</p>
    </div>
  );
}

function LeaderFace({ card, value, onChange }: { card: LeaderCard; value: number | null; onChange: (value: number) => void }) {
  return (
    <div className="grid grid-cols-2 gap-2" data-testid="leader-options">
      {card.options.map((option, i) => (
        <Tap key={option.label} place={i} value={value} onChange={onChange} label={option.label} center>
          <span className="block text-3xl" aria-hidden="true">
            {option.emoji}
          </span>
          <span className="block text-sm font-black leading-tight">{option.label}</span>
        </Tap>
      ))}
    </div>
  );
}

// ---- slider cards -----------------------------------------------------------

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
        className="h-10 w-full touch-none accent-accent-brand"
      />
    </div>
  );
}

function PercentScale() {
  return (
    <div className="flex justify-between text-sm font-semibold text-text-secondary">
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
            <div className="text-xs font-black uppercase tracking-wide text-text-secondary">A number to go on</div>
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
            <span className="text-sm font-bold text-text-secondary line-through">{part.label}</span>
          </div>
        ))}
        <div className="flex min-h-[64px] flex-col items-center justify-center rounded-2xl border-2 border-text-primary bg-surface-card px-1 text-center">
          <span className="text-2xl" aria-hidden="true">
            {card.emoji}
          </span>
          <span className="text-sm font-black text-text-primary">Anyone else</span>
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
      <div className="flex justify-between text-sm font-semibold text-text-secondary">
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
              className="h-10 min-w-0 flex-1 touch-none accent-accent-brand"
            />
            {step(i, 1)}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function CardFace({ card, value, onChange }: FaceProps) {
  // A guess left over from another card never reaches this one.
  const safe = isValidGuess(card, value) ? value : startGuess(card);
  switch (card.kind) {
    case "side":
      return <SideFace card={card} value={safe} onChange={onChange} />;
    case "versus":
      return <VersusFace card={card} value={safe} onChange={onChange} />;
    case "four":
      return <FourFace card={card} value={safe} onChange={onChange} />;
    case "leader":
      return <LeaderFace card={card} value={safe} onChange={onChange} />;
    case "chance":
      return <ChanceFace card={card} value={safe ?? 50} onChange={onChange} />;
    case "count":
      return <CountFace card={card} value={safe ?? 0} onChange={onChange} />;
    case "duo":
      return <DuoFace card={card} value={safe ?? 0} onChange={onChange} />;
  }
}
