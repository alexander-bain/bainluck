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
}

export interface CardActionCallbacks {
  onDetailClick?: () => void;
  onShare?: () => void;
  onContextExpand?: () => void;
  onContextCollapse?: () => void;
}
