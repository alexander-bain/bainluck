import raw from './esportsWinnerHistory.json' with {type:'json'};
import type {CombatWinnerPoint} from './combatWinnerHistory';
export type EsportsWinnerWire=typeof raw;
// The verified full-event speaker supplies binary orientation; the parent also contains a nested handicap.
export function esportsWinnerHistory(w:EsportsWinnerWire):CombatWinnerPoint[]{
 if(w.event_id!==15322123||w.home_team!=='Nice Try'||w.away_team!=='Flame Hard'||w.status!=='suspended'||w.completed_at!==null||w.commence_time_is_kickoff!==true||w.verified_scope!=='full_event_winner'||JSON.stringify(w.binary_outcomes)!==JSON.stringify(['Nice Try','Flame Hard']))return [];
 const start=Date.parse(w.commence_time),cadence=w.evidence_contract.resolution_s;
 if(!Number.isFinite(start)||cadence!==300||!w.terminalWitnesses.length)return [];
 const terminals=w.terminalWitnesses.map(r=>Date.parse(r.timestamp));
 if(w.terminalWitnesses.some((r,i)=>!Number.isFinite(terminals[i])||terminals[i]<start||r.evidence.kind!=='final'||r.home_probability!==1||r.away_probability!==0||r.draw_probability!==null))return [];
 const boundary=Math.min(...terminals),points:CombatWinnerPoint[]=[];let previous=-Infinity,segment=0,broken=false;
 for(const [index,row] of w.aggregate_line.entries()){
  const t=Date.parse(row.timestamp),home=row.home_probability;
  if(!Number.isFinite(t)||t<=previous)return [];previous=t;
  if(t>=boundary||typeof home!=='number'||!Number.isFinite(home)||home<=0||home>=1){broken=true;continue;}
  if(points.length&&(broken||t-points.at(-1)!.t>cadence*1000))segment++;
  points.push({index,t,at:row.timestamp,home,away:1-home,pregame:t<start,segment});broken=false;
 }
 return points;
}
export const retainedEsportsWinnerHistory=esportsWinnerHistory(raw);
