import {ChevronRightIcon} from '@radix-ui/react-icons';
import {PieChart,Pie,Cell} from 'recharts';
import {soccerFeedPreview,type SoccerFeedID} from './soccerFeedCards';
import type {HalfCompetitor} from './soccerHalfResults';
import {probabilityLabel} from './probabilityLabel';
import type {SnackID} from './snackReplay';
import type {SoccerLifecycleContext} from './soccerLifecycle';
import './soccerNextPreview.css';

export function SoccerNextPreview({id,context,open,halfCompetitor='home'}:{id:SoccerFeedID;halfCompetitor?:HalfCompetitor;context:SoccerLifecycleContext;open:()=>void}){
 const preview=soccerFeedPreview(id,context,halfCompetitor);
 return <button className="sn-next" onClick={open} aria-label={`Explore next: ${preview.title}. ${preview.predicate}, ${probabilityLabel(preview.probability)} pre-match. ${preview.actual}.`}>
  <span className="sn-next-copy"><span className="sn-next-title">Up next · {preview.title}</span><strong>{preview.predicate}</strong><span>{preview.actual}</span></span>
  <span className="sn-next-chance"><span className="sn-next-ring" aria-hidden="true">{preview.probability!==null&&<PieChart width={64} height={64}><Pie data={[{value:preview.probability},{value:1-preview.probability}]} dataKey="value" cx={27} cy={27} innerRadius={25} outerRadius={29} startAngle={90} endAngle={-270} isAnimationActive={false} stroke="none"><Cell fill="var(--series-home)"/><Cell fill="var(--surface-border)"/></Pie></PieChart>}<b>{probabilityLabel(preview.probability)}</b></span><span>Pre-match</span></span>
  <ChevronRightIcon aria-hidden="true"/>
 </button>;
}
