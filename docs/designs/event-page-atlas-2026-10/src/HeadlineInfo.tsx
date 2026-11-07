import {useRef,useEffect,useContext,type ReactNode} from 'react';
import {useStoryState} from './StorySession';
import {ReaderInfoContext} from './CardFocus';
import './headlineInfo.css';
import * as Dialog from '@radix-ui/react-dialog';
import {InfoCircledIcon} from '@radix-ui/react-icons';
import {BottomSheet,useKeyboard} from './mobile';

/** Secondary provenance stays one tap away; meaning and reliability stay inline. */
export function HeadlineInfo({scopeKey,wide,large=false,children,title="About this game",triggerLabel="About these probabilities and scores"}:{scopeKey:string;wide:boolean;large?:boolean;children:ReactNode;title?:string;triggerLabel?:string}){
 const [open,setOpen]=useStoryState('headline-info',scopeKey,false);const keyboard=useKeyboard();const readerHost=useContext(ReaderInfoContext);
 const triggerRef=useRef<HTMLButtonElement>(null);const wasOpen=useRef(false);
 useEffect(()=>{const shouldRestore=wasOpen.current&&!open;wasOpen.current=open;if(!shouldRestore)return;const id=requestAnimationFrame(()=>triggerRef.current?.focus({preventScroll:true}));return()=>cancelAnimationFrame(id)},[open]);
 const trigger=<button ref={triggerRef} className="headline-info-button" aria-label={triggerLabel} aria-haspopup="dialog" aria-expanded={open} onClick={()=>{keyboard.hide();setOpen(true)}}><InfoCircledIcon/></button>;
 const content=<div className={`headline-info-content ${large?'large-text':''}`}><button className="sheet-done" onClick={()=>setOpen(false)}>Done</button>{children}</div>;
 useEffect(()=>{if(!readerHost)return;if(open)readerHost.setPanel({key:scopeKey,title,content:<ReaderInfoContent large={large} onClose={()=>setOpen(false)}>{children}</ReaderInfoContent>});else readerHost.setPanel(old=>old?.key===scopeKey?null:old);return()=>readerHost.setPanel(old=>old?.key===scopeKey?null:old)},[readerHost,open,scopeKey,large,children,setOpen,title]);
 if(readerHost)return trigger;
 return <>{trigger}{wide?<Dialog.Root open={open} onOpenChange={setOpen}><Dialog.Portal><Dialog.Overlay className="atlas-modal-overlay headline-info-overlay"/><Dialog.Content className="atlas-dialog headline-info-dialog" aria-describedby={undefined} onCloseAutoFocus={e=>{e.preventDefault();triggerRef.current?.focus({preventScroll:true})}}><Dialog.Title>{title}</Dialog.Title>{content}</Dialog.Content></Dialog.Portal></Dialog.Root>:<BottomSheet open={open} onOpenChange={setOpen} title={title}>{content}</BottomSheet>}</>;
}

function ReaderInfoContent({large,onClose,children}:{large:boolean;onClose:()=>void;children:ReactNode}){
 const done=useRef<HTMLButtonElement>(null);
 useEffect(()=>{done.current?.focus({preventScroll:true})},[]);
 return <div className={`headline-info-content ${large?'large-text':''}`}><button ref={done} className="sheet-done" onClick={onClose}>Done</button>{children}</div>;
}
