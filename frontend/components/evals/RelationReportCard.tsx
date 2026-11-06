"use client";

import { useState } from "react";

import EvalsSection from "@/components/evals/EvalsSection";
import Figure, { PlannedItem } from "@/components/evals/Figure";
import { CONFUSION_COPY as COPY } from "@/lib/evals/copy";
import { issueRef, type MeasuredTruth } from "@/lib/evals/truth";
import { ANSWERS, ANSWER_WORDS, answersFor, type TwinConfusion } from "@/lib/evals/twinConfusion";
import {
  PASSES,
  RELATIONS,
  RELATION_WORDS,
  SPLITS,
  examTruth,
  type Count,
  type PassId,
  type Relation,
  type Split,
  type TwinExam,
} from "@/lib/evals/twinExam";
import { rangeText } from "@/lib/evals/wilson";

function LockIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" className="h-3 w-3 fill-current text-text-tertiary">
      <path d="M5 7V5a3 3 0 1 1 6 0v2h.5A1.5 1.5 0 0 1 13 8.5v5a1.5 1.5 0 0 1-1.5 1.5h-7A1.5 1.5 0 0 1 3 13.5v-5A1.5 1.5 0 0 1 4.5 7H5Zm1.5 0h3V5a1.5 1.5 0 0 0-3 0v2Z" />
    </svg>
  );
}

/** The share as a bar, with the likely range drawn across it as a whisker. Nothing to draw at 0/0. */
function Bar({ count }: { count: Count }) {
  if (count.n === 0) return <div aria-hidden="true" className="mt-1 h-2" />;
  const range = count.wilson95;
  return (
    <div aria-hidden="true" className="relative mt-1 h-2 w-full rounded-full bg-surface-elevated">
      <div className="absolute inset-y-0 left-0 rounded-full bg-accent-brand/70" style={{ width: `${(100 * count.k) / count.n}%` }} />
      {range && (
        <>
          <div
            className="absolute top-1/2 h-px -translate-y-1/2 bg-text-primary"
            style={{ left: `${100 * range[0]}%`, width: `${100 * (range[1] - range[0])}%` }}
          />
          <div className="absolute top-0 h-2 w-px bg-text-primary" style={{ left: `${100 * range[0]}%` }} />
          <div className="absolute top-0 h-2 w-px bg-text-primary" style={{ left: `calc(${100 * range[1]}% - 1px)` }} />
        </>
      )}
    </div>
  );
}

function Metric({ name, label, count, truth }: { name: string; label: string; count: Count; truth: MeasuredTruth }) {
  return (
    <div data-metric={name} data-k={count.k} data-n={count.n}>
      <p className="flex items-baseline justify-between gap-2 text-micro">
        <span className="text-text-secondary">{label}</span>
        {count.n === 0 ? (
          <span data-none="" title={COPY.noneMeans} className="text-text-secondary">
            {COPY.none}
          </span>
        ) : (
          <span className="whitespace-nowrap">
            <Figure truth={truth} value={`${count.k}/${count.n}`} className="text-text-primary">
              {`${count.k}/${count.n}`}
            </Figure>
            {count.wilson95 && (
              <>
                {" "}
                <span className="text-text-tertiary">
                  (
                  <Figure truth={truth} value={count.wilson95.join(",")}>
                    {rangeText(count.wilson95)}
                  </Figure>
                  )
                </span>
              </>
            )}
          </span>
        )}
      </p>
      <Bar count={count} />
    </div>
  );
}

/**
 * Tap a kind to see what the judge answered for those pairs: a stacked bar and
 * the counts, the right answer first. Held-out rows say why they are counts
 * only; development rows name the pair export they wait on (Decide 43-B1).
 */
function Answers({
  confusion,
  pass,
  split,
  relation,
  truth,
}: {
  confusion: TwinConfusion;
  pass: PassId;
  split: Split;
  relation: Relation;
  truth: MeasuredTruth;
}) {
  const row = answersFor(confusion, pass, split, relation);
  if (row.n === 0) return null;
  const given = ANSWERS.filter((a) => row.counts[a] > 0).sort((a, b) =>
    a === relation ? -1 : b === relation ? 1 : row.counts[b] - row.counts[a]
  );
  return (
    <details data-answers={relation} data-answers-n={row.n} className="group text-micro">
      <summary className="cursor-pointer list-none text-accent-brand [&::-webkit-details-marker]:hidden">
        <span className="inline-block group-open:rotate-90 transition-transform" aria-hidden="true">
          ›
        </span>{" "}
        {COPY.answers}
      </summary>
      <div className="mt-1.5 space-y-1.5">
        <div aria-hidden="true" className="flex h-2 w-full overflow-hidden rounded-full bg-surface-elevated">
          {given.map((a) => (
            <div
              key={a}
              className={a === relation ? "bg-accent-brand/70" : "bg-accent-danger/50 border-l border-surface-card"}
              style={{ width: `${(100 * row.counts[a]) / row.n}%` }}
            />
          ))}
        </div>
        <ul className="flex flex-wrap gap-x-3 gap-y-0.5">
          {given.map((a) => (
            <li key={a} data-answer={a} className={a === relation ? "text-text-primary" : "text-text-secondary"}>
              {ANSWER_WORDS[a]}{" "}
              <Figure truth={truth} value={String(row.counts[a])}>
                {String(row.counts[a])}
              </Figure>
              {a === relation && <span className="text-text-tertiary"> ({COPY.answersRight})</span>}
            </li>
          ))}
        </ul>
        {split === "test" && <p className="text-text-tertiary">{COPY.heldOutCountsOnly}</p>}
        {split === "dev" && (
          <PlannedItem waitingOn={COPY.devPairsWaitingOn} repoRef={issueRef(12102)}>
            <p className="text-text-secondary">{COPY.devPairs}</p>
          </PlannedItem>
        )}
      </div>
    </details>
  );
}

function Toggle<T extends string>({
  label,
  options,
  value,
  onChange,
  words,
  testId,
}: {
  label: string;
  options: readonly T[];
  value: T;
  onChange: (v: T) => void;
  words: (v: T, i: number) => string;
  testId: string;
}) {
  return (
    <div role="group" aria-label={label} data-testid={testId} className="inline-flex flex-wrap gap-1">
      {options.map((o, i) => (
        <button
          key={o}
          type="button"
          aria-pressed={o === value}
          data-option={o}
          onClick={() => onChange(o)}
          className={`rounded-full border px-2.5 py-0.5 text-micro transition-colors ${
            o === value
              ? "border-accent-brand bg-surface-elevated text-text-primary"
              : "border-surface-border text-text-secondary hover:bg-surface-elevated"
          }`}
        >
          {words(o, i)}
        </button>
      ))}
    </div>
  );
}

/**
 * "Where the judge gets confused" — per kind of pair, how many it found and how
 * often it was right when it used the label, from the scorer's own counts and
 * ranges. Held-out first, because that is the fair test; development and all
 * pairs are a tap away, and so is each pass (they are repeats of the same
 * pairs, never pooled).
 */
export default function RelationReportCard({ exam, confusion = null }: { exam: TwinExam; confusion?: TwinConfusion | null }) {
  const [split, setSplit] = useState<Split>("test");
  const [pass, setPass] = useState<PassId>("1");
  const truth = examTruth(exam);
  const record = exam.perPass[pass][split];
  return (
    <EvalsSection id="confusion" title={COPY.title} lead={COPY.lead} detail={COPY.detail} truth={truth}>
      <div className="space-y-3" data-split={split} data-pass={pass}>
        <div className="flex flex-wrap items-center gap-2">
          <Toggle
            label={COPY.viewLabel}
            options={SPLITS}
            value={split}
            onChange={setSplit}
            words={(s) => COPY.views[s]}
            testId="evals-confusion-split"
          />
          <Toggle
            label={COPY.passLabel}
            options={PASSES}
            value={pass}
            onChange={setPass}
            words={(_p, i) => COPY.passes[i]}
            testId="evals-confusion-pass"
          />
        </div>
        {split === "test" && (
          <p className="flex items-center gap-1.5 text-micro text-text-secondary" data-testid="evals-heldout-note">
            <LockIcon />
            {COPY.heldOutNote}
          </p>
        )}
        <ul className="grid gap-x-6 gap-y-3 sm:grid-cols-2" data-testid="evals-report-card">
          {RELATIONS.map((r) => (
            <li key={r} data-relation={r} className="space-y-1.5">
              <p className="flex items-center gap-1.5 text-caption-strong text-text-primary">
                {RELATION_WORDS[r]}
                {split === "test" && (
                  <span data-lock="" className="inline-flex items-center">
                    <LockIcon />
                    <span className="sr-only">{COPY.lock}</span>
                  </span>
                )}
              </p>
              <Metric name="recall" label={COPY.found} count={record.perRelation[r].recall} truth={truth} />
              <Metric name="precision" label={COPY.right} count={record.perRelation[r].precision} truth={truth} />
              {confusion && <Answers confusion={confusion} pass={pass} split={split} relation={r} truth={truth} />}
            </li>
          ))}
        </ul>
      </div>
    </EvalsSection>
  );
}
