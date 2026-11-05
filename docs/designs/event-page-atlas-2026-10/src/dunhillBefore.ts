import original from './dunhill-before.json' with {type:'json'};
export type BeforePoint={at:string;t:number;probability:number;volume:number;sourceFile:string;sourceCandleIndex:number;originalCandle:{end_period_ts:number;price:{close_dollars?:string};volume_fp:string}};
export type BeforeGolfer={id:string;name:string;ticker:string;points:BeforePoint[]};
export type BeforeFixture={schema:number;eventKey:string;name:string;marketID:number;source:string;predicate:string;recording:string;intervalMinutes:number;beforeBoundary:string;exactFirstTeeKnown:boolean;rows:BeforeGolfer[]};
export const dunhillBefore=original as BeforeFixture;
const HOUR=3_600_000;
/** Only original positively traded hourly closes are eligible; no final fields enter this model. */
export function admittedBefore(source:BeforeFixture=dunhillBefore):BeforeGolfer[] {
 if(source.schema!==1||source.eventKey!=='kalshi:KXDPWORLDTOUR-ALDLC26'||source.marketID!==62455818||source.source!=='kalshi'||source.predicate!=='tournament-winner'||source.recording!=='positive-volume-hour-ending-trade'||source.intervalMinutes!==60||source.beforeBoundary!=='2026-10-01T00:00:00+00:00'||source.exactFirstTeeKnown!==false)return [];
 const cutoff=Date.parse(source.beforeBoundary);
 const duplicate=(field:'id'|'ticker'|'name',value:string)=>source.rows.filter(r=>r[field]===value).length!==1;
 return source.rows.filter(r=>{
  if(!r.id||!r.name||!r.ticker.startsWith('KXDPWORLDTOUR-ALDLC26-')||(['id','ticker','name'] as const).some(k=>duplicate(k,r[k])))return false;
  const times=new Set<number>();
  return r.points.every(p=>{
   if(!Number.isFinite(p.t)||Date.parse(p.at)!==p.t||p.t>cutoff||p.t%HOUR!==0||times.has(p.t)||!Number.isFinite(p.probability)||p.probability<=0||p.probability>=1||!Number.isFinite(p.volume)||p.volume<=0)return false;
   const raw=p.originalCandle;if(!raw||raw.end_period_ts*1000!==p.t||Number(raw.price?.close_dollars)!==p.probability||Number(raw.volume_fp)!==p.volume)return false;
   times.add(p.t);return true;
  });
 }).map(r=>({id:r.id,name:r.name,ticker:r.ticker,points:[...r.points].sort((a,b)=>a.t-b.t)}));
}
export function beforeHours(source:BeforeFixture=dunhillBefore){return [...new Set(admittedBefore(source).flatMap(r=>r.points.map(p=>p.t)))].sort((a,b)=>a-b);}
export function beforeSegments(points:readonly BeforePoint[]){
 const segments:BeforePoint[][]=[];
 for(const point of points){const last=segments.at(-1)?.at(-1);if(!last||point.t-last.t!==HOUR)segments.push([point]);else segments[segments.length-1].push(point);}
 return segments;
}
export function beforeFrame(at:number,source:BeforeFixture=dunhillBefore){
 const rows=admittedBefore(source),hours=[...new Set(rows.flatMap(r=>r.points.map(p=>p.t)))].sort((a,b)=>a-b);
 if(!Number.isFinite(at)||!hours.includes(at))return null;
 const entries=rows.map(row=>{
  const points=row.points.filter(p=>p.t<=at),point=points.find(p=>p.t===at)??null,dayEarlier=points.find(p=>p.t===at-24*HOUR)??null;
  return {id:row.id,name:row.name,ticker:row.ticker,points,segments:beforeSegments(points),point,lastRecorded:points.at(-1)??null,dayEarlier,change:point&&dayEarlier?point.probability-dayEarlier.probability:null};
 });
 const ceiling=Math.min(1,Math.max(.05,Math.ceil((Math.max(0,...entries.flatMap(r=>r.points.map(p=>p.probability)))+.005)*20)/20));
 const ranked=entries.filter(r=>r.point!==null).sort((a,b)=>b.point!.probability-a.point!.probability||a.name.localeCompare(b.name));
 const movement=entries.filter(r=>r.change!==null).sort((a,b)=>Math.abs(b.change!)-Math.abs(a.change!)||a.name.localeCompare(b.name));
 return {at,first:hours[0],hours:hours.filter(t=>t<=at),ceiling,entries,ranked,movement};
}
export type BeforeFrame=NonNullable<ReturnType<typeof beforeFrame>>;
/** The user-selected golfer is retained even when no trade exists in the selected hour. */
export function beforeCohort(frame:BeforeFrame,selected?:string){
 const chosen=frame.entries.find(r=>r.id===selected);
 return [...(chosen?[chosen]:[]),...frame.ranked.filter(r=>r.id!==chosen?.id).slice(0,chosen?2:3)];
}
/** A historical point never becomes a current quote merely because it is the latest available. */
export function beforeReadout(entry:BeforeFrame['entries'][number]){
 return entry.point?{state:'recorded' as const,probability:entry.point.probability,at:entry.point.at}:{state:'not-recorded' as const,probability:null,at:null};
}
