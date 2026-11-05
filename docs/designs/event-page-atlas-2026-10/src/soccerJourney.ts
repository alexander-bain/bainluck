import live from './liveSoccer.json' with {type:'json'};
import final from './soccerFinal.json' with {type:'json'};
import receipt from './soccerJourneyReceipt.json' with {type:'json'};
import {soccerLifecycleContext,soccerLifecycleTimes,type SoccerLifecycleContext} from './soccerLifecycle.ts';
export const soccerJourneyTimes=[...soccerLifecycleTimes(live.baseline.at),receipt.finalEvidenceCapturedAt];
export function soccerJourneyContext(sequence:number):SoccerLifecycleContext {
 if(sequence<7)return soccerLifecycleContext(live.points,live.scoreHistory,live.baseline.at,sequence);
 if(sequence!==7)throw new Error('Invalid match journey stage');
 const history=final.points.filter(p=>Date.parse(p.at)>=Date.parse(final.baseline.at));
 return {phase:'final',at:receipt.finalEvidenceCapturedAt,history,point:history.at(-1)!,score:final.scoreHistory.at(-1)!,scores:final.scoreHistory};
}
export function soccerJourneyResult(sequence:number,key:string){
 if(!Number.isInteger(sequence)||sequence<0||sequence>7)throw new Error('Invalid match journey stage');
 if(sequence!==7)return null;
 const rows=final.rows.filter(r=>r.key===key);if(rows.length!==1)throw new Error('Unknown original outcome');return rows[0];
}
export const soccerFinalReceipt=receipt;
