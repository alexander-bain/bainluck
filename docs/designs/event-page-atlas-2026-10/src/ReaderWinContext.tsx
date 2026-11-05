import {probabilityStatusLabel} from './probabilityStatusLabel';
import {eventReaderTime} from './eventReaderTime.ts';
import {AflwCaptureReader} from './AflwCaptureReader';
import {aflwCaptureStageForDetail} from './aflwHistoryStage';
import {AflwFinalReader} from './AflwFinalHeader';
import {aflwFinalForDetail} from './aflwFinalScore';
import {CircleIcon,DotFilledIcon} from '@radix-ui/react-icons';
import {HeadlineInfo} from './HeadlineInfo';
import {probabilityLabel} from './probabilityLabel';
import {readerWinContext,type ReaderEvent} from './readerWinEvidence';
import './readerWinContext.css';
const clock=eventReaderTime.full;
export function ReaderWinContext({ev,mode,wide,large}:{ev:ReaderEvent;mode:string;wide:boolean;large:boolean}){
 if(ev.key==='aflw-refresh'&&aflwFinalForDetail(ev.detail))return <AflwFinalReader detail={ev.detail} wide={wide} large={large}/>;
 const aflwStage=ev.key==='aflw-refresh'?aflwCaptureStageForDetail(ev.detail):null;
 if(aflwStage)return <AflwCaptureReader stage={aflwStage} wide={wide} large={large}/>;
 const c=readerWinContext(ev,mode);if(!c)return <><b>{String(ev.detail.home_team)} · {String(ev.detail.away_team??'')}</b><span>{String(ev.detail.status)} capture{ev.detail.home_score!=null&&ev.detail.away_score!=null?` · ${ev.detail.home_score}–${ev.detail.away_score}`:''}</span><span>Event win chances unavailable in this reader</span></>;
 const recorded=c.rows.some(r=>r.recorded!==undefined);
 return <section className="reader-win" aria-label="Event win chances">
  <div className="reader-win-top"><span>{c.state}</span><HeadlineInfo scopeKey={`reader:${ev.key}`} wide={wide} large={large}><h3>{c.label}</h3>{c.rows.map(r=><p key={r.name}>{r.name}: {probabilityLabel(r.baseline)} before the match. {r.baselineAt?clock(r.baselineAt):'Exact opening quote time unavailable.'}{r.recorded!==undefined&&` Recorded in game: ${probabilityLabel(r.recorded)}.`}</p>)}<p>{c.note}</p>{c.resultSource&&<p><a href={c.resultSource.url} target="_blank" rel="noopener noreferrer">{c.resultSource.label} ↗</a></p>}<p>Source: {c.source}</p></HeadlineInfo></div>
  <div className="reader-win-label">{recorded?<DotFilledIcon/>:<CircleIcon/>}{c.label}{c.at&&<time dateTime={c.at}>{clock(c.at)}</time>}</div>
  <div className="reader-win-sides" style={{gridTemplateColumns:`repeat(${c.rows.length},minmax(0,1fr))`}}>{c.rows.map((r,i)=><div className={`reader-win-side reader-win-side-${i}`} key={r.name}><span>{r.name}</span><strong>{probabilityLabel(r.recorded??r.baseline)}</strong>{recorded&&<span className="reader-win-before"><CircleIcon/>Pregame {probabilityLabel(r.baseline)}</span>}</div>)}</div>
  {c.unavailable&&<span className="reader-win-missing">{probabilityStatusLabel(c.unavailable)}</span>}
 </section>;
}
