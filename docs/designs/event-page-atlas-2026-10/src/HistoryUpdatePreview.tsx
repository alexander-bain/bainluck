import type {RetainedHistorySelection} from './historyObservation';
import {useStoryState} from './StorySession';
import type {HistoryUpdateMode} from './historyReplayRecords';
export function HistoryUpdatePreview({eventKey}:{eventKey:string}){
 const [mode,setMode]=useStoryState<HistoryUpdateMode>(eventKey,'history-update-preview','original');
 const [selection]=useStoryState<RetainedHistorySelection|null>(eventKey,'hero-history-observation',null);
 const [,setOmittedAt]=useStoryState<number|null>(eventKey,'history-update-omitted-at',null);
 return <label>History update replay<select aria-label="History update replay" value={mode} onChange={e=>{if(e.target.value==='omit')setOmittedAt(selection?.point.t??null);setMode(e.target.value as HistoryUpdateMode)}}><option value="original">All recorded observations</option><option value="thin">Every other recorded observation</option><option value="reverse">Reordered received observations</option><option value="omit" disabled={!selection}>Selected timestamp absent</option><option value="empty">Empty history update</option></select></label>;
}
