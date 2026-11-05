import {eventReaderTime} from './eventReaderTime';
import {HockeyFirstChances} from './HockeyFirstChances';
import {scorerPregame} from './hockeyScorerPregame';
import {useState} from 'react';
import {CheckCircledIcon,ChevronDownIcon,ChevronUpIcon,ChevronRightIcon} from '@radix-ui/react-icons';
import {CatalogProbabilityCard} from './CatalogProbabilityCard';
import {probabilityLabel} from './probabilityLabel';
import {PregameContext} from './PregameContext';
import {pregameNote,selectedPregame} from './pregameEvidence';
import {catalogAnchor,resolveCatalogSelection,type CatalogAnchor} from './catalogSelection';
import {hockeyScoringRows,hockeyScoringRecord,hockeyGoalLabel,type HockeyScoringRow,type HockeyScoringKind} from './hockeyScoringEvidence';
import './hockeyScoring.css';
export function HockeyScoringCard<T extends HockeyScoringRow>({rows:allRows,eventID,kind,mode,onPick,savedAnchor,onSelection,playersOpen,onPlayersOpen}:{savedAnchor?:CatalogAnchor<T>|null;onSelection?:(anchor:CatalogAnchor<T>)=>void;playersOpen?:boolean;onPlayersOpen?:(value:boolean)=>void;rows:T[];eventID:unknown;kind:HockeyScoringKind;mode:string;onPick:(row:T)=>void}){
 const rows=hockeyScoringRows(allRows,eventID,kind);
 const records=rows.map(row=>hockeyScoringRecord(row,kind)!);
 const scorers=records.filter(record=>(record.actual??0)>0).sort((a,b)=>(b.actual!-a.actual!)||a.player.localeCompare(b.player));
 const winners=records.filter(record=>record.result==='Won');
 const first=kind==='first'&&winners.length===1?winners[0]:null;
 const initial=first??scorers[0]??records[0];
 const [localAnchor,setLocalAnchor]=useState<CatalogAnchor<T>|null>(()=>initial?catalogAnchor(initial.row):null);
 const [localExpanded,setLocalExpanded]=useState(false);
 const anchor=savedAnchor??localAnchor,setAnchor=onSelection??setLocalAnchor,expanded=playersOpen??localExpanded,setExpanded=onPlayersOpen??setLocalExpanded;
 const selectedRow=resolveCatalogSelection(rows,anchor).row;
 const selected=selectedRow?hockeyScoringRecord(selectedRow,kind):null;
 if(!records.length||!selected||!selectedRow)return null;
 return <article className="atlas-card hockey-scoring-card" aria-label={kind==='first'?'Hockey first goalscorer':'Hockey player goals'}>
  <div className="atlas-card-head"><div><span className="eyebrow">Kalshi · {kind==='first'?'first goalscorer':'player goals'}</span><h3>{kind==='first'?'Who scored first?':'Who found the net?'}</h3></div><button className="tap-icon" aria-label={kind==='first'?'First-goalscorer details':'Player goals details'} onClick={()=>onPick(selectedRow)}><ChevronRightIcon/></button></div>
  {kind==='first'?first?<button className="hockey-first-result" aria-label={`Select confirmed first scorer ${first.player}`} onClick={()=>setAnchor(catalogAnchor(first.row))}><CheckCircledIcon aria-hidden="true"/><div><strong>{first.player}</strong><span>First goalscorer · confirmed result</span></div></button>:<p>First goalscorer unconfirmed</p>:<><p className="hockey-goal-key">Pregame chance of scoring 1+ goals</p>{records.every(record=>selectedPregame(record.row)===null)&&<p className="hockey-price-gap">Pre-game scoring probabilities unavailable.</p>}<div className="hockey-goal-grid">{scorers.map(record=><button key={record.id} className="hockey-goal-tile" aria-pressed={selected.id===record.id} aria-label={`${record.player}, ${hockeyGoalLabel(record.actual)}. Pregame chance ${selectedPregame(record.row)===null?'unavailable':probabilityLabel(selectedPregame(record.row))}. Select 1 or more goals prop.`} onClick={()=>setAnchor(catalogAnchor(record.row))}><b>{record.player}</b><span>{record.team??'Team unavailable'}</span><div className="hockey-tile-chance">{selectedPregame(record.row)!==null?<svg className="hockey-chance-ring" viewBox="0 0 80 80" aria-hidden="true"><circle cx="40" cy="40" r="32" className="hockey-ring-track"/><circle cx="40" cy="40" r="32" className="hockey-ring-value" pathLength="100" strokeDasharray={`${selectedPregame(record.row)!*100} 100`} transform="rotate(-90 40 40)"/><text x="40" y="46" textAnchor="middle">{probabilityLabel(selectedPregame(record.row))}</text></svg>:<strong className="hockey-ring-missing">Unavailable</strong>}<div className="hockey-chance-caption"><span>Pregame</span><small>{scorerPregame(record.row)?eventReaderTime.full(scorerPregame(record.row)!.at):'No captured trade'}</small></div></div><div className="hockey-tile-actual"><strong>Final · {hockeyGoalLabel(record.actual)}</strong><span className="hockey-pucks" aria-hidden="true">{Array.from({length:record.actual!},(_,i)=><i key={i}/>)}</span></div></button>)}</div></>}
  {(kind==='first'||!scorers.some(record=>record.id===selected.id))&&<PregameContext label="Pregame chance" value={selectedPregame(selectedRow)} note={pregameNote(selectedRow)} subject={`${selected.player} · ${kind==='first'?'first goalscorer':'1+ goals'}`}/>}
  {kind==='first'&&first&&selected.id!==first.id&&<p className="hockey-goal-selected">Selected first-goalscorer contract · <strong>{selected.result}</strong></p>}
  {kind==='first'&&<HockeyFirstChances rows={rows} selectedID={selected.id} onSelect={row=>setAnchor(catalogAnchor(row))}/>}
  {kind==='goals'&&<>{!scorers.some(record=>record.id===selected.id)&&<div className="hockey-goal-selected" aria-live="polite"><span>Final · {hockeyGoalLabel(selected.actual)}</span><strong>1+ contract · {selected.result}</strong></div>}<p className="hockey-goal-key">{records.filter(record=>record.actual===0).length} recorded zero goals · {records.filter(record=>record.actual===null).length} goal totals unavailable. Rings: pregame trades · times: minute endings. Pucks: final goals.</p></>}
  <button className="card-link" aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>{expanded?'Hide all players':`Explore all ${rows.length} outcomes`}{expanded?<ChevronUpIcon/>:<ChevronDownIcon/>}</button>
  <div hidden={!expanded} className="hockey-scoring-expanded"><CatalogProbabilityCard rows={rows} context={{status:'completed',qualityHold:false,mode}} savedAnchor={anchor} onSelection={setAnchor} onPick={onPick}/></div>
 </article>;
}
