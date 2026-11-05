import {combatMomentOrder,combatStoryFamilies} from './combatMomentStories';
import {createStoryStream,selectStory,holdStories,type StoryStreamState} from './storyStreamState';
import {catalogAnchor} from './catalogSelection';
import {StoryStream} from './StoryStream';
import {combatFinalFor} from './combatOfficialFinal';
import {useStoryState,useStoryReaderMemory} from './StorySession';
import {useMemo,type Dispatch,type SetStateAction} from 'react';
import {CardFocus,ExpandCard} from './CardFocus';
import {CombatOutcomeCard} from './CombatOutcomeCards';
import {CombatDurationCard} from './CombatDurationCard';
import {type CombatRow} from './combatOutcome';
import {retainedCombatWinnerHistory} from './combatWinnerHistory';
import {probabilityLabel} from './probabilityLabel';
import type {CatalogAnchor} from './catalogSelection';
import {useKeyboard} from './mobile';
import './combatFocus.css';
const families=combatStoryFamilies;
type Family=typeof families[number]['id'];
export function CombatStories<T extends CombatRow>({rows,eventID,onPick,wide,large,anchors,setAnchors}:{rows:T[];eventID:number;onPick:(row:T)=>void;wide:boolean;large:boolean;anchors:Record<string,CatalogAnchor<T>>;setAnchors:Dispatch<SetStateAction<Record<string,CatalogAnchor<T>>>>}){
 const scope=`combat:${eventID}`,rank=useMemo(()=>combatMomentOrder(rows,eventID),[rows,eventID]);
 const [historyReaderOpen]=useStoryState<boolean>(scope,'history-reader-open',false);
 const [stream,setStream]=useStoryState<StoryStreamState>(scope,'stream',()=>createStoryStream(rank.ids));
 const [readerOrder,setReaderOrder]=useStoryState<string[]>(scope,'readerOrder',[]);
 const memory=useStoryReaderMemory('mma');const [readerActive,setReaderActive]=useStoryState<string|null>('mma','readerActive',null);
 const [focus,setFocus]=useStoryState<Family|null>('mma','focus',null),keyboard=useKeyboard();
 const admitted=rank.ids.flatMap(id=>{const card=families.find(f=>f.id===id);return card?[card]:[]});
 const readerCards=(focus!==null&&readerOrder.length?readerOrder:stream.order).flatMap(id=>{const card=admitted.find(f=>f.id===id);return card?[card]:[]});
 const expand=(id:Family)=>{keyboard.hide();setStream(s=>selectStory(s,id));setReaderOrder([...stream.order]);setReaderActive(id);setFocus(id)};
 const activate=(id:string)=>{setReaderActive(id);setStream(s=>selectStory(s,id))};
 const selectCard=(id:Family)=>setStream(s=>focus===null?selectStory(s,id):holdStories(s));
 const final=combatFinalFor(eventID);
 const baseline=retainedCombatWinnerHistory.filter(p=>p.pregame).at(-1);
 const story=(id:Family)=>{
  const key='combat:'+id,initial=rows.find(row=>row.key===rank.selectedKeys[id]);
  const common={rows,eventID,onPick:(row:T)=>{selectCard(id);onPick(row)},savedAnchor:anchors[key]??(initial?catalogAnchor(initial):null),onSelection:(anchor:CatalogAnchor<T>)=>{selectCard(id);setAnchors(old=>({...old,[key]:anchor}))},finalStory:!!rank.reasons[id]};
  return id==='duration'?<CombatDurationCard {...common} leadKey={initial?.key}/>:<CombatOutcomeCard {...common} family={id}/>;
 };
 return <><StoryStream event={scope} subject="fight" wide={wide} requireCardVisibility basis={Object.keys(rank.reasons).length?"Recorded final · ranked from the bout result":"Recorded fight · captured cards"} readerOpen={focus!==null||historyReaderOpen} cards={admitted.map(card=>({...card,visual:<div className="combat-story-slot"><ExpandCard label={card.name} onClick={()=>expand(card.id)}/>{rank.reasons[card.id]&&<p className="combat-moment-reason">{rank.reasons[card.id]}</p>}{story(card.id)}</div>}))}/>
 <CardFocus memory={memory} resumeAt={readerActive} onActiveCardChange={activate} start={focus} cards={readerCards.map(card=>({...card,visual:<div className={`combat-focus-content ${large?'large-text':''}`}>{story(card.id)}</div>}))} onClose={()=>setFocus(null)} wide={wide} large={large} returnLabel="Back to fight" anchor={<><b>{final?'Kopylov won · TKO · R1, 3:12':'Gautier · Kopylov · Suspended'}</b><span>Pre-match win · Gautier {probabilityLabel(baseline?.home)} / Kopylov {probabilityLabel(baseline?.away)}</span>{!final&&<span>Current probability unavailable · bout result unconfirmed</span>}</>}/>
 </>;
}
