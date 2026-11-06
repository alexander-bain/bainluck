"use client";

import Figure from "@/components/evals/Figure";
import TruthChip from "@/components/evals/TruthChip";
import type { ForwardRecordState } from "@/components/evals/useForwardRecord";
import { HERO_TILE_COPY } from "@/lib/evals/copy";

/**
 * The hero's tiles. Each jumps to its section and carries its own truth label;
 * a tile whose section is not on the page is absent. This step (S3) has the
 * forward record's; the exam and tests-for-the-tests tiles arrive with S2 and S4.
 */
export default function HeroTiles({ forward }: { forward: ForwardRecordState }) {
  const ready = forward.status === "ready" ? forward : null;
  const proof = ready?.view.proof ?? null;
  return (
    <div className="grid gap-3 sm:grid-cols-3 text-left" data-testid="evals-hero-tiles">
      <a
        href="#forward-record"
        data-hero-tile="forward-record"
        data-truth-scope={ready ? "live" : undefined}
        className="block rounded-xl border border-surface-border bg-surface-card p-4 hover:bg-surface-elevated transition-colors"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-caption-strong text-text-primary">{HERO_TILE_COPY.forwardTitle}</span>
          {ready && <TruthChip truth={ready.truth} linked={false} />}
        </div>
        <p className="mt-2 text-caption text-text-secondary">
          {ready && proof ? (
            <>
              <Figure truth={ready.truth} value={String(proof.errorPp)} className="text-prob-sm text-text-primary">
                {proof.errorText}
              </Figure>{" "}
              {HERO_TILE_COPY.forwardPointsAfter}{" "}
              <Figure truth={ready.truth} value={String(proof.outcomes)}>
                {proof.outcomesText}
              </Figure>{" "}
              {HERO_TILE_COPY.forwardOutcomesAfter}
            </>
          ) : forward.status === "loading" ? (
            HERO_TILE_COPY.loading
          ) : (
            HERO_TILE_COPY.unavailable
          )}
        </p>
      </a>
    </div>
  );
}
