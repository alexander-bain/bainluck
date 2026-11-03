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
    {conclusion:'failure',summary:'tier-b requires an approving review at the current head from someone other than the PR author. The installed Claude GitHub Action supplies an independent bot identity; the author cannot approve their own PR.'};
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
  const eventNumber=context.eventName === 'schedule' ? undefined : Number(
    context.payload.pull_request?.number ?? context.payload.client_payload?.pull_number ?? context.payload.inputs?.pull_number);
  if (eventNumber !== undefined && (!Number.isSafeInteger(eventNumber) || eventNumber < 1)) {
    throw new Error('A pull request number is required outside the scheduled sweep.');
  }
  const observed=new Set();
  // Events touch their PR only. The half-hour sweep also reconciles review
  // dismissals and events coalesced by GitHub's per-PR concurrency queue.
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
        const files = await github.paginate(github.rest.pulls.listFiles, {...repo,pull_number:pr.number,per_page:100});
        const policyChanged = files.some(file => [file.filename,file.previous_filename].some(name => ['.github/workflows/tier-b-review.yml','docs/release-loop/tier-b-review-brief.md'].includes(name)));
        const eligible = policyChanged ? reviews.filter(review => review.user.type !== 'Bot' && !review.user.login.endsWith('[bot]')) : reviews;
        let result = verdict(pr,eligible);
        if (policyChanged && result.conclusion !== 'success' && pr.labels.some(label=>label.name==='alex-approved')) {
          const events = await github.paginate(github.rest.issues.listEvents, {...repo,issue_number:pr.number,per_page:100});
          const applied = events.filter(event=>['labeled','unlabeled'].includes(event.event) && event.label?.name==='alex-approved')
            .sort((a,b)=>b.id-a.id)[0];
          if (applied?.event==='labeled' && applied.actor?.login==='alexander-bain') {
            const head = await github.rest.repos.getCommit({...repo,ref:pr.head.sha}).then(r=>r.data);
            const labeledAt = Date.parse(applied.created_at);
            const committedAt = Date.parse(head.commit?.committer?.date);
            result = Number.isFinite(labeledAt) && Number.isFinite(committedAt) && labeledAt > committedAt
              ? {conclusion:'success',summary:'Alex approved this review-policy change via alex-approved. Attribution uses Alex’s shared account; windows must never apply this label.'}
              : {conclusion:'failure',summary:'alex-approved predates the current head; re-apply after review'};
          } else {
            result = {...result,summary:result.summary+' The alex-approved label must be applied by Alex.'};
          }
        }
        results.push(policyChanged ? {...result,summary:result.summary+' Review policy changed; Alex must merge this PR.'} : result);
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
