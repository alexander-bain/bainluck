import {reconcileReaderSelection} from './readerSelection.ts';
import {createStoryStream,holdStories,receiveStoryOrder,resumeStories,advanceStory,type StoryStreamState} from './storyStreamState.ts';

/** A coherent presentation frame. Source-specific timestamps remain inside payload. */
export interface StoryFrame<T> {scope:string;sequence:number;through:string;order:string[];payload:T}
export interface StoryReadingFrame<T> {
 displayed:StoryFrame<T>;received:StoryFrame<T>;stream:StoryStreamState;
 allowed:string[];locks:string[];
}
export type StoryReadingAction<T>=
 | {type:'receive';frame:StoryFrame<T>}
 | {type:'inspect';frame:StoryFrame<T>}
 | {type:'hold'} | {type:'resume';manual?:boolean}
 | {type:'refresh';selected?:string|null}
 | {type:'lock';name:string;active:boolean}
 | {type:'move';delta:number;automatic?:boolean}
 | {type:'select';id:string};

function valid<T>(frame:StoryFrame<T>,scope:string,allowed:string[]){
 return frame.scope===scope&&Number.isSafeInteger(frame.sequence)&&frame.sequence>=0
  &&Number.isFinite(Date.parse(frame.through))
  &&frame.order.every(id=>allowed.includes(id))&&new Set(frame.order).size===frame.order.length;
}
export function createStoryReadingFrame<T>(frame:StoryFrame<T>,allowed:string[]):StoryReadingFrame<T>{
 if(!valid(frame,frame.scope,allowed)||!frame.scope)throw new Error('Invalid initial story frame');
 const initial=structuredClone(frame);
 return {displayed:initial,received:initial,stream:holdStories(createStoryStream(frame.order)),allowed:[...allowed],locks:[]};
}
export function storyReadingReducer<T>(state:StoryReadingFrame<T>,action:StoryReadingAction<T>):StoryReadingFrame<T>{
 switch(action.type){
  case 'hold':return state.stream.held?state:{...state,stream:holdStories(state.stream)};
  case 'lock':{
   const locks=action.active?[...new Set([...state.locks,action.name])]:state.locks.filter(name=>name!==action.name);
   if(locks.join('|')===state.locks.join('|'))return state;
   return {...state,locks,stream:action.active?holdStories(state.stream):state.stream};
  }
  case 'receive':{
   const frame=action.frame;
   if(!valid(frame,state.received.scope,state.allowed)||frame.sequence<=state.received.sequence
    ||Date.parse(frame.through)<Date.parse(state.received.through))return state;
   const received=structuredClone(frame),stream=receiveStoryOrder(state.stream,received.order);
   return {...state,received,displayed:stream.held?state.displayed:received,stream};
  }
  case 'refresh':{
   // A deliberate refresh may occur within the reader, never through a detail,
   // background, inactive-page or catalog lock. It never restarts auto-advance.
   if(state.locks.some(lock=>lock!=='reader'))return state;
   const order=[...state.received.order];
   const selection=action.selected&&state.stream.order.includes(action.selected)?action.selected:state.stream.active;
   const active=reconcileReaderSelection(state.stream.order,selection,order);
   return {...state,displayed:state.received,stream:{order,active,held:true,pending:null}};
  }
  case 'resume':{
   if(state.locks.length)return state;
   const stream=resumeStories(receiveStoryOrder(state.stream,state.received.order));
   return {...state,displayed:state.received,stream:action.manual?holdStories(stream):stream};
  }
  case 'inspect':{
   if(state.locks.length||!valid(action.frame,state.received.scope,state.allowed)
    ||action.frame.sequence>state.received.sequence||Date.parse(action.frame.through)>Date.parse(state.received.through))return state;
   const displayed=structuredClone(action.frame);
   let stream=resumeStories(receiveStoryOrder({...state.stream,held:false,pending:null},displayed.order));
   stream=receiveStoryOrder(holdStories(stream),state.received.order);
   return {...state,displayed,stream};
  }
  case 'move':return state.locks.length?state:{...state,stream:advanceStory(state.stream,action.delta,!action.automatic)};
  case 'select':return state.locks.length||!state.stream.order.includes(action.id)?state:{...state,stream:{...holdStories(state.stream),active:action.id}};
 }
}
