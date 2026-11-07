import {rangeGestureProps} from './rangeGesture';
import {ChevronLeftIcon,ChevronRightIcon} from '@radix-ui/react-icons';
import {eventReaderTime} from './eventReaderTime';
import {probabilityLabel} from './probabilityLabel';
import type {nflHistoryInspection} from './nflHistoryInspection';
import './nflHistoryReadout.css';
export function NFLHistoryReadout({inspection,onSelect}:{inspection:ReturnType<typeof nflHistoryInspection>;onSelect:(index:number)=>void}){
 const {points,point,index,unavailable,label}=inspection;
 const valueText=point?`${label}. ${eventReaderTime.full(point.at,true)}. Bears ${probabilityLabel(point.home)}, Eagles ${probabilityLabel(point.away)}.`:'Selected observation unavailable';
 return <section className="nfl-history-readout" aria-label="Inspected win probabilities">
  {unavailable||!point?<p role="status">This observation is outside the displayed history. {points.length>0&&<button onClick={()=>onSelect(points.length-1)}>Inspect latest available</button>}</p>:<>
   <p className="nfl-history-stamp"><b>{point.pregame?label:`Recorded · ${label}`}</b><time dateTime={point.at}>{eventReaderTime.full(point.at,true)}</time></p>
   <div className="nfl-history-pair"><div className="pr-home"><span>Bears</span><strong>{probabilityLabel(point.home)}</strong></div><div className="pr-away"><span>Eagles</span><strong>{probabilityLabel(point.away)}</strong></div></div>
   <div className="nfl-history-scrub"><button aria-label="Previous probability observation" disabled={index===0} onClick={()=>onSelect(index-1)}><ChevronLeftIcon/></button><input {...rangeGestureProps} type="range" aria-label="Inspect win probability history" min={0} max={Math.max(0,points.length-1)} step={1} value={index} aria-valuetext={valueText} onChange={e=>onSelect(Number(e.target.value))}/><button aria-label="Next probability observation" disabled={index===points.length-1} onClick={()=>onSelect(index+1)}><ChevronRightIcon/></button></div>
   <p className="nfl-history-help">Recorded observations · match snapshot unchanged.</p>
  </>}
 </section>;
}
