import {pokerFeaturedContext,pokerTradeContext} from './pokerFeaturedContext';
import {pokerCapture,type PokerPhase} from './pokerEvidence';
import {probabilityLabel as pct} from './probabilityLabel';
import {eventReaderTime as clock} from './eventReaderTime';
import './pokerFeaturedContext.css';
const colors=['var(--series-home)','var(--series-away)','var(--text-secondary)'];
export function PokerFeaturedBaselines({ids,selected,phase,onChoose}:{ids:readonly string[];selected:string;phase:PokerPhase;onChoose:(id:string)=>void}){
 const rows=pokerFeaturedContext(ids,phase);
 return <div className="pk-baseline-field"><span className="pk-baseline-heading">Before final table · win chances</span><div role="group" aria-label="Featured poker histories">{rows.map(row=><button key={row.id} style={{color:colors[row.slot],borderColor:colors[row.slot]}} aria-pressed={row.id===selected} onClick={()=>onChoose(row.id)} aria-label={`${row.name}, ${row.shape}, ${row.baseline===null?'Unavailable':pct(row.baseline)} before final table${row.finish===null?'':', reported finish '+row.finish}. Select player`}><span>{row.short}</span><strong data-unavailable={row.baseline===null}>{row.baseline===null?'Unavailable':pct(row.baseline)}</strong><small>{row.shape}</small></button>)}</div></div>;
}
export function PokerRecordedReading({id,phase,index}:{id:string;phase:PokerPhase;index:number|null}){
 const market=pokerCapture.markets.find(m=>m.id===id&&m.kind==='winner');
 if(!market)return <p className="pk-history-price">Selected player unavailable · Current probability unavailable</p>;
 const reading=pokerTradeContext(market,phase,index);
 if(!reading.showReading)return null;
 return <div className="pk-reading pk-recorded-reading" aria-label="Selected recorded poker trade"><div><span>{market.name}</span><strong>{reading.point?pct(reading.point.p):'No trade'}</strong></div><p>{reading.label}{reading.point?' · '+clock.full(reading.point.t*1000):''}</p></div>;
}
