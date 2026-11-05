import {readerTime,readerClock,deviceTimeZone} from './readerTime.ts';
import raw from './cricketLiveCapture.json' with {type:'json'};
export const cricketLiveWire=raw;
export const liveCricketEvent='KXTESTMATCH-26OCT090330AUSSA';
export const liveCricketSides=['SA','AUS','TIE'] as const;
export type LiveCricketSide=typeof liveCricketSides[number];
export type CricketTrade={t:number;value:number;interval:number};
type Candle={end_period_ts:number;volume_fp?:unknown;price?:{close_dollars?:unknown}};
export function cricketTradedHistory(ticker:string,candles:Candle[],interval:number,cutoff:number):CricketTrade[]{
 if(!liveCricketSides.some(s=>ticker===liveCricketEvent+'-'+s)||!Number.isFinite(cutoff)||![60,3600].includes(interval))return [];
 const counts=new Map<number,number>();for(const c of candles)counts.set(c.end_period_ts,(counts.get(c.end_period_ts)??0)+1);
 return candles.flatMap(c=>{const t=c.end_period_ts*1000,price=c.price?.close_dollars,value=typeof price==='string'&&price.trim()?Number(price):NaN,volume=typeof c.volume_fp==='string'?Number(c.volume_fp):NaN;
  return Number.isFinite(t)&&t<=cutoff&&c.end_period_ts%interval===0&&counts.get(c.end_period_ts)===1&&Number.isFinite(value)&&value>=0&&value<=1&&volume>0?[{t,value,interval}]:[];
 }).sort((a,b)=>a.t-b.t);
}
export const cricketLiveStages=raw.stages;
export const cricketLiveName=(s:LiveCricketSide)=>s==='SA'?'South Africa':s==='AUS'?'Australia':'Draw / tie';
// Freeze the device zone for this mounted atlas session; source instants never change.
export const cricketLiveZone=deviceTimeZone();
export const cricketLiveClock=(t:number,timeZone=cricketLiveZone)=>readerTime(t,{timeZone,seconds:true});
export const cricketLiveAxisDate=(t:number,timeZone=cricketLiveZone)=>readerTime(t,{timeZone,dateOnly:true});
export const cricketLiveAxisClock=(t:number,timeZone=cricketLiveZone)=>readerClock(t,{timeZone});
export function liveCricketHistory(side:LiveCricketSide,stage:number,window:'match'|'day5'='day5'){
 const record=raw.history.find(h=>h.ticker===liveCricketEvent+'-'+side),moment=raw.stages[stage];if(!record||!moment)return [];
 const cutoff=Date.parse(moment.reportedAt),data=window==='day5'?record.minute:record.hourly;
 if(data.ticker!==record.ticker)return [];
 return cricketTradedHistory(record.ticker,data.candlesticks,window==='day5'?60:3600,cutoff);
}
export function liveCricketBaseline(side:LiveCricketSide){const h=raw.history.find(h=>h.ticker===liveCricketEvent+'-'+side);return h&&h.hourly.ticker===h.ticker?cricketTradedHistory(h.ticker,h.hourly.candlesticks,3600,Date.parse('2026-10-09T00:00:00Z')).at(-1)??null:null;}
export function liveCricketQuote(side:LiveCricketSide,stage:number){const history=liveCricketHistory(side,stage),last=history.at(-1),at=Date.parse(raw.stages[stage]?.reportedAt??'');return last&&at-last.t<=300000?last:null;}
export function cricketOverBalls(overs:string):number|null{const m=/^(\d+)\.([0-5])$/.exec(overs);return m?Number(m[1])*6+Number(m[2]):null;}
export function cricketChase(stage:number){const s=raw.stages[stage];if(!s||cricketOverBalls(s.overs)===null||s.wickets<0||s.wickets>10||s.runs<0||s.runs>=raw.targetRuns)return null;return {...s,need:raw.targetRuns-s.runs,wicketsLeft:10-s.wickets,target:raw.targetRuns,balls:cricketOverBalls(s.overs)!};}
export function liveCricketPlot(stage:number,window:'match'|'day5'){
 const series=liveCricketSides.map(side=>({side,points:liveCricketHistory(side,stage,window)}));
 const times=[...new Set(series.flatMap(s=>s.points.map(p=>p.t)))].sort((a,b)=>a-b);if(!times.length)return [];
 const step=window==='day5'?60000:3600000,start=times[0],end=Math.floor(Date.parse(raw.stages[stage].reportedAt)/step)*step;
 return Array.from({length:Math.floor((end-start)/step)+1},(_,i)=>{const t=start+i*step;return {t,...Object.fromEntries(series.map(s=>[s.side,s.points.find(p=>p.t===t)?.value??null]))} as {t:number}&Record<LiveCricketSide,number|null>});
}
