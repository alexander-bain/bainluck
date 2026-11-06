import { PlannedItem } from "@/components/evals/Figure";
import RepoRefLink from "@/components/evals/RepoRefLink";
import type { Gap } from "@/lib/evals/gaps";

function GapText({ gap }: { gap: Gap }) {
  return (
    <p className="text-body text-text-primary">
      {gap.text} <RepoRefLink repoRef={gap.ref} />
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
