import {createContext,useCallback,useContext,useState,type ReactNode,type SetStateAction} from 'react';
import type {CatalogAnchor} from './catalogSelection';
import type {CatalogEvidenceRow} from './probabilityPresentation';
interface ReaderSession{anchors:Record<string,CatalogAnchor<CatalogEvidenceRow>>;catalog:boolean;large:boolean;searchOpen:boolean;query:string;category:string;limit:number;focus:string|null;activeCard:string|null}
const initial=(key:string):ReaderSession=>({anchors:{},catalog:key==='aflw-refresh',large:false,searchOpen:false,query:'',category:'All',limit:12,focus:null,activeCard:null});
const Context=createContext<{sessions:Record<string,ReaderSession>;setSessions:React.Dispatch<SetStateAction<Record<string,ReaderSession>>>}|null>(null);
export function CatalogReaderSessionProvider({children}:{children:ReactNode}){const [sessions,setSessions]=useState<Record<string,ReaderSession>>({});return <Context.Provider value={{sessions,setSessions}}>{children}</Context.Provider>}
export function useCatalogReaderSession(key:string){
 const store=useContext(Context);if(!store)throw new Error('Catalog reader session missing');const {sessions,setSessions}=store;
 const set=useCallback(<K extends keyof ReaderSession>(field:K,value:SetStateAction<ReaderSession[K]>)=>setSessions(old=>{const s=old[key]??initial(key);const next=typeof value==='function'?(value as (v:ReaderSession[K])=>ReaderSession[K])(s[field]):value;return Object.is(s[field],next)?old:{...old,[key]:{...s,[field]:next}}}),[key,setSessions]);
 return {...(sessions[key]??initial(key)),set};
}
