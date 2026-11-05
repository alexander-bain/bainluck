'use client';

import React, { useEffect, useId, useRef } from 'react';
import { formatProbabilityPercent } from '@/lib/probabilityDisplay';
import {
  ATLAS_STATE_COPY,
  formatAtlasAttribution,
  formatAtlasTimestampPT,
  resolveOriginalMarketUrl,
} from './atlasStateCopy';

export interface AtlasObservationDetail {
  probability: number;
  observedAt: string;
  label?: string;
}

export interface AtlasDetailsSheetProps {
  open: boolean;
  onClose: () => void;
  subjectName: string;
  marketTitle: string;
  isSettled?: boolean;
  settledResult?: 'won' | 'lost' | null;
  openingProbability?: number | null;
  renderedOpening?: number | null;
  openingObservedAt?: string | null;
  lastProbability?: number | null;
  renderedLast?: number | null;
  lastObservedAt?: string | null;
  selectedObservation?: AtlasObservationDetail | null;
  resolutionDate?: string | null;
  settledAt?: string | null;
  source?: string | null;
  sourceCount?: number | null;
  sourceLabels?: string[];
  externalId?: string | null;
  marketId?: number | string | null;
  outcomeId?: number | string | null;
  rulesText?: string | null;
}

export default function AtlasDetailsSheet({
  open,
  onClose,
  subjectName,
  marketTitle,
  isSettled = false,
  settledResult = null,
  openingProbability = null,
  renderedOpening = null,
  openingObservedAt = null,
  lastProbability = null,
  renderedLast = null,
  lastObservedAt = null,
  selectedObservation = null,
  resolutionDate = null,
  settledAt = null,
  source = null,
  sourceCount = null,
  sourceLabels,
  externalId = null,
  marketId = null,
  outcomeId = null,
  rulesText = null,
}: AtlasDetailsSheetProps) {
  const titleId = useId();
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    if (typeof document !== 'undefined' && document.activeElement instanceof HTMLElement) {
      previousFocusRef.current = document.activeElement;
    }
    const timer = window.setTimeout(() => {
      closeButtonRef.current?.focus();
    }, 0);

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('keydown', handleKeyDown);
      if (previousFocusRef.current && typeof previousFocusRef.current.focus === 'function') {
        previousFocusRef.current.focus();
      }
    };
  }, [open, onClose]);

  if (!open) return null;

  const isMultiVenue =
    (sourceCount ?? 1) > 1 || (sourceLabels != null && sourceLabels.length > 1);

  // Hold back opening chance on two-venue blended markets until the backend serves
  // a blended opening (#12043). Hold back opening observation time until supplied (#12045).
  const showOpeningChance =
    !isMultiVenue &&
    openingProbability != null &&
    Number.isFinite(openingProbability);
  const openingObservedLabel = showOpeningChance
    ? formatAtlasTimestampPT(openingObservedAt, { includeSeconds: true })
    : null;

  const selectedObservedLabel = selectedObservation
    ? formatAtlasTimestampPT(selectedObservation.observedAt, { includeSeconds: true })
    : null;
  const lastObservedLabel = formatAtlasTimestampPT(lastObservedAt, {
    includeSeconds: true,
  });
  const scheduledResolutionLabel = formatAtlasTimestampPT(resolutionDate, {
    includeSeconds: false,
  });
  // Hold back settlement time unless an authoritative settled_at is supplied (#12047).
  const settledAtLabel = isSettled
    ? formatAtlasTimestampPT(settledAt, { includeSeconds: false })
    : null;

  const attributionLabel = formatAtlasAttribution(source, {
    sourceCount,
    sourceLabels,
  });
  const originalLink = resolveOriginalMarketUrl({
    source,
    externalId,
  });
  const humanExternalId =
    externalId && !/^\d+$/.test(externalId.trim()) ? externalId.trim() : null;
  const cleanedRules = (rulesText || '').trim();

  const hasLastProbability =
    lastProbability != null && Number.isFinite(lastProbability);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-text-primary/30 p-0 min-[760px]:items-center min-[760px]:p-6"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
      data-testid="atlas-details-backdrop"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        data-testid="atlas-details-sheet"
        className="w-full max-h-[82vh] overflow-y-auto rounded-t-2xl border border-surface-border bg-surface-card p-5 shadow-xl min-[760px]:max-w-[520px] min-[760px]:rounded-2xl min-[760px]:p-6"
      >
        {/* Drag handle on phone */}
        <div
          aria-hidden="true"
          className="mx-auto mb-3 h-1 w-9 rounded-full bg-surface-border min-[760px]:hidden"
        />

        <div className="flex items-start justify-between gap-4 border-b border-surface-border pb-3.5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2
                id={titleId}
                className="text-base font-bold text-text-primary break-words"
              >
                {subjectName}
              </h2>
              {isSettled && settledResult === 'won' && (
                <span
                  data-testid="atlas-details-result-badge"
                  className="inline-flex items-center rounded-md bg-accent-live/15 px-2 py-0.5 text-xs font-semibold text-accent-live"
                >
                  {ATLAS_STATE_COPY.wonWithCheck}
                </span>
              )}
              {isSettled && settledResult === 'lost' && (
                <span
                  data-testid="atlas-details-result-badge"
                  className="inline-flex items-center rounded-md bg-surface-elevated px-2 py-0.5 text-xs font-semibold text-text-secondary"
                >
                  {ATLAS_STATE_COPY.lostWithCross}
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-text-secondary break-words">
              {marketTitle}
            </p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="Close details"
            data-testid="atlas-details-close"
            className="shrink-0 rounded-lg border border-surface-border bg-surface-elevated px-2.5 py-1 text-xs font-medium text-text-secondary transition-colors hover:text-text-primary"
          >
            Close
          </button>
        </div>

        <dl className="divide-y divide-surface-border text-xs">
          {showOpeningChance && (
            <div
              className="grid grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)] gap-3 py-3"
              data-testid="atlas-details-opening"
            >
              <dt className="text-text-muted">Opening chance</dt>
              <dd className="min-w-0 text-text-primary">
                <strong className="font-semibold tabular-nums">
                  {formatProbabilityPercent(openingProbability!, {
                    rendered: renderedOpening,
                  })}
                </strong>
                {openingObservedLabel && (
                  <span className="mt-0.5 block text-text-secondary">
                    {openingObservedLabel}
                  </span>
                )}
              </dd>
            </div>
          )}

          {selectedObservation && (
            <div
              className="grid grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)] gap-3 py-3"
              data-testid="atlas-details-selected-observation"
            >
              <dt className="text-text-muted">
                {selectedObservation.label || 'Selected observation'}
              </dt>
              <dd className="min-w-0 text-text-primary">
                <strong className="font-semibold tabular-nums">
                  {formatProbabilityPercent(selectedObservation.probability)}
                </strong>
                {selectedObservedLabel && (
                  <span className="mt-0.5 block text-text-secondary">
                    {selectedObservedLabel}
                  </span>
                )}
              </dd>
            </div>
          )}

          {!isSettled && (hasLastProbability || lastObservedLabel) && (
            <div
              className="grid grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)] gap-3 py-3"
              data-testid="atlas-details-last-observation"
            >
              <dt className="text-text-muted">Last recorded reading</dt>
              <dd className="min-w-0 text-text-primary">
                <strong className="font-semibold tabular-nums">
                  {hasLastProbability
                    ? formatProbabilityPercent(lastProbability!, {
                        rendered: renderedLast,
                      })
                    : ATLAS_STATE_COPY.noRecentPrice}
                </strong>
                {lastObservedLabel && (
                  <span className="mt-0.5 block text-text-secondary">
                    {lastObservedLabel}
                  </span>
                )}
              </dd>
            </div>
          )}

          {settledAtLabel && (
            <div
              className="grid grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)] gap-3 py-3"
              data-testid="atlas-details-settled-at"
            >
              <dt className="text-text-muted">Settled</dt>
              <dd className="min-w-0 text-text-primary">
                <strong className="font-semibold">{settledAtLabel}</strong>
              </dd>
            </div>
          )}

          {scheduledResolutionLabel && (
            <div
              className="grid grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)] gap-3 py-3"
              data-testid="atlas-details-scheduled-resolution"
            >
              <dt className="text-text-muted">Scheduled resolution</dt>
              <dd className="min-w-0 text-text-primary">
                <strong className="font-semibold">
                  {scheduledResolutionLabel}
                </strong>
              </dd>
            </div>
          )}

          <div
            className="grid grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)] gap-3 py-3"
            data-testid="atlas-details-attribution"
          >
            <dt className="text-text-muted">Attribution</dt>
            <dd className="min-w-0 text-text-primary">
              <strong className="font-semibold">{attributionLabel}</strong>
            </dd>
          </div>

          {(humanExternalId || originalLink) && (
            <div
              className="grid grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)] gap-3 py-3"
              data-testid="atlas-details-original-market"
            >
              <dt className="text-text-muted">Original market</dt>
              <dd className="min-w-0 text-text-primary break-all">
                {humanExternalId && (
                  <strong className="block font-semibold">{humanExternalId}</strong>
                )}
                {originalLink && (
                  <a
                    href={originalLink.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    data-testid="atlas-details-original-link"
                    className="mt-1.5 inline-flex items-center gap-1 font-medium text-accent-brand underline underline-offset-2 hover:opacity-80"
                  >
                    {originalLink.label}
                    <span aria-hidden="true">↗</span>
                  </a>
                )}
              </dd>
            </div>
          )}

          {cleanedRules && (
            <div
              className="grid grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)] gap-3 py-3"
              data-testid="atlas-details-rules"
            >
              <dt className="text-text-muted">Settlement rules</dt>
              <dd className="min-w-0 text-text-secondary leading-relaxed whitespace-pre-line break-words">
                {cleanedRules}
              </dd>
            </div>
          )}
        </dl>
      </div>
    </div>
  );
}
