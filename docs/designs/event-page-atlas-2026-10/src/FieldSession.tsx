import {createContext,useCallback,useContext,useState,type ReactNode,type Dispatch,type SetStateAction} from 'react';
import {emptyFieldSession,type FieldReadingSession} from './fieldFocus';
type Store={sessions:Record<string,FieldReadingSession>;setSessions:Dispatch<SetStateAction<Record<string,FieldReadingSession>>>};
const Context=createContext<Store|null>(null);
export function FieldSessionProvider({children}:{children:ReactNode}){
 const [sessions,setSessions]=useState<Record<string,FieldReadingSession>>({});
 return <Context.Provider value={{sessions,setSessions}}>{children}</Context.Provider>;
}
export function useFieldSession(key:string){
 const store=useContext(Context);if(!store)throw new Error('Field session provider missing');
 const {sessions,setSessions}=store;
 const setAnchors=useCallback<Dispatch<SetStateAction<FieldReadingSession['anchors']>>>(next=>setSessions(old=>{const s=old[key]??emptyFieldSession;return {...old,[key]:{...s,anchors:typeof next==='function'?next(s.anchors):next}}}),[key,setSessions]);
 const setFocus=useCallback((focus:string|null)=>setSessions(old=>({...old,[key]:{...(old[key]??emptyFieldSession),focus}})),[key,setSessions]);
 const setActiveCard=useCallback((activeCard:string)=>setSessions(old=>{const s=old[key]??emptyFieldSession;return s.activeCard===activeCard?old:{...old,[key]:{...s,activeCard}}}),[key,setSessions]);
 return {...(sessions[key]??emptyFieldSession),setAnchors,setFocus,setActiveCard};
}
