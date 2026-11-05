import {storyCardVisibility} from './storyCardVisibility';
import {storyRankedIDs} from './storyRankedIDs';
import {pinnedStoryInset} from './pinnedStoryInset';
import {StoryCardActivation} from './StoryCardActivation';
import {useCallback,useEffect,useRef,useState,type ReactNode} from 'react';
import {ChevronLeftIcon,ChevronRightIcon,PauseIcon,PlayIcon} from '@radix-ui/react-icons';
import {ChartVisibility} from './ChartVisibility';
import {useStoryState} from './StorySession';
import {advanceStory,canAdvanceStories,createStoryStream,selectStory,holdStories,receiveStoryOrder,resumeStories,type StoryStreamState} from './storyStreamState';
import './storyStream.css';
export interface StoryStreamControl {state:StoryStreamState;hold:()=>void;resume:(manual:boolean)=>void;move:(delta:number,manual:boolean)=>void;select:(id:string)=>void}
export interface StreamCard {id:string;name:string;visual:ReactNode}
export function StoryStream({event,cards,readerOpen,wide,subject="game",basis,eyebrow,topOccluder,requireCardVisibility=false,resumeAfterScroll=false,rankedIDs,control}:{event:string;cards:StreamCard[];readerOpen:boolean;wide:boolean;subject?:"game"|"fight"|"match"|"race"|"awards"|"day";basis?:string;eyebrow?:string;topOccluder?:string;requireCardVisibility?:boolean;resumeAfterScroll?:boolean;rankedIDs?:readonly string[];control?:StoryStreamControl}){
 const [historyReaderOpen]=useStoryState(event,'full-probability-history',false);
 const anyReaderOpen=readerOpen||historyReaderOpen;
 const admitted=storyRankedIDs(cards.map(c=>c.id),rankedIDs);
 const [localState,setState]=useStoryState(event,'stream',()=>createStoryStream(admitted));
 const state=control?.state??localState;
 const pause=useCallback(()=>{if(control)control.hold();else setState(holdStories)},[control?.hold,setState]);
 const move=useCallback((delta:number,manual:boolean)=>{if(control)control.move(delta,manual);else setState(s=>advanceStory(s,delta,manual))},[control?.move,setState]);
 const [visible,setVisible]=useState(false),[watched,setWatched]=useState(false),[hidden,setHidden]=useState(document.hidden),[reduced,setReduced]=useState(()=>matchMedia('(prefers-reduced-motion: reduce)').matches);
 const root=useRef<HTMLElement>(null);
 const [scrolling,setScrolling]=useState(false),[pointerDown,setPointerDown]=useState(false);
 const scrollIdle=useRef<ReturnType<typeof setTimeout>|null>(null);
 const suspendScroll=useCallback(()=>{
  if(!resumeAfterScroll){pause();return;}
  setScrolling(true);if(scrollIdle.current!==null)clearTimeout(scrollIdle.current);
  scrollIdle.current=setTimeout(()=>{scrollIdle.current=null;setScrolling(false)},180);
 },[pause,resumeAfterScroll]);
 useEffect(()=>{
  const release=()=>setPointerDown(false);
  window.addEventListener('pointerup',release);window.addEventListener('pointercancel',release);
  return()=>{window.removeEventListener('pointerup',release);window.removeEventListener('pointercancel',release);if(scrollIdle.current!==null)clearTimeout(scrollIdle.current)};
 },[]);
 const [priority]=useStoryState('preview','priority','original');
 const ranked=priority==='none'?[]:priority==='reverse'?[...admitted].reverse():admitted;
 const orderKey=ranked.join('|');
 useEffect(()=>{if(!control)setState(s=>receiveStoryOrder(s,orderKey?orderKey.split('|'):[]))},[orderKey,setState,!!control]);
 useEffect(()=>{
  const host=root.current!,target=requireCardVisibility?host.querySelector('.story-stream-stage')??host:host;
  const scroller=host.closest('.mobile-scroll, .wide-stage')??document;
  const occluder=topOccluder?host.parentElement?.querySelector<HTMLElement>(topOccluder):null;
  let observer:IntersectionObserver;
  const observe=()=>{
   observer?.disconnect();
   // Opaque pinned headers cannot count as watched content.
   const top=occluder?pinnedStoryInset(parseFloat(getComputedStyle(occluder).top),occluder.offsetHeight):0;
   observer=new IntersectionObserver(entries=>{const next=storyCardVisibility(entries[0],requireCardVisibility);setVisible(next.visible);setWatched(next.watched)},{root:occluder&&scroller instanceof Element?scroller:null,rootMargin:`-${top}px 0px 0px 0px`,threshold:requireCardVisibility?[0,.55]:.15});
   observer.observe(target);
  };
  observe();
  const resize=occluder?new ResizeObserver(observe):null;if(occluder)resize?.observe(occluder);
  const onVisibility=()=>{setHidden(document.hidden);if(document.hidden)pause()};
  const media=matchMedia('(prefers-reduced-motion: reduce)');const onMotion=()=>{setReduced(media.matches);if(media.matches)pause()};
  const onScroll=suspendScroll;
  document.addEventListener('visibilitychange',onVisibility);media.addEventListener('change',onMotion);scroller.addEventListener('scroll',onScroll,{passive:true});
  return()=>{observer.disconnect();resize?.disconnect();document.removeEventListener('visibilitychange',onVisibility);media.removeEventListener('change',onMotion);scroller.removeEventListener('scroll',onScroll)};
 },[pause,suspendScroll,requireCardVisibility,topOccluder,requireCardVisibility?state.active:null]);
 useEffect(()=>{if(anyReaderOpen)pause()},[anyReaderOpen,pause]);
 const running=canAdvanceStories(state,{visible:requireCardVisibility?watched:visible,hidden,reduced,readerOpen:anyReaderOpen,scrolling,pointerDown});
 useEffect(()=>{if(!running)return;const timer=setInterval(()=>move(1,false),10000);return()=>clearInterval(timer)},[running,move]);
 const index=state.order.indexOf(state.active??''),active=cards.find(c=>c.id===state.active);
 const shown=active;
 const manualAction=reduced||state.order.length<2,showsPlayback=state.order.length>1||state.pending!==null;
 const renderCard=(card:StreamCard)=><StoryCardActivation.Provider value={()=>{if(control)control.select(card.id);else setState(s=>selectStory(s,card.id))}}><ChartVisibility key={card.id} visible={visible}>{card.visual}</ChartVisibility></StoryCardActivation.Provider>;
 const companion=cards.find(c=>c.id===state.order[(index+1)%state.order.length]);
 return <section ref={root} className={`story-stream ${wide?'story-stream-wide':''}`} aria-label="Visual story stream" data-render-visible={visible} data-card-watched={watched}>
  <header className="story-stream-controls"><div><span className="eyebrow">{eyebrow??`THE ${subject.toUpperCase()} IN PROBABILITIES`}</span><h3>{subject==='game'?'Explore the story':`Explore the ${subject}`}</h3></div>{showsPlayback&&<button className="story-stream-play" aria-label={manualAction?(state.pending!==null?'Apply story updates':'Manual story browsing'):state.held?'Resume story stream':'Pause story stream'} disabled={anyReaderOpen||(reduced&&state.pending===null)||(state.order.length<2&&state.pending===null)} onClick={()=>{if(anyReaderOpen)return;if(control){if(manualAction||state.held)control.resume(manualAction);else control.hold()}else setState(reduced?s=>holdStories(resumeStories(s)):manualAction||state.held?resumeStories:holdStories)}}>{state.held?<PlayIcon/>:<PauseIcon/>}{manualAction?(state.pending!==null?'Apply updates':'Manual'):state.held?'Resume':'Pause'}</button>}</header>
  <div className="story-stream-status" aria-live="polite"><span>{!shown?'Browse every original in All props':state.order.length===1?'Explore this card at your pace':reduced?'Reduced motion · browse at your pace':state.held?'Paused · take your time':'Cards advance when you’re watching'}</span>{state.pending!==null&&<span className="story-stream-pending">New order ready · {manualAction?'Apply updates':'Resume to apply'}</span>}</div>
  {shown?<><div className="story-stream-stage" onPointerDownCapture={e=>{if(!resumeAfterScroll){pause();return;}setPointerDown(true);if((e.target as Element).closest('button,input,select,textarea,a,[role=button]'))pause()}} onClickCapture={pause} onWheelCapture={e=>{if(!resumeAfterScroll||Math.abs(e.deltaX)>Math.abs(e.deltaY))pause();else suspendScroll()}} onFocusCapture={pause} onPointerEnter={e=>{if(!resumeAfterScroll&&e.pointerType==='mouse')pause()}}>
   {renderCard(shown)}
   {wide&&state.order.length>1&&companion&&<div className="story-stream-companion"><span className="eyebrow">UP NEXT</span>{renderCard(companion)}</div>}
  </div>{state.order.length>1&&<footer className="story-stream-navigation"><button aria-label="Previous story card" onClick={()=>move(-1,true)} disabled={state.order.length<2}><ChevronLeftIcon/></button><div><b>{shown.name}</b><span>{index+1} of {state.order.length}</span></div><button aria-label="Next story card" onClick={()=>move(1,true)} disabled={state.order.length<2}><ChevronRightIcon/></button></footer>}
  {state.order.length>1&&<div className="story-stream-next">Next: {cards.find(c=>c.id===state.order[(index+1)%state.order.length])?.name}</div>}</>:<p className="story-stream-empty">No stories in this order. Every original prop is still in All props.</p>}
  <p className="story-stream-basis">{basis??`Recorded ${subject} · editorial card order`}</p>
 </section>;
}
