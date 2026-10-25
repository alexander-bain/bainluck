'use client';

import { useEffect, useState } from 'react';
import { fetchTeamPropFamilies, type PropFamily } from '@/lib/api';
import { propRosterCoverage, type PropRosterCoverage } from '@/lib/propRosterCoverage';

// Prop families (L2-167): a team's futures/prop markets grouped into cohort
// races (Next Team, awards, ladders). Supplementary + best-effort — a failed
// payload, or an empty one from a whole-roster search, hides the Prop Races
// section. An empty payload from a capped roster search keeps its coverage, so
// the section can still say the roster was not fully checked.
//
// #2311: the families and the roster coverage they were found under travel as
// ONE value, tagged with the slug that produced them. A team switch therefore
// cannot show one team's races under another team's coverage caption, and the
// previous team's value is not returned for even one render: it is only ever
// handed back for the slug it was fetched for.

export interface TeamPropRaces {
  families: PropFamily[];
  coverage: PropRosterCoverage;
}

export const NO_PROP_RACES: TeamPropRaces = { families: [], coverage: null };

export function useTeamPropRaces(slug: string): TeamPropRaces {
  const [loaded, setLoaded] = useState<{ slug: string; races: TeamPropRaces } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchTeamPropFamilies(slug)
      .then((result) => {
        if (!cancelled) {
          setLoaded({
            slug,
            races: { families: result.families || [], coverage: propRosterCoverage(result) },
          });
        }
      })
      .catch(() => {
        if (!cancelled) setLoaded({ slug, races: NO_PROP_RACES });
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  return loaded !== null && loaded.slug === slug ? loaded.races : NO_PROP_RACES;
}
