import {soccerFeedFrame,soccerFeedKeys} from './soccerFeedCards';
import type {HalfCompetitor} from './soccerHalfResults';
import {soccerJourneyContext,soccerJourneyTimes} from './soccerJourney';
import {eventReaderTime} from './eventReaderTime.ts';
import type {CardFocusMemory} from './readerRail';
import {useEffect,useReducer,useRef,useState} from 'react';
import f from './liveSoccer.json';
import {soccerLifecycleContext,soccerLifecycleRank,soccerLifecycleTimes,type SoccerLifecycleContext} from './soccerLifecycle';

import {createStoryReadingFrame,storyReadingReducer,type StoryFrame} from './storyReadingFrame';

export const soccerFrame=soccerFeedFrame;
export function useSoccerReadingSession(active:boolean,includeFinal=false){
 const times=includeFinal?soccerJourneyTimes:soccerLifecycleTimes(f.baseline.at);
 const [halfCompetitor,setHalfCompetitor]=useState<HalfCompetitor>('home');
 const [historyOpen,setHistoryOpen]=useState(false),[historyIndex,setHistoryIndex]=useState<number|null>(null),[historyFullScale,setHistoryFullScale]=useState(false);
 const [historyWindow,setHistoryWindow]=useState<'match'|'before'>('match'),[matchHistoryAt,setMatchHistoryAt]=useState<string|null>(null);
 const historyMemory=useRef<CardFocusMemory>({scrollTop:{}}).current;
 const readerMemory=useRef<CardFocusMemory>({scrollTop:{}}).current;
 const scope=useRef('soccer:valladolid-albacete:recorded:'+crypto.randomUUID()).current;
 const [state,dispatch]=useReducer(storyReadingReducer<SoccerLifecycleContext>,undefined,()=>createStoryReadingFrame(soccerFrame(0,scope,includeFinal),includeFinal?soccerFeedKeys:['goals','both','first']));
 const [receiving,setReceiving]=useState(false),[reduced,setReduced]=useState(false),[hidden,setHidden]=useState(document.hidden);
 const [expanded,setExpanded]=useState<string|null>(null),[readerActive,setReaderActive]=useState<string|null>(null);
 const [selected,setSelected]=useState<typeof f.rows[number]|null>(null),[info,setInfo]=useState(false),[catalog,setCatalog]=useState(false),[large,setLarge]=useState(false);
 useEffect(()=>{const media=matchMedia('(prefers-reduced-motion: reduce)'),update=()=>{setReduced(media.matches);if(media.matches)dispatch({type:'hold'})};update();media.addEventListener('change',update);return()=>media.removeEventListener('change',update)},[]);
 useEffect(()=>{const update=()=>{setHidden(document.hidden);dispatch({type:'lock',name:'background',active:document.hidden})};update();document.addEventListener('visibilitychange',update);return()=>document.removeEventListener('visibilitychange',update)},[]);
 useEffect(()=>{dispatch({type:'lock',name:'history',active:historyOpen})},[historyOpen]);
 useEffect(()=>{dispatch({type:'lock',name:'reader',active:expanded!==null})},[expanded]);
 useEffect(()=>{dispatch({type:'lock',name:'details',active:selected!==null||info})},[selected,info]);
 useEffect(()=>{dispatch({type:'lock',name:'catalog',active:catalog})},[catalog]);
 useEffect(()=>{dispatch({type:'lock',name:'inactive',active:!active});if(!active)setReceiving(false)},[active]);
 useEffect(()=>{
  if(!receiving||reduced||hidden||!active)return;
  if(state.received.sequence===times.length-1){setReceiving(false);return}
  const timer=setInterval(()=>dispatch({type:'receive',frame:soccerFrame(state.received.sequence+1,scope,includeFinal)}),4000);
  return()=>clearInterval(timer);
 },[receiving,reduced,hidden,active,state.received.sequence,scope]);
 const arrive=()=>{if(state.received.sequence<times.length-1)dispatch({type:'receive',frame:soccerFrame(state.received.sequence+1,scope,includeFinal)})};
 return {halfCompetitor,setHalfCompetitor,historyWindow,setHistoryWindow,matchHistoryAt,setMatchHistoryAt,includeFinal,times,historyOpen,setHistoryOpen,historyIndex,setHistoryIndex,historyFullScale,setHistoryFullScale,historyMemory,scope,state,dispatch,readerMemory,receiving,setReceiving,reduced,hidden,arrive,expanded,setExpanded,readerActive,setReaderActive,selected,setSelected,info,setInfo,catalog,setCatalog,large,setLarge};
}
export function SoccerArrivalControls({session:s}:{session:ReturnType<typeof useSoccerReadingSession>}){
 const end=s.state.received.sequence===s.times.length-1;
 return <details className="sr-arrival-controls"><summary>Recorded arrival controls</summary><div><span>Recorded arrivals · simulated timing</span><button onClick={s.arrive} disabled={end}>Receive next recorded update</button><button disabled={end||s.reduced} onClick={()=>s.setReceiving(!s.receiving)}>{s.receiving?'Stop arrivals':'Start arrivals'}</button><span>Received through {eventReaderTime.full(s.state.received.through,true)}{end?' · capture ended':''}</span></div></details>;
}
