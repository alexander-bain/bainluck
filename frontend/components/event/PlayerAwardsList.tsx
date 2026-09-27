import { teamTextColor } from "@/lib/teamColors";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import type { PlayerAwardRow } from "@/lib/playerAwardRows";

/**
 * A team card's PLAYER AWARDS rows — one component for the home and away cards.
 *
 * #9048: the name used to sit in a fixed 96px column (`w-24 truncate`), so
 * "Patrick Mahomes" printed as "Patrick Maho…" beside free space. One grid now
 * spans every row: the name column is as wide as the LONGEST name in the list
 * (capped at 55% of the card, so an outlier still truncates rather than
 * squeezing the numbers off the card), and the awards still line up across rows,
 * which is what the fixed width was for. The number goes through the shared
 * rule (#3867), so a near-certain finalist cannot print "100%".
 */
export default function PlayerAwardsList({ rows, color }: { rows: PlayerAwardRow[]; color: string }) {
  return (
    <div
      className="grid grid-cols-[1.5rem_fit-content(55%)_minmax(0,1fr)] items-center gap-x-2 gap-y-3 py-1"
      data-testid="player-awards-list"
    >
      {rows.map((p) => {
        const initials = p.name.split(" ").map((w) => w[0]).join("").slice(0, 2);
        return (
          <div key={p.name} className="contents">
            <div className="w-6 h-6 rounded-full grid place-items-center font-mono font-bold text-white text-[9px]" style={{ background: color }}>{initials}</div>
            <span className="text-xs font-semibold min-w-0 truncate" title={p.name}>{p.name}</span>
            <div className="flex items-center gap-3 flex-wrap min-w-0">
              {p.awards.map((a, i) => (
                <span key={i} className="text-[10px] text-text-secondary">
                  {a.label} <span className="font-bold font-mono" style={{ color: teamTextColor(color) || "var(--text-primary)" }}>{formatProbabilityPercent(a.prob)}</span>
                </span>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
