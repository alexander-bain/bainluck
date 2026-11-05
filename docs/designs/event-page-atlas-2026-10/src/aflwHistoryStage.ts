import captures from './aflwCaptures.json' with {type:'json'};
import {retainedAflwHistory} from './aflwWinnerHistory.ts';
import type {FinalHistoryPoint} from './finalHistoryEvidence';
export type AflwHistoryStage='earlier'|'suspended'|'final';
export function historyThrough(points:FinalHistoryPoint[],at:string){
 const cutoff=Date.parse(at);if(!Number.isFinite(cutoff))return [];
 return points.filter(p=>p.t<=cutoff);
}
export function aflwHistoryStage(stage:AflwHistoryStage){
 const cutoff=stage==='earlier'?captures.earlierAt:stage==='suspended'?captures.latestAt:null;
 const points=cutoff?historyThrough(retainedAflwHistory,cutoff):retainedAflwHistory;
 return {stage,cutoff,points,baseline:points.filter(p=>p.pregame).at(-1),key:`aflw:15324784:${stage}`};
}
/** Bind this archived specimen before lending event context to a prop reader. */
export function aflwCaptureStageForDetail(d:Record<string,unknown>):'earlier'|'suspended'|null{
 if(d.id!==15324784||d.home_team!=='Sydney Swans'||d.away_team!=='Carlton Blues'||d.home_score!=null||d.away_score!=null||d.quality_hold)return null;
 if(d.sport!=null&&d.sport!=='aussierules_aflw')return null;
 if(d.commence_time!=null&&d.commence_time!==captures.latestDetail.commence_time)return null;
 if(d.status==='live')return 'earlier';
 if(d.status==='suspended')return 'suspended';
 return null;
}
