/** Display-only: final means no current-probability claim; result uncertainty stays explicit. */
export function probabilityAvailabilityNotice(phase: string, mode = 'captured', important: string | null = null): string | null {
 const final = phase === 'Final' || phase === 'final' || phase === 'completed';
 const refresh = mode === 'loading' ? 'Refreshing recorded data' : mode === 'error' ? 'Refresh failed' : null;
 const parts = [refresh, final ? null : 'Current probability unavailable', important].filter((p): p is string => Boolean(p));
 return parts.length ? parts.join(' · ') : null;
}
