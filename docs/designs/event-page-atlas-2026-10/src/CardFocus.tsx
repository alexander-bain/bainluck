import {rememberReaderControl,restoreReaderControl} from './readerControlFocus';
import {attachReaderSettling} from './readerSettling';
import {reconcileReaderSelection} from './readerSelection';
import {StoryCardActivation} from './StoryCardActivation';
import {readerCardWidth,readerCardOffset,readerIndexFromScroll,readerOpeningSelection,type CardFocusMemory} from './readerRail';
import {createContext,useContext,useEffect,useLayoutEffect,useRef,useState,useMemo,type ReactNode,type Dispatch,type SetStateAction} from 'react';
import {ChevronLeftIcon,ChevronRightIcon,EnterFullScreenIcon} from '@radix-ui/react-icons';
import * as Dialog from '@radix-ui/react-dialog';
import {BottomSheet,Carousel,MobileScroll} from './mobile';
import './cardFocus.css';

type ReaderInfoPanel={key:string;title?:string;content:ReactNode};
export const ReaderInfoContext=createContext<{setPanel:Dispatch<SetStateAction<ReaderInfoPanel|null>>}|null>(null);
const DisclosureContext=createContext(false);
export const ReaderDisclosureBoundary=DisclosureContext.Provider;

export function ExpandCard({label,onClick}:{label:string;onClick:()=>void}){
 const activate=useContext(StoryCardActivation);
 return <button className="cf-expand" aria-label={`Expand ${label}`} onClick={()=>{activate?.();onClick()}}><EnterFullScreenIcon/>Explore card</button>;
}
export type FocusCard={id:string;name:string;visual:ReactNode};
function FocusBody({cards,start,anchor,onClose,wide,large,returnLabel,readerTitle='Explore match cards',resumeAt,onActiveCardChange,memory,peekAdjacent=false,settleCards=true,refreshControl}:{cards:FocusCard[];start:string;anchor:ReactNode;onClose:()=>void;wide:boolean;large?:boolean;returnLabel?:string;readerTitle?:string;resumeAt?:string|null;onActiveCardChange?:(id:string)=>void;memory:CardFocusMemory;peekAdjacent?:boolean;settleCards?:boolean;refreshControl?:ReactNode}){
 const [infoPanel,setInfoPanel]=useState<ReaderInfoPanel|null>(null);
 const infoHost=useMemo(()=>({setPanel:setInfoPanel}),[]);
 const root=useRef<HTMLDivElement>(null);
 const order=cards.map(card=>card.id),orderKey=JSON.stringify(order);
 const [selection,setSelection]=useState<{order:string[];id:string|null}>(()=>readerOpeningSelection(order,start,resumeAt,memory.selection));
 const selectedID=reconcileReaderSelection(selection.order,selection.id,order);
 const active=selectedID===null?-1:order.indexOf(selectedID);
 useLayoutEffect(()=>{memory.selection={openingID:start,cardID:selectedID,order:[...order]}},[selectedID,orderKey,start,memory]);
 const requestedControl=useRef(memory.control),captureControl=useRef(memory.control===undefined);
 const rememberControl=(target:EventTarget|null)=>{
  if(!captureControl.current||selectedID===null||!root.current)return;
  const control=rememberReaderControl(root.current,target,selectedID);if(control)memory.control=control;
 };
 // Reconcile during render so no effect or accessibility tree sees a stale index.
 if(JSON.stringify(selection.order)!==orderKey||selection.id!==selectedID)setSelection({order,id:selectedID});
 const [width,setWidth]=useState(0);
 const positioned=useRef(false),activeRef=useRef(active),measuredWidth=useRef(0);
 activeRef.current=active;
 useEffect(()=>{if(selectedID!==null)onActiveCardChange?.(selectedID)},[selectedID,onActiveCardChange]);
 useLayoutEffect(()=>{
  const host=root.current!,scroller=host.querySelector<HTMLElement>('.cf-carousel')!,track=host.querySelector<HTMLElement>('.cf-track')!;
  const content=host.querySelectorAll<HTMLElement>('.cf-card-content')[active];
  if(!content)return;
  // Layout height stays in CSS pixels even when the device preview is scaled.
  const vertical=host.querySelector<HTMLElement>('.mobile-scroll')!,id=cards[active].id;
  const saved=memory.scrollTop[id]??0;let restoring=true;
  const remember=()=>{if(!restoring)memory.scrollTop[id]=vertical.scrollTop};
  vertical.addEventListener('scroll',remember,{passive:true});
  // A synchronous height write inside ResizeObserver can cause a layout feedback loop.
  // Coalesce to the next frame and only write when the measured height changes.
  let pendingFrame:number|null=null;
  const resize=new ResizeObserver(()=>{
   if(pendingFrame!==null)return;
   pendingFrame=requestAnimationFrame(()=>{
    pendingFrame=null;
    const css=getComputedStyle(track),height=`${content.offsetHeight+parseFloat(css.paddingTop)+parseFloat(css.paddingBottom)}px`;
    if(scroller.style.height!==height)scroller.style.height=height;
    if(restoring){vertical.scrollTop=saved;restoring=false}
   });
  });
  resize.observe(content);
  return()=>{remember();vertical.removeEventListener('scroll',remember);resize.disconnect();if(pendingFrame!==null)cancelAnimationFrame(pendingFrame)};
 },[selectedID,orderKey,memory]);
 useEffect(()=>{
  const host=root.current!,scroller=host.querySelector<HTMLElement>('.mobile-carousel')!;
  const resize=new ResizeObserver(()=>{const next=readerCardWidth(scroller.clientWidth,cards.length,peekAdjacent);if(next===measuredWidth.current)return;positioned.current=false;measuredWidth.current=next;setWidth(next)});
  const update=()=>{const card=host.querySelector<HTMLElement>('.cf-slide');if(card)setSelection(previous=>{const index=readerIndexFromScroll({left:scroller.scrollLeft,viewport:scroller.clientWidth,width:card.offsetWidth,count:cards.length,previous:Math.max(0,order.indexOf(previous.id??'')),positioned:positioned.current,peekAdjacent});const id=order[index]??null;return previous.id===id?previous:{order,id}})};
  scroller.addEventListener('scroll',update,{passive:true});resize.observe(scroller);
  return()=>{resize.disconnect();scroller.removeEventListener('scroll',update)};
 },[orderKey,peekAdjacent]);
 useLayoutEffect(()=>{if(width<=0)return;const scroller=root.current?.querySelector<HTMLElement>('.mobile-carousel');if(scroller){scroller.scrollLeft=readerCardOffset(activeRef.current,width);positioned.current=true}},[width,orderKey]);
 // Source Details unmounts this body. Restore the exact original action after
 // its closing layer leaves, without letting default dialog autofocus replace
 // the saved identity or scroll the independently retained card position.
 useLayoutEffect(()=>{
  const requested=requestedControl.current,host=root.current;
  if(!requested||!host||width<=0||selectedID===null)return;
  let frame:number|null=null,settle:number|null=null;
  const schedule=()=>{if(frame!==null)return;frame=requestAnimationFrame(()=>{
   frame=null;
   if(document.querySelector('[role="dialog"][data-state="closed"]'))return;
   settle=requestAnimationFrame(()=>{
    settle=null;
    if(restoreReaderControl(host,requested,selectedID)){
     requestedControl.current=undefined;captureControl.current=true;observer.disconnect();
    }
   });
  })};
  const observer=new MutationObserver(schedule);
  observer.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['data-state','inert','hidden']});
  schedule();
  return()=>{observer.disconnect();if(frame!==null)cancelAnimationFrame(frame);if(settle!==null)cancelAnimationFrame(settle)};
 },[selectedID,width,memory]);
 // The template's generic carousel intentionally coasts freely. A full-size
 // quantitative card must finish aligned after that motion stops, so its axis
 // and controls are not clipped between adjacent cards. Opt-in at the host;
 // never interrupt a live drag or the template's momentum frames.
 useEffect(()=>{
  if(!settleCards||width<=0)return;
  const rail=root.current?.querySelector<HTMLElement>('.mobile-carousel');if(!rail)return;
  return attachReaderSettling(rail,()=>positioned.current?readerCardOffset(Math.max(0,activeRef.current),width):null);
 },[settleCards,width,orderKey]);
 const move=(index:number)=>{
  root.current?.querySelector<HTMLElement>('.mobile-carousel')?.scrollTo({left:readerCardOffset(index,width),behavior:'instant'});
  setSelection({order,id:order[index]??null});
 };
 return <ReaderInfoContext.Provider value={infoHost}><div ref={root} onFocusCapture={e=>rememberControl(e.target)} onClickCapture={e=>rememberControl(e.target)} className={`cf-view ${wide?'cf-wide':''} ${large?'cf-large':''} ${cards.length===1?'cf-single':''}`} style={wide?{height:'min(78vh, 830px)'}:undefined}>
  <header className="cf-header" inert={infoPanel!==null}><button className="cf-back" aria-label={returnLabel??'Back to chart'} onClick={onClose}><ChevronLeftIcon/><span>{wide?(returnLabel??'Back to chart'):'Back'}</span></button><div className="cf-anchor">{anchor}</div>{refreshControl}</header>
  <div className="cf-body" inert={infoPanel!==null}><MobileScroll>{cards.length===0&&<section className="cf-empty" role="status"><h2>No cards available in this update</h2><p>Return to the match to explore all props.</p></section>}<Carousel ariaLabel={readerTitle} className="cf-carousel" contentClassName="cf-track">{cards.map((card,i)=><section key={card.id} className="cf-slide pr-feed" style={{width:width||300}} aria-label={card.name} inert={i!==active}><div className="cf-card-content">{card.visual}</div></section>)}</Carousel></MobileScroll></div>
  {cards.length>1&&<footer className="cf-footer" inert={infoPanel!==null}><div className="cf-navigation"><button aria-label="Previous expanded card" disabled={active===0} onClick={()=>move(active-1)}><ChevronLeftIcon/></button><div aria-live="polite"><b>{cards[active]?.name}</b><span>{active+1} of {cards.length} · Swipe to explore</span></div><button aria-label="Next expanded card" disabled={active===cards.length-1} onClick={()=>move(active+1)}><ChevronRightIcon/></button></div>{cards.length<=12&&<div className="cf-dots" aria-hidden="true">{cards.map((c,i)=><i key={c.id} data-active={i===active}/>)}</div>}</footer>}
 {infoPanel&&<section className="cf-info-panel" role="region" aria-label={infoPanel.title??"About this game"}><h2>{infoPanel.title??"About this game"}</h2><MobileScroll>{infoPanel.content}</MobileScroll></section>}
 </div></ReaderInfoContext.Provider>;
}
export function CardFocus({start,cards,anchor,onClose,wide,large,returnLabel,readerTitle='Explore match cards',resumeAt,onActiveCardChange,suspended=false,memory,peekAdjacent=false,settleCards=true,refreshControl}:{start:string|null;cards:FocusCard[];anchor:ReactNode;onClose:()=>void;wide:boolean;large?:boolean;returnLabel?:string;readerTitle?:string;resumeAt?:string|null;onActiveCardChange?:(id:string)=>void;suspended?:boolean;memory?:CardFocusMemory;peekAdjacent?:boolean;settleCards?:boolean;refreshControl?:ReactNode}){
 const localMemory=useRef<CardFocusMemory>({scrollTop:{}});
 const disclosureOpen=useContext(DisclosureContext);
 const retainedMemory=memory??localMemory.current;
 useLayoutEffect(()=>{if(start===null){delete retainedMemory.control;delete retainedMemory.selection}},[start,retainedMemory]);
 if(suspended||disclosureOpen)return null;
 const body=start===null?null:<FocusBody key={start} cards={cards} start={start} anchor={anchor} onClose={onClose} wide={wide} large={large} returnLabel={returnLabel} readerTitle={readerTitle} resumeAt={resumeAt} onActiveCardChange={onActiveCardChange} memory={retainedMemory} peekAdjacent={peekAdjacent} settleCards={settleCards} refreshControl={refreshControl}/>;
 return wide?<Dialog.Root open={start!==null} onOpenChange={v=>{if(!v)onClose()}}><Dialog.Portal><Dialog.Overlay className="cf-overlay"/><Dialog.Content className="cf-dialog" aria-describedby={undefined}><Dialog.Title className="sr-only">{readerTitle}</Dialog.Title>{body}</Dialog.Content></Dialog.Portal></Dialog.Root>:<BottomSheet open={start!==null} onOpenChange={v=>{if(!v)onClose()}} title={readerTitle} snap={.94}>{body}</BottomSheet>;
}
