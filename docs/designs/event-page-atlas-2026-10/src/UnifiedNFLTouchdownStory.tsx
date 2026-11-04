import {ProbabilityAvailabilityNote} from './ProbabilityAvailabilityNote';
import {PassingTouchdownsCard,PassingTouchdownsSummary} from './PassingTouchdownsCard';
import {touchdownID} from './passingTouchdowns';
import {PassingYardsCard,PassingYardsSummary} from './PassingYardsCard';
import {passingID} from './passingYards';
import {ReceptionCountCard} from './ReceptionCountCard';
import {receptionProfile,receptionID,receptionComparison} from './receptionCounts';
import {useCallback,useEffect,useMemo,useRef} from 'react';
import {CheckIcon,Cross2Icon} from '@radix-ui/react-icons';
import {StoryStream} from './StoryStream';
import {CardFocus} from './CardFocus';
import {useStoryState,useStoryReaderMemory} from './StorySession';
import {createStoryStream,holdStories,resumeStories,advanceStory,selectStory,receiveStoryOrder,type StoryStreamState} from './storyStreamState';
import {CombinedYardsCard} from './CombinedYardsStory';
import {TeamMilestoneCard} from './TeamMilestonesStory';
import {combinedProfile,combinedResult} from './combinedYardage';
import {teamMilestones,teamMilestoneDefinitions,type TeamMilestoneKind} from './teamMilestones';
import {nflTouchdownCandidates as nflStoryCandidates,previewNFLTouchdownOrder as previewNFLOrder} from './unifiedNFLTouchdownStories';
import {probabilityLabel as pct} from './probabilityLabel';
import './unifiedNFLStories.css';

export function UnifiedNFLTouchdownStory({phase,wide,large,detailOpen,matchLabel,onOriginal,mode,onChart}:{phase:string;wide:boolean;large:boolean;detailOpen:boolean;matchLabel:string;onOriginal:(key:string)=>void;mode:string;onChart:()=>void}){
 const scope='unified416:'+phase;
 const [priority]=useStoryState('preview','priority','original');
 const ranked=previewNFLOrder(phase,priority),orderKey=JSON.stringify(ranked);
 const candidates=useMemo(()=>nflStoryCandidates(phase),[phase]);
 const [streams,setStreams]=useStoryState<Record<string,StoryStreamState>>('unified416','streams',()=>Object.fromEntries(['Before','During','Final'].map(p=>[p,createStoryStream(previewNFLOrder(p,'original'))])));
 const change=useCallback((fn:(s:StoryStreamState)=>StoryStreamState)=>setStreams(old=>{const s=fn(old[phase]);return s===old[phase]?old:{...old,[phase]:s}}),[phase,setStreams]);
 const actions=useMemo(()=>({hold:()=>change(holdStories),resume:(manual:boolean)=>change(s=>manual?holdStories(resumeStories(s)):resumeStories(s)),move:(n:number,manual:boolean)=>change(s=>advanceStory(s,n,manual)),select:(id:string)=>change(s=>selectStory(s,id))}),[change]);
 const control=useMemo(()=>({state:streams[phase],...actions}),[streams,phase,actions]);
 const [focus,setFocus]=useStoryState<string|null>(scope,'opening',null);
 const [active,setActive]=useStoryState<string>(scope,'reader-active',ranked[0]??'team:field-goals');
 const [readerOrder,setReaderOrder]=useStoryState<string[]>(scope,'reader-order',[]);
 const [selection,setSelection]=useStoryState<Record<string,string|number>>(scope,'selection',{});
 const memory=useStoryReaderMemory(scope),priorPhase=useRef(phase);
 useEffect(()=>{change(s=>receiveStoryOrder(s,JSON.parse(orderKey)))},[orderKey,change]);
 useEffect(()=>{if(priorPhase.current!==phase){setFocus(null);actions.hold()};priorPhase.current=phase},[phase,actions,setFocus]);
 const choose=(id:string,value:string|number)=>{actions.hold();setSelection(old=>old[id]===value?old:{...old,[id]:value})};
 const open=(id:string)=>{actions.select(id);setReaderOrder([...streams[phase].order]);setActive(id);setFocus(id)};
 const render=(id:string,expanded=false)=>{
  if(id===touchdownID)return <PassingTouchdownsCard phase={phase} threshold={typeof selection[id]==='number'?selection[id] as number:2} choose={n=>choose(id,n)} expanded={expanded} large={large} mode={mode} expand={()=>open(id)} original={onOriginal}/>;
  if(id===passingID)return <PassingYardsCard phase={phase} threshold={typeof selection[id]==='number'?selection[id] as number:225} choose={n=>choose(id,n)} expanded={expanded} large={large} mode={mode} expand={()=>open(id)} original={onOriginal}/>;
  if(id===receptionID)return <ReceptionCountCard phase={phase} selected={typeof selection[id]==='string'?selection[id] as string:undefined} choose={key=>choose(id,key)} expanded={expanded} large={large} mode={mode} expand={()=>open(id)} original={onOriginal}/>;
  if(id.startsWith('yards:')){const name=id.slice(6);return <CombinedYardsCard showSettlement name={name} phase={phase} selected={typeof selection[id]==='string'?selection[id] as string:undefined} choose={key=>choose(id,key)} expand={expanded?undefined:()=>open(id)} original={onOriginal} expanded={expanded} mode={mode} large={large}/>}
  const kind=id.slice(5) as TeamMilestoneKind;
  return <TeamMilestoneCard kind={kind} phase={phase} threshold={typeof selection[id]==='number'?selection[id] as number:teamMilestoneDefinitions[kind].thresholds[0]} choose={n=>choose(id,n)} expanded={expanded} large={large} mode={mode} expand={()=>open(id)} original={onOriginal}/>;
 };
 const cards=candidates.map(c=>({id:c.id,name:c.name,visual:render(c.id)}));
 const title=candidates.find(c=>c.id===active)?.name;
 let selectedAnchor;
 if(active===touchdownID){
  selectedAnchor=large?<b>Quarterbacks · passing touchdowns</b>:<PassingTouchdownsSummary phase={phase} threshold={typeof selection[active]==='number'?selection[active] as number:2} original={onOriginal}/>;
 }else if(active===passingID){
  selectedAnchor=large?<b>Quarterbacks · passing yards</b>:<PassingYardsSummary phase={phase} threshold={typeof selection[active]==='number'?selection[active] as number:225} original={onOriginal}/>;
 }else if(active===receptionID){
  const p=receptionProfile(phase),q=p?.points.find(q=>q.over.row_key===(selection[active]??p.defaultKey))??p?.points[0];
  selectedAnchor=large?<b>Wicks · catches</b>:<><div className="uf-reader-values"><div><b>Dontayvion Wicks</b><span>{p?.actual==null?'Actual unavailable':p.actual+' catches · final'}</span></div><div><b>{q?.needed}+ catches</b><span>{pct(q?.baseline)} pregame</span></div></div>{p?.actual!=null&&q&&<span className="uf-contract">{receptionComparison(p.actual,q.needed)}</span>}</>;
 }else if(active.startsWith('yards:')){
  const name=active.slice(6),p=combinedProfile(name,phase),q=p?.points.find(q=>q.row.row_key===(selection[active]??p.defaultKey));
  selectedAnchor=<><div className="uf-reader-values"><div><b>{name}</b><span>{phase==='Final'?(p?.total==null?'Actual unavailable':p.total+' yards · final'):'Player actual unavailable'}</span></div><div><b>{q?.threshold}+ yards</b><span>{pct(q?.baseline)} pregame</span></div></div>{q&&phase==='Final'&&p?.total==null&&<span className="uf-contract">{q.threshold}+ yards · {combinedResult(q.row,phase)}</span>}</>;
 }else{
  const kind=active.slice(5) as TeamMilestoneKind,p=teamMilestones(kind,phase),n=typeof selection[active]==='number'?selection[active] as number:teamMilestoneDefinitions[kind].thresholds[0];
  selectedAnchor=<><b>{n}+ {teamMilestoneDefinitions[kind].unit} · pregame chances</b><div className="tm-reader-values">{p?.profiles.map(t=>{const q=t.points.find(q=>q.threshold===n)!;return <button key={t.team} aria-describedby={q.result!==null?'uf-reader-'+q.row.row_key:undefined} onClick={()=>onOriginal(q.row.row_key)} aria-label={t.name+' '+n+'+ '+p.definition.unit+' · '+pct(q.baseline)+' pregame · Details'}><span>{t.name}</span><b>{pct(q.baseline)}</b>{q.result!==null&&<em id={'uf-reader-'+q.row.row_key}>{q.result==='Hit'?<><CheckIcon/>{n}+ hit</>:q.result==='Missed'?<><Cross2Icon/>{n}+ missed</>:'Result unconfirmed'}</em>}</button>})}</div></>;
 }
 return <section className={'cy-stories tm-stories uf-stories '+(large?'tm-large cy-large':'')} aria-label="Ranked Bears Eagles probability stories"><div className="cy-match-context tm-story-context" hidden={wide} aria-label="Bears Eagles probability context"><div><b>{matchLabel}</b><button onClick={()=>{actions.hold();onChart()}}>Chart</button></div><span>Bears 36.5% · Eagles 63.5% pregame</span></div><StoryStream topOccluder={wide?undefined:'.tm-story-context'} control={control} key={scope} event={scope} cards={cards} rankedIDs={ranked} readerOpen={detailOpen||focus!==null} wide={wide} requireCardVisibility subject="game" eyebrow="EXPECTATIONS & RESULTS" basis={phase==='Final'?'Pregame expectations · recorded performance and results':'Pregame baselines · milestones with visual variety'}/><CardFocus settleCards peekAdjacent={false} memory={memory} start={focus} resumeAt={active} onActiveCardChange={setActive} suspended={detailOpen} cards={readerOrder.flatMap(id=>{const c=candidates.find(c=>c.id===id);return c?[{id,name:c.name,visual:render(id,true)}]:[]})} wide={wide} large={large} onClose={()=>setFocus(null)} readerTitle="Bears–Eagles stories" returnLabel="Back to Bears–Eagles" anchor={<><b>{matchLabel}</b><span>Pregame Bears 36.5% · Eagles 63.5%</span>{!large&&<span className="sr-only uf-reader-title">{title}</span>}{selectedAnchor}<ProbabilityAvailabilityNote as="small" phase={phase} important={phase==='Final'?(active===receptionID?'Settlement unconfirmed':active.startsWith('team:')?'Exact final counts unavailable':null):null}/></>}/></section>;
}
