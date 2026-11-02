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

async function evaluate(github, context) {
  const repo = context.repo;
  // Checks are SHA-scoped, so every open PR sharing a SHA contributes. A
  // non-Tier-B PR must never overwrite an unapproved sibling with success.
  const open = await github.paginate(github.rest.pulls.list,{...repo,state:'open',per_page:100});
  const eventNumber = context.payload.pull_request?.number || context.payload.client_payload?.pull_number;
  let shas;
  if (eventNumber) {
    const eventPR = await github.rest.pulls.get({...repo,pull_number:eventNumber}).then(r=>r.data);
    if (eventPR.state !== 'open') return;
    shas = [eventPR.head.sha];
  } else {
    shas = [...new Set(open.map(pr=>pr.head.sha))];
  }
  for (const sha of shas) {
    // Re-read current PRs after inventory; stale heads and labels cannot pass.
    const siblings = [];
    for (const snapshot of open.filter(pr=>pr.head.sha===sha)) {
      const current = await github.rest.pulls.get({...repo,pull_number:snapshot.number}).then(r=>r.data);
      if (current.state === 'open' && current.head.sha === sha) siblings.push(current);
    }
    if (!siblings.length) continue;
    const results = [];
    for (const pr of siblings) {
      const reviews = await github.paginate(github.rest.pulls.listReviews,{...repo,pull_number:pr.number,per_page:100});
      const current = await github.rest.pulls.get({...repo,pull_number:pr.number}).then(r=>r.data);
      if (current.state !== 'open' || current.head.sha !== sha || JSON.stringify(current.labels) !== JSON.stringify(pr.labels)) {
        results.push({conclusion:'failure',summary:'PR head or labels changed during evaluation; re-evaluation required.'});
      } else {
        results.push(verdict(current,reviews));
      }
    }
    const failed = results.filter(result=>result.conclusion!=='success');
    const result = failed.length ? {conclusion:'failure',summary:failed.map(x=>x.summary).join('\n')} :
      {conclusion:'success',summary:results.map(x=>x.summary).join('\n')};
    const checks = await github.paginate(github.rest.checks.listForRef,{...repo,ref:sha,check_name:'Tier-B approval',per_page:100});
    const previous = checks.filter(check=>check.app?.slug==='github-actions').sort((a,b)=>b.id-a.id)[0];
    if (previous?.conclusion === result.conclusion && previous?.output?.summary === result.summary) continue;
    await github.rest.checks.create({...repo,name:'Tier-B approval',head_sha:sha,
      status:'completed',conclusion:result.conclusion,completed_at:new Date().toISOString(),
      output:{title:'Tier-B approval',summary:result.summary}});
  }
}

module.exports = {verdict,evaluate};
