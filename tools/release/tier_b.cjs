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
    review.user.login === 'claude[bot]' && review.user.login !== pr.user.login &&
    review.state === 'APPROVED' &&
    review.commit_id === pr.head.sha);
  return approval ? {conclusion:'success',summary:`Approved at this head by ${approval.user.login}. The author window merges after green CI and Fable ACCEPT at this head.`} :
    {conclusion:'failure',summary:'tier-b requires claude[bot] approval at the current head. The author window merges only after green CI and Fable ACCEPT at that head; labels and human reviews cannot replace the bot approval.'};
}

async function currentOpen(github, repo, eventNumber) {
  if (eventNumber) {
    const pr = await github.rest.pulls.get({...repo,pull_number:eventNumber}).then(r=>r.data);
    return pr.state === 'open' ? [pr] : [];
  }
  const listed = await github.paginate(github.rest.pulls.list,{...repo,state:'open',per_page:100});
  const current = [];
  for (const listedPR of listed) {
    // Tier A is label-only. Refresh Tier B before reading its head's reviews
    // and grouping siblings; the final membership read catches list changes.
    const pr = listedPR.labels.some(label=>label.name==='tier-b')
      ? await github.rest.pulls.get({...repo,pull_number:listedPR.number}).then(r=>r.data)
      : listedPR;
    if (pr.state === 'open') current.push(pr);
  }
  return current;
}

function membership(prs) {
  return JSON.stringify(prs.map(pr=>({number:pr.number,sha:pr.head.sha,
    labels:pr.labels.map(label=>label.name).sort(),author:pr.user.login}))
    .sort((a,b)=>a.number-b.number));
}

async function publish(github,repo,sha,result) {
  const checks = await github.paginate(github.rest.checks.listForRef,{...repo,ref:sha,check_name:'Tier-B approval',per_page:100});
  const previous = checks.filter(check=>check.app?.slug==='github-actions').sort((a,b)=>b.id-a.id)[0];
  if (previous?.conclusion === result.conclusion && previous?.output?.summary === result.summary) return;
  await github.rest.checks.create({...repo,name:'Tier-B approval',head_sha:sha,
    status:'completed',conclusion:result.conclusion,completed_at:new Date().toISOString(),
    output:{title:'Tier-B approval',summary:result.summary}});
}

async function evaluate(github, context) {
  const repo=context.repo;
  const run=context.payload.workflow_run;
  if (context.eventName === 'workflow_run' && (
    context.payload.action !== 'completed' || run?.status !== 'completed' ||
    run.name !== 'Tier-B review' || run.path !== '.github/workflows/tier-b-review.yml' ||
    run.event !== 'pull_request' || !Array.isArray(run.pull_requests) || run.pull_requests.length !== 1
  )) {
    throw new Error('A completed installed Tier-B reviewer run with exactly one associated PR is required.');
  }
  const eventNumber=context.eventName === 'schedule' ? undefined : Number(
    context.eventName === 'workflow_run' ? run.pull_requests[0].number :
      context.payload.pull_request?.number ?? context.payload.client_payload?.pull_number ?? context.payload.inputs?.pull_number);
  if (eventNumber !== undefined && (!Number.isSafeInteger(eventNumber) || eventNumber < 1)) {
    throw new Error('A pull request number is required outside the scheduled sweep.');
  }
  const observed=new Set();
  // Events touch their PR only. Reviewer runs only identify that PR: current
  // heads and reviews come from GitHub, never run artifacts, outputs or SHA.
  // The half-hour sweep also reconciles dismissals and coalesced events.
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
        if (!pr.labels.some(label=>label.name==='tier-b')) {
          results.push(verdict(pr,[]));
          continue;
        }
        const reviews=await github.paginate(github.rest.pulls.listReviews,{...repo,pull_number:pr.number,per_page:100});
        results.push(verdict(pr,reviews));
      }
      const failed=results.filter(result=>result.conclusion!=='success');
      verdicts.set(sha,{conclusion:failed.length?'failure':'success',
        summary:(failed.length?failed:results).map(x=>x.summary).join('\n')});
    }
    for (const [sha,result] of verdicts) await publish(github,repo,sha,result);
    // One membership check after publishing, never an all-PR read per SHA.
    // Retry once if a head or label moved; repeated churn fails observed heads.
    const refreshed=await currentOpen(github,repo,eventNumber);
    refreshed.forEach(pr=>observed.add(pr.head.sha));
    if (membership(current)===membership(refreshed)) return;
  }
  for (const sha of observed) await publish(github,repo,sha,{conclusion:'failure',
    summary:'PR membership, head or labels changed during both evaluation attempts; re-evaluation required.'});
}

module.exports = {verdict,evaluate};
