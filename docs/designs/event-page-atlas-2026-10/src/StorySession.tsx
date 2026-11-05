import type {CardFocusMemory} from './readerRail';
import {createContext,useCallback,useContext,useRef,useState,type Dispatch,type ReactNode,type SetStateAction} from 'react';
const Context=createContext<{memories:Record<string,CardFocusMemory>;values:Record<string,unknown>;setValues:Dispatch<SetStateAction<Record<string,unknown>>>}|null>(null);
export function StorySessionProvider({children}:{children:ReactNode}){
 const memories=useRef<Record<string,CardFocusMemory>>({}).current;
 const [values,setValues]=useState<Record<string,unknown>>({});
 return <Context.Provider value={{memories,values,setValues}}>{children}</Context.Provider>;
}
/** Page-owned card choices survive phone/wide reconstruction. Retained disclosure records stay distinct from live probability eligibility. */
export function useStoryState<T>(event:string,field:string,initial:T|(()=>T)):[T,Dispatch<SetStateAction<T>>]{
 const store=useContext(Context);if(!store)throw new Error('Missing story session');
 const fallback=useRef<T>(typeof initial==='function'?(initial as ()=>T)():initial).current;
 const key=event+':'+field;
 const set=useCallback<Dispatch<SetStateAction<T>>>(next=>store.setValues(old=>{
  const prior=(Object.hasOwn(old,key)?old[key]:fallback) as T;
  const value=typeof next==='function'?(next as (v:T)=>T)(prior):next;
  return Object.is(prior,value)&&Object.hasOwn(old,key)?old:{...old,[key]:value};
 }),[store.setValues,key,fallback]);
 return [(Object.hasOwn(store.values,key)?store.values[key]:fallback) as T,set];
}
/** Scenario control outside product chrome; supplies orders without inventing a ranking service. */
export function StoryOrderControl(){
 const [order,setOrder]=useStoryState('preview','priority','original');
 return <label>Story order simulation<select aria-label="Story order simulation" value={order} onChange={e=>setOrder(e.target.value)}><option value="original">Editorial order</option><option value="reverse">Reversed priority</option><option value="none">No ranked stories</option></select></label>;
}

/** Layout-owned readers share a stable scroll memory under the page session. */
export function useStoryReaderMemory(key:string){
 const store=useContext(Context);if(!store)throw new Error('Missing story session');
 return store.memories[key]??(store.memories[key]={scrollTop:{}});
}
