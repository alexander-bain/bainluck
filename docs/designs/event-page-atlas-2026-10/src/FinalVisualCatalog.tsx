import {ReceivingLeaderCatalog,isReceivingLeaderCatalog} from './ReceivingLeaderCatalog';
import {useDenseCardLayout} from './useDenseCardLayout';
import {FinalTotalTrack} from './FinalTotalTrack';
import {useState} from 'react';
import {CatalogProbabilityCard} from './CatalogProbabilityCard';
import {browseCatalogEntries,catalogEntryContext,type CatalogSession} from './catalogPageSession';
import {finalCatalogPresentation,finalCatalogSearchText,isFinalTotalTrack,type FinalCatalogRow} from './finalCatalogEvidence';
import type {CatalogAnchor} from './catalogSelection';
import './finalVisualCatalog.css';
export function FinalVisualCatalog({session,phase,query,category,limit,onPick,onReveal,onMore}:{session:CatalogSession<FinalCatalogRow>;phase:string;query:string;category:string;limit:number;onPick:(row:FinalCatalogRow)=>void;onReveal:(row:FinalCatalogRow)=>void;onMore:()=>void}){
 const denseRef=useDenseCardLayout();
 const [anchors,setAnchors]=useState<Record<string,CatalogAnchor<FinalCatalogRow>>>({});
 const term=query.trim().toLocaleLowerCase();
 const groups=browseCatalogEntries(session.entries,'',category==='Overview'?'All':category).map(group=>({...group,visibleRows:group.visibleRows.filter(row=>finalCatalogSearchText(row).toLocaleLowerCase().includes(term))})).filter(group=>group.visibleRows.length>0);
 const count=groups.reduce((n,group)=>n+group.visibleRows.length,0);
 return <div className="final-visual-catalog">
  <p className="final-catalog-count">{count.toLocaleString()} {query?'matching ':''}outcomes · {groups.length.toLocaleString()} prop groups</p>
  <p className="final-catalog-note">{phase==='Final'?'Final results. A result marked pending or unconfirmed is not a win or a loss.':'Pregame chances are labeled where available. In-game probabilities and progress are unavailable; later final results stay hidden.'}</p>
  <div ref={denseRef} className="final-catalog-grid">{groups.slice(0,limit).map(group=><div className="retained-question" key={group.key}>
   {group.absentFromUpdate&&<div className="retained-question-note"><strong>Earlier prop · absent from this update</strong>Last quotes remain in details.</div>}
   <CatalogProbabilityCard rows={group.rows} visibleRows={group.visibleRows} savedAnchor={anchors[group.key]??null}
    onSelection={anchor=>setAnchors(old=>old[group.key]?.row===anchor.row?old:{...old,[group.key]:anchor})}
    onReveal={()=>{const row=anchors[group.key]?.row;if(row)onReveal(row)}} onPick={onPick}
    context={catalogEntryContext(session,group,phase==='Final'?'captured':'historical')}
    baselineInVisual={isReceivingLeaderCatalog(group.rows,session.snapshot.eventID)||phase==='Final'&&isFinalTotalTrack(group.rows,session.snapshot.eventID)}
    selectedSummaryInVisual={isReceivingLeaderCatalog(group.rows,session.snapshot.eventID)||phase==='Final'&&isFinalTotalTrack(group.rows,session.snapshot.eventID)}
    selectionControlsInVisual={isReceivingLeaderCatalog(group.rows,session.snapshot.eventID)||phase==='Final'&&isFinalTotalTrack(group.rows,session.snapshot.eventID)}
    displayTitle={isReceivingLeaderCatalog(group.rows,session.snapshot.eventID)?'Most receiving yards':phase==='Final'&&isFinalTotalTrack(group.rows,session.snapshot.eventID)?'Scoring vs expectations':undefined}
    presentationFor={(row,context)=>finalCatalogPresentation(row,context,phase)}
    visual={isReceivingLeaderCatalog(group.rows,session.snapshot.eventID)?(row,choose)=><ReceivingLeaderCatalog supportRows={session.snapshot.rows} eventID={session.snapshot.eventID} rows={group.rows} visibleRows={group.visibleRows} selected={row} phase={phase} choose={choose} pick={onPick}/>:phase==='Final'&&isFinalTotalTrack(group.rows,session.snapshot.eventID)?(row,choose)=><FinalTotalTrack rows={group.rows} visibleRows={group.visibleRows} selected={row} onChoose={choose}/>:undefined}/>
  </div>)}</div>
  {!groups.length&&<div className="unavailable">No matching props. Try a player name or prop.</div>}
  {groups.length>limit&&<button className="load-more" onClick={onMore}>Show {Math.min(12,groups.length-limit)} more prop groups</button>}
 </div>;
}
