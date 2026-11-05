import {HockeyContributionCard,type ContributionSelection} from './HockeyContributionCard';
import {hockeyContributionProfiles} from './hockeyContributions';
import {hockeyFamilies as baseFamilies,hockeyMomentOrder} from './hockeyMomentStories';
import {createStoryStream,holdStories,selectStory,type StoryStreamState} from './storyStreamState';
import {catalogAnchor} from './catalogSelection';
import {useStoryReaderMemory} from './StorySession';
import {type ReactNode} from 'react';
import {StoryStream} from './StoryStream';
import {useStoryState} from './StorySession';
import type {Row} from './Atlas';
import type {CatalogAnchor} from './catalogSelection';
import {HockeyGoalsCard} from './HockeyGoalsCard';
import {HockeyScoringCard} from './HockeyScoringCard';
import {hockeyEvidence} from './hockeyEvidence';
import {finalHeaderFor} from './FinalOutcomeHeader';
import {probabilityLabel} from './probabilityLabel';
import {CardFocus,ExpandCard} from './CardFocus';
import {useKeyboard} from './mobile';
import './hockeyFocus.css';
const families=[...baseFamilies,{id:'points',name:'Points versus expectations'},{id:'assists',name:'Who set them up?'}] as const;
type Family=typeof families[number]['id'];
export function HockeyStories({rows,eventID,mode,onPick,wide,large,forecast}:{forecast:ReactNode;rows:Row[];eventID:unknown;mode:string;onPick:(row:Row)=>void;wide:boolean;large:boolean}){
 const base=hockeyMomentOrder(rows,eventID);
 const available=(['points','assists'] as const).filter(kind=>hockeyContributionProfiles(rows,eventID,kind).length>0);
 const rank={...base,ids:[...base.ids,...available] as Family[],reasons:base.reasons as Partial<Record<Family,string>>};
 const [stream,setStream]=useStoryState<StoryStreamState>('nhl','stream',()=>createStoryStream(rank.ids));
 const [readerOrder,setReaderOrder]=useStoryState<string[]>('nhl','readerOrder',[]);
 const ordered=rank.ids.flatMap(id=>{const card=families.find(c=>c.id===id);return card?[card]:[]});
 const memory=useStoryReaderMemory('nhl');
 const keyboard=useKeyboard();
 const [focus,setFocus]=useStoryState<Family|null>('nhl','focus',null);
 const [readerActive,setReaderActive]=useStoryState<string|null>('nhl','readerActive',null);
 const [milestone,setMilestone]=useStoryState('nhl','milestone',()=>hockeyEvidence.points.find(p=>p.count===6)!.key);
 const [anchors,setAnchors]=useStoryState<Partial<Record<'first'|'goals',CatalogAnchor<Row>>>>('nhl','anchors',()=>{const selected=rows.find(row=>row.key===rank.selectedScorerKey);return selected?{goals:catalogAnchor(selected)}:{}});
 const [players,setPlayers]=useStoryState('nhl','players',{first:false,goals:false});
 const [contributions,setContributions]=useStoryState<Record<'points'|'assists',ContributionSelection>>('nhl','contribution-selection',{points:{player:'Quinn Hughes',threshold:2},assists:{player:'Quinn Hughes',threshold:2}});
 const [contributionPlayers,setContributionPlayers]=useStoryState('nhl','contribution-players',{points:false,assists:false});
 const header=finalHeaderFor('nhl')!;
 const expand=(id:Family)=>{keyboard.hide();setStream(s=>selectStory(s,id));setReaderOrder([...stream.order]);setReaderActive(id);setFocus(id)};
 const activateReader=(id:string)=>{setReaderActive(id);setStream(s=>selectStory(s,id))};
 const readerCards=(focus!==null&&readerOrder.length?readerOrder:stream.order).flatMap(id=>{const card=families.find(c=>c.id===id);return card?[card]:[]});
 const pick=(row:Row,id:Family)=>{setStream(s=>focus===null?selectStory(s,id):holdStories(s));onPick(row)};
 const story=(id:Family)=>id==='points'||id==='assists'?<HockeyContributionCard rows={rows} eventID={eventID} kind={id} selection={contributions[id]} onSelection={selection=>setContributions(previous=>({...previous,[id]:selection}))} playersOpen={contributionPlayers[id]} onPlayersOpen={open=>setContributionPlayers(previous=>({...previous,[id]:open}))} large={large} onPick={row=>pick(row,id)}/>:id==='forecast'?forecast:id==='totals'?<HockeyGoalsCard onPick={row=>pick(row,'totals')} selectedKey={milestone} onSelection={setMilestone}/>:<HockeyScoringCard rows={rows} eventID={eventID} kind={id} mode={mode} onPick={row=>pick(row,id)} savedAnchor={anchors[id]} onSelection={anchor=>setAnchors(previous=>({...previous,[id]:anchor}))} playersOpen={players[id]} onPlayersOpen={value=>setPlayers(previous=>({...previous,[id]:value}))}/>;
 return <><StoryStream event="nhl" wide={wide} requireCardVisibility basis="Recorded final · ranked from this game's outcome" readerOpen={focus!==null} cards={ordered.map(card=>({...card,visual:<div className="hockey-story-slot"><ExpandCard label={card.name} onClick={()=>expand(card.id)}/>{rank.reasons[card.id]&&<p className="hockey-moment-reason">{rank.reasons[card.id]}</p>}{story(card.id)}</div>}))}/>
 <CardFocus memory={memory} start={focus} resumeAt={readerActive} onActiveCardChange={activateReader} cards={readerCards.map(card=>({...card,visual:<div className={`hockey-focus-content ${large?'large-text':''}`}>{story(card.id)}</div>}))} onClose={()=>setFocus(null)} wide={wide} large={large} returnLabel="Back to match" anchor={<><b>Minnesota {header.homeScore}–{header.awayScore} Boston · Final</b><span>Pregame · opening win chance · Minnesota {probabilityLabel(header.homeBaseline)} / Boston {probabilityLabel(header.awayBaseline)}</span></>}/>
 </>;
}
