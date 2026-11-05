import raw from './golfFinishHistory.json' with {type:'json'};
import {journeyWire,journeyFor} from './golfJourneyEvidence.ts';
export type FinishKind='win'|'top_5'|'top_10'|'top_20';
export type FinishStage='before'|'recorded'|'final';
export const finishKinds:FinishKind[]=['win','top_5','top_10','top_20'];
export const finishNames:Record<FinishKind,string>={win:'Win',top_5:'Top 5',top_10:'Top 10',top_20:'Top 20'};
export type FinishPoint={timestamp:string;probability:number;bookmaker?:string};
type Original={id:number;name:string;probability:number|null};
type FinishMarket={kind:string;market:{id:number;name:string;source:string;external_id:string;mutually_exclusive:boolean;commence_time:string|null;outcomes:Original[]};history:{market_id:number;market_name:string;outcomes:{outcome_id:number;name:string;history:FinishPoint[]}[]};sources:unknown[]};
export type FinishWire={eventKey:string;start:string;markets:FinishMarket[]};
export const finishWire:FinishWire=raw;
const expectedIDs:Record<FinishKind,number>={win:64266833,top_5:64266834,top_10:64266835,top_20:64266836};
function admitted(kind:FinishKind,name:string,wire:FinishWire){
 if(wire.eventKey!==journeyWire.eventKey||Date.parse(wire.start)!==Date.parse(journeyWire.start))return null;
 const bundle=wire.markets.filter(m=>m.kind===kind);
 const market=kind==='win'?journeyWire.market:bundle.length===1?bundle[0].market:null;
 if(!market||market.id!==expectedIDs[kind]||market.source!=='datagolf'||market.external_id!==wire.eventKey+':'+kind)return null;
 if(kind!=='win'&&(market.mutually_exclusive!==false||Date.parse((market as FinishMarket['market']).commence_time??'')!==Date.parse(wire.start)||market.name!==`Baycurrent Classic - ${finishNames[kind]} Finish`))return null;
 const originals=market.outcomes.filter(r=>r.name===name);
 if(originals.length!==1||market.outcomes.filter(r=>r.id===originals[0].id).length!==1)return null;
 const original=originals[0];
 if(kind!=='win'&&(bundle[0].history.market_id!==market.id||bundle[0].history.market_name!==market.name))return null;
 const rows=kind==='win'?journeyWire.history.outcomes:bundle[0].history.outcomes;
 const matched=rows.filter(r=>r.outcome_id===original.id&&r.name===name);
 if(matched.length!==1||rows.filter(r=>r.outcome_id===original.id||r.name===name).length!==1)return null;
 const points:FinishPoint[]=matched[0].history,seen=new Set<number>();
 for(const p of points){const time=Date.parse(p.timestamp);if(!Number.isFinite(time)||!Number.isFinite(p.probability)||p.probability<0||p.probability>1||seen.has(time))return null;seen.add(time)}
 return {market,original,points:[...points].sort((a,b)=>Date.parse(a.timestamp)-Date.parse(b.timestamp)),sources:kind==='win'?[]:bundle[0].sources};
}
export function finishProfile(name:string,{stage,through,at,gap=false}:{stage:FinishStage;through?:string;at?:string;gap?:boolean},wire:FinishWire=finishWire){
 const start=Date.parse(journeyWire.start),terminal=Date.parse(journeyWire.terminalObservation.timestamp);
 const shown=stage==='final'?start:Date.parse(through??''),selected=stage==='final'||at===undefined?shown:Date.parse(at);
 const valid=(stage==='final'||!gap)&&Number.isFinite(shown)&&Number.isFinite(selected)&&selected<=shown;
 const cutoff=Math.min(selected,terminal),result=stage==='final'?journeyFor(name)?.final:null;
 const position=result&&/^(?:T)?[1-9][0-9]*$/.test(result.position)?Number(result.position.replace('T','')):null;
 return {name,stage,inspected:stage!=='final'&&at!==undefined,cutoff:valid?cutoff:null,position:result?.position??null,entries:finishKinds.map(kind=>{
  const source=admitted(kind,name,wire),before=valid?source?.points.filter(p=>Date.parse(p.timestamp)<start&&Date.parse(p.timestamp)<=cutoff).at(-1)??null:null;
  const recorded=valid&&stage==='recorded'?source?.points.filter(p=>Date.parse(p.timestamp)>=start&&Date.parse(p.timestamp)<=cutoff).at(-1)??null:null;
  const limit=kind==='win'?1:Number(kind.slice(4));
  return {kind,label:finishNames[kind],before,recorded,actual:position===null?null:position<=limit,source};
 })};
}
export type FinishProfile=ReturnType<typeof finishProfile>;
export const finishChance=(p:number|null|undefined)=>p==null||!Number.isFinite(p)||p<0||p>1?'Not recorded':p===0?'0%':p===1?'100%':p<.001?'<0.1%':Math.round(p*1000)===1000?'>99.9%':`${Math.round(p*1000)/10}%`;
