import {archiveMatchClock} from './archiveMatchClock';
import './archivedTradeStamp.css';
/** Always date each independently timed quote, including full-size readers. */
export function ArchivedTradeStamp({at,includeDate=true}:{at:number;includeDate?:boolean}){
 return <time className="archived-trade-stamp" dateTime={new Date(at*1000).toISOString()} aria-label={`Recorded trade ${archiveMatchClock.full(at)}`}>{includeDate&&<span>{archiveMatchClock.date(at)}</span>}<span>{archiveMatchClock.short(at)}</span></time>;
}
