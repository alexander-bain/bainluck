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
}

export interface CardActionCallbacks {
  onDetailClick?: () => void;
  onShare?: () => void;
  onContextExpand?: () => void;
  onContextCollapse?: () => void;
}
