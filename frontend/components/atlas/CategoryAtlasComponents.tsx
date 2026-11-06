'use client';

import React, { useMemo, useState } from 'react';
import Link from 'next/link';
import { formatProbabilityPercent } from '@/lib/probabilityDisplay';
import AtlasDetailsSheet from './AtlasDetailsSheet';
import {
  ATLAS_STATE_COPY,
  formatAtlasMarketHeading,
  formatAtlasTimestampPT,
} from './atlasStateCopy';

export interface AtlasCategoryOutcome {
  id?: number | string;
  label: string;
  /** Probability in [0, 1] or null when unpriced / withheld. */
  probability?: number | null;
  /** Server-supplied whole percent when available. */
  renderedPercent?: number | null;
  /** Opening probability in [0, 1] when single-venue opening is known. */
  openingProbability?: number | null;
  renderedOpening?: number | null;
  openingObservedAt?: string | null;
  observedAt?: string | null;
  party?: 'D' | 'R' | 'I' | string | null;
  imageUrl?: string | null;
  isWinner?: boolean | null;
  isSettled?: boolean;
  settledResult?: 'won' | 'lost' | 'void' | null;
  notOffered?: boolean;
}

export interface AtlasJourneyPoint {
  observedAt: string;
  probability: number;
}

export interface AtlasJourneySeries {
  label: string;
  party?: string | null;
  points: AtlasJourneyPoint[];
}

export interface AtlasMarketMeta {
  marketId?: number | null;
  marketTitle: string;
  kicker?: string | null;
  subtitle?: string | null;
  source?: string | null;
  sourceCount?: number | null;
  sourceLabels?: string[];
  externalId?: string | null;
  resolutionDate?: string | null;
  settledAt?: string | null;
  observedAt?: string | null;
  loading?: boolean;
  updateInterrupted?: boolean;
}

function normalizeProb01(
  prob: number | null | undefined,
  rendered?: number | null,
): number | null {
  if (typeof prob === 'number' && Number.isFinite(prob)) {
    if (prob > 1 && prob <= 100) return prob / 100;
    if (prob >= 0 && prob <= 1) return prob;
  }
  if (typeof rendered === 'number' && Number.isFinite(rendered)) {
    if (rendered >= 0 && rendered <= 100) return rendered / 100;
  }
  return null;
}

function formatOutcomePercent(o: AtlasCategoryOutcome): string | null {
  const p01 = normalizeProb01(o.probability, o.renderedPercent);
  if (p01 === null) return null;
  return formatProbabilityPercent(p01, {
    rendered:
      typeof o.renderedPercent === 'number' && Number.isFinite(o.renderedPercent)
        ? Math.round(o.renderedPercent)
        : undefined,
  });
}

function partyBadgeClass(party?: string | null): string | null {
  const p = (party || '').trim().toUpperCase();
  if (p === 'D' || p === 'DEM' || p === 'DEMOCRAT' || p === 'DEMOCRATIC') {
    return 'bg-surface-elevated text-text-primary border border-surface-border';
  }
  if (p === 'R' || p === 'REP' || p === 'REPUBLICAN' || p === 'GOP') {
    return 'bg-surface-elevated text-text-primary border border-surface-border';
  }
  if (p === 'I' || p === 'IND' || p === 'INDEPENDENT') {
    return 'bg-surface-elevated text-text-secondary border border-surface-border';
  }
  return null;
}

function partyLetter(party?: string | null): string | null {
  const p = (party || '').trim().toUpperCase();
  if (p.startsWith('D')) return 'D';
  if (p.startsWith('R') || p === 'GOP') return 'R';
  if (p.startsWith('I')) return 'I';
  return null;
}

function initialsFromName(name: string): string {
  const parts = name
    .replace(/\([^)]*\)/g, '')
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

/**
 * Timestamped step-line journey chart on fixed 0–100 y-axis with tappable PT readings.
 * Never invents points and never auto-scales the y-axis (#11929, standing ruling 4).
 */
export function AtlasCategoryJourneyChart({
  series,
  isSettled = false,
}: {
  series: AtlasJourneySeries[];
  isSettled?: boolean;
}) {
  const [selected, setSelected] = useState<{
    label: string;
    probability: number;
    observedAt: string;
  } | null>(null);

  const validSeries = useMemo(() => {
    return series
      .map((s) => ({
        ...s,
        points: s.points
          .filter((pt) => {
            const d = new Date(pt.observedAt);
            return (
              !Number.isNaN(d.getTime()) &&
              typeof pt.probability === 'number' &&
              Number.isFinite(pt.probability)
            );
          })
          .map((pt) => ({
            observedAt: pt.observedAt,
            t: new Date(pt.observedAt).getTime(),
            p: pt.probability > 1 ? pt.probability / 100 : pt.probability,
          }))
          .sort((a, b) => a.t - b.t),
      }))
      .filter((s) => s.points.length >= 2);
  }, [series]);

  if (validSeries.length === 0) return null;

  const allTimes = validSeries.flatMap((s) => s.points.map((pt) => pt.t));
  const minT = Math.min(...allTimes);
  const maxT = Math.max(...allTimes);
  const spanT = Math.max(1, maxT - minT);

  const width = 560;
  const height = 148;
  const padL = 32;
  const padR = 14;
  const padT = 12;
  const padB = 22;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const xOf = (t: number) => padL + ((t - minT) / spanT) * plotW;
  const yOf = (p: number) => padT + (1 - Math.max(0, Math.min(1, p))) * plotH;

  const strokes = [
    'var(--series-1, #2563eb)',
    'var(--text-primary, #111827)',
    'var(--text-secondary, #4b5563)',
    'var(--text-muted, #9ca3af)',
  ];

  return (
    <div
      className="mt-4 rounded-xl border border-surface-border bg-surface-elevated/40 p-3"
      data-testid="atlas-category-journey-chart"
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-text-secondary">
        <div className="flex flex-wrap items-center gap-3">
          {validSeries.slice(0, 4).map((s, idx) => (
            <span key={s.label} className="inline-flex items-center gap-1.5 font-medium text-text-primary">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ backgroundColor: strokes[idx % strokes.length] }}
              />
              {s.label}
            </span>
          ))}
        </div>
        {selected ? (
          <span className="font-mono text-[11px] text-text-secondary" data-testid="atlas-journey-selected-reading">
            {selected.label} · {formatProbabilityPercent(selected.probability)} ·{' '}
            {formatAtlasTimestampPT(selected.observedAt) ?? selected.observedAt}
          </span>
        ) : (
          <span className="text-[11px] text-text-muted">
            {isSettled ? 'Completed journey · 0–100%' : 'Tap a reading for PT time · 0–100%'}
          </span>
        )}
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-36 w-full overflow-visible"
        role="img"
        aria-label="Probability journey on a 0 to 100 percent scale"
      >
        {[0, 0.5, 1].map((tick) => {
          const y = yOf(tick);
          return (
            <g key={tick}>
              <line
                x1={padL}
                x2={width - padR}
                y1={y}
                y2={y}
                stroke="currentColor"
                className="text-surface-border"
                strokeDasharray={tick === 0.5 ? '3 3' : undefined}
              />
              <text
                x={padL - 6}
                y={y + 3}
                textAnchor="end"
                className="fill-text-muted font-mono text-[9px]"
              >
                {Math.round(tick * 100)}%
              </text>
            </g>
          );
        })}

        {validSeries.slice(0, 4).map((s, idx) => {
          const color = strokes[idx % strokes.length];
          const dParts: string[] = [];
          s.points.forEach((pt, i) => {
            const x = xOf(pt.t);
            const y = yOf(pt.p);
            if (i === 0) {
              dParts.push(`M ${x.toFixed(1)} ${y.toFixed(1)}`);
            } else {
              const prevY = yOf(s.points[i - 1].p);
              // Step line (decision 11-A) through unobserved time (#11929)
              dParts.push(`L ${x.toFixed(1)} ${prevY.toFixed(1)} L ${x.toFixed(1)} ${y.toFixed(1)}`);
            }
          });
          const first = s.points[0];
          const last = s.points[s.points.length - 1];
          return (
            <g key={s.label}>
              <path
                d={dParts.join(' ')}
                fill="none"
                stroke={color}
                strokeWidth={1.75}
              />
              {/* Hollow opening mark */}
              <circle
                cx={xOf(first.t)}
                cy={yOf(first.p)}
                r={3.5}
                fill="var(--surface-card, #ffffff)"
                stroke={color}
                strokeWidth={1.5}
                className="cursor-pointer"
                onClick={() =>
                  setSelected({
                    label: s.label,
                    probability: first.p,
                    observedAt: first.observedAt,
                  })
                }
              />
              {/* Solid recorded reading marks */}
              {s.points.slice(1).map((pt, i) => (
                <circle
                  key={`${s.label}-${i}`}
                  cx={xOf(pt.t)}
                  cy={yOf(pt.p)}
                  r={i === s.points.length - 2 ? 3.5 : 2.5}
                  fill={color}
                  className="cursor-pointer"
                  onClick={() =>
                    setSelected({
                      label: s.label,
                      probability: pt.p,
                      observedAt: pt.observedAt,
                    })
                  }
                />
              ))}
              {isSettled && idx === 0 && (
                <text
                  x={Math.min(width - padR, xOf(last.t) + 6)}
                  y={yOf(last.p) + 3}
                  className="fill-text-primary font-mono text-[9px] font-semibold"
                >
                  {ATLAS_STATE_COPY.wonWithCheck}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/**
 * 1. FIELD BOARD — One bar per contestant on 0–100 with a hollow opening mark,
 * optional journey chart for the leaders, and "N more" full-field expansion.
 */
export function FieldBoard({
  meta,
  outcomes,
  journeySeries = [],
  previewCount = 6,
  showPartyPills = false,
}: {
  meta: AtlasMarketMeta;
  outcomes: AtlasCategoryOutcome[];
  journeySeries?: AtlasJourneySeries[];
  previewCount?: number;
  showPartyPills?: boolean;
}) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const heading = formatAtlasMarketHeading(meta.marketTitle);
  const isSettled = outcomes.some(
    (o) => o.isWinner === true || o.settledResult === 'won',
  );
  const shownOutcomes = expanded ? outcomes : outcomes.slice(0, previewCount);
  const hiddenCount = Math.max(0, outcomes.length - shownOutcomes.length);
  const lead = outcomes[0];
  const leadP01 = lead ? normalizeProb01(lead.probability, lead.renderedPercent) : null;
  const readingPT = formatAtlasTimestampPT(lead?.observedAt ?? meta.observedAt);

  return (
    <article
      className="rounded-2xl border border-surface-border bg-surface-card p-5"
      data-testid="atlas-field-board"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {meta.kicker && (
            <div className="font-mono text-[11px] font-semibold uppercase tracking-wider text-text-muted">
              {meta.kicker}
            </div>
          )}
          <h3 className="mt-0.5 text-base font-semibold leading-snug text-text-primary">
            {meta.marketId ? (
              <Link href={`/futures/${meta.marketId}?atlas=1`} className="hover:underline">
                {heading}
              </Link>
            ) : (
              heading
            )}
          </h3>
          {meta.subtitle && (
            <p className="mt-0.5 text-xs text-text-secondary">{meta.subtitle}</p>
          )}
        </div>
        <button
          type="button"
          onClick={() => setSheetOpen(true)}
          aria-label={`Details for ${heading}`}
          data-testid="atlas-details-trigger"
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-surface-border text-xs font-semibold text-text-secondary hover:bg-surface-elevated hover:text-text-primary"
        >
          ⓘ
        </button>
      </div>

      {meta.updateInterrupted && (
        <div
          className="mt-2 rounded-lg border border-surface-border bg-surface-elevated px-3 py-1.5 text-xs text-text-secondary"
          data-testid="atlas-update-interrupted"
        >
          {ATLAS_STATE_COPY.updateInterrupted}
          {readingPT ? ` · last reading ${readingPT}` : ''}
        </div>
      )}

      <div className="mt-4 space-y-2.5">
        {outcomes.length === 0 && meta.loading && (
          <div className="py-4 text-xs text-text-muted">{ATLAS_STATE_COPY.loading}</div>
        )}
        {shownOutcomes.map((o, idx) => {
          const p01 = normalizeProb01(o.probability, o.renderedPercent);
          const pctLabel = formatOutcomePercent(o);
          const open01 = normalizeProb01(o.openingProbability, o.renderedOpening);
          const pLetter = showPartyPills ? partyLetter(o.party) : null;
          const pClass = showPartyPills ? partyBadgeClass(o.party) : null;
          const won = o.isWinner === true || o.settledResult === 'won';
          const lost =
            !won && (isSettled || o.isWinner === false || o.settledResult === 'lost');

          return (
            <div
              key={o.id ?? `${o.label}-${idx}`}
              className="space-y-1"
              data-testid="atlas-field-board-row"
            >
              <div className="flex items-baseline justify-between gap-2 text-sm">
                <div className="flex min-w-0 items-center gap-2">
                  {pLetter && pClass && (
                    <span
                      className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-[11px] font-bold ${pClass}`}
                    >
                      {pLetter}
                    </span>
                  )}
                  <span className="truncate font-medium text-text-primary">{o.label}</span>
                </div>
                <span className="shrink-0 font-mono text-sm font-semibold tabular-nums text-text-primary">
                  {meta.loading ? (
                    <span className="text-xs font-normal text-text-muted">
                      {ATLAS_STATE_COPY.loading}
                    </span>
                  ) : won ? (
                    <span>{ATLAS_STATE_COPY.wonWithCheck}</span>
                  ) : lost ? (
                    <span className="text-text-secondary">{ATLAS_STATE_COPY.lostWithCross}</span>
                  ) : pctLabel !== null ? (
                    pctLabel
                  ) : (
                    <span className="font-sans text-xs font-normal text-text-muted">
                      {ATLAS_STATE_COPY.noRecentPrice}
                    </span>
                  )}
                </span>
              </div>
              <div className="relative h-2 w-full overflow-hidden rounded-full bg-surface-elevated">
                {!meta.loading && !won && !lost && p01 !== null && (
                  <div
                    className="h-full rounded-full bg-[var(--series-1,#2563eb)]"
                    style={{ width: `${Math.max(1, Math.min(100, p01 * 100))}%` }}
                  />
                )}
                {open01 !== null && (
                  <span
                    title="Opening probability"
                    aria-label="Opening mark"
                    className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-text-primary bg-surface-card"
                    style={{ left: `${Math.max(2, Math.min(98, open01 * 100))}%` }}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>

      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="mt-3 text-xs font-medium text-accent-brand hover:underline"
          data-testid="atlas-field-board-more"
        >
          {hiddenCount} more ›
        </button>
      )}

      {journeySeries.length > 0 && (
        <AtlasCategoryJourneyChart series={journeySeries} isSettled={isSettled} />
      )}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-surface-border pt-2.5 text-[11px] text-text-muted">
        <span>
          {isSettled
            ? 'Settled field'
            : `${outcomes.length} contenders · one winner`}
        </span>
        {readingPT && <span className="font-mono">reading {readingPT}</span>}
      </div>

      <AtlasDetailsSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        subjectName={lead?.label ?? heading}
        marketTitle={heading}
        isSettled={isSettled}
        settledResult={
          lead?.isWinner === true || lead?.settledResult === 'won'
            ? 'won'
            : isSettled
              ? 'lost'
              : null
        }
        openingProbability={
          lead ? normalizeProb01(lead.openingProbability, lead.renderedOpening) : null
        }
        renderedOpening={lead?.renderedOpening ?? null}
        openingObservedAt={lead?.openingObservedAt ?? null}
        lastProbability={leadP01}
        renderedLast={lead?.renderedPercent ?? null}
        lastObservedAt={lead?.observedAt ?? meta.observedAt ?? null}
        resolutionDate={meta.resolutionDate ?? null}
        settledAt={meta.settledAt ?? null}
        source={meta.source ?? null}
        sourceCount={meta.sourceCount ?? null}
        sourceLabels={meta.sourceLabels}
        externalId={meta.externalId ?? null}
      />
    </article>
  );
}

/**
 * 2. BINARY ROW — One row per binary (ruling 047): name, whole %, a 0–100 track,
 * a hollow opening mark, result word when settled, no verdict pill.
 */
export function BinaryRow({
  meta,
  outcome,
}: {
  meta: AtlasMarketMeta;
  outcome: AtlasCategoryOutcome;
}) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const heading = formatAtlasMarketHeading(meta.marketTitle || outcome.label);
  const p01 = normalizeProb01(outcome.probability, outcome.renderedPercent);
  const pctLabel = formatOutcomePercent(outcome);
  const open01 = normalizeProb01(outcome.openingProbability, outcome.renderedOpening);
  const won = outcome.isWinner === true || outcome.settledResult === 'won';
  const lost = outcome.isWinner === false || outcome.settledResult === 'lost';
  const voided = outcome.settledResult === 'void';
  const isSettled = won || lost || voided || outcome.isSettled === true;

  return (
    <div
      className="rounded-xl border border-surface-border bg-surface-card px-4 py-3"
      data-testid="atlas-binary-row"
    >
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0 flex-1">
          {meta.kicker && (
            <div className="font-mono text-[10px] font-semibold uppercase tracking-wider text-text-muted">
              {meta.kicker}
            </div>
          )}
          <div className="text-sm font-medium leading-snug text-text-primary">
            {meta.marketId ? (
              <Link href={`/futures/${meta.marketId}?atlas=1`} className="hover:underline">
                {heading}
              </Link>
            ) : (
              heading
            )}
          </div>
          {meta.subtitle && (
            <div className="mt-0.5 text-xs text-text-secondary">{meta.subtitle}</div>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <span className="font-mono text-sm font-semibold tabular-nums text-text-primary">
            {meta.loading ? (
              <span className="font-sans text-xs font-normal text-text-muted">
                {ATLAS_STATE_COPY.loading}
              </span>
            ) : voided ? (
              <span>{ATLAS_STATE_COPY.voided}</span>
            ) : won ? (
              <span>{ATLAS_STATE_COPY.wonWithCheck}</span>
            ) : lost ? (
              <span className="text-text-secondary">{ATLAS_STATE_COPY.lostWithCross}</span>
            ) : pctLabel !== null ? (
              pctLabel
            ) : (
              <span className="font-sans text-xs font-normal text-text-muted">
                {ATLAS_STATE_COPY.noRecentPrice}
              </span>
            )}
          </span>
          <button
            type="button"
            onClick={() => setSheetOpen(true)}
            aria-label={`Details for ${heading}`}
            data-testid="atlas-details-trigger"
            className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-surface-border text-[11px] text-text-secondary hover:bg-surface-elevated hover:text-text-primary"
          >
            ⓘ
          </button>
        </div>
      </div>

      <div className="relative mt-2 h-2 w-full overflow-hidden rounded-full bg-surface-elevated">
        {!meta.loading && !isSettled && p01 !== null && (
          <div
            className="h-full rounded-full bg-[var(--series-1,#2563eb)]"
            style={{ width: `${Math.max(1, Math.min(100, p01 * 100))}%` }}
          />
        )}
        {open01 !== null && (
          <span
            title="Opening probability"
            aria-label="Opening mark"
            className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-text-primary bg-surface-card"
            style={{ left: `${Math.max(2, Math.min(98, open01 * 100))}%` }}
          />
        )}
      </div>

      <AtlasDetailsSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        subjectName={outcome.label || heading}
        marketTitle={heading}
        isSettled={isSettled}
        settledResult={won ? 'won' : lost ? 'lost' : null}
        openingProbability={open01}
        renderedOpening={outcome.renderedOpening ?? null}
        openingObservedAt={outcome.openingObservedAt ?? null}
        lastProbability={p01}
        renderedLast={outcome.renderedPercent ?? null}
        lastObservedAt={outcome.observedAt ?? meta.observedAt ?? null}
        resolutionDate={meta.resolutionDate ?? null}
        settledAt={meta.settledAt ?? null}
        source={meta.source ?? null}
        sourceCount={meta.sourceCount ?? null}
        sourceLabels={meta.sourceLabels}
        externalId={meta.externalId ?? null}
      />
    </div>
  );
}

/**
 * 3. THRESHOLD LADDER CARD — Rungs in threshold or date order, unconnected dots
 * on 0–100 + "Independent chances · do not add to 100". Never subtracts rungs.
 */
export function ThresholdLadderCard({
  meta,
  rungs,
  reportedActualLabel,
}: {
  meta: AtlasMarketMeta;
  rungs: AtlasCategoryOutcome[];
  reportedActualLabel?: string | null;
}) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const heading = formatAtlasMarketHeading(meta.marketTitle);
  const lead = rungs[0];
  const readingPT = formatAtlasTimestampPT(lead?.observedAt ?? meta.observedAt);

  return (
    <article
      className="rounded-2xl border border-surface-border bg-surface-card p-5"
      data-testid="atlas-threshold-ladder"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {meta.kicker && (
            <div className="font-mono text-[11px] font-semibold uppercase tracking-wider text-text-muted">
              {meta.kicker}
            </div>
          )}
          <h3 className="mt-0.5 text-base font-semibold leading-snug text-text-primary">
            {meta.marketId ? (
              <Link href={`/futures/${meta.marketId}?atlas=1`} className="hover:underline">
                {heading}
              </Link>
            ) : (
              heading
            )}
          </h3>
          <p className="mt-0.5 text-xs text-text-secondary">
            {ATLAS_STATE_COPY.independentChancesLabel}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setSheetOpen(true)}
          aria-label={`Details for ${heading}`}
          data-testid="atlas-details-trigger"
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-surface-border text-xs font-semibold text-text-secondary hover:bg-surface-elevated hover:text-text-primary"
        >
          ⓘ
        </button>
      </div>

      <div className="mt-4 space-y-2.5">
        {rungs.map((r, idx) => {
          const p01 = normalizeProb01(r.probability, r.renderedPercent);
          const pctLabel = formatOutcomePercent(r);
          const won = r.isWinner === true || r.settledResult === 'won';
          const lost = r.isWinner === false || r.settledResult === 'lost';

          return (
            <div
              key={r.id ?? `${r.label}-${idx}`}
              className="grid grid-cols-[minmax(0,1.2fr)_minmax(0,2fr)_4.5rem] items-center gap-3 text-sm"
              data-testid="atlas-threshold-rung"
            >
              <span className="truncate font-mono text-xs font-medium text-text-primary">
                {r.label}
              </span>
              <div className="relative h-2 w-full rounded-full bg-surface-elevated">
                {!meta.loading && !won && !lost && p01 !== null && (
                  <span
                    className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--series-1,#2563eb)]"
                    style={{ left: `${Math.max(3, Math.min(97, p01 * 100))}%` }}
                    data-testid="atlas-threshold-dot"
                  />
                )}
              </div>
              <span className="text-right font-mono text-xs font-semibold tabular-nums text-text-primary">
                {meta.loading ? (
                  <span className="font-sans font-normal text-text-muted">
                    {ATLAS_STATE_COPY.loading}
                  </span>
                ) : won ? (
                  <span>{ATLAS_STATE_COPY.wonWithCheck}</span>
                ) : lost ? (
                  <span className="text-text-secondary">{ATLAS_STATE_COPY.lostWithCross}</span>
                ) : pctLabel !== null ? (
                  pctLabel
                ) : (
                  <span className="font-sans text-[11px] font-normal text-text-muted">
                    —
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>

      {reportedActualLabel && (
        <div
          className="mt-3 border-t border-surface-border pt-2.5 font-mono text-xs font-medium text-text-primary"
          data-testid="atlas-threshold-actual"
        >
          ┃ {reportedActualLabel}
        </div>
      )}

      {readingPT && (
        <div className="mt-3 border-t border-surface-border pt-2 text-right font-mono text-[11px] text-text-muted">
          reading {readingPT}
        </div>
      )}

      <AtlasDetailsSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        subjectName={lead?.label ?? heading}
        marketTitle={heading}
        lastProbability={
          lead ? normalizeProb01(lead.probability, lead.renderedPercent) : null
        }
        renderedLast={lead?.renderedPercent ?? null}
        lastObservedAt={lead?.observedAt ?? meta.observedAt ?? null}
        resolutionDate={meta.resolutionDate ?? null}
        settledAt={meta.settledAt ?? null}
        source={meta.source ?? null}
        sourceCount={meta.sourceCount ?? null}
        sourceLabels={meta.sourceLabels}
        externalId={meta.externalId ?? null}
      />
    </article>
  );
}

/**
 * 4. RACE CARD — A race shows one state everywhere (settled means settled).
 * Once settled, shows winner photo or initials, ✓ Won, opening chance, and settle time in PT.
 */
export function RaceCard({
  meta,
  contenders,
  settledWinner,
}: {
  meta: AtlasMarketMeta;
  contenders: AtlasCategoryOutcome[];
  settledWinner?: string | null;
}) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const heading = formatAtlasMarketHeading(meta.marketTitle);
  const winnerOutcome =
    contenders.find((c) => c.isWinner === true || c.settledResult === 'won') ??
    (settledWinner
      ? contenders.find(
          (c) => c.label.trim().toLowerCase() === settledWinner.trim().toLowerCase(),
        ) ?? {
          label: settledWinner,
          isWinner: true,
          settledResult: 'won' as const,
        }
      : null);
  const isSettled = Boolean(winnerOutcome);
  const lead = winnerOutcome ?? contenders[0];
  const readingPT = formatAtlasTimestampPT(lead?.observedAt ?? meta.observedAt);
  const settledPT = formatAtlasTimestampPT(meta.settledAt);
  const hasAnyPrice = contenders.some(
    (c) => normalizeProb01(c.probability, c.renderedPercent) !== null,
  );

  return (
    <article
      className="rounded-2xl border border-surface-border bg-surface-card p-4"
      data-testid="atlas-race-card"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-mono text-[10px] font-semibold uppercase tracking-wider text-text-muted">
            {meta.kicker ?? (isSettled ? 'RACE CARD · settled' : 'RACE CARD · open')}
          </div>
          <h4 className="mt-0.5 text-sm font-semibold text-text-primary">
            {meta.marketId ? (
              <Link href={`/futures/${meta.marketId}?atlas=1`} className="hover:underline">
                {heading}
              </Link>
            ) : (
              heading
            )}
          </h4>
        </div>
        <button
          type="button"
          onClick={() => setSheetOpen(true)}
          aria-label={`Details for ${heading}`}
          data-testid="atlas-details-trigger"
          className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-surface-border text-[11px] text-text-secondary hover:bg-surface-elevated hover:text-text-primary"
        >
          ⓘ
        </button>
      </div>

      {isSettled && winnerOutcome ? (
        <div className="mt-3" data-testid="atlas-race-settled">
          <div className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2.5">
              {winnerOutcome.imageUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={winnerOutcome.imageUrl}
                  alt={winnerOutcome.label}
                  className="h-8 w-8 shrink-0 rounded-full object-cover"
                />
              ) : (
                <span
                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-elevated font-mono text-xs font-semibold text-text-primary"
                  data-testid="atlas-race-initials"
                >
                  {initialsFromName(winnerOutcome.label)}
                </span>
              )}
              <span className="truncate text-sm font-semibold text-text-primary">
                {winnerOutcome.label}
              </span>
            </div>
            <span className="shrink-0 font-mono text-xs font-semibold text-text-primary">
              {ATLAS_STATE_COPY.wonWithCheck}
            </span>
          </div>
          <div className="mt-2 font-mono text-[11px] text-text-secondary">
            {heading}
            {normalizeProb01(
              winnerOutcome.openingProbability,
              winnerOutcome.renderedOpening,
            ) !== null
              ? ` · opening ${formatProbabilityPercent(
                  normalizeProb01(
                    winnerOutcome.openingProbability,
                    winnerOutcome.renderedOpening,
                  )!,
                )}`
              : ''}
            {settledPT ? ` · settled ${settledPT}` : ''}
          </div>
        </div>
      ) : !hasAnyPrice && !meta.loading ? (
        <div
          className="mt-3 text-xs text-text-muted"
          data-testid="atlas-race-no-recent-probability"
        >
          {ATLAS_STATE_COPY.noRecentPrice}
        </div>
      ) : (
        <div className="mt-3 space-y-2">
          {contenders.map((c, idx) => {
            const p01 = normalizeProb01(c.probability, c.renderedPercent);
            const pctLabel = formatOutcomePercent(c);
            const open01 = normalizeProb01(c.openingProbability, c.renderedOpening);
            const pLetter = partyLetter(c.party ?? c.label);
            const pClass = partyBadgeClass(c.party ?? c.label);

            return (
              <div key={c.id ?? `${c.label}-${idx}`} className="space-y-1">
                <div className="flex items-baseline justify-between gap-2 text-xs">
                  <div className="flex min-w-0 items-center gap-1.5">
                    {pLetter && pClass && (
                      <span
                        className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded text-[10px] font-bold ${pClass}`}
                      >
                        {pLetter}
                      </span>
                    )}
                    <span className="truncate font-medium text-text-primary">
                      {c.label}
                    </span>
                  </div>
                  <span className="shrink-0 font-mono text-xs font-semibold tabular-nums text-text-primary">
                    {meta.loading
                      ? ATLAS_STATE_COPY.loading
                      : pctLabel ?? ATLAS_STATE_COPY.noRecentPrice}
                  </span>
                </div>
                <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-surface-elevated">
                  {!meta.loading && p01 !== null && (
                    <div
                      className="h-full rounded-full bg-[var(--series-1,#2563eb)]"
                      style={{ width: `${Math.max(1, Math.min(100, p01 * 100))}%` }}
                    />
                  )}
                  {open01 !== null && (
                    <span
                      className="absolute top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-text-primary bg-surface-card"
                      style={{ left: `${Math.max(2, Math.min(98, open01 * 100))}%` }}
                    />
                  )}
                </div>
              </div>
            );
          })}
          <div className="flex items-center justify-between pt-1 font-mono text-[10px] text-text-muted">
            <span>○ opening · ● reading {readingPT ?? 'latest'}</span>
            {meta.marketId && (
              <Link
                href={`/futures/${meta.marketId}?atlas=1`}
                className="text-text-secondary hover:text-text-primary"
              >
                ›
              </Link>
            )}
          </div>
        </div>
      )}

      <AtlasDetailsSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        subjectName={lead?.label ?? heading}
        marketTitle={heading}
        isSettled={isSettled}
        settledResult={isSettled ? 'won' : null}
        openingProbability={
          lead ? normalizeProb01(lead.openingProbability, lead.renderedOpening) : null
        }
        renderedOpening={lead?.renderedOpening ?? null}
        openingObservedAt={lead?.openingObservedAt ?? null}
        lastProbability={
          lead ? normalizeProb01(lead.probability, lead.renderedPercent) : null
        }
        renderedLast={lead?.renderedPercent ?? null}
        lastObservedAt={lead?.observedAt ?? meta.observedAt ?? null}
        resolutionDate={meta.resolutionDate ?? null}
        settledAt={meta.settledAt ?? null}
        source={meta.source ?? null}
        sourceCount={meta.sourceCount ?? null}
        sourceLabels={meta.sourceLabels}
        externalId={meta.externalId ?? null}
      />
    </article>
  );
}

/**
 * 5. BUCKET DISTRIBUTION — Exclusive buckets in numeric order with the venue's
 * exact edges on 0–100. Headline is the leading bucket with its edges ("62–63°F
 * most likely · 34%"), never a derived temperature, midpoint, or "modal outcome".
 */
export function BucketDistribution({
  meta,
  buckets,
  guardFailed = false,
  stationContextLabel = null,
}: {
  meta: AtlasMarketMeta;
  buckets: AtlasCategoryOutcome[];
  guardFailed?: boolean;
  stationContextLabel?: string | null;
}) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const [showAllRanges, setShowAllRanges] = useState(false);

  const heading = formatAtlasMarketHeading(meta.marketTitle);
  const settledBucket = buckets.find(
    (b) => b.isWinner === true || b.settledResult === 'won',
  );
  const isSettled = Boolean(settledBucket);

  const peakBucket = useMemo(() => {
    if (guardFailed || isSettled) return null;
    let best: AtlasCategoryOutcome | null = null;
    let bestP = -1;
    for (const b of buckets) {
      const p = normalizeProb01(b.probability, b.renderedPercent);
      if (p !== null && p > bestP) {
        bestP = p;
        best = b;
      }
    }
    return best;
  }, [buckets, guardFailed, isSettled]);

  const peakPct = peakBucket ? formatOutcomePercent(peakBucket) : null;
  const readingPT = formatAtlasTimestampPT(
    peakBucket?.observedAt ?? settledBucket?.observedAt ?? meta.observedAt,
  );

  // Split low-probability tail buckets (< 2%) when there are > 7 buckets and not expanded.
  const canCollapseTail = !showAllRanges && !guardFailed && buckets.length > 7;
  const mainBuckets = canCollapseTail
    ? buckets.filter((b) => {
        const p = normalizeProb01(b.probability, b.renderedPercent);
        return (
          b === peakBucket ||
          b.isWinner === true ||
          (p !== null && p >= 0.02)
        );
      })
    : buckets;
  const tailBuckets = canCollapseTail
    ? buckets.filter((b) => !mainBuckets.includes(b))
    : [];

  return (
    <article
      className="rounded-2xl border border-surface-border bg-surface-card p-5"
      data-testid="atlas-bucket-distribution"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-mono text-[10px] font-semibold uppercase tracking-wider text-text-muted">
            {meta.kicker ?? `BUCKET DISTRIBUTION · ${heading}`}
          </div>
          {!guardFailed && isSettled && settledBucket ? (
            <h3
              className="mt-1 font-mono text-lg font-semibold text-text-primary"
              data-testid="atlas-bucket-headline"
            >
              {settledBucket.label} · {ATLAS_STATE_COPY.wonWithCheck}
            </h3>
          ) : !guardFailed && peakBucket && peakPct ? (
            <h3
              className="mt-1 font-mono text-lg font-semibold text-text-primary"
              data-testid="atlas-bucket-headline"
            >
              {peakBucket.label} most likely · {peakPct}
            </h3>
          ) : (
            <h3 className="mt-1 text-base font-semibold text-text-primary">
              {heading}
            </h3>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {readingPT && (
            <span className="font-mono text-[11px] text-text-muted">
              reading {readingPT}
            </span>
          )}
          <button
            type="button"
            onClick={() => setSheetOpen(true)}
            aria-label={`Details for ${heading}`}
            data-testid="atlas-details-trigger"
            className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-surface-border text-xs font-semibold text-text-secondary hover:bg-surface-elevated hover:text-text-primary"
          >
            ⓘ
          </button>
        </div>
      </div>

      <div className="mt-4 space-y-2">
        {(mainBuckets.length > 0 ? mainBuckets : buckets).map((b, idx) => {
          const p01 = normalizeProb01(b.probability, b.renderedPercent);
          const pctLabel = formatOutcomePercent(b);
          const won = b.isWinner === true || b.settledResult === 'won';

          return (
            <div
              key={b.id ?? `${b.label}-${idx}`}
              className="grid grid-cols-[minmax(0,1.1fr)_minmax(0,2fr)_3.5rem] items-center gap-3 text-xs"
              data-testid="atlas-bucket-row"
            >
              <span className="truncate font-mono font-medium text-text-primary">
                {b.label}
              </span>
              <div className="h-2 w-full overflow-hidden rounded-full bg-surface-elevated">
                {!meta.loading && !b.notOffered && !guardFailed && p01 !== null && (
                  <div
                    className="h-full rounded-full bg-[var(--series-1,#2563eb)]"
                    style={{ width: `${Math.max(1, Math.min(100, p01 * 100))}%` }}
                  />
                )}
              </div>
              <span className="text-right font-mono font-semibold tabular-nums text-text-primary">
                {meta.loading ? (
                  <span className="font-sans font-normal text-text-muted">
                    {ATLAS_STATE_COPY.loading}
                  </span>
                ) : b.notOffered ? (
                  <span className="font-sans font-normal text-text-muted">
                    not offered
                  </span>
                ) : won ? (
                  <span>✓</span>
                ) : !guardFailed && pctLabel !== null ? (
                  pctLabel
                ) : (
                  <span className="font-sans font-normal text-text-muted">—</span>
                )}
              </span>
            </div>
          );
        })}

        {tailBuckets.length > 0 && (
          <div
            className="flex flex-wrap items-baseline justify-between gap-2 pt-1 font-mono text-[11px] text-text-secondary"
            data-testid="atlas-bucket-tail-summary"
          >
            <span>{tailBuckets.map((b) => b.label).join(' · ')}</span>
            <span>
              {tailBuckets
                .map((b) => formatOutcomePercent(b) ?? '—')
                .join(' · ')}
            </span>
          </div>
        )}
      </div>

      {stationContextLabel && (
        <div className="mt-3 border-t border-surface-border pt-2 font-mono text-[11px] text-text-secondary">
          {stationContextLabel}
        </div>
      )}

      <div className="mt-3 flex items-center justify-between border-t border-surface-border pt-2.5 text-[11px] text-text-muted">
        <span>{buckets.length} ranges · exactly one settles</span>
        {tailBuckets.length > 0 ? (
          <button
            type="button"
            onClick={() => setShowAllRanges(true)}
            className="font-medium text-accent-brand hover:underline"
          >
            All ranges ›
          </button>
        ) : meta.marketId ? (
          <Link
            href={`/futures/${meta.marketId}?atlas=1`}
            className="font-medium text-accent-brand hover:underline"
          >
            All ranges ›
          </Link>
        ) : null}
      </div>

      <AtlasDetailsSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        subjectName={peakBucket?.label ?? settledBucket?.label ?? heading}
        marketTitle={heading}
        isSettled={isSettled}
        settledResult={isSettled ? 'won' : null}
        lastProbability={
          peakBucket
            ? normalizeProb01(peakBucket.probability, peakBucket.renderedPercent)
            : null
        }
        renderedLast={peakBucket?.renderedPercent ?? null}
        lastObservedAt={peakBucket?.observedAt ?? meta.observedAt ?? null}
        resolutionDate={meta.resolutionDate ?? null}
        settledAt={meta.settledAt ?? null}
        source={meta.source ?? null}
        sourceCount={meta.sourceCount ?? null}
        sourceLabels={meta.sourceLabels}
        externalId={meta.externalId ?? null}
      />
    </article>
  );
}

/**
 * 6. RELEASE CARD — Holds a bucket distribution or a threshold ladder matching
 * the venue's structure. Requires a stored release time in PT (`releaseAt`);
 * refuses to show when `releaseAt` is absent.
 */
export function ReleaseCard({
  meta,
  releaseAt,
  shape,
  outcomes,
  reportedActualLabel = null,
}: {
  meta: AtlasMarketMeta;
  releaseAt: string | null | undefined;
  shape: 'buckets' | 'ladder';
  outcomes: AtlasCategoryOutcome[];
  reportedActualLabel?: string | null;
}) {
  const releasePT = formatAtlasTimestampPT(releaseAt);
  if (!releasePT) {
    // Partial data contract: "No stored release time means the card refuses to show"
    return null;
  }

  const heading = formatAtlasMarketHeading(meta.marketTitle);

  return (
    <div className="space-y-2" data-testid="atlas-release-card">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-t-2xl border border-b-0 border-surface-border bg-surface-elevated/60 px-5 py-2.5 text-xs">
        <span className="font-mono font-semibold text-text-primary">
          RELEASE CARD · {heading}
        </span>
        <span className="font-mono text-text-secondary" data-testid="atlas-release-time-pt">
          Release {releasePT}
        </span>
      </div>
      {shape === 'ladder' ? (
        <ThresholdLadderCard
          meta={meta}
          rungs={outcomes}
          reportedActualLabel={reportedActualLabel}
        />
      ) : (
        <BucketDistribution
          meta={meta}
          buckets={outcomes}
          stationContextLabel={
            reportedActualLabel ? `Reported ${reportedActualLabel} ┃ ✓ on its bracket · official, PT` : null
          }
        />
      )}
    </div>
  );
}
