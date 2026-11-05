import historyWire from './aflwWinnerHistory.json' with {type:'json'};
import scoreWire from './aflwFinalScore.json' with {type:'json'};
import {aflwWinnerHistory} from './aflwWinnerHistory.ts';
import {aflwFinalForDetail,qualifyAflwFinal} from './aflwFinalScore.ts';
export function aflwPayoff(detail:Record<string,unknown>,history=historyWire,score=scoreWire){
 const actual=qualifyAflwFinal(score);
 if(!aflwFinalForDetail(detail)||!actual)return null;
 const baseline=aflwWinnerHistory(history).filter(p=>p.pregame).at(-1)??null;
 const breaks=actual.checkpoints.map((q,i)=>({id:i,label:q.label,home:q.home.points,away:q.away.points,lead:q.away.points-q.home.points,gain:q.away.points-q.home.points-(i?actual.checkpoints[i-1].away.points-actual.checkpoints[i-1].home.points:0)}));
 return {actual,baseline,breaks,title:baseline&&baseline.away>baseline.home?'The favorite won':'Carlton’s final result'};
}
