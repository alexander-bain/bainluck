import {probabilityLabel} from './probabilityLabel';
import {TennisPropChance} from './TennisPropChance';
import {tennisPropBaseline,tennisPropNote} from './tennisPropPregame';
import {useState} from 'react';
import {tennisScoreOutcome} from './tennisScoreOutcome';
import type {TennisScore,TennisScoreRow} from './tennisScoreOutcome';
import {catalogPresentation,type CatalogContext} from './probabilityPresentation';
import {catalogOutcomeIdentity} from './catalogSelection';
import './tennisScoreOutcome.css';
export function TennisScoreOutcomeCard<T extends TennisScoreRow>({data,selected,visibleRows,context,choose}:{data:TennisScore<T>;selected:T;visibleRows:T[];context:CatalogContext;choose:(r:T)=>void}){
 const visible=new Set(visibleRows.map(catalogOutcomeIdentity));
 return <section className="tennis-score" aria-label="Exact match score alternatives in sets">
 <p className="tennis-score-key">Sets won · best of {data.target*2-1}</p>
 <div className="tennis-score-players">{data.players.map((name,player)=><div className="tennis-score-player" key={name}><h4>{name}</h4><div className="tennis-finish-options">{Array.from({length:data.target},(_,lost)=>{
 const cell=data.cells.find(c=>c.player===player&&c.lost===lost);if(!cell)return <div className="tennis-score-missing" key={lost}><strong>{data.target}–{lost}</strong><span>Not listed</span></div>;
 const active=catalogOutcomeIdentity(cell.row)===catalogOutcomeIdentity(selected),shown=visible.has(catalogOutcomeIdentity(cell.row)),state=catalogPresentation(cell.row,context);
 return <button key={lost} aria-pressed={active} disabled={!shown} onClick={()=>choose(cell.row)} aria-label={`${name} wins ${data.target}-${lost} sets: ${shown?state.label:'Outside filter'}; pre-match chance ${probabilityLabel(tennisPropBaseline(cell.row)?.value??null)}`} className={state.label==='Won'?'tennis-score-won':''}>
 {tennisPropBaseline(cell.row)&&<TennisPropChance row={cell.row}/>}<strong>{data.target}–{lost}</strong><div className="tennis-set-count" aria-hidden="true"><div>{Array.from({length:data.target},(_,i)=><i key={i}/>)}</div><div>{Array.from({length:data.target},(_,i)=><i key={i} className={i<lost?'opponent':'empty'}/>)}</div></div><span>{shown?(state.label==='Won'?'✓ Won':state.label==='Lost'?'× Lost':state.label):'Outside filter'}</span></button>
 })}</div></div>)}</div>
 <p className="tennis-score-note">Blocks count sets won by each player; they do not show playing order. Results come from provider settlement. {tennisPropBaseline(selected)?tennisPropNote(selected):'Pre-match chances unavailable.'}</p>
 </section>
}

export function TennisScoreStory<T extends TennisScoreRow>({rows,onPick,selectedKey,onSelection}:{rows:T[];onPick:(r:T)=>void;selectedKey?:string;onSelection?:(key:string)=>void}){
 const [key,setKey]=useState(rows[0]?.key);const data=tennisScoreOutcome(rows,'completed');const selected=rows.find(r=>r.key===(selectedKey??key))??rows[0];
 if(!data||!selected)return null;
 return <><TennisScoreOutcomeCard data={data} selected={selected} visibleRows={rows} context={{status:'completed',qualityHold:false,mode:'captured'}} choose={r=>{setKey(r.key);onSelection?.(r.key)}}/><button className="card-link" onClick={()=>onPick(selected)}>Details · {selected.outcome_name}</button></>;
}
