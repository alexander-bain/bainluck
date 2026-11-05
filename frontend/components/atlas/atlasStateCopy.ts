'use client';

import { useEffect, useState } from 'react';

/**
 * Shared state wording and formatting helpers for the event-page and futures-page
 * atlas adoption (#883, #11974).
 *
 * Rulings built to:
 * - #11929: solid line through unobserved time, no gap call-outs.
 * - #11995 (decision 6-A): one-winner fields normalized server-side inside existing
 *   guards; the page prints the server's numbers and never normalizes on the client;
 *   independent sets are never normalized.
 * - #11990: whole numbers by default; one decimal where DNPL-fed and fast-moving.
 * - NOW #11852 decisions 10, 11, 12: "No recent price", step lines, keep all
 *   production features.
 */
export const ATLAS_STATE_COPY = {
  loading: 'Loading',
  updateInterrupted: 'Update interrupted',
  postponed: 'Postponed',
  voided: 'Void',
  noRecentPrice: 'No recent price',
  won: 'Won',
  lost: 'Lost',
  wonWithCheck: '✓ Won',
  lostWithCross: '✗ Lost',
  resultUnavailable: 'Result unavailable',
  independentChancesLabel: 'Independent chances · do not add to 100',
} as const;

export function resolveAtlasOptIn(
  searchParams?:
    | { get?: (key: string) => string | null }
    | URLSearchParams
    | string
    | null,
): boolean {
  if (!searchParams) return false;
  if (typeof searchParams === 'string') {
    const params = new URLSearchParams(
      searchParams.startsWith('?') ? searchParams.slice(1) : searchParams,
    );
    const val = params.get('atlas');
    return val === '1' || val === 'true';
  }
  if (typeof searchParams.get === 'function') {
    const val = searchParams.get('atlas');
    return val === '1' || val === 'true';
  }
  return false;
}

export function useAtlasOptIn(): boolean {
  const [enabled, setEnabled] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return resolveAtlasOptIn(window.location.search);
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    setEnabled(resolveAtlasOptIn(window.location.search));
  }, []);

  return enabled;
}

function parseIsoForPT(iso: string | null | undefined): Date | null {
  if (!iso || typeof iso !== 'string') return null;
  const trimmed = iso.trim();
  if (!trimmed) return null;
  // Bare YYYY-MM-DD dates are anchored at noon UTC so America/Los_Angeles
  // formatting never shifts them to the previous calendar day.
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(trimmed)
    ? `${trimmed}T12:00:00Z`
    : trimmed;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return null;
  return date;
}

/**
 * Formats an ISO date or timestamp as a Pacific Time calendar date (e.g. "Nov 3, 2026").
 */
export function formatAtlasDatePT(iso: string | null | undefined): string | null {
  const date = parseIsoForPT(iso);
  if (!date) return null;
  const currentYear = new Date().getFullYear();
  const targetYear = Number(
    new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Los_Angeles',
      year: 'numeric',
    }).format(date),
  );
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Los_Angeles',
    month: 'short',
    day: 'numeric',
    ...(targetYear !== currentYear ? { year: 'numeric' } : {}),
  }).format(date);
}

/**
 * Formats an ISO date or timestamp in Pacific Time with an explicit "PT" suffix.
 * When the input is a bare YYYY-MM-DD string, returns the calendar date in PT.
 */
export function formatAtlasTimestampPT(
  iso: string | null | undefined,
  options?: { includeSeconds?: boolean },
): string | null {
  if (!iso || typeof iso !== 'string') return null;
  const trimmed = iso.trim();
  if (!trimmed) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    const dateOnly = parseIsoForPT(trimmed);
    if (!dateOnly) return null;
    const formattedDate = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Los_Angeles',
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    }).format(dateOnly);
    return `${formattedDate} PT`;
  }
  const date = parseIsoForPT(trimmed);
  if (!date) return null;
  const includeSeconds = options?.includeSeconds ?? false;
  const formatted = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Los_Angeles',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    ...(includeSeconds ? { second: '2-digit' } : {}),
  }).format(date);
  return `${formatted} PT`;
}

/**
 * Formats source attribution for the details sheet and footer without putting
 * venue names inside narrative sentences.
 */
export function formatAtlasAttribution(
  source: string | null | undefined,
  options?: {
    sourceCount?: number | null;
    sourceLabels?: string[];
  },
): string {
  if (options?.sourceLabels && options.sourceLabels.length > 0) {
    return options.sourceLabels.join(' · ');
  }
  if ((options?.sourceCount ?? 0) >= 2) {
    return 'Kalshi and Polymarket';
  }
  const normalized = (source || '').trim().toLowerCase();
  if (normalized === 'kalshi') return 'Kalshi';
  if (normalized === 'polymarket') return 'Polymarket';
  if (normalized === 'odds_api' || normalized === 'the_odds_api') {
    return 'Sportsbooks';
  }
  if (normalized === 'datagolf') return 'DataGolf';
  if (!normalized) return 'Published source';
  return source!.trim();
}

/**
 * Builds an external venue link for the details sheet when a single-venue or
 * primary source identifier is present on the market payload.
 */
export function resolveOriginalMarketUrl(params: {
  source?: string | null;
  externalId?: string | null;
}): { url: string; label: string; venueName: string } | null {
  const normalizedSource = (params.source || '').trim().toLowerCase();
  const externalId = (params.externalId || '').trim();

  if (normalizedSource === 'kalshi') {
    const seriesTicker = externalId ? externalId.split('-')[0] : '';
    if (seriesTicker) {
      return {
        url: `https://kalshi.com/markets/${encodeURIComponent(seriesTicker.toLowerCase())}`,
        label: 'Original market on Kalshi',
        venueName: 'Kalshi',
      };
    }
    return {
      url: 'https://kalshi.com/markets',
      label: 'Original market on Kalshi',
      venueName: 'Kalshi',
    };
  }

  if (normalizedSource === 'polymarket') {
    return {
      url: 'https://polymarket.com',
      label: 'Original market on Polymarket',
      venueName: 'Polymarket',
    };
  }

  return null;
}

/**
 * Formats the market name as a clean predicate heading (strips trailing question
 * mark when present, matching the atlas headline contract).
 */
export function formatAtlasMarketHeading(title: string | null | undefined): string {
  const cleaned = (title || '').trim();
  if (!cleaned) return '';
  return cleaned.replace(/\?+$/, '').trim();
}
