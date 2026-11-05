import {useMemo} from 'react';
import type {BeforeProp} from './hockeyBeforeEvidence';
import type {ContributionKind} from './hockeyContributions';
import {beforeContributionProfiles} from './hockeyBeforeContributions';
import {HockeyContributionVisual,type ContributionSelection} from './HockeyContributionVisual';
export function HockeyBeforeContributionCard({rows,eventID,kind,...rest}:{rows:BeforeProp[];eventID:unknown;kind:ContributionKind;selection:ContributionSelection;onSelection:(s:ContributionSelection)=>void;onPick:(r:BeforeProp)=>void;playersOpen:boolean;onPlayersOpen:(open:boolean)=>void;large?:boolean}){
 const profiles=useMemo(()=>beforeContributionProfiles(rows,eventID,kind),[rows,eventID,kind]);
 return <HockeyContributionVisual profiles={profiles} kind={kind} phase="before" {...rest}/>;
}
