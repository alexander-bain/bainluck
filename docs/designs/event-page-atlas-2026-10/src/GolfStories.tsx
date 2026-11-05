import {useStoryState,useStoryReaderMemory} from './StorySession';
import {useEffect,type Dispatch,type SetStateAction} from 'react';
import type {Row} from './Atlas';
import {catalogAnchor,type CatalogAnchor} from './catalogSelection';
import {groupCatalogRows} from './catalogGroups';
import {golfGroupKey,golfStorySelection,placementStorySelection,placementSelectionKey,rememberGolfCatalogSelection} from './golfFocus';
import {golfRows,golfScore,golfPregame} from './golfEvidence';
import {placementDefault,type PlacementRow} from './placementEvidence';
import {GolfFinalStories} from './GolfFinal';
import {PlacementStory} from './PlacementFinal';
import {CardFocus,ExpandCard} from './CardFocus';
import {probabilityLabel} from './probabilityLabel';
import {useKeyboard} from './mobile';
import './golfFocus.css';
type Props={onPick:(row:Row)=>void;wide:boolean;large:boolean;anchors:Record<string,CatalogAnchor<Row>>;setAnchors:Dispatch<SetStateAction<Record<string,CatalogAnchor<Row>>>>};
export function GolfStories({onPick,wide,large,anchors,setAnchors,active=true}:Props&{active?:boolean}){
 const memory=useStoryReaderMemory('golf');const [focus,setFocus]=useStoryState('golf','focus',false),[roundsOpen,setRoundsOpen]=useStoryState('golf','roundsOpen',false),keyboard=useKeyboard();
 const selected=golfStorySelection(anchors),winner=golfRows.find(r=>r.result)!;
 useEffect(()=>setAnchors(old=>old[golfGroupKey]?old:{...old,[golfGroupKey]:catalogAnchor(winner.final as Row)}),[setAnchors,winner]);
 if(!selected||!active)return null;
 const choose=(key:string)=>{const row=golfRows.find(r=>r.key===key);if(row)setAnchors(old=>({...old,[golfGroupKey]:catalogAnchor(row.final as Row)}))};
 const story=(focused=false)=><GolfFinalStories focused={focused} onPick={onPick} selectedKey={selected.key} onSelection={choose} roundsOpen={roundsOpen} onRoundsOpen={value=>setRoundsOpen(old=>old===value?old:value)}/>;
 return <div className="golf-story-slot"><ExpandCard label="Golf scorecards" onClick={()=>{keyboard.hide();setFocus(true)}}/>{story()}
 <CardFocus memory={memory} start={focus?'scorecards':null} cards={[{id:'scorecards',name:'Golf scorecards',visual:<div className={`golf-focus-content ${large?'large-text':''}`}>{story(true)}</div>}]} wide={wide} large={large} onClose={()=>setFocus(false)} returnLabel="Back to tournament" anchor={<><b>Dunhill Links · Final</b><span>{winner.name} won · {golfScore(winner)}</span><span>Pre-event win chance {probabilityLabel(golfPregame(winner.final)?.value)}</span></>}/></div>;
}
export function PlacementStories({onPick,wide,large,anchors,setAnchors,active=true}:Props&{active?:boolean}){
 const memory=useStoryReaderMemory('golf-top10');const [focus,setFocus]=useStoryState('golf-top10','focus',false),keyboard=useKeyboard();const selected=placementStorySelection(anchors);
 useEffect(()=>setAnchors(old=>{if(old[placementSelectionKey])return old;const row=placementDefault.final as Row;return rememberGolfCatalogSelection(old,groupCatalogRows([row])[0].key,catalogAnchor(row))}),[setAnchors]);
 if(!selected)return null;
 const choose=(point:PlacementRow)=>{const row=point.final as Row;setAnchors(old=>rememberGolfCatalogSelection(old,groupCatalogRows([row])[0].key,catalogAnchor(row)))};
 const story=(enabled:boolean)=><PlacementStory onPick={onPick} active={enabled} selectedPoint={selected} onSelection={choose}/>;
 return <div className="golf-story-slot"><ExpandCard label="Top-10 expectations" onClick={()=>{keyboard.hide();setFocus(true)}}/>{story(active&&!focus)}
 <CardFocus memory={memory} start={focus?'top10':null} cards={[{id:'top10',name:'Top-10 expectations',visual:<div className={`golf-focus-content ${large?'large-text':''}`}>{story(focus)}</div>}]} wide={wide} large={large} onClose={()=>setFocus(false)} returnLabel="Back to tournament" anchor={<><b>Open de España · Final</b><span>Top 10 including ties · pre-event expectations</span></>}/></div>;
}
