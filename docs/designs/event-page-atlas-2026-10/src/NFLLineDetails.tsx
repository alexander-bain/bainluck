import {nflLineDetails,type NFLDetailRow} from './nflLineEvidence';
import {PregameContext} from './PregameContext';
import {probabilityLabel} from './probabilityLabel';
import {eventReaderTime} from './eventReaderTime';
import './nflLineDetails.css';
export function NFLLineDetails({row,at,final,conflict,large=false}:{row:NFLDetailRow|undefined;at:string;final:boolean;conflict:boolean;large?:boolean}){
 const detail=nflLineDetails(row,at,final,conflict);
 if(!detail)return <section className={`nfl-line-details ${large?'nfl-line-large':''}`}><h3>This line is unavailable</h3><p>Close details to return to your card.</p></section>;
 const {pregame,quote,quotedAt,actual,result,admitted}=detail;
 const venue=({kalshi:'Kalshi',polymarket:'Polymarket'} as Record<string,string>)[row!.source]??row!.source;
 return <section className={`nfl-line-details ${large?'nfl-line-large':''}`} aria-label="Selected prop details">
  <span className="nfl-line-venue">{venue}</span><h3>{row!.outcome_name}</h3><p className="nfl-line-market">{row!.market_name}</p>
  <PregameContext value={pregame} note={pregame===null?'No pregame baseline was supplied for this exact side.':'Historical pregame baseline · exact quote time unavailable'}/>
  {admitted&&(actual!==null||result!==null)?<div className="nfl-line-result"><span>Final result</span>{actual!==null&&<strong>{actual}<small>final {row!.market_name.endsWith('Rushing Yards')?'rushing yards':row!.market_name.endsWith('Passing Touchdowns')?'passing touchdowns':'actual'}</small></strong>}{result&&<b>{result}</b>}</div>:<p className="nfl-line-unavailable">{admitted?'Result unconfirmed':'Current probability unavailable'}</p>}
  {!admitted&&<p>Only the pregame expectation is available for this line at this point in the replay. A later quote or result is not shown.</p>}
  <details><summary>Quote &amp; source</summary>{quote!==null&&quotedAt?<><p><b>{probabilityLabel(quote)}</b> · last archived quote</p><p>Quoted {eventReaderTime.full(quotedAt)}.</p><p>This is a dated quote, not a current chance.</p></>:<p>No quote available at this reading snapshot.</p>}<p>{venue} · Market {row!._market_id}</p><p>Reading snapshot: {eventReaderTime.full(at)}.</p></details>
 </section>;
}
