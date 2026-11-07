import { CHIP_COPY } from "@/lib/evals/copy";
import type { RepoRef } from "@/lib/evals/truth";

/**
 * "#12095", linked. An identifier, not a figure: `data-evals-ref` is what the
 * page test reads to tell an issue number from a number someone typed.
 */
export default function RepoRefLink({ repoRef }: { repoRef: RepoRef }) {
  const kind = repoRef.kind === "pull" ? CHIP_COPY.pull : CHIP_COPY.issue;
  return (
    <a
      href={repoRef.href}
      target="_blank"
      rel="noopener noreferrer"
      data-evals-ref=""
      aria-label={`${kind} #${repoRef.number}`}
      className="font-mono text-micro text-accent-brand hover:underline whitespace-nowrap"
    >
      #{repoRef.number}
    </a>
  );
}
