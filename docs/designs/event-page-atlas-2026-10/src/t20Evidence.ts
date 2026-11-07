import {readerTime} from './readerTime.ts';
import wire from './t20Evidence.json' with {type:'json'};
export const t20Wire=wire;
export const t20Event='KXT20MATCH-26OCT090930WIIND';
export const t20Sides=['IND','WI'] as const;
export type T20Side=typeof t20Sides[number];
export const t20Name=(side:T20Side)=>side==='IND'?'India':'West Indies';
export const t20Clock=readerTime;
export type T20Point={t:number;value:number};
type Candle={end_period_ts?:unknown;volume_fp?:unknown;price?:{close_dollars?:unknown}};
const number=(v:unknown)=>typeof v==='number'?v:typeof v==='string'&&v.trim()!==''?Number(v):NaN;
export function t20TradedHistory(ticker:string,candles:Candle[],cutoff:number):T20Point[]{
 if(!t20Sides.some(s=>ticker===t20Event+'-'+s)||!Number.isFinite(cutoff))return [];
 const counts=new Map<number,number>();
 for(const c of candles){const t=number(c.end_period_ts);counts.set(t,(counts.get(t)??0)+1)}
 return candles.flatMap(c=>{const t=number(c.end_period_ts),value=number(c.price?.close_dollars),volume=number(c.volume_fp);return Number.isSafeInteger(t)&&t%60===0&&t>0&&t*1000<=cutoff&&counts.get(t)===1&&Number.isFinite(value)&&value>=0&&value<=1&&Number.isFinite(volume)&&volume>0?[{t:t*1000,value}]:[]}).sort((a,b)=>a.t-b.t);
}
export function t20Cutoff(stage:number){return stage===-1?Date.parse(wire.pregame.reportedAt):stage===4?Date.parse(wire.final.report.reportedAt):wire.stages[stage]?Date.parse(wire.stages[stage].report.reportedAt):NaN}
export function t20History(side:T20Side,stage:number){
 const h=wire.histories[side],ticker=t20Event+'-'+side;
 if(!h||h.ticker!==ticker||wire.event.event_ticker!==t20Event||wire.event.series_ticker!=='KXT20MATCH'||wire.event.markets.filter(m=>m.ticker===ticker&&m.event_ticker===t20Event).length!==1)return [];
 return t20TradedHistory(ticker,h.candlesticks,t20Cutoff(stage));
}
export function t20Baseline(side:T20Side){return t20History(side,-1).at(-1)??null}
export function t20Last(side:T20Side,stage:number){return t20History(side,stage).at(-1)??null}
export function t20Quote(side:T20Side,stage:number,mode='captured'){const p=t20Last(side,stage);return mode==='captured'&&p&&t20Cutoff(stage)-p.t<=300000?p:null}
export function t20Balls(overs:string){const m=/^(\d+)\.([0-5])$/.exec(overs);if(!m)return null;const n=Number(m[1])*6+Number(m[2]);return Number.isSafeInteger(n)?n:null}
export function t20Chase(stage:number){
 const s=stage===4?wire.final:wire.stages[stage];if(!s)return null;
 const balls=t20Balls(s.overs);if(balls===null||balls>wire.legalBallLimit||s.wickets<0||s.wickets>10)return null;
 const left=wire.legalBallLimit-balls,need=Math.max(0,wire.target-s.runs);
 return {...s,balls,ballsLeft:left,need,target:wire.target,wicketsLeft:10-s.wickets,runRate:balls?s.runs*6/balls:null,requiredRate:need===0?0:left?need*6/left:null};
}
export function t20Plot(stage:number,window:'match'|'finish'='match'){
 const histories=t20Sides.map(s=>t20History(s,stage)),all=histories.flat();if(!all.length)return [];
 const start=window==='finish'&&stage>=0?Date.parse(wire.stages[0].report.reportedAt)-120000:Math.min(...all.map(p=>p.t));
 const end=Math.floor(t20Cutoff(stage)/60000)*60000;
 const maps=histories.map(ps=>new Map(ps.map(p=>[p.t,p.value])));
 const rows:{t:number;IND:number|null;WI:number|null}[]=[];
 for(let t=Math.ceil(start/60000)*60000;t<=end;t+=60000)rows.push({t,IND:maps[0].get(t)??null,WI:maps[1].get(t)??null});
 return rows;
}
export function t20Original(side:T20Side,stage:number){const market=wire.event.markets.find(m=>m.ticker===t20Event+'-'+side);if(!market)return null;return {ticker:market.ticker,title:market.title,rules_primary:market.rules_primary,rules_secondary:market.rules_secondary,baseline:t20Baseline(side),lastTrade:t20Last(side,stage),...(stage===4?{result:market.result,settlement_ts:market.settlement_ts,close_time:market.close_time}: {})}}
