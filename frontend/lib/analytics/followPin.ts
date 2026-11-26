import { trackEvent } from './core';
import type { FollowTeamParams, PinItemParams } from './types';

/**
 * Emit a consent-gated `follow_team` event (#13261 row 5, 181-C).
 * Carries only action + sport/league key + enum relation/surface (zero PII).
 */
export function trackFollowTeam(params: {
  action: FollowTeamParams['action'];
  sport?: string | null;
  relation_type?: FollowTeamParams['relation_type'];
  surface?: FollowTeamParams['surface'];
}): void {
  const payload: FollowTeamParams = {
    action: params.action,
    ...(params.sport ? { sport: params.sport } : {}),
    ...(params.relation_type ? { relation_type: params.relation_type } : {}),
    ...(params.surface ? { surface: params.surface } : {}),
  };
  trackEvent('follow_team', payload);
}

/**
 * Emit a consent-gated `pin_item` event (#13261 row 5, 181-C).
 * Carries only item_type ('event' | 'future') and action ('pin' | 'unpin').
 */
export function trackPinItem(params: PinItemParams): void {
  trackEvent('pin_item', {
    item_type: params.item_type,
    action: params.action,
  });
}
