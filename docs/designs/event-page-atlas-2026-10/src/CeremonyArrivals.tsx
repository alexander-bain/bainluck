import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {ceremonyArrivalCutoffs,ceremonyArrivalFrame,createCeremonyArrival,ceremonyArrivalReducer,type CeremonyArrivalPayload} from './ceremonyArrivalFrame';
import type {StoryReadingAction,StoryReadingFrame} from './storyReadingFrame';
import type {AwardPhase} from './ceremonyEvidence';
import type {StoryStreamControl} from './StoryStream';
import {eventReaderTime as clock} from './eventReaderTime';
export function useCeremonyArrivals(){
 const [phase,setPhase]=useState<AwardPhase>('final');
 const [frames,setFrames]=useState(()=>({before:createCeremonyArrival('before'),final:createCeremonyArrival('final')}));
 const state=frames[phase];
 const dispatch=useCallback((action:StoryReadingAction<CeremonyArrivalPayload>)=>setFrames(old=>{
  const next=ceremonyArrivalReducer(old[phase],action);return next===old[phase]?old:{...old,[phase]:next};
 }),[phase]);
 const actions=useMemo(()=>({hold:()=>dispatch({type:'hold'}),resume:(manual:boolean)=>dispatch({type:'resume',manual}),move:(delta:number,manual:boolean)=>dispatch({type:'move',delta,automatic:!manual}),select:(id:string)=>dispatch({type:'select',id})}),[dispatch]);
 const control:StoryStreamControl=useMemo(()=>({state:state.stream,...actions}),[state.stream,actions]);
 const receiveNext=useCallback(()=>setFrames(old=>{
  const final=old.final,index=Math.min(ceremonyArrivalCutoffs.length-1,final.received.sequence+1);
  const next=ceremonyArrivalReducer(final,{type:'receive',frame:ceremonyArrivalFrame(index)});return next===final?old:{...old,final:next};
 }),[]);
 const reset=useCallback(()=>setFrames(old=>old.final.locks.length?old:{...old,final:createCeremonyArrival('final',false)}),[]);
 return {phase,setPhase,state,dispatch,control,receiveNext,reset,total:ceremonyArrivalCutoffs.length};
}
export type CeremonyArrivals=ReturnType<typeof useCeremonyArrivals>;
/** Outside product chrome: replay real retained source observations, with simulated delivery timing. */
export function CeremonyArrivalControls({session}:{session:CeremonyArrivals}){
 const timer=useRef<ReturnType<typeof setTimeout>|null>(null),[armed,setArmed]=useState(false);
 useEffect(()=>()=>{if(timer.current)clearTimeout(timer.current)},[]);
 const before=session.phase==='before',last=session.state.received.sequence>=session.total-1;
 return <div className="aw-arrival-preview" aria-label="Recorded probability arrival simulation"><span>Retained trade arrivals · delivery timing simulated</span><button disabled={before||session.state.locks.length>0||armed} onClick={session.reset}>Earlier retained probabilities</button><button disabled={before||last||armed} onClick={session.receiveNext}>Receive next probabilities</button><button disabled={before||last||armed} onClick={()=>{setArmed(true);timer.current=setTimeout(()=>{session.receiveNext();setArmed(false);timer.current=null},4000)}}>{armed?'Arrival armed':'Receive in 4 seconds'}</button><span>{before?'Before-day view':`${session.state.received.sequence+1} of ${session.total} retained windows`}</span></div>;
}
export function CeremonyUpdateDock({state,onUpdate}:{state:StoryReadingFrame<CeremonyArrivalPayload>;onUpdate:()=>void}){
 const pending=state.received.sequence>state.displayed.sequence;
 return <div className="aw-update-dock" role="status" aria-label="Recorded probability reading"><div><b>Historical probabilities</b><span>Trades through {clock.full(state.displayed.through)}</span></div>{pending&&<div><span>New recorded probabilities ready</span><button onClick={onUpdate} disabled={state.locks.length>0}>Update cards</button></div>}</div>;
}
