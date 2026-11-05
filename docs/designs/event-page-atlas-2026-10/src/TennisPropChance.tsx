import {tennisPropBaseline} from './tennisPropPregame';
import {probabilityLabel} from './probabilityLabel';
import './tennisPropChance.css';
export function TennisPropChance({row,rail=false}:{row:unknown;rail?:boolean}){
 const b=tennisPropBaseline(row);
 return <div className={'tennis-prop-chance '+(rail?'rail':'ring')} aria-label={`Pre-match chance ${b?probabilityLabel(b.value):'unavailable'}`}>
 {b&&<svg viewBox={rail?'0 0 100 12':'0 0 80 80'} aria-hidden="true">{rail?<><line x1="5" x2="95" y1="6" y2="6" className="track"/><circle cx={5+90*b.value} cy="6" r="4" className="marker"/></>:<><circle cx="40" cy="40" r="34" className="track"/><circle cx="40" cy="40" r="34" pathLength="100" strokeDasharray={`${b.value*100} 100`} className="chance"/></>}</svg>}
 <strong>{b?probabilityLabel(b.value):'Unavailable'}</strong><span>Pre-match</span>
 </div>
}
