import raw from './dartsFinalScore.json' with {type:'json'};
import {dartsEvent,dartsTickers} from './dartsMatchEvidence.ts';
export const dartsScoreWire=raw;
export function qualifiedDartsScore(wire=raw){
 if(wire.eventTicker!==dartsEvent||wire.date!=='2026-10-12'||wire.competition!=='MODUS Super Series'||wire.status!=='final'||wire.unit!=='legs'||wire.scores.length!==2)return null;
 if(wire.scores.some((s,i)=>s.ticker!==dartsTickers[i]||!Number.isInteger(s.legs)||s.legs<0))return null;
 const [a,b]=wire.scores;
 if(a.marketName!=='Jim McEwan'||a.reportName!=='Jim McEwan'||b.marketName!=='Sander van Ockenburg'||b.reportName!=='Sander Van Ockenburg-Zwaan')return null;
 if(a.legs!==0||b.legs!==4||wire.provenance.reportedResult!==`${b.reportName} ${b.legs}-${a.legs} ${a.reportName}`)return null;
 return wire;
}
export function dartsFinalLegs(ticker:string,wire=raw){return qualifiedDartsScore(wire)?.scores.find(s=>s.ticker===ticker)?.legs??null;}
