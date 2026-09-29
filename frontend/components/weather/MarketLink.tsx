import Link from "next/link";
import type { CSSProperties, MouseEventHandler, ReactNode } from "react";

/** The market page a /weather row opens, or null when the row carries no id.
 *
 *  #9478: every card on /weather looked tappable and none of them went
 *  anywhere; the only way through to a market was the temperature panel's
 *  "View probability timeline". `/api/weather/featured` already served
 *  `market_id` and the hero ignored it. An id that is absent (a payload out of
 *  the hourly Redis cache from before the field, or a route that does not
 *  serve one yet) leaves the row exactly as it was: never a link to
 *  `/futures/undefined`. */
export function marketHref(marketId: number | null | undefined): string | null {
  return typeof marketId === "number" && Number.isInteger(marketId) && marketId > 0
    ? `/futures/${marketId}`
    : null;
}

interface MarketLinkProps {
  marketId: number | null | undefined;
  className?: string;
  style?: CSSProperties;
  onMouseEnter?: MouseEventHandler<HTMLElement>;
  onMouseLeave?: MouseEventHandler<HTMLElement>;
  children: ReactNode;
}

/** A row's own box: the market page's link when the row has an id, the same
 *  `<div>` it always was when it has none. An `<a>` is inline, so a caller
 *  whose box had no display class of its own passes `block`; one that already
 *  says `grid` or `flex` keeps it, with no second display class to fight. */
export default function MarketLink({ marketId, className, style, onMouseEnter, onMouseLeave, children }: MarketLinkProps) {
  const href = marketHref(marketId);
  if (!href) {
    return (
      <div className={className} style={style} onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave}>
        {children}
      </div>
    );
  }
  return (
    <Link
      href={href}
      data-testid="weather-market-link"
      className={className}
      style={style}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      {children}
    </Link>
  );
}
