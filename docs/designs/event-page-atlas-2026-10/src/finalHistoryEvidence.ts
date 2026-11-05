import raw from './finalHistoryEvidence.json' with {type:'json'};
export type FinalHistoryWire=typeof raw[number];
export type FinalHistoryPoint={index:number;t:number;at:string;home:number;away:number;pregame:boolean;segment:number};
export type FinalHistoryScope='game'|'pregame'|'all';
const identities:Record<string,[number,string,string]>={'nba-half':[15321889,'Golden State Warriors','Los Angeles Lakers'],nba:[15320337,'Los Angeles Clippers','Golden State Warriors'],mlb:[15321836,'Houston Astros','Chicago White Sox'],nhl:[15169793,'Minnesota Wild','Boston Bruins']};
export function finalHistoryEvidence(w:FinalHistoryWire):FinalHistoryPoint[]{
 const id=identities[w.key];if(!id||w.event_id!==id[0]||w.home_team!==id[1]||w.away_team!==id[2]||w.status!=='completed'||!w.binaryBlend||!w.commence_time_is_kickoff)return [];
 const start=Date.parse(w.commence_time),end=Date.parse(w.completed_at),cadence=w.evidence_contract.resolution_s;
 if(!Number.isFinite(start)||!Number.isFinite(end)||end<start||cadence!==300)return [];
 const terminal=w.aggregate_line.at(-1);
 if(!terminal||!w.terminalWitnesses.some(p=>p.timestamp===terminal.timestamp&&p.home_probability===terminal.home_probability&&((p.evidence as {kind?:string}|null)?.kind==='final'||(p.game_state as {final?:boolean}|null)?.final===true)))return [];
 const points:FinalHistoryPoint[]=[];let previous=-Infinity,segment=0,broken=false;
 for(const [index,row] of w.aggregate_line.slice(0,-1).entries()){
  const t=Date.parse(row.timestamp),home=row.home_probability;
  if(!Number.isFinite(t)||t<=previous)return [];previous=t;
  if(t>end||typeof home!=='number'||!Number.isFinite(home)||home<0||home>1){broken=true;continue;}
  if(points.length&&(broken||t-points.at(-1)!.t>cadence*1000))segment++;
  points.push({index,t,at:row.timestamp,home,away:1-home,pregame:t<start,segment});broken=false;
 }
 return points;
}
export const finalHistoryWires=raw;
export const finalHistories=Object.fromEntries(raw.map(w=>[w.key,finalHistoryEvidence(w)]));
export function finalHistoryScope(points:FinalHistoryPoint[],scope:FinalHistoryScope){if(scope==='all')return points;if(scope==='pregame')return points.filter(p=>p.pregame);const pre=points.filter(p=>p.pregame).at(-1);return points.filter(p=>!p.pregame||p.index===pre?.index);}
export function finalHistoryAt(points:FinalHistoryPoint[],t:number):FinalHistoryPoint|null{
 if(!Number.isFinite(t)||!points.length||t<points[0].t||t>points.at(-1)!.t)return null;
 const exact=points.find(p=>p.t===t);if(exact)return exact;
 const right=points.findIndex(p=>p.t>t);if(right<1)return null;const a=points[right-1],b=points[right];if(a.segment!==b.segment)return null;return t-a.t<=b.t-t?a:b;
}
