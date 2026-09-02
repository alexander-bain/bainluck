/**
 * Custom Hooks
 */

// The three GA4 hooks CLAUDE.md mandates on every page come straight from their own
// modules. They used to be laundered through './useAnalytics', which re-exports them —
// so a route that imports only these three still dragged in the whole event catalog
// (event_card_click, chart hovers, league filters, view-mode toggles). Discover is such
// a route, and that catalog is not reachable from a cold landing. The hooks stay eager;
// only the catalog behind them stops riding along. (LAT-P209)
export { usePageTracking } from './usePageTracking';
export { useScrollDepth } from './useScrollDepth';
export { useEngagementTime } from './useEngagementTime';

// `useAnalytics` is deliberately NOT re-exported here. A static re-export is not
// tree-shaken across this client-module boundary (measured: leaving it cost 4,920 of
// the 4,948 brotli bytes), so the barrel would put the catalog back on every route
// that touches any hook. Its three consumers import it from '@/hooks/useAnalytics'.
export { usePinnedEvents } from './usePinnedEvents';
export { usePinnedFutures } from './usePinnedFutures';
