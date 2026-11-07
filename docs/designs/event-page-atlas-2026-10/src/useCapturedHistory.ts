import {useStoryState} from './StorySession';
import {retainHistoryObservation,resolveHistorySelection,pinHistorySelection,type RetainedHistorySelection} from './historyObservation';
import {historyUpdatePreview,type HistoryUpdateMode} from './historyReplayRecords';
import type {FinalHistoryPoint,FinalHistoryScope} from './finalHistoryEvidence';
/** Captured-history selection model shared by compact/regular presentations. */
export function useCapturedHistory<T extends FinalHistoryPoint>(eventKey:string,original:T[],filter:(points:T[],scope:FinalHistoryScope)=>T[]){
 const [selection,setSelection]=useStoryState<RetainedHistorySelection|null>(eventKey,'hero-history-observation',null);
 const [scope,setScope]=useStoryState<FinalHistoryScope>(eventKey,'hero-history-scope','game');
 const [mode]=useStoryState<HistoryUpdateMode>(eventKey,'history-update-preview','original');
 const [omittedAt]=useStoryState<number|null>(eventKey,'history-update-omitted-at',null);
 const retained=historyUpdatePreview(original,mode,omittedAt),points=filter(retained,scope);
 const {point:selected,index,unavailable}=resolveHistorySelection(eventKey,points,selection);
 const choose=(i:number)=>{if(points[i])setSelection(retainHistoryObservation(eventKey,points[i]))};
 const pin=()=>setSelection(prior=>pinHistorySelection(eventKey,points,prior));
 const change=(next:FinalHistoryScope)=>{
  setScope(next);
  const nextPoints=filter(retained,next);
  setSelection(prior=>pinHistorySelection(eventKey,nextPoints,resolveHistorySelection(eventKey,nextPoints,prior).unavailable?null:prior));
 };
 return {selection,scope,points,selected,index,unavailable,choose,change,pin};
}
