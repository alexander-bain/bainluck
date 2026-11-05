import {readerDay} from './readerTime.ts';
import raw from './cricketMatch.json' with {type:'json'};
export const cricketWire=raw;
export const cricketEvent='KXTESTMATCH-26SEP290000AUS-AINA';
export const cricketTickers=[cricketEvent+'-INA',cricketEvent+'-AUS-A',cricketEvent+'-TIE'];
export type CricketPoint={at:number;p:number;volume:number};
export function cricketSeries(wire=raw){
 if(wire.event.event.event_ticker!==cricketEvent||wire.event.event.series_ticker!=='KXTESTMATCH')return [];
 return cricketTickers.flatMap(ticker=>{
  const originals=wire.event.markets.filter(m=>m.ticker===ticker&&m.event_ticker===cricketEvent),groups=wire.history.markets.filter(h=>h.market_ticker===ticker);
  if(originals.length!==1||groups.length!==1)return [];
  const original=originals[0],start=Date.parse(original.open_time)/1000,end=Date.parse(original.close_time)/1000;
  const points:CricketPoint[]=groups[0].candlesticks.flatMap(c=>{
   const value=c.price.close_dollars,volume=c.volume_fp,p=typeof value==='string'&&/^\d+(\.\d+)?$/.test(value)?Number(value):NaN,v=typeof volume==='string'&&/^\d+(\.\d+)?$/.test(volume)?Number(volume):NaN,at=c.end_period_ts;
   if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start||!Number.isFinite(at)||at<=start||at>end||!Number.isFinite(p)||p<0||p>1||!Number.isFinite(v)||v<=0||groups[0].candlesticks.filter(o=>o.end_period_ts===at).length!==1)return [];
   return [{at,p,volume:v}];
  }).sort((a,b)=>a.at-b.at);
  return [{ticker,name:original.yes_sub_title,original,points,baseline:null,result:original.status==='finalized'&&['yes','no'].includes(original.result)?original.result:null}];
 });
}
export const cricketDay=(at:number,timeZone='UTC')=>readerDay(at*1000,timeZone)??'';
export const cricketTimes=(series=cricketSeries())=>[...new Set(series.flatMap(s=>s.points.map(p=>p.at)))].sort((a,b)=>a-b);
export const cricketDays=(series=cricketSeries(),timeZone='UTC')=>[...new Set(cricketTimes(series).map(t=>cricketDay(t,timeZone)))];
export function cricketDateStarts(series=cricketSeries(),timeZone='UTC'){const seen=new Set<string>();return cricketTimes(series).flatMap(at=>{const day=cricketDay(at,timeZone);if(seen.has(day))return [];seen.add(day);return [{day,at}];});}
export function cricketWindow(day:string,series=cricketSeries(),timeZone='UTC'){return series.map(s=>({...s,points:s.points.filter(p=>day==='all'||cricketDay(p.at,timeZone)===day)}));}
export function cricketExact(ticker:string,at:number|null,day='all',series=cricketSeries(),timeZone='UTC'){
 const points=cricketWindow(day,series,timeZone).find(s=>s.ticker===ticker)?.points??[];
 if(at===null)return points.at(-1)??null;
 const matches=points.filter(p=>p.at===at);return matches.length===1?matches[0]:null;
}
export function cricketSegments(points:CricketPoint[]){const chunks:CricketPoint[][]=[];for(const point of points){const last=chunks.at(-1);if(last&&point.at-last.at(-1)!.at<=7200)last.push(point);else chunks.push([point]);}return chunks;}
export function cricketPairNote(at:number|null,day='all',timeZone='UTC'){
 const points=cricketSeries().map(s=>cricketExact(s.ticker,at,day,cricketSeries(),timeZone));
 if(points.some(p=>!p))return 'Only exact-hour trades are shown. Missing trades stay unavailable.';
 return Math.abs(points.reduce((sum,p)=>sum+p!.p,0)-1)>.005?'Separate trades; these probabilities do not add to 100%.':'Separate contract trades; not a synchronized forecast.';
}
export interface CricketSession{timeZone:string;day:string;at:number|null;focus:boolean;focusCard:'history'|'chase';panel:string|null;large:boolean}
export const initialCricket:CricketSession={timeZone:'UTC',day:'all',at:null,focus:false,focusCard:'history',panel:null,large:false};
export type CricketAction={type:'day';day:string}|{type:'inspect';at:number|null}|{type:'focus';open:boolean;card?:'history'|'chase'}|{type:'panel';id:string|null}|{type:'large'};
export function cricketReduce(state:CricketSession,action:CricketAction):CricketSession{
 if(state.panel!==null&&action.type!=='panel')return state;
 switch(action.type){
  case 'day':return action.day==='all'||cricketDays(cricketSeries(),state.timeZone).includes(action.day)?{...state,day:action.day,at:state.at!==null&&(action.day==='all'||cricketDay(state.at,state.timeZone)===action.day)?state.at:null}:state;
  case 'inspect':return action.at===null||cricketTimes(cricketWindow(state.day,cricketSeries(),state.timeZone)).includes(action.at)?{...state,at:action.at}:state;
  case 'focus':return {...state,focus:action.open,focusCard:action.card??state.focusCard};
  case 'panel':return action.id===null||action.id==='about'||cricketTickers.includes(action.id)?{...state,panel:action.id}:state;
  case 'large':return {...state,large:!state.large};
 }
}
