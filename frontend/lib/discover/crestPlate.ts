import { colorDistance } from "@/lib/probabilityBarPair";
import { hexToRgb } from "@/lib/teamColors";

/**
 * #9133 — A CREST IN ITS CLUB'S COLOUR VANISHES INTO A HERO OF THE SAME COLOUR.
 *
 * The Discover event hero is painted with the sport's `CATEGORY_GRADIENTS` entry,
 * and football's is green (`#14532d → #15803d`). On production 2026-09-27 the
 * New York Jets crest (`#115740`) sat on it at 390px and a reader saw one crest
 * and a green smudge. Measured from stored `teams.primary_color`, redmean
 * distance to the nearer gradient stop: Packers 22, Jets 34, Portland Timbers
 * 57, Eagles 68 — then a gap to Austin FC at 89, whose crest is mostly black.
 * 80 sits in that gap.
 *
 * Only a club this close to the hero gets the plate; every other crest keeps
 * the bare look. The club colour is a stand-in for the crest's pixels (we have
 * no image luminance at render time), so a missing or unparseable colour or
 * background never plates.
 */
export const CREST_PLATE_DISTANCE = 80;

type Rgb = readonly [number, number, number];

function rgb(hex: string): Rgb | null {
  const s = hexToRgb(hex);
  if (!s) return null;
  const [r, g, b] = s.split(" ").map(Number);
  return [r, g, b] as const;
}

/** Every `#rrggbb` stop in a CSS gradient string, in order. */
export function gradientStops(background: string | null | undefined): Rgb[] {
  if (!background) return [];
  return (background.match(/#[0-9a-fA-F]{6}\b/g) ?? [])
    .map(rgb)
    .filter((c): c is Rgb => c !== null);
}

export function crestNeedsPlate(
  teamColor: string | null | undefined,
  background: string | null | undefined,
): boolean {
  const team = teamColor ? rgb(teamColor) : null;
  if (!team) return false;
  return gradientStops(background).some((stop) => colorDistance(team, stop) < CREST_PLATE_DISTANCE);
}
