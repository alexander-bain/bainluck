import raw from './tennisProbabilityHistory.json' with {type:'json'};
export type TennisHistoryWire=typeof raw;
export type TennisHistoryPoint={index:number;t:number;at:string;home:number;away:number;books:number;pregame:boolean;segment:number};
export type TennisHistoryScope='game'|'pregame'|'all';
export function tennisProbabilityHistory(w:TennisHistoryWire):TennisHistoryPoint[]{
 if(w.event_id!==15310688||w.home_team!=='Alexander Zverev'||w.away_team!=='Ben Shelton'||w.status!=='completed')return [];
 const start=Date.parse(w.commence_time),end=Date.parse(w.completed_at);if(!Number.isFinite(start)||!Number.isFinite(end)||end<start)return [];
 const points:TennisHistoryPoint[]=[];let previous=-Infinity,segment=0,broken=false;
 for(const [index,row] of w.history.entries()){
  const t=Date.parse(row.timestamp),valid=(n:unknown)=>typeof n==='number'&&Number.isFinite(n)&&n>=0&&n<=1;
  if(!Number.isFinite(t)||t<=previous)return [];previous=t;
  if(t>end||!Number.isInteger(row.bookmaker_count)||row.bookmaker_count<1||!valid(row.home_probability)||!valid(row.away_probability)){broken=true;continue;}
  if(points.length&&(broken||t-points.at(-1)!.t>300000))segment++;
  points.push({index,t,at:row.timestamp,home:row.home_probability,away:row.away_probability,books:row.bookmaker_count,pregame:t<start,segment});broken=false;
 }
 return points;
}
export const retainedTennisHistory=tennisProbabilityHistory(raw);
export function tennisHistoryScope(points:TennisHistoryPoint[],scope:TennisHistoryScope){if(scope==='all')return points;if(scope==='pregame')return points.filter(p=>p.pregame);const pre=points.filter(p=>p.pregame).at(-1);return points.filter(p=>!p.pregame||p.index===pre?.index);}
export function tennisHistoryAt(points:TennisHistoryPoint[],t:number):TennisHistoryPoint|null{
 if(!Number.isFinite(t)||!points.length||t<points[0].t||t>points.at(-1)!.t)return null;
 const exact=points.find(p=>p.t===t);if(exact)return exact;
 const right=points.findIndex(p=>p.t>t);if(right<1)return null;const a=points[right-1],b=points[right];if(a.segment!==b.segment)return null;return t-a.t<=b.t-t?a:b;
}
