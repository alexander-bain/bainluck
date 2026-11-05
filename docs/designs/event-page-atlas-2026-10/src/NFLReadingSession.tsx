import type {RetainedHistorySelection} from './historyObservation';
import {eventReaderTime} from './eventReaderTime.ts';
import type {CardFocusMemory} from './readerRail';
import {advanceForecastClock,nflForecastPresentation} from './nflForecastValidity';
import {useEffect,useReducer,useRef,useState} from 'react';
import {nflReadingFrame,nflReadingMoments} from './nflReadingFrame';
import {createStoryReadingFrame,storyReadingReducer} from './storyReadingFrame';
import type {nflContext} from './nflReplay';
import {useCatalogPageSession} from './useCatalogPageSession';
import {adaptFinalRows,type ArchivedFinalRow} from './finalCatalogEvidence';
import flags from './finalCatalogFlags.json';
import rows from './markets.json';
import profiles from './profiles.json';

const catalogRows=adaptFinalRows(rows as ArchivedFinalRow[],flags);
export function useNFLReadingSession(active:boolean){
 const readerMemory=useRef<CardFocusMemory>({scrollTop:{}}).current;
 const scope=useRef('nfl:14780549:recorded:'+crypto.randomUUID()).current;
 const [state,dispatch]=useReducer(storyReadingReducer<ReturnType<typeof nflContext>>,undefined,
  ()=>createStoryReadingFrame(nflReadingFrame(0,scope),['finish','rush','touchdowns']));
 const [forecastClock,tickForecastClock]=useReducer(advanceForecastClock,{scope,through:nflReadingMoments[0].at});
 const forecast=nflForecastPresentation(state,forecastClock);
 const [scheduledExpiry,setScheduledExpiry]=useState<string|null>(null);
 const [forecastDetailKey,setForecastDetailKey]=useState<string|null>(null);
 useEffect(()=>{if(!scheduledExpiry)return;const timer=setTimeout(()=>{tickForecastClock({scope,through:scheduledExpiry});setScheduledExpiry(null)},4000);return()=>clearTimeout(timer)},[scheduledExpiry,scope]);
 useEffect(()=>{if(!active)setScheduledExpiry(null)},[active]);
 const catalogSession=useCatalogPageSession('14780549','completed',false,catalogRows);
 const [compact,setCompact]=useState(false);
 const [historySelection,setHistorySelection]=useState<RetainedHistorySelection|null>(null);
 const [inspecting,setInspecting]=useState(false);
 useEffect(()=>{dispatch({type:'lock',name:'history-inspection',active:inspecting})},[inspecting]);
 const [scheduledArrival,setScheduledArrival]=useState<number|null>(null);
 useEffect(()=>{if(scheduledArrival===null)return;const timer=setTimeout(()=>{dispatch({type:'receive',frame:nflReadingFrame(scheduledArrival,scope)});setScheduledArrival(null)},4000);return()=>clearTimeout(timer)},[scheduledArrival,scope]);
 useEffect(()=>{if(!active)setScheduledArrival(null)},[active]);
 const [receiving,setReceiving]=useState(false),[reduced,setReduced]=useState(false),[hidden,setHidden]=useState(document.hidden);
 const [expanded,setExpanded]=useState<string|null>(null),[readerActive,setReaderActive]=useState<string|null>(null);
 const [returnOrigin,setReturnOrigin]=useState<string|null>(null);
 const [details,setDetails]=useState<string|null>(null),[info,setInfo]=useState(false),[catalog,setCatalog]=useState(false),[large,setLarge]=useState(false);
 const [rushKey,setRushKey]=useState(profiles[0].points.find(p=>p.x===profiles[0].focus)!.row_key);
 useEffect(()=>{const media=matchMedia('(prefers-reduced-motion: reduce)'),update=()=>{setReduced(media.matches);if(media.matches)dispatch({type:'hold'})};update();media.addEventListener('change',update);return()=>media.removeEventListener('change',update)},[]);
 useEffect(()=>{const update=()=>{setHidden(document.hidden);dispatch({type:'lock',name:'background',active:document.hidden})};update();document.addEventListener('visibilitychange',update);return()=>document.removeEventListener('visibilitychange',update)},[]);
 useEffect(()=>{dispatch({type:'lock',name:'reader',active:expanded!==null})},[expanded]);
 useEffect(()=>{dispatch({type:'lock',name:'details',active:details!==null||info})},[details,info]);
 useEffect(()=>{dispatch({type:'lock',name:'catalog',active:catalog})},[catalog]);
 useEffect(()=>{dispatch({type:'lock',name:'inactive',active:!active});if(!active)setReceiving(false)},[active]);
 useEffect(()=>{
  if(!receiving||reduced||hidden||!active)return;
  if(state.received.sequence===nflReadingMoments.length-1){setReceiving(false);return}
  const timer=setInterval(()=>dispatch({type:'receive',frame:nflReadingFrame(state.received.sequence+1,scope)}),4000);
  return()=>clearInterval(timer);
 },[receiving,reduced,hidden,active,state.received.sequence,scope]);
 const arrive=()=>{if(state.received.sequence<nflReadingMoments.length-1)dispatch({type:'receive',frame:nflReadingFrame(state.received.sequence+1,scope)})};
 return {historySelection,setHistorySelection,inspecting,setInspecting,compact,setCompact,scope,state,dispatch,readerMemory,forecast,forecastClock,tickForecastClock,scheduledExpiry,setScheduledExpiry,forecastDetailKey,setForecastDetailKey,catalogSession,receiving,setReceiving,scheduledArrival,setScheduledArrival,reduced,hidden,arrive,expanded,setExpanded,readerActive,setReaderActive,returnOrigin,setReturnOrigin,details,setDetails,info,setInfo,catalog,setCatalog,large,setLarge,rushKey,setRushKey};
}
export function NFLArrivalControls({session:s}:{session:ReturnType<typeof useNFLReadingSession>}){
 const end=s.state.received.sequence===nflReadingMoments.length-1;
 const expiry=s.state.displayed.payload.projection?.valid_until;
 const canExpire=!!expiry&&!!s.forecast.context.projection;
 return <details className="sr-arrival-controls"><summary>Football replay controls</summary><div><span>Recorded arrivals · simulated timing</span><button aria-pressed={s.compact} onClick={()=>s.setCompact(!s.compact)}>{s.compact?'Restore standard phone content':'Test 375 × 583 phone content'}</button><button onClick={s.arrive} disabled={end}>Receive next football update</button><button disabled={end||s.scheduledArrival!==null} onClick={()=>s.setScheduledArrival(s.state.received.sequence+1)}>{s.scheduledArrival!==null?'Update scheduled':'Receive next update in 4 seconds'}</button><button disabled={end||s.reduced} onClick={()=>s.setReceiving(!s.receiving)}>{s.receiving?'Stop arrivals':'Start arrivals'}</button><span>Received through {eventReaderTime.full(s.state.received.through,true)}{end?' · capture ended':nflReadingMoments[s.state.received.sequence].kind==='expiry'?' · forecast validity boundary':''}</span><span>Validity clock · {eventReaderTime.full(s.forecast.horizon,true)}</span><button disabled={!canExpire||!!s.scheduledExpiry} onClick={()=>{if(expiry)s.tickForecastClock({scope:s.scope,through:expiry})}}>Advance clock to forecast expiry</button><button disabled={!canExpire||!!s.scheduledExpiry} onClick={()=>{if(expiry)s.setScheduledExpiry(expiry)}}>{s.scheduledExpiry?'Clock advance scheduled':'Advance clock in 4 seconds'}</button><span>Clock controls deliver no new match data.</span></div></details>;
}
