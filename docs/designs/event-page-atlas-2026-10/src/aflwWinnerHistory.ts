import raw from './aflwWinnerHistory.json' with {type:'json'};
import type {FinalHistoryPoint} from './finalHistoryEvidence';
export type AflwHistoryWire=typeof raw;
export const aflwStart=Date.parse(raw.commence_time);
/** Both team prices are supplied; neither a complement nor a blend is synthesized. */
export function aflwWinnerHistory(w:AflwHistoryWire):FinalHistoryPoint[]{
 if(w.event_id!==15324784||w.home_team!=='Sydney Swans'||w.away_team!=='Carlton Blues'||w.commence_time_is_kickoff!==true||w.evidence_contract.resolution_s!==300)return [];
 const start=Date.parse(w.commence_time);if(start!==Date.parse('2026-10-11T04:04:00Z'))return [];
 const rows=w.win_prob_history.polymarket;
 const result:FinalHistoryPoint[]=[];let previous=-Infinity,segment=0;
 for(const [index,row] of rows.entries()){
  const t=Date.parse(row.timestamp);if(!Number.isFinite(t)||t<=previous)return [];previous=t;
  if(row.evidence?.kind==='final')break;
  const home=row.home_probability,away=row.away_probability;
  if(!Number.isFinite(home)||!Number.isFinite(away)||home<0||home>1||away<0||away>1||row.draw_probability!==null)return [];
  if(result.length&&t-result.at(-1)!.t>300000)segment++;
  result.push({index,t,at:row.timestamp,home,away,pregame:t<start,segment});
 }
 return result;
}
export const retainedAflwHistory=aflwWinnerHistory(raw);
export const aflwPregame=retainedAflwHistory.filter(p=>p.pregame).at(-1);
