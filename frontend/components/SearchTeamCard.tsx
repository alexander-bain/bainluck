import Link from "next/link";

import { getTeamRowSportLabel } from "@/lib/sportCategories";
import { buildTeamPageUrl } from "@/lib/teamUrls";
import type { SearchSportFacet, SearchTeam } from "@/lib/types";

/**
 * A team result on `/search`.
 *
 * #7390 (#5780's web twin): `sports` is the SAME array the filter pills above
 * these cards are built from, and it is passed in so the row can read the name
 * the server gave this league instead of shortening the key itself — the card
 * used to print `sport_key.split("_").slice(1).join(" ").toUpperCase()`, so
 * Worcester Red Sox read "MILB" under a pill reading "MiLB". A card rendered
 * without the facets still says a sport, never a key; see
 * `getTeamRowSportLabel`.
 *
 * It lives here rather than inside `app/search/page.tsx` because a Next page
 * module may not carry a second named export (`OmitWithTag<…>` fails the
 * generated page type), and a card nothing can render is a card nothing can
 * test.
 */
export default function SearchTeamCard({
  team,
  sports,
}: {
  team: SearchTeam;
  sports?: SearchSportFacet[];
}) {
  const url = buildTeamPageUrl(team.name, team.sport_key);
  if (!url) return null;

  const sportLabel = getTeamRowSportLabel(team.sport_key, sports);

  return (
    <Link
      href={url}
      className="flex items-center gap-3 p-3 bg-surface-card border border-surface-border rounded-card hover:shadow-md hover:border-accent-brand/30 transition-all"
    >
      {team.logo ? (
        <img
          src={team.logo}
          alt=""
          className="w-10 h-10 object-contain flex-shrink-0"
          crossOrigin="anonymous"
        />
      ) : (
        <div className="w-10 h-10 rounded-lg bg-surface-elevated flex items-center justify-center text-sm font-bold text-text-muted flex-shrink-0">
          {team.abbreviation || team.name.charAt(0)}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-text-primary truncate">{team.name}</div>
        <div className="text-xs text-text-secondary">
          {team.record && <span>{team.record}</span>}
          {team.record && sportLabel && <span> · </span>}
          {sportLabel && <span>{sportLabel}</span>}
        </div>
      </div>
    </Link>
  );
}
