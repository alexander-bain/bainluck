import raw from './cricketLifecycleCapture.json' with {type:'json'};
import {cricketLiveWire,liveCricketEvent,liveCricketSides,cricketTradedHistory,type LiveCricketSide} from './cricketLiveEvidence.ts';
export type CricketPhase='before'|'final';
export const cricketLifecycleWire=raw;
export const cricketPhaseWindow=(phase:CricketPhase|undefined,window:'match'|'day5')=>phase==='before'?'match':window;
export const cricketPhaseCutoff=(phase:CricketPhase)=>Date.parse(phase==='before'?raw.beforeAt:raw.final.reportedAt);
export function cricketPhaseHistory(side:LiveCricketSide,phase:CricketPhase,window:'match'|'day5'){
 const h=cricketLiveWire.history.find(h=>h.ticker===liveCricketEvent+'-'+side);if(!h||raw.eventTicker!==liveCricketEvent)return [];
 const hourly=cricketPhaseWindow(phase,window)==='match',data=hourly?h.hourly:h.minute;
 return data.ticker===h.ticker?cricketTradedHistory(h.ticker,data.candlesticks,hourly?3600:60,cricketPhaseCutoff(phase)):[];
}
export function cricketLifecyclePlot(phase:CricketPhase,window:'match'|'day5'){
 const all=liveCricketSides.map(side=>({side,points:cricketPhaseHistory(side,phase,window)}));
 const times=all.flatMap(s=>s.points.map(p=>p.t));if(!times.length)return [];
 const step=cricketPhaseWindow(phase,window)==='match'?3600000:60000,start=Math.min(...times),end=Math.floor(cricketPhaseCutoff(phase)/step)*step;
 const maps=all.map(s=>({side:s.side,values:new Map(s.points.map(p=>[p.t,p.value]))}));
 return Array.from({length:(end-start)/step+1},(_,i)=>{const t=start+i*step;return {t,...Object.fromEntries(maps.map(s=>[s.side,s.values.get(t)??null]))} as {t:number}&Record<LiveCricketSide,number|null>});
}
export function cricketContractResult(side:LiveCricketSide,phase:CricketPhase):'Won'|'Lost'|'Unconfirmed'{
 if(phase!=='final'||raw.eventTicker!==liveCricketEvent)return 'Unconfirmed';
 const matches=cricketLiveWire.event.markets.filter(m=>m.ticker===liveCricketEvent+'-'+side);
 const m=matches.length===1?matches[0]:undefined;
 if(!m||m.status!=='finalized')return 'Unconfirmed';
 return m.result==='yes'?'Won':m.result==='no'?'Lost':'Unconfirmed';
}
