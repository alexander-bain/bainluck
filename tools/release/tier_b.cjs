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
  let candidates;
  if (context.payload.pull_request) {
    candidates = [await github.rest.pulls.get({...repo,pull_number:context.payload.pull_request.number}).then(r=>r.data)];
  } else {
    // Review submission/dismissal has no pull_request_target event. Poll the
    // reviewed default-branch code, never execute code from a PR with write rights.
    candidates = await github.paginate(github.rest.pulls.list,{...repo,state:'open',per_page:100});
    candidates = candidates.filter(pr=>pr.labels.some(label=>label.name==='tier-b'));
  }
  for (const pr of candidates) {
    if (pr.state !== 'open') continue;
    const reviews = await github.paginate(github.rest.pulls.listReviews,{...repo,pull_number:pr.number,per_page:100});
    const result = verdict(pr,reviews);
    const checks = await github.paginate(github.rest.checks.listForRef,{...repo,ref:pr.head.sha,check_name:'Tier-B approval',per_page:100});
    const previous = checks.filter(check=>check.app?.slug==='github-actions').sort((a,b)=>b.id-a.id)[0];
    if (previous?.conclusion === result.conclusion && previous?.output?.summary === result.summary) continue;
    await github.rest.checks.create({...repo,name:'Tier-B approval',head_sha:pr.head.sha,
      status:'completed',conclusion:result.conclusion,completed_at:new Date().toISOString(),
      output:{title:'Tier-B approval',summary:result.summary}});
  }
}

module.exports = {verdict,evaluate};
