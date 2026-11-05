import {eventReaderTime} from './eventReaderTime';
import {completionFinal} from './nflCompletion';
import {useEffect,useState} from 'react';
import {ResponsiveContainer} from './ChartVisibility';
import {ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, ReferenceLine} from 'recharts';
import {CircleIcon,DotFilledIcon} from '@radix-ui/react-icons';
import fixture from './livePlayers.json';
import {livePointSelection,livePlayerBookmark,resolveLivePlayerSelection,type LivePlayerBookmark,type LivePlayerProfile} from './livePlayerEvidence';
import {probabilityLabel} from './probabilityLabel';
const clock=(value:string|null)=>eventReaderTime.full(value,true);
export function LivePlayerCard({profile,mode,final=false}:{profile:LivePlayerProfile;mode:string;final?:boolean}){
 const [bookmark,setBookmark]=useState<LivePlayerBookmark|null>(()=>{const first=profile.points.find(p=>p.count===profile.defaultCount)??profile.points[0];return first?livePlayerBookmark(profile,first):null});
 const view=resolveLivePlayerSelection(profile,bookmark,final?'captured':mode);
 useEffect(()=>{if(view?.present&&bookmark?.point!==view.point)setBookmark(livePlayerBookmark(profile,view.point))},[view?.present,view?.point,bookmark,profile]);
 if(!view)return <article className="atlas-card compact-player live-player-profile"><h3>{profile.name}</h3><p>No milestones in this update.</p></article>;
 const {point,baseline,recorded,delta,present,ambiguous}=view;
 const finish=final?completionFinal(profile,point):null,actual=final?finish!.actual:view.actual,remaining=actual===null?null:Math.max(0,point.count-actual);
 const selected=point.count;
 const points=profile.points.map(p=>{const state=livePointSelection(p,actual,final?'captured':mode);return {x:p.count,baseline:state.baseline,recorded:state.recorded}});
 const unavailable=final?'Earlier quote unavailable':mode==='loading'?'Loading…':'Current probability unavailable';
 return <article className="atlas-card compact-player live-player-profile">
  <div className="atlas-card-head"><div><span className="eyebrow">Completions · {final?'final capture':'in-game capture'}</span><h3>{profile.name}</h3></div><div className="player-final"><strong>{actual??'—'}</strong><span>{final?'FINAL':'RECORDED'}</span></div></div>
  <p className="axis-caption">Chance to finish with each total</p>
  <div className="live-profile-plot" role="img" aria-label={`${profile.name}: ${actual??'unavailable'} ${final?'final':'recorded'} completions; player-stat time unavailable. Hollow marks are pregame, solid marks are explicitly dated earlier in-game quotes. ${selected}+: pregame ${probabilityLabel(baseline)}, ${recorded===null?'no recent probability update':probabilityLabel(recorded)+' recorded at '+clock(point.recordedAt)}.`}>
   <ResponsiveContainer width="100%" height="100%"><ScatterChart margin={{top:26,bottom:3,left:-16,right:17}}>
    <CartesianGrid vertical={false} stroke="var(--surface-border)" strokeDasharray="3 4"/>
    <XAxis dataKey="x" type="number" domain={[0,Math.max(...points.map(p=>p.x),selected,actual??0)+2]} axisLine={false} tickLine={false} tick={{fontSize:11}}/>
    <YAxis dataKey="y" type="number" domain={[0,1]} ticks={[0,.5,1]} tickFormatter={probabilityLabel} axisLine={false} tickLine={false} tick={{fontSize:11}}/>
    <Scatter data={points.filter(p=>p.baseline!==null).map(p=>({x:p.x,y:p.baseline}))} dataKey="y" isAnimationActive={false} shape={(p:any)=><circle cx={p.cx} cy={p.cy} r={p.payload.x===selected?7:5} fill="white" stroke="var(--series-home)" strokeWidth={2}/>}/>
    <Scatter data={points.filter(p=>p.recorded!==null).map(p=>({x:p.x,y:p.recorded}))} dataKey="y" isAnimationActive={false} fill="var(--series-away)" shape={(p:any)=><circle cx={p.cx} cy={p.cy} r={p.payload.x===selected?5:3.5} fill="var(--series-away)"/>}/>
    {actual!==null&&<ReferenceLine x={actual} stroke="var(--text-primary)" strokeWidth={3} label={{value:`${actual} ${final?'final':'recorded'}`,position:'top',fontSize:11,fill:'var(--text-primary)'}}/>}
   </ScatterChart></ResponsiveContainer>
  </div>
  <div className="live-profile-choices" role="group" aria-label={`${profile.name} completion milestones`}>{profile.points.map(p=><button key={p.key} aria-pressed={present&&p.key===point.key} onClick={()=>setBookmark(livePlayerBookmark(profile,p))}>{p.count}+</button>)}</div>
  {!present&&<p className="atlas-note" role="status">{ambiguous?'This update has conflicting records for your selected milestone.':'Your selected milestone is not in this update.'} Its original prop and pregame baseline remain below.</p>}
  <div className="live-profile-takeaway"><strong>{selected}+ completions</strong>{remaining!==null&&<span>{final?(remaining===0?'Target reached in final stats':`Finished ${remaining} short`):remaining===0?'Target reached in recorded stats':`${remaining} more from recorded ${actual}`}</span>}</div>
  <div className="live-profile-readouts"><div><span><CircleIcon/>Pregame · {clock(point.baselineAt)}</span><strong>{probabilityLabel(baseline)}</strong></div><div><span>{recorded!==null&&<DotFilledIcon/>}{recorded!==null?`${final?'Earlier in game':'In game'} · ${clock(point.recordedAt)}`:final?'Earlier in-game quote':'In-game quote'}</span><strong className={recorded===null?'quote-missing':''}>{recorded===null?unavailable:probabilityLabel(recorded)}</strong></div></div>
  {final&&<p className="live-profile-movement">Contract result: <strong>{finish!.result}</strong></p>}
  {delta!==null&&<p className="live-profile-movement"><strong>{delta>0?'+':''}{delta} percentage {Math.abs(delta)===1?'point':'points'}</strong> {final?'at the earlier quote':'since pregame'}</p>}
  <p className="atlas-note">{final?`Final-stat capture: ${clock(finish?.capturedAt??null)}; stat observation time unavailable. The solid dots remain earlier quotes, not final probabilities.`:'Player-stat time unavailable. The recorded count and quote have separate clocks.'}</p>
  <details className="live-profile-details"><summary>Details & timing</summary><h4>{point.marketName}</h4><p>{point.outcomeName} · {profile.period}</p><dl><dt>Last captured quote</dt><dd>{probabilityLabel(point.recorded)} · {clock(point.recordedAt)}</dd><dt>Pregame baseline</dt><dd>{probabilityLabel(point.baseline)} · {clock(point.baselineAt)} · {point.baselineBasis==='pregame_pin'?'Pinned before play':point.baselineBasis??'Basis unavailable'}</dd><dt>{final?'Final statistic':'Recorded statistic'}</dt><dd>{actual??'Unavailable'} completions · observation time unavailable</dd><dt>Response captured</dt><dd>{final?finish!.capturedAt??'Unavailable':profile.actualCapturedAt} (fetch time, not stat time)</dd><dt>Original market</dt><dd>{point.source} · {point.marketID}</dd></dl><p>Archived in-game evidence from October 11, 2026. No current probability or synchronized replay is implied. A reached count is not provider settlement.{final&&<> Final result: {finish!.result}. Earlier live actual: {profile.actual??'Unavailable'} completions.</>}</p></details>
 </article>;
}
export function LivePlayerProfiles({mode,refresh='original',final=false}:{mode:string;refresh?:string;final?:boolean}){return <>{fixture.profiles.map(original=>{const profile={...original,points:refresh==='reverse'?[...original.points].reverse():refresh==='omit'?original.points.filter(p=>p.count!==original.defaultCount):refresh==='empty'?[]:refresh==='clock'?original.points.map(p=>({...p,recordedAt:null})):original.points};return <LivePlayerCard key={profile.name} profile={profile} mode={mode} final={final}/>})}</>;}
