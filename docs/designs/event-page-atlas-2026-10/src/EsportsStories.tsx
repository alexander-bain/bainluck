import {StoryStream} from './StoryStream';
import {reportedEsportsFinal} from './esportsFinalScore';
import {useStoryReaderMemory} from './StorySession';
import {useEffect} from 'react';
import {useEsportsSession} from './EsportsSession';
import {CardFocus,ExpandCard} from './CardFocus';
import {CatalogProbabilityCard} from './CatalogProbabilityCard';
import {EsportsQuestionVisual} from './EsportsQuestionVisual';
import {esportsFocusGroups,type EsportsFamily} from './esportsFocus';
import type {EsportsRow} from './esportsEvidence';
import type {CatalogAnchor} from './catalogSelection';
import {retainedEsportsWinnerHistory} from './esportsWinnerHistory';
import {probabilityLabel} from './probabilityLabel';
import {useKeyboard} from './mobile';
import './esportsFocus.css';
export function EsportsStories<T extends EsportsRow>({rows,status,onPick,wide,large}:{rows:T[];status:string;onPick:(row:T)=>void;wide:boolean;large:boolean}){
 const memory=useStoryReaderMemory('esports');
 const {activeCard,setActiveCard,focus,setFocus,anchors,setAnchors}=useEsportsSession(),keyboard=useKeyboard(),groups=esportsFocusGroups(rows);
 // The full-size reader contains no text entry. A restored catalog search focus
 // must not leave the preview keyboard covering these charts.
 useEffect(()=>{if(focus&&keyboard.visible)keyboard.hide()},[focus,keyboard.visible,keyboard.hide]);
 const baseline=retainedEsportsWinnerHistory.filter(p=>p.pregame).at(-1),context={status,qualityHold:false,mode:'captured'};
 const story=(g:typeof groups[number],expanded=false)=><CatalogProbabilityCard rows={g.rows} context={context} onPick={onPick} displayTitle={g.title} savedAnchor={anchors[g.groupKey] as CatalogAnchor<T>??null} onSelection={anchor=>setAnchors(old=>({...old,[g.groupKey]:anchor}))} baselineInVisual={g.id==='winner'} selectionControlsInVisual={g.id==='winner'} visual={(selected,choose)=><EsportsQuestionVisual data={g.data} selected={selected} visibleRows={g.rows} context={context} choose={choose} readerMode={expanded}/>}/>;
 return <><StoryStream event="esports" subject="match" wide={wide} readerOpen={focus!==null} cards={groups.map(g=>({id:g.id,name:g.name,visual:<div className="esports-story-slot"><ExpandCard label={g.name} onClick={()=>{keyboard.hide();setActiveCard(g.id);setFocus(g.id)}}/>{story(g)}</div>}))}/>
 <CardFocus memory={memory} resumeAt={activeCard} onActiveCardChange={setActiveCard} start={focus&&groups.some(g=>g.id===focus)?focus:null} cards={groups.map(g=>({id:g.id,name:g.name,visual:<div className={`esports-focus-content ${large?'large-text':''}`}>{story(g,true)}</div>}))} onClose={()=>setFocus(null)} wide={wide} large={large} returnLabel="Back to match" anchor={<div className="esports-reader-anchor"><b>{reportedEsportsFinal?'Nice Try 13–1 Flame Hard':'Nice Try · Flame Hard · Suspended'}</b><span>Pre-match blend · Nice Try {probabilityLabel(baseline?.home)} / Flame Hard {probabilityLabel(baseline?.away)}</span>{reportedEsportsFinal?<span>Final rounds · Map 1 · Dust2</span>:<span>Current probability unavailable · match result unconfirmed</span>}</div>}/></>;
}
