import raw from './soccerFinalHistory.json' with {type:'json'};
export type SoccerFinalWire=typeof raw;
export type SoccerPoint={index:number;t:number;at:string;home:number;away:number;draw:number;pregame:boolean;segment:number};
export type SoccerScope='game'|'pregame'|'all';
export function soccerFinalHistory(w:SoccerFinalWire):SoccerPoint[]{
 if(w.eventID!==15311089||w.home!=='Hull City'||w.away!=='Everton'||w.source!=='kalshi'||w.verifiedScope!=='full_event_winner'||!w.verifiedStart||w.status!=='completed'||w.homeScore!==2||w.awayScore!==2||w.cadence!==300)return [];
 const start=Date.parse(w.start),end=Date.parse(w.completedAt);if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start)return [];
 const points:SoccerPoint[]=[];let previous=-Infinity,segment=0,broken=false;
 for(const [index,row] of w.rows.entries()){
  const t=Date.parse(row.timestamp),home=row.home_probability,away=row.away_probability,draw=row.draw_probability;
  if(!Number.isFinite(t)||t<=previous)return [];previous=t;
  if(t>=end||row.evidence?.kind==='terminal_row'||[home,away,draw].some(p=>typeof p!=='number'||!Number.isFinite(p)||p<=0||p>=1)){broken=true;continue}
  if(points.length&&(broken||t-points.at(-1)!.t>w.cadence*1000))segment++;
  points.push({index,t,at:row.timestamp,home,away,draw:draw!,pregame:t<start,segment});broken=false;
 }
 return points;
}
export const retainedSoccerHistory=soccerFinalHistory(raw);
export function soccerScope(points:SoccerPoint[],scope:SoccerScope){if(scope==='all')return points;if(scope==='pregame')return points.filter(p=>p.pregame);const pre=points.filter(p=>p.pregame).at(-1);return points.filter(p=>!p.pregame||p.index===pre?.index)}
export function soccerAt(points:SoccerPoint[],t:number){const exact=points.find(p=>p.t===t);if(exact)return exact;const right=points.findIndex(p=>p.t>t);if(right<1)return null;const a=points[right-1],b=points[right];return a.segment===b.segment?(t-a.t<=b.t-t?a:b):null}
