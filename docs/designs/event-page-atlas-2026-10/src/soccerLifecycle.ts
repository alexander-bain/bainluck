import {replayContext,replayTimes,rankSnacks,type ReplayPoint,type ScorePoint} from './snackReplay.ts';
export type SoccerLifecycleContext=ReturnType<typeof replayContext>&{phase:'before'|'in-match'|'final'};
export function soccerLifecycleTimes(baselineAt:string){return [baselineAt,...replayTimes]}
export function soccerLifecycleContext(points:ReplayPoint[],scores:ScorePoint[],baselineAt:string,sequence:number):SoccerLifecycleContext{
 const times=soccerLifecycleTimes(baselineAt);
 if(!Number.isInteger(sequence)||sequence<0||sequence>=times.length)throw new Error('Invalid recorded soccer stage');
 return {...replayContext(points,scores,times[sequence]),phase:sequence===0?'before':'in-match'};
}
export function soccerLifecycleRank(context:SoccerLifecycleContext){
 return context.phase==='before'?[{id:'both' as const,reason:'What the pre-match market expected'},{id:'goals' as const,reason:'The pre-match goal expectations'},{id:'first' as const,reason:'Who was expected to score first'}]:rankSnacks(context.score);
}
export function soccerScoreLabel(context:SoccerLifecycleContext){
 return context.phase==='before'?'vs':context.score?`${context.score.home_score}–${context.score.away_score}`:'Score unavailable';
}
