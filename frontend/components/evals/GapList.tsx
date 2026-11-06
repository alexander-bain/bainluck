import { Fragment } from "react";

import { PlannedItem } from "@/components/evals/Figure";
import RepoRefLink from "@/components/evals/RepoRefLink";
import { CHIP_COPY } from "@/lib/evals/copy";
import type { Gap } from "@/lib/evals/gaps";
import { calendarMonthLabel, pacificDayLabel } from "@/lib/evals/truth";

/** A `{name}` in a row's text, rendered as the `<time>` its `dates` entry names. */
function GapDate({ value }: { value: string | undefined }) {
  const label = value ? calendarMonthLabel(value) ?? pacificDayLabel(value) : null;
  return <time dateTime={value}>{label ?? CHIP_COPY.dateUnreadable}</time>;
}

function GapText({ gap }: { gap: Gap }) {
  const pieces = gap.text.split(/\{(\w+)\}/);
  return (
    <p className="text-body text-text-primary">
      {pieces.map((piece, i) =>
        i % 2 === 1 ? (
          <GapDate key={i} value={gap.dates?.[piece]} />
        ) : (
          <Fragment key={i}>{piece}</Fragment>
        )
      )}{" "}
      <RepoRefLink repoRef={gap.ref} />
    </p>
  );
}

/**
 * An unchecked list: each row is a thing we have not tested, linked to the
 * issue that owns it. A row whose fix is being built is a PLANNED item, which
 * names what it waits on and can hold no figure.
 */
export default function GapList({ gaps }: { gaps: readonly Gap[] }) {
  return (
    <ul className="space-y-3" data-testid="evals-gap-list">
      {gaps.map((gap) => (
        <li key={gap.id} data-gap-id={gap.id} className="flex gap-3">
          <span
            aria-hidden="true"
            className="mt-1.5 h-3.5 w-3.5 flex-none rounded-sm border border-text-muted"
          />
          <div className="min-w-0">
            {gap.planned ? (
              <PlannedItem waitingOn={gap.planned.waitingOn} repoRef={gap.planned.ref}>
                <GapText gap={gap} />
              </PlannedItem>
            ) : (
              <GapText gap={gap} />
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
