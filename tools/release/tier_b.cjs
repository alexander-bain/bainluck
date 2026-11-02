'use strict';

function verdict(pr, reviews) {
  if (!pr.labels.some(label => label.name === 'tier-b')) {
    return {conclusion:'success',summary:'This PR does not carry tier-b.'};
  }
  const latest = new Map();
  for (const review of [...reviews].sort((a,b) => a.id - b.id)) {
    if (['APPROVED','CHANGES_REQUESTED','DISMISSED'].includes(review.state)) {
      latest.set(review.user.login,review);
    }
  }
  const approval = [...latest.values()].find(review =>
    review.user.login !== pr.user.login && review.state === 'APPROVED' &&
    review.commit_id === pr.head.sha);
  return approval ? {conclusion:'success',summary:`Approved at this head by ${approval.user.login}.`} :
    {conclusion:'failure',summary:'tier-b requires an approving review at the current head from someone other than the PR author. Until #2734 gives agents their own GitHub App identity, Alex or Fable must handle the Tier-B merge; the author cannot approve their own PR.'};
}

async function currentOpen(github, repo, eventNumber) {
  const listed = await github.paginate(github.rest.pulls.list,{...repo,state:'open',per_page:100});
  const numbers = [...new Set([...listed.map(pr=>pr.number),...(eventNumber?[eventNumber]:[])])];
  const current = [];
  // Refresh before grouping: a PR may have synchronized to another sibling's
  // SHA since pagination. Initial list head/label fields are never authority.
  for (const number of numbers) {
    const pr = await github.rest.pulls.get({...repo,pull_number:number}).then(r=>r.data);
    if (pr.state === 'open') current.push(pr);
  }
  return current;
}

function membership(prs) {
  return JSON.stringify(prs.map(pr=>({number:pr.number,sha:pr.head.sha,
    labels:pr.labels.map(label=>label.name).sort(),author:pr.user.login}))
    .sort((a,b)=>a.number-b.number));
}

async function publish(github,repo,sha,result,stillCurrent) {
  const checks = await github.paginate(github.rest.checks.listForRef,{...repo,ref:sha,check_name:'Tier-B approval',per_page:100});
  if (stillCurrent && !(await stillCurrent())) return false;
  const previous = checks.filter(check=>check.app?.slug==='github-actions').sort((a,b)=>b.id-a.id)[0];
  if (previous?.conclusion === result.conclusion && previous?.output?.summary === result.summary) return true;
  await github.rest.checks.create({...repo,name:'Tier-B approval',head_sha:sha,
    status:'completed',conclusion:result.conclusion,completed_at:new Date().toISOString(),
    output:{title:'Tier-B approval',summary:result.summary}});
  return true;
}

async function evaluate(github, context) {
  const repo=context.repo;
  const eventNumber=context.payload.pull_request?.number || context.payload.client_payload?.pull_number;
  const observed=new Set();
  // Every event reconciles EVERY current SHA. GitHub concurrency coalesces
  // pending events; the surviving event must also cover a discarded dismissal.
  for (let attempt=0;attempt<2;attempt++) {
    const current=await currentOpen(github,repo,eventNumber);
    const groups=new Map();
    for (const pr of current) {
      observed.add(pr.head.sha);
      if (!groups.has(pr.head.sha)) groups.set(pr.head.sha,[]);
      groups.get(pr.head.sha).push(pr);
    }
    const verdicts=new Map();
    for (const [sha,prs] of groups) {
      const results=[];
      for (const pr of prs) {
        const reviews=await github.paginate(github.rest.pulls.listReviews,{...repo,pull_number:pr.number,per_page:100});
        results.push(verdict(pr,reviews));
      }
      const failed=results.filter(result=>result.conclusion!=='success');
      verdicts.set(sha,{conclusion:failed.length?'failure':'success',
        summary:(failed.length?failed:results).map(x=>x.summary).join('\n')});
    }
    const refreshed=await currentOpen(github,repo,eventNumber);
    refreshed.forEach(pr=>observed.add(pr.head.sha));
    if (membership(current)!==membership(refreshed)) continue;
    const stillCurrent=async()=>{
      const latest=await currentOpen(github,repo,eventNumber);
      latest.forEach(pr=>observed.add(pr.head.sha));
      return membership(current)===membership(latest);
    };
    let changed=false;
    for (const [sha,result] of verdicts) {
      if (!(await publish(github,repo,sha,result,stillCurrent))) {changed=true;break;}
    }
    if (changed) continue;
    return;
  }
  for (const sha of observed) await publish(github,repo,sha,{conclusion:'failure',
    summary:'PR membership, head or labels changed during both evaluation attempts; re-evaluation required.'});
}

module.exports = {verdict,evaluate};
