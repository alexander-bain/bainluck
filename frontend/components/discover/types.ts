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
}

export interface CardActionCallbacks {
  onDetailClick?: () => void;
  onShare?: () => void;
  onContextExpand?: () => void;
  onContextCollapse?: () => void;
}
