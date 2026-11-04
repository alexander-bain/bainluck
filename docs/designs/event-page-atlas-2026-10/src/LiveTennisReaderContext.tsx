import {InfoCircledIcon} from '@radix-ui/react-icons';
import {probabilityLabel as pct} from './probabilityLabel';
import f from './liveTennis.json';
import './liveTennisReaderContext.css';

/** This archive contains a qualified two-player blend; no prop probabilities are inferred. */
export function LiveTennisReaderContext({captured,onInfo}:{captured:boolean;onInfo:()=>void}){
 const players=[{name:'Fils',before:f.baseline.value,recorded:f.headline.home,tone:'home'},{name:'Zandschulp',before:1-f.baseline.value,recorded:f.headline.away,tone:'away'}];
 return <div className="lt-reader-context">
  <div className="lt-reader-score"><b>Fils 0–1 Zandschulp · Set 2: 3–3</b></div>
  <div className="lt-reader-legend"><span className="lt-reader-label">Match win ·</span><span className="lt-reader-phase"><i className="before" aria-hidden="true"/>Pre-match</span>{captured&&<><span aria-hidden="true">→</span><span className="lt-reader-phase"><i className="recorded" aria-hidden="true"/>Recorded</span></>}<button onClick={onInfo} aria-label="About the recorded score and win chances"><InfoCircledIcon/></button></div>
  <div className="lt-reader-pair">{players.map(player=><div key={player.name} className={`lt-reader-player ${player.tone}`} aria-label={`${player.name}: pre-match win chance ${pct(player.before)}; ${captured?`recorded win chance ${pct(player.recorded)}`:'Current probability unavailable'}`}>
   <span className="lt-reader-name">{player.name}</span>
   <div className="lt-reader-values"><span>{pct(player.before)}</span>{captured&&<><span className="lt-reader-arrow" aria-hidden="true">→</span><strong>{pct(player.recorded)}</strong></>}</div>
   <div className="lt-reader-track" aria-hidden="true">
    {captured&&<><i className="lt-reader-change" style={{left:`${100*Math.min(player.before,player.recorded)}%`,width:`${100*Math.abs(player.recorded-player.before)}%`}}/><i className="lt-reader-dot" style={{left:`${100*player.recorded}%`}}/></>}
    <i className="lt-reader-opening" style={{left:`${100*player.before}%`}}/>
   </div>
  </div>)}</div>
  {!captured&&<span className="lt-reader-note">Current probability unavailable</span>}
 </div>;
}
