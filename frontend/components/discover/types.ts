import type { FeedItem } from "@/lib/types";
import type { ShareContentType } from "@/lib/share";

export interface DiscoverGroupedItem {
  type: "single" | "group";
  item?: FeedItem;
  items?: FeedItem[];
  groupTitle?: string;
}

export interface DiscoverCardProps {
  groupedItem: DiscoverGroupedItem;
  onDismiss?: () => void;
  positionIndex?: number;
}

export interface ActionBarProps {
  liked: boolean;
  setLiked: (v: boolean) => void;
  shareUrl: string;
  shareTitle: string;
  shareText?: string;
  contentType: ShareContentType;
  itemId: number | string;
  onShare?: () => void;
  /**
   * UX-P234 (board item 16): the pin, on the surface that never had one. OPTIONAL
   * and omitted by default, so the five card types that do not yet have a pin
   * binding are byte-identical — this ship wires futures only, which is the half
   * that pairs with item 15's detail page. Events are the obvious next one and
   * need `usePinnedEvents` rather than a new affordance.
   */
  pin?: {
    pinned: boolean;
    onToggle: () => void;
    atMax: boolean;
    noun: string;
  };
  /**
   * When this card's prices were last seen (#5752) — the futures payload's
   * `price_observed_at`, handed straight down.
   *
   * It lives on the action bar for the same reason the pin above does: every
   * futures card format closes on an `ActionBar`, and there are seven of them
   * across `FuturesCard` and `ComparisonCard`. Hanging the mark here is one
   * place that all seven inherit, instead of seven chances for a format to be
   * the one that keeps quiet about its age.
   *
   * OPTIONAL, and omitted by every non-futures card, so those stay
   * byte-identical: an event card's age is a different fact with a different
   * carrier (`win_probability_sources[*].updated_at`) and is not this ship.
   */
  priceObservedAt?: string | null;
  /**
   * The market's `status`, used for ONE decision: which staleness bound the age
   * mark above is held to (#5843).
   *
   * A `live` card marks at 30 minutes; every other status is on the hourly sweep
   * and marks at the backend's 6h contract. The status itself is not rendered
   * here — the card already draws its own `● Live` pill from the same field — so
   * this is a cadence hint, not a second source of truth about liveness.
   *
   * ### Which cards can actually take the `live` arm — measured, because it is
   * one component and THREE payloads
   *
   * `futures_markets.status` is only ever `open` or `resolved` (987,750 resolved
   * / 41,108 open on production, 2026-09-13), and the feed serves only the open
   * ones. So a `FuturesCard` or `ComparisonCard` is ALWAYS `open` and always
   * takes the 6h arm — correct, since those are the hourly ladders, but it means
   * the `live` arm is unreachable from those two.
   *
   * It is reachable, and load-bearing, from `ConceptCard`: a concept's status is
   * calendar-driven (`marquee_pin_state` — "live" during the event), and the
   * specimen that component was filed on is exactly a live concept whose price
   * had gone quiet. Same feed read: Vuelta a España 2026, `live`, 169.6m old.
   * A flat 6h would have silenced it.
   *
   * Absent means "not live", which is the correct default for this bar: every
   * card that mounts an `ActionBar` with a price is a futures card, and an
   * hourly-polled one is what that is. Defaulting the other way would leave a
   * caller that forgets the prop reproducing the exact 30-of-30 defect.
   */
  priceStatus?: string | null;
}

export interface CardActionCallbacks {
  onDetailClick?: () => void;
  onShare?: () => void;
  onContextExpand?: () => void;
  onContextCollapse?: () => void;
}
