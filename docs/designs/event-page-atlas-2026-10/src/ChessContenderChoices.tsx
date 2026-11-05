import type {CSSProperties} from 'react';
import {CheckIcon} from '@radix-ui/react-icons';
import {chessContenders} from './chessHistory';
import {chessChoiceFrame,chessChoicePreview} from './chessChoicePreview';
import {chessIdentityColor} from './contenderColors';
import {eventReaderTime as clock} from './eventReaderTime';
import {probabilityLabel as pct} from './probabilityLabel';
import './chessContenderChoices.css';
export function ChessContenderChoices({selected,expanded,onChoose,onExpand}:{selected:number;expanded:boolean;onChoose:(id:number)=>void;onExpand:()=>void}){
 const frame=chessChoiceFrame(chessContenders);
 if(!frame)return null;
 const players=expanded?chessContenders:chessContenders.filter(c=>[235705516,235705515,235705523,selected].includes(c.outcome_id));
 return <section className="chess-choices" aria-label="Choose contender history">
  <div className="chess-choice-heading"><h3>Explore another contender</h3><button aria-expanded={expanded} onClick={onExpand}>{expanded?'Hide previews':'Compare 10 histories'}</button></div>
  {expanded&&<p className="chess-choice-scope">Full captured window · {clock.range(frame.from,frame.through)}<br/>Same 0–{pct(frame.ceiling)} scale · gaps stay blank</p>}
  <div className={expanded?'chess-choice-grid':'chess-choice-shortlist'}>{players.map(c=>{
   const preview=chessChoicePreview(c,frame),last=preview.last,ink=chessIdentityColor(c.outcome_id);
   return <button key={c.outcome_id} style={{'--choice-ink':ink} as CSSProperties} aria-pressed={c.outcome_id===selected} onClick={event=>{onChoose(c.outcome_id);event.currentTarget.closest('.chess-history')?.querySelector('.chess-readout')?.scrollIntoView({block:'start',behavior:'instant'})}} aria-label={`Show ${c.name}'s full captured history. ${last?`Last recorded ${pct(last.probability)} at ${clock.full(last.timestamp)}.`:'No recorded history.'} Not a current or pre-tournament chance.`}>
    <div className="chess-choice-name"><strong>{c.name}</strong>{selected===c.outcome_id&&<CheckIcon aria-label="Selected"/>}</div>
    <div className="chess-choice-visual"><div><small>Last recorded</small><b>{last?pct(last.probability):'Unavailable'}</b></div>
    {expanded&&last&&<div className="chess-choice-mini"><svg viewBox="0 0 142 72" aria-hidden="true"><line x1="8" x2="134" y1="66" y2="66" className="chess-choice-zero"/>{preview.segments.map((segment,i)=>segment.length===1?<circle key={i} cx={8+segment[0].x*126} cy={6+segment[0].y*60} r="2" fill="currentColor"/>:<polyline key={i} points={segment.map(p=>`${8+p.x*126},${6+p.y*60}`).join(' ')} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/>)}<circle cx={8+last.x*126} cy={6+last.y*60} r="3.2" fill="currentColor"/></svg><small>0–{pct(frame.ceiling)} chance</small></div>}
    </div>
    <time>{last?clock.full(last.timestamp):'Time unavailable'}</time>
   </button>;
  })}</div>
  <p className="chess-choice-note">{expanded?'10 recorded histories, in source order. ':''}Each probability keeps its own date. Choosing a contender opens their last recorded point. Pre-tournament chances remain unavailable.</p>
 </section>;
}
