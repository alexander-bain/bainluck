import {PostponedReader} from './PostponedHeader';
import {postponedBaseline} from './postponedEvidence';
import {probabilityLabel} from './probabilityLabel';
import {useStoryReaderMemory} from './StorySession';
import {useEffect} from 'react';
import {ChevronLeftIcon,ChevronRightIcon} from '@radix-ui/react-icons';
import {CardFocus,ExpandCard} from './CardFocus';
import {CatalogProbabilityCard} from './CatalogProbabilityCard';
import {PregameContext} from './PregameContext';
import {catalogAnchor,catalogOutcomeIdentity,resolveCatalogSelection,type CatalogAnchor} from './catalogSelection';
import {catalogPresentation,type CatalogContext,type CatalogEvidenceRow} from './probabilityPresentation';
import {selectedPregame,pregameNote} from './pregameEvidence';
import {fieldFocusGroups,voidStoryKey} from './fieldFocus';
import {useFieldSession} from './FieldSession';
import {useKeyboard} from './mobile';
import './fieldFocus.css';

function FieldSelection<T extends CatalogEvidenceRow>({rows,selected,choose,context,independent}:{rows:T[];selected:T;choose:(r:T)=>void;context:CatalogContext;independent:boolean}){
 const selection=resolveCatalogSelection(rows,catalogAnchor(selected)),state=catalogPresentation(selected,selection.present?context:{...context,mode:'stale'});
 return <section className="field-selection" aria-label="Explore the field">
  <div className="field-selected"><span>{independent?'Qualification chance':'Chance to win'}</span><h4>{selected.outcome_name}</h4><strong>{state.label}</strong></div>
  <PregameContext label="Pre-event chance" value={selectedPregame(selected)} note={pregameNote(selected)}/>
  <div className="field-name-grid" role="group" aria-label="Contenders in original source order">{selection.shown.map(row=><button key={catalogOutcomeIdentity(row)} aria-pressed={catalogOutcomeIdentity(row)===catalogOutcomeIdentity(selected)} onClick={()=>choose(row)}><span>{row.outcome_name}</span></button>)}</div>
  <div className="field-window"><button aria-label="Previous contenders" disabled={selection.offset===0} onClick={()=>choose(rows[Math.max(0,selection.offset-6)])}><ChevronLeftIcon/></button><span>{selection.offset+1}–{Math.min(rows.length,selection.offset+6)} of {rows.length}<small>Source order · not a ranking</small></span><button aria-label="Next contenders" disabled={selection.offset+6>=rows.length} onClick={()=>choose(rows[selection.offset+6])}><ChevronRightIcon/></button></div>
  <p>{independent?'Countries qualify independently. Their chances are not shares of a single winner.':'The captured probabilities cannot support a reliable comparison.'} Last quotes remain in details.</p>
 </section>;
}

export function FieldStories<T extends CatalogEvidenceRow>({eventKey,title,rows,context,onPick,wide,large}:{eventKey:string;title:string;rows:T[];context:CatalogContext;onPick:(r:T)=>void;wide:boolean;large:boolean}){
 const memory=useStoryReaderMemory('field:'+eventKey);
 const {anchors,setAnchors,focus,setFocus,activeCard,setActiveCard}=useFieldSession(eventKey),sourceGroups=fieldFocusGroups(eventKey,rows),keyboard=useKeyboard();
 const groups=eventKey==='void'&&sourceGroups.length? [{key:voidStoryKey,id:voidStoryKey,name:'Closed contracts',rows:sourceGroups.flatMap(g=>g.rows)}]:sourceGroups;
 useEffect(()=>{if(focus&&keyboard.visible)keyboard.hide()},[focus,keyboard.visible,keyboard.hide]);
 const held=context.qualityHold,independent=eventKey==='lacrosse-field';
 const story=(g:typeof groups[number])=><CatalogProbabilityCard rows={g.rows} context={context} onPick={onPick} savedAnchor={anchors[g.key] as CatalogAnchor<T>??null} onSelection={anchor=>setAnchors(old=>({...old,[g.key]:anchor}))} displayTitle={eventKey==='void'?'Closed without a winner':undefined} baselineInVisual={held||eventKey==='void'} selectionControlsInVisual={held||eventKey==='void'} selectedSummaryInVisual={held} visual={held?(selected,choose)=><FieldSelection rows={g.rows} selected={selected} choose={choose} context={context} independent={independent}/>:eventKey==='void'?(selected,choose)=><section aria-label="Closed contract outcomes"><div className="void-contract-tiles">{g.rows.map(row=><button key={catalogOutcomeIdentity(row)} aria-pressed={catalogOutcomeIdentity(row)===catalogOutcomeIdentity(selected)} onClick={()=>{choose(row);const source=sourceGroups.find(item=>item.rows.includes(row));if(source)setAnchors(old=>({...old,[source.key]:catalogAnchor(row)}))}}><span aria-hidden="true">—</span><strong>{row.outcome_name}</strong>{postponedBaseline(row)&&<small className="postponed-tile-baseline">Pregame {probabilityLabel(postponedBaseline(row)?.value)}</small>}</button>)}</div><p className="void-contract-note">All three contracts closed at fair value. No winner was declared. Settlement amounts remain in details.</p></section>:undefined}/>;
 return <>{groups.map(g=><div className="field-story-slot" key={g.key}><ExpandCard label={g.name} onClick={()=>{keyboard.hide();setActiveCard(g.id);setFocus(g.id)}}/>{story(g)}</div>)}
 <CardFocus memory={memory} start={focus&&groups.some(g=>g.id===focus)?focus:null} resumeAt={activeCard} onActiveCardChange={setActiveCard} cards={groups.map(g=>({id:g.id,name:g.name,visual:<div className={`field-focus-content ${large?'large-text':''}`}>{story(g)}</div>}))} onClose={()=>setFocus(null)} wide={wide} large={large} returnLabel="Back to event" readerTitle="Explore event cards" anchor={eventKey==='void'&&context.status==='voided'&&!held&&rows.some(row=>postponedBaseline(row))?<PostponedReader wide={wide} large={large}/>:<><b>{title}</b><span>{eventKey==='void'?'Closed · no winner':held?'Current probability unavailable · retained field':context.mode==='captured'?'Recorded earnings outlook':'Current probability unavailable'}</span><span>{eventKey==='economics'?'Earlier chance unavailable':eventKey==='void'?'Settlement amounts are not probabilities':'Pre-event chances unavailable'}</span></>}/></>;
}
