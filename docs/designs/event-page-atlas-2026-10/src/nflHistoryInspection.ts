import {nflGame,type nflContext} from './nflReplay.ts';
import {nflTimeline} from './nflTimeline.ts';
import {resolveHistorySelection,retainHistoryObservation,type RetainedHistorySelection} from './historyObservation.ts';
export const nflHistoryKey='nfl:14780549';
/** Select only retained, paired observations; chart gaps are never selectable prices. */
export function nflHistoryInspection(context:ReturnType<typeof nflContext>,selection:RetainedHistorySelection|null){
 const points=nflTimeline(context).history.map(p=>({t:p.time,at:new Date(p.time).toISOString(),home:p.home,away:p.away,pregame:p.time<Date.parse(nflGame.commence_time)}));
 const resolved=resolveHistorySelection(nflHistoryKey,points,selection);
 const point=resolved.point;
 // Use only an exact game-state row for the inspected clock. No wall-time conversion.
 const state=point?nflGame.game_states.find(s=>Date.parse(s.timestamp)===point.t):undefined;
 const label=point?.pregame?'Pregame observation':state?.game_state.period.replace(' - ',' · ')??'Recorded observation';
 return {points,...resolved,label};
}
export function selectNFLHistory(context:ReturnType<typeof nflContext>,index:number){
 const points=nflHistoryInspection(context,null).points;
 return Number.isInteger(index)&&index>=0&&index<points.length?retainHistoryObservation(nflHistoryKey,points[index]):null;
}
