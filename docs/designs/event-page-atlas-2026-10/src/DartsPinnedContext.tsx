import {ArrowTopRightIcon} from '@radix-ui/react-icons';
import {qualifiedDartsScore} from './dartsFinalScore';
import {dartsSeries,dartsPairNote} from './dartsMatchEvidence';
import {archivedTradeReadout,archivedTradeSharedInstant} from './archivedTradeReadout';
import {archiveMatchClock as clock} from './archiveMatchClock';
import {probabilityLabel as pct} from './probabilityLabel';
import './dartsPinnedContext.css';

/** Selected archival readings, never a replacement for a current forecast. */
export function DartsPinnedContext({at,onChart}:{at:number|null;onChart:()=>void}) {
 const rows=dartsSeries().map(s=>({...s,...archivedTradeReadout(s.points,at)}));
 const shared=archivedTradeSharedInstant(rows.map(s=>s.point));
 return <aside className="dm-pinned-context" aria-label="Darts probability context">
  <header><span>{at!==null?`${dartsPairNote(at)?'Separate trades':'Recorded'} · ${clock.full(at)}`:shared!==null?`Last trades · ${clock.full(shared)}`:'Last recorded trades'}</span><button onClick={onChart} aria-label="Open darts win probability">Chart <ArrowTopRightIcon/></button></header>
  <div className="dm-pinned-values">{rows.map((s,i)=><div className={`side-${i}`} key={s.ticker}><span>{i===0?'McEwan':'van Ockenburg'}</span><b className={s.point?undefined:'dm-pinned-missing'}>{s.point?pct(s.point.p):s.emptyLabel}</b>{at===null&&shared===null&&s.point&&<small>{clock.full(s.point.at)}</small>}</div>)}</div>
  <p>Pre-match chance unavailable · {qualifiedDartsScore()?'Final 0–4':'Score unavailable'}</p>
 </aside>;
}
