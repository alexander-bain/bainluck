"use client";

/**
 * #10868 — the hockey journey's "All props" entry (web): every original the
 * page's catalogue lists, once each, in its order, each with its own Details.
 * Readings, grades and ids are the view model's (`HockeyJourneyOriginals`); this
 * file holds only which list and which Details the reader opened. Unknown is
 * not loss: an unconfirmed grade says so in words. During play the row's
 * figure is only ever an admitted CURRENT chance; a refused quote is printed
 * once, in Details, as the historical quote with its own clock and venue.
 */

import { useId, useState } from "react";
import { propVerdictLabel } from "@/lib/propGrade";
import type {
  HockeyJourneyOriginal,
  HockeyJourneyOriginalReading,
  HockeyJourneyOriginals,
} from "@/lib/eventPage10868/hockeyJourney";

function ReadingText({ reading }: { reading: HockeyJourneyOriginalReading }) {
  return reading.kind === "value" ? (
    <span className="text-base font-bold tabular-nums">{reading.text}</span>
  ) : (
    <span className="text-sm font-medium text-text-secondary">{reading.words}</span>
  );
}

/** A grade in web's one settled vocabulary (lib/propGrade.ts), or its own words when there is no verdict. */
function gradeWords(grade: NonNullable<HockeyJourneyOriginal["grade"]>): string {
  return grade.hit === null ? grade.words : propVerdictLabel(grade.hit);
}

function headlineOf(original: HockeyJourneyOriginal): HockeyJourneyOriginalReading {
  if (original.grade) return { kind: "value", text: gradeWords(original.grade), placement: 0, provenance: original.grade.provenance };
  return original.later ?? original.pregame;
}

function OriginalRow({ original }: { original: HockeyJourneyOriginal }) {
  const detailsId = useId();
  const [open, setOpen] = useState(false);
  return (
    <li className="border-b border-surface-border py-2 last:border-b-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="min-w-0 break-words text-sm font-medium">{original.label}</span>
        <ReadingText reading={headlineOf(original)} />
      </div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={detailsId}
        onClick={() => setOpen((v) => !v)}
        className="min-h-11 text-sm font-semibold text-text-primary underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand"
      >
        Details<span className="sr-only">{`: ${original.label}`}</span>
      </button>
      <div id={detailsId} hidden={!open} className="space-y-2 pb-2 text-sm">
        <p className="font-semibold break-words">{original.title}</p>
        <p className="text-text-secondary break-words">{original.outcome}</p>
        <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div>
            <dt className="font-medium text-text-secondary">Pregame chance</dt>
            <dd>
              <ReadingText reading={original.pregame} />
              {original.pregame.kind === "value" && original.pregame.provenance && (
                <span className="block text-text-secondary">{original.pregame.provenance}</span>
              )}
            </dd>
          </div>
          {original.later && (
            <div>
              <dt className="font-medium text-text-secondary">Current chance</dt>
              <dd>
                <ReadingText reading={original.later} />
                {original.later.kind === "value" && original.later.provenance && (
                  <span className="block text-text-secondary">{original.later.provenance}</span>
                )}
              </dd>
            </div>
          )}
          {original.grade && (
            <div>
              <dt className="font-medium text-text-secondary">Result</dt>
              <dd>
                <span className="text-base font-bold">{gradeWords(original.grade)}</span>
                <span className="block text-text-secondary">{original.grade.provenance}</span>
              </dd>
            </div>
          )}
        </dl>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-text-secondary">
          {original.about.source && (
            <div className="contents">
              <dt>Venue</dt>
              <dd className="text-text-primary">{original.about.source}</dd>
            </div>
          )}
          <div className="contents">
            <dt>Rules</dt>
            <dd>{original.about.rules}</dd>
          </div>
          {original.about.rows.map((row) => (
            <div key={row.label} className="contents">
              <dt>{row.label}</dt>
              <dd className="break-all">{row.value}</dd>
            </div>
          ))}
          {original.about.historical && (
            <div className="contents">
              <dt>{original.about.historical.label}</dt>
              <dd className="break-words">{original.about.historical.value}</dd>
            </div>
          )}
        </dl>
      </div>
    </li>
  );
}

export default function HockeyJourneyAllProps({
  originals,
  entryLabel,
}: {
  originals: HockeyJourneyOriginals;
  entryLabel: string | null;
}) {
  const headingId = useId();
  const listId = useId();
  const [open, setOpen] = useState(false);
  return (
    <section aria-labelledby={headingId} className="space-y-2">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id={headingId} className="text-base font-semibold">
          {originals.heading}
        </h3>
        {originals.context && <span className="text-sm text-text-secondary">{originals.context}</span>}
      </header>
      {originals.originals.length === 0 ? (
        <p className="text-sm text-text-secondary">{originals.emptyWords}</p>
      ) : (
        <>
          <button
            type="button"
            aria-expanded={open}
            aria-controls={listId}
            onClick={() => setOpen((v) => !v)}
            className="min-h-11 w-full rounded-md border border-surface-border px-3 text-left text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand"
          >
            {entryLabel ?? originals.heading}
          </button>
          <ul id={listId} hidden={!open}>
            {originals.originals.map((original) => (
              <OriginalRow key={original.key} original={original} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
