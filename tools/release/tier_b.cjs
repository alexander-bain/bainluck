'use strict';

// 119-A (Alex, Nov 10, #12538/#12539): Fable's ACCEPT is needed only when a PR
// (a) changes what a reader sees, or a number a reader sees, on web, phone or
// Watch; (b) deletes or rewrites stored data or is migration-class; or (c)
// changes an eval, a gate, an exam, a licence or grades. Every other tier-b PR
// merges on claude[bot]'s approval at its head and green CI.
//
// The PR's first line declares which: `Fable: needed (reader-visible |
// destructive | eval)` or `Fable: not needed`. A PR with no such line is read as
// needing Fable. A `not needed` PR that touches any path below is blocked, with
// the paths named. A false match only asks for Fable's review, while a miss lets
// a reader-visible change skip it, so the list errs broad. Argue with it here,
// in one place.
//
// `tasks/__init__.py` is NOT plumbing: it also holds task bodies, among them
// `update_max_movement`, which writes the movement a reader sees (Fable, #12543).
//
// THE DEFAULT IS FLIPPED FOR backend/app/ AND backend/data/ (Fable's review of
// #12543): a file there needs Fable UNLESS its name says it is plumbing, meaning
// it only watches, files or measures. A keyword list of reader-facing names
// missed 593 of 740 backend modules, among them team_merge.py (this morning's
// deleted names) and the seating and calibration code.
const PLUMBING = new RegExp('^backend/app/(?!routes/)(' + [
  '.*(sentinel|watchdog)[^/]*\\.py$',           // the alarms
  '.*(alert|issue_labels|bug_report|filing)[^/]*\\.py$', // alert and issue filing
  '.*(log_redaction|logging)[^/]*\\.py$',       // logging
  '.*(task_memory|memory_turns|latency|timing|task_metrics|sampler|heartbeat)[^/]*\\.py$', // memory and timing instrumentation
].join('|') + ')');

const FABLE_PATHS = [
  // Reader-facing pages, components and client code (web), minus their tests,
  // and the three configs that change what the web app serves.
  {why: 'reader-visible (web page or component)', re: /^frontend\/(app|components|lib|hooks|public|styles|src)\/(?!.*(__tests__\/|\.test\.|\.spec\.))/},
  {why: 'reader-visible (web config)', re: /^frontend\/(next\.config\.mjs|tailwind\.config\.ts|vercel\.json)$/},
  // The phone and the Watch app, minus their test targets (BainLuckTests,
  // BainLuckUITests, BainLuckWatchUITests), as the web rule skips web tests.
  {why: 'reader-visible (iOS / Watch)', re: /^ios\/(?![^/]+\/[^/]*Tests\/)/},
  // API responses a page reads, and every admin handler (some are destructive).
  {why: 'reader-visible or destructive (API route)', re: /^backend\/app\/routes\//},
  // Everything else in the app and its data, unless the name says plumbing.
  {why: 'reader-visible or destructive (backend app code; not plumbing)', re: /^backend\/app\//, unless: PLUMBING},
  {why: 'reader-visible, graded or licensed data (backend data)', re: /^backend\/data\//},
  // Evals, gates, exams, grades and the release machinery itself.
  {why: 'eval or gate (exam, golden set or grades)', re: /(exam|golden|grade)/i},
  {why: 'licence', re: /licen[cs]e/i},
  {why: 'eval or gate', re: /^(evals\/|backend\/scripts\/evals\/|backend\/tests\/evals\/|tools\/release\/|tools\/ranking\/|tools\/reader_walk\/|docs\/release-loop\/|\.github\/workflows\/|\.github\/PULL_REQUEST_TEMPLATE)/},
  // Migrations, index changes and data repairs.
  {why: 'destructive (migration, index change or data repair)', re: /^backend\/(alembic\/|scripts\/[^/]*\.sql$|scripts\/[^/]*(repair|restore|backfill|apply|fold|merge|delete|purge|fix|seed|populate|ingest|import|reconcile|settle|cleanup|dedup|prune)[^/]*$|cleanup_soccer\.py$|deduplicate_snapshots\.py$)/},
];

// The first non-empty line of the PR body, read as the 119-A declaration.
function fableLine(body) {
  const first = String(body || '').split(/\r?\n/).map(line => line.trim()).find(line => line) || '';
  const m = first.match(/^\**\s*Fable:\s*(not needed|needed)\b/i);
  if (!m) return 'missing';
  return m[1].toLowerCase() === 'not needed' ? 'not needed' : 'needed';
}

// Files a `Fable: not needed` PR touches that the list says need Fable.
function fableHits(files) {
  const hits = [];
  for (const file of files || []) {
    // A rename is judged by both names, so moving a file off a listed path
    // cannot take it off the list.
    for (const name of [file.filename || file, file.previous_filename].filter(Boolean)) {
      const rule = FABLE_PATHS.find(rule => rule.re.test(name) && !(rule.unless && rule.unless.test(name)));
      if (rule) { hits.push(`${name} (${rule.why})`); break; }
    }
  }
  return hits;
}

function verdict(pr, reviews, files) {
  if (pr.labels.some(label => label.name === 'eval-candidate')) {
    return {conclusion:'failure',summary:'Never-merge reviewer eval candidate. Its bot verdict is study evidence; this label cannot authorize a merge.'};
  }
  if (!pr.labels.some(label => label.name === 'tier-b')) {
    return {conclusion:'success',summary:'This PR does not carry tier-b.'};
  }
  const latest = new Map();
  for (const review of [...reviews].sort((a,b) => a.id - b.id)) {
    if (['APPROVED','CHANGES_REQUESTED','DISMISSED'].includes(review.state)) {
      latest.set(review.user.login,review);
    }
  }
  const declared = fableLine(pr.body);
  if (declared === 'not needed') {
    const hits = fableHits(files);
    if (hits.length) {
      return {conclusion:'failure',summary:`The first line says \`Fable: not needed\`, but this PR touches paths that need Fable's ACCEPT under 119-A: ${hits.slice(0,10).join('; ')}${hits.length>10?` (+${hits.length-10} more)`:''}. Change the first line to \`Fable: needed (reader-visible | destructive | eval)\`, or take those files out.`};
    }
  }
  const approval = [...latest.values()].find(review =>
    review.user.login === 'claude[bot]' && review.user.login !== pr.user.login &&
    review.state === 'APPROVED' &&
    review.commit_id === pr.head.sha);
  const fable = declared === 'not needed'
    ? 'The first line says `Fable: not needed` and no file is on the 119-A list, so the author window merges after green CI.'
    : declared === 'needed'
      ? 'The first line says `Fable: needed`, so the author window merges after green CI and Fable ACCEPT at this head.'
      : 'There is no `Fable:` first line, so Fable ACCEPT at this head is needed (119-A); the author window merges after green CI and that ACCEPT.';
  return approval ? {conclusion:'success',summary:`Approved at this head by ${approval.user.login}. ${fable}`} :
    {conclusion:'failure',summary:`tier-b requires claude[bot] approval at the current head; labels and human reviews cannot replace it. ${fable}`};
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
        // File scope is read only to test a `Fable: not needed` claim; it never
        // grants approval and is never read for any other PR.
        const files=fableLine(pr.body)==='not needed'
          ? await github.paginate(github.rest.pulls.listFiles,{...repo,pull_number:pr.number,per_page:100}) : [];
        results.push(verdict(pr,reviews,files));
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

module.exports = {verdict,evaluate,fableLine,fableHits,FABLE_PATHS,PLUMBING};
