import {seriesPregame} from './seriesPregame';
import {probabilityLabel} from './probabilityLabel';
import './tennisPropChance.css';
/** Same independent-probability ring as the accepted tennis cards; never a pie of the field. */
export function SeriesPregameChance({row}:{row:unknown}){
 const p=seriesPregame(row);
 return <div className="tennis-prop-chance ring series-pregame-chance" aria-label={`Pre-series chance ${p?probabilityLabel(p.value):'unavailable'}`}>
 {p&&<svg viewBox="0 0 80 80" aria-hidden="true"><circle cx="40" cy="40" r="34" className="track"/><circle cx="40" cy="40" r="34" pathLength="100" strokeDasharray={`${p.value*100} 100`} className="chance"/></svg>}
 <strong>{p?probabilityLabel(p.value):'Unavailable'}</strong><span>Pre-series</span>
 </div>;
}
