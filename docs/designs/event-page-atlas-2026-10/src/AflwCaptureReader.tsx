import {readerTime} from './readerTime';
import {aflwStart} from './aflwWinnerHistory';
import {HeadlineInfo} from './HeadlineInfo';
import {aflwHistoryStage} from './aflwHistoryStage';
import {probabilityLabel} from './probabilityLabel';
export function AflwCaptureReader({stage,wide,large}:{stage:'earlier'|'suspended';wide:boolean;large:boolean}){
 const h=aflwHistoryStage(stage);const cutoff=readerTime(h.cutoff!,{seconds:true});return <div className="aflw-final-reader"><div><b>{stage==='earlier'?'Earlier in-game capture':'Suspended · result unconfirmed'}</b><HeadlineInfo scopeKey={`aflw-reader:${stage}`} wide={wide} large={large}><h3>Event win probabilities</h3><p>Polymarket event history supplies Sydney 32% / Carlton 68% at {h.baseline?readerTime(h.baseline.at,{seconds:true}):'an unavailable time'}, before kickoff at {readerTime(aflwStart)}.</p><p>This retrospective history is limited to records timestamped by {cutoff}. It does not prove receipt by the app at that time or current trading activity. Original prop rows retain their own quote clocks and independent baseline/settlement evidence.</p><p>No actual score, quarter or projection was supplied in this capture. No final result is inferred.</p><p>Original cutoff: {h.cutoff}. Original pregame timestamp: {h.baseline?.at??'unavailable'}.</p></HeadlineInfo></div><span>Sydney Swans · Carlton Blues</span><span>Pregame quote · Sydney {probabilityLabel(h.baseline?.home)} / Carlton {probabilityLabel(h.baseline?.away)}</span><span>Score and quarter unavailable</span></div>;
}
