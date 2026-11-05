import raw from './combatWinnerHistory.json' with {type:'json'};
export type CombatWinnerWire=typeof raw;
export type CombatWinnerPoint={index:number;t:number;at:string;home:number;away:number;pregame:boolean;segment:number};
export type CombatWinnerScope='game'|'pregame'|'all';
export function combatWinnerHistory(w:CombatWinnerWire):CombatWinnerPoint[]{
 if(w.event_id!==15318681||w.home_team!=='Ateba Gautier'||w.away_team!=='Roman Kopylov'||w.status!=='suspended'||w.completed_at!==null||w.commence_time_is_kickoff!==true||JSON.stringify(w.binary_outcomes)!==JSON.stringify(['Ateba Gautier','Roman Kopylov']))return [];
 const start=Date.parse(w.commence_time),cadence=w.evidence_contract.resolution_s;
 if(!Number.isFinite(start)||cadence!==300)return [];
 const points:CombatWinnerPoint[]=[];let previous=-Infinity,segment=0,broken=false;
 for(const [index,row] of w.aggregate_line.entries()){
  const t=Date.parse(row.timestamp),home=row.home_probability;
  if(!Number.isFinite(t)||t<=previous)return [];previous=t;
  if(typeof home!=='number'||!Number.isFinite(home)||home<=0||home>=1){broken=true;continue;}
  if(points.length&&(broken||t-points.at(-1)!.t>cadence*1000))segment++;
  points.push({index,t,at:row.timestamp,home,away:1-home,pregame:t<start,segment});broken=false;
 }
 return points;
}
export const retainedCombatWinnerHistory=combatWinnerHistory(raw);
export function combatWinnerScope(points:CombatWinnerPoint[],scope:CombatWinnerScope){if(scope==='all')return points;if(scope==='pregame')return points.filter(p=>p.pregame);const pre=points.filter(p=>p.pregame).at(-1);return points.filter(p=>!p.pregame||p.index===pre?.index);}
export function combatWinnerAt(points:CombatWinnerPoint[],t:number):CombatWinnerPoint|null{
 if(!Number.isFinite(t)||!points.length||t<points[0].t||t>points.at(-1)!.t)return null;
 const exact=points.find(p=>p.t===t);if(exact)return exact;
 const right=points.findIndex(p=>p.t>t);if(right<1)return null;const a=points[right-1],b=points[right];if(a.segment!==b.segment)return null;return t-a.t<=b.t-t?a:b;
}
