// Exact design specimen only. Production identity/blending/freshness stay owner controlled.
export type Phase = 'before' | 'during' | 'final';
export type Side = 'Yes' | 'No';
export type Point = {t:number;p:number};
export type Outcome = {side:Side;token:string;winner:boolean;history:Point[]};
export type Market = {id:string;condition:string;label:string;low:number|null;high:number|null;predicate:string;rules:string;settledAt:number;outcomes:Outcome[]};
export type Observation = {id:string;t:number;c:number;f:number};
export type Capture = {eventID:string;station:string;eventTimeZone:string;dayStart:number;dayEnd:number;duringCutoff:number;markets:Market[];observations:Observation[]};
const finite = (v:unknown):v is number => typeof v==='number' && Number.isFinite(v);
const validPoint = (p:Point) => finite(p.t) && Number.isSafeInteger(p.t) && finite(p.p) && p.p>=0 && p.p<=1;
function admitted(c:Capture){return c.eventID==='1186943'&&c.station==='KLGA'&&c.eventTimeZone==='America/New_York'&&c.dayStart===1792123200&&c.dayEnd===1792209600&&c.duringCutoff===1792166400;}
export function phaseCutoff(c:Capture,phase:Phase){return phase==='before'?c.dayStart:phase==='during'?c.duringCutoff:c.dayEnd;}
/** A duplicate identity never quietly borrows another market/outcome. */
export function weatherMarket(c:Capture,id:string){if(!admitted(c))return null;const rows=c.markets.filter(m=>m.id===id);return rows.length===1?rows[0]:null;}
export function weatherOutcome(m:Market,side:Side){const rows=m.outcomes.filter(o=>o.side===side);return rows.length===1?rows[0]:null;}
/** The pre-day reference is strict, dated and independent for every source token. */
export function weatherBaseline(c:Capture,m:Market,side:Side='Yes'){
 if(!admitted(c)||weatherMarket(c,m.id)!==m)return null;
 const points=weatherOutcome(m,side)?.history.filter(p=>validPoint(p)&&p.t<c.dayStart)??[];
 return uniqueLast(points);
}
function uniqueLast(points:Point[]){
 if(!points.length)return null;
 const last=Math.max(...points.map(p=>p.t)),same=points.filter(p=>p.t===last);
 return same.length===1?same[0]:null;
}
/** Final history stops at the observation day's end; no post-day near-certainty or result endpoint is appended. */
export function weatherHistory(c:Capture,m:Market,side:Side,phase:Phase){
 if(!admitted(c)||weatherMarket(c,m.id)!==m)return [];
 const cutoff=phaseCutoff(c,phase),before=phase==='before';
 const points=weatherOutcome(m,side)?.history.filter(p=>validPoint(p)&&(before?p.t<cutoff:p.t<=cutoff))??[];
 const counts=new Map<number,number>();for(const p of points)counts.set(p.t,(counts.get(p.t)??0)+1);
 return points.filter(p=>counts.get(p.t)===1).sort((a,b)=>a.t-b.t);
}
export function weatherSegments(points:Point[],maxGap=90*60){
 const segments:Point[][]=[];
 for(const p of points){const segment=segments.at(-1);if(!segment||p.t-segment.at(-1)!.t>maxGap)segments.push([p]);else segment.push(p);}
 return segments;
}
/** No nearest-neighbour snap and no last-known-value fill while inspecting a time. */
export function weatherAt(points:Point[],t:number){const rows=points.filter(p=>p.t===t);return rows.length===1?rows[0]:null;}
export function weatherActual(c:Capture,phase:Phase){
 if(phase==='before'||!admitted(c))return null;
 const cutoff=phaseCutoff(c,phase),rows=c.observations.filter(p=>finite(p.t)&&p.t>=c.dayStart&&p.t<c.dayEnd&&p.t<=cutoff&&finite(p.c)&&finite(p.f)&&Math.abs(p.f-(p.c*9/5+32))<.00001);
 if(!rows.length)return null;
 const value=Math.max(...rows.map(p=>p.f)),first=rows.filter(p=>p.f===value).sort((a,b)=>a.t-b.t)[0];
 return {f:value,firstObservedAt:first.t,readingCount:rows.length,label:phase==='final'?'Captured station high':'Captured high so far'};
}
/** Settlement is supplied by exact CLOB token winner flags, never terminal price or the station trace. */
export function weatherResult(c:Capture,m:Market,side:Side,phase:Phase){
 if(!admitted(c)||weatherMarket(c,m.id)!==m||phase!=='final'||!finite(m.settledAt)||m.settledAt<c.dayEnd)return null;
 const outcome=weatherOutcome(m,side);
 if(!outcome||m.outcomes.length!==2||m.outcomes.some(o=>typeof o.winner!=='boolean')||m.outcomes.filter(o=>o.winner).length!==1)return null;
 return outcome.winner?'Won':'Lost';
}
export function weatherReading(c:Capture,id:string,side:Side,phase:Phase){
 const market=weatherMarket(c,id);if(!market)return null;
 const outcome=weatherOutcome(market,side);if(!outcome)return null;
 const history=weatherHistory(c,market,side,phase);
 return {id:market.id,side,token:outcome.token,label:market.label,predicate:market.predicate,rules:market.rules,baseline:weatherBaseline(c,market,side),history,last:uniqueLast(history),result:weatherResult(c,market,side,phase),currentChance:null};
}
/** Current source capture cannot supply a live headline, and independent bins are never normalized. */
export function weatherRangeFrame(c:Capture,phase:Phase){
 const rows=c.markets.flatMap(m=>{const r=weatherReading(c,m.id,'Yes',phase);return r?[r]:[]});
 const order=rows.filter(r=>r.baseline).sort((a,b)=>b.baseline!.p-a.baseline!.p||a.id.localeCompare(b.id)).map(r=>r.id);
 return {phase,cutoff:phaseCutoff(c,phase),rows,order,actual:weatherActual(c,phase),currentChance:null};
}
