import capture from './earnings-capture.json' with {type:'json'};
export const earningsCapture=capture;
export const earningsEvent='earnings:1106010';
export const earningsHistory=capture.history.map(p=>({t:p.t*1000,value:p.p}));
export const earningsFirst=earningsHistory[0],earningsLast=earningsHistory.at(-1)!;
export type EarningsPhase='before'|'reported';
export function earningsSelection(index:number){return earningsHistory[Math.max(0,Math.min(earningsHistory.length-1,Math.trunc(Number.isFinite(index)?index:earningsHistory.length-1)))];}
export function earningsFacts(phase:EarningsPhase){return {threshold:capture.threshold,actual:phase==='reported'?capture.company.dilutedEPS:null,beat:phase==='reported'?capture.resolvedYes:null,deltaCents:phase==='reported'?Math.round((capture.company.dilutedEPS-capture.threshold)*100):null};}
/** Leave missing intervals blank; the source contains observations, not proven trades. */
export function earningsPlot(){return earningsHistory.flatMap((p,i)=>i&&p.t-earningsHistory[i-1].t>90*60*1000?[{t:earningsHistory[i-1].t+1,value:null},p]:[p]);}
