import {readerClock} from './readerTime.ts';
import raw from './racingLiveCapture.json' with {type:'json'};
import originals from './racingEvidence.json' with {type:'json'};
export const racingLiveWire=raw;
export type RaceTrade={asset:string;conditionId:string;timestamp:number;price:number;size:number;outcome:string;transactionHash:string};
export type RacePoint={t:number;value:number};
export const raceClock=(t:number|string)=>readerClock(t,{seconds:true});
export function raceStage(index:number){return Number.isInteger(index)&&index>=0&&index<raw.stages.length?raw.stages[index]:null;}
export function raceTrades(rows:RaceTrade[],token:string,condition:string,start:number,cutoff:number):RacePoint[]{
 if(!Number.isFinite(start)||!Number.isFinite(cutoff)||cutoff<start)return [];
 const times=new Map<number,Set<number>>();
 for(const r of rows){
  if(r.asset!==token||r.conditionId!==condition||r.outcome!=='Yes'||!r.transactionHash||!Number.isFinite(r.timestamp)||!Number.isInteger(r.timestamp)||!Number.isFinite(r.price)||r.price<0||r.price>1||!Number.isFinite(r.size)||r.size<=0)continue;
  const t=r.timestamp*1000;if(t<start||t>cutoff)continue;
  const values=times.get(t)??new Set<number>();values.add(r.price);times.set(t,values);
 }
 // Different prices in the same reported second are ambiguous; do not invent ordering or an average.
 return [...times].filter(([,values])=>values.size===1).map(([t,values])=>({t,value:[...values][0]})).sort((a,b)=>a.t-b.t);
}
export function raceHistory(key:string,stage:number){const d=raw.drivers.find(d=>d.key===key),frame=raceStage(stage);return d&&frame?raceTrades(d.trades,d.tokenID,d.conditionID,Date.parse(raw.start),Date.parse(frame.reportedAt)):[];}
export function raceQuote(key:string,stage:number,mode='captured'){const frame=raceStage(stage);if(!frame||mode!=='captured')return null;const q=raceHistory(key,stage).at(-1);return q&&Date.parse(frame.reportedAt)-q.t<=300000?q:null;}
export function raceBaseline(key:string){const d=originals.rows.find(r=>r.key===key);const b=d?.baseline;return b&&Number.isFinite(b.value)&&b.value>=0&&b.value<=1&&Date.parse(b.at)<Date.parse(raw.start)?b:null;}
export function raceSegments(points:RacePoint[]){const out:RacePoint[][]=[];for(const p of points){const last=out.at(-1);if(last&&p.t-last.at(-1)!.t<=300000)last.push(p);else out.push([p]);}return out;}
export function racePlot(key:string,stage:number){return raceSegments(raceHistory(key,stage)).flatMap((group,i)=>i?[{t:group[0].t-1,value:null},...group]:group);}
export function raceExact(key:string,stage:number,at:number){return raceHistory(key,stage).find(p=>p.t===at)??null;}
export function raceDelta(key:string,stage:number,mode='captured'){const q=raceQuote(key,stage,mode),b=raceBaseline(key);return q&&b?q.value-b.value:null;}
export const raceOriginals=originals.rows.map(r=>({key:r.key,name:r.name,family:r.family,marketID:r.sourceMarketID,conditionID:r.conditionID,selected:r.selected,rules:r.rules,baseline:raceBaseline(r.key)}));

export function raceTimes(stage:number){return [...new Set(raw.drivers.flatMap(d=>raceHistory(d.key,stage).map(p=>p.t)))].sort((a,b)=>a-b);}
