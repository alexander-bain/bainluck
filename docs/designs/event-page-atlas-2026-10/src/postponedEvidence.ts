import {eventReaderTime} from './eventReaderTime.ts';
import capture from './postponedCapture.json' with {type:'json'};
export const postponedCapture=capture;
export const postponedCutoff=Date.parse(capture.historyCutoff);
export const postponedSides=['home','away','draw'] as const;
export type PostponedSide=typeof postponedSides[number];
export type TradePoint={t:number;value:number};
type Candle={end_period_ts:number;volume_fp?:unknown;price?:{close_dollars?:unknown}};
const contracts=['KXLALIGAGAME-26SEP16LEVATH-LEV','KXLALIGAGAME-26SEP16LEVATH-ATH','KXLALIGAGAME-26SEP16LEVATH-TIE'];
/** Last trade within a positively traded hour, never a carried previous price, midpoint or settlement. */
export function tradedHours(ticker:string,candles:Candle[],cutoff=postponedCutoff):TradePoint[]{
 if(!contracts.includes(ticker)||!Number.isFinite(cutoff)||cutoff>postponedCutoff)return [];
 const result=new Map<number,TradePoint>(),conflicts=new Set<number>();
 for(const c of candles){const t=c.end_period_ts*1000,raw=c.price?.close_dollars,v=typeof raw==='string'&&raw.trim()!==''?Number(raw):NaN,volume=typeof c.volume_fp==='string'?Number(c.volume_fp):NaN;
  if(!Number.isFinite(t)||t%3600000!==0||t>cutoff||t<Date.parse('2026-09-12T00:00:00Z')||!Number.isFinite(v)||v<0||v>1||!(volume>0))continue;
  const prev=result.get(t);if(prev&&prev.value!==v)conflicts.add(t);else result.set(t,{t,value:v});
 }
 return [...result.values()].filter(p=>!conflicts.has(p.t)).sort((a,b)=>a.t-b.t);
}
export const postponedHistories=postponedSides.map((side,i)=>({side,name:capture.contracts[i].name,ticker:contracts[i],points:tradedHours(capture.contracts[i].ticker,capture.contracts[i].candles)}));
export const postponedTimeline=Array.from({length:97},(_,i)=>{const t=Date.parse('2026-09-12T00:00:00Z')+i*3600000;return {t,...Object.fromEntries(postponedHistories.map(h=>[h.side,h.points.find(p=>p.t===t)?.value??null]))} as {t:number}&Record<PostponedSide,number|null>});
export const postponedObservations=postponedTimeline.filter(p=>postponedSides.some(side=>p[side]!==null));
export function postponedForDetail(d:Record<string,unknown>):boolean{return (d.event_id??d.id)===capture.eventId&&d.home_team===capture.home&&d.away_team===capture.away&&d.status==='voided'&&!d.quality_hold&&d.home_score==null&&d.away_score==null;}
type PostponedRow={source?:unknown;source_file?:unknown;_inverted?:unknown;_market_id?:unknown;ticker?:unknown;outcome_name?:unknown;_postponed_history?:unknown};
export function withPostponedHistory<T>(detail:Record<string,unknown>,rows:T[]):T[]{return postponedForDetail(detail)?rows.map(row=>({...row,_postponed_history:'levante-traded-hours-v183'})):rows;}
export function postponedBaseline(row:PostponedRow):TradePoint|null{
 if(row._postponed_history!=='levante-traded-hours-v183'||row.source!=='kalshi'||row.source_file!=='void-kalshi-original.json'||row._inverted===true)return null;
 const h=postponedHistories.find(h=>h.ticker===row._market_id&&h.ticker===row.ticker);
 if(!h||row.outcome_name!==(h.side==='draw'?'Tie':h.name))return null;
 return h.points.at(-1)??null;
}
export const postponedClock=(t:number)=>eventReaderTime.full(t);
export function postponedBaselineNote(row:PostponedRow):string|null{const p=postponedBaseline(row);return p?`Kalshi last trade in the hour ending ${postponedClock(p.t)}. Before the original scheduled match; not a closing probability or settlement amount.`:null;}

/** Exact-hour inspection never substitutes the last trade for a missing value. */
export function postponedSelection(at:number){
 const index=postponedObservations.findIndex(p=>p.t===at),selected=index<0?null:postponedObservations[index];
 return {index,selected,values:postponedHistories.map(h=>({side:h.side,name:h.name,value:selected?.[h.side]??null,latest:h.points.at(-1)?.value??null}))};
}
