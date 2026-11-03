const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const file = path.resolve(__dirname, '../../tools/release/tier_b.cjs');
test('Tier-B rejects self-approval and accepts current-head independent approval', () => {
  assert.ok(fs.existsSync(file), 'Tier-B policy missing');
  const {verdict} = require(file);
  const pr = {user:{login:'alex'},head:{sha:'abc'},labels:[{name:'tier-b'}]};
  assert.equal(verdict(pr, [{id:1,user:{login:'alex'},state:'APPROVED',commit_id:'abc'}]).conclusion,'failure');
  assert.equal(verdict(pr, [{id:1,user:{login:'fable'},state:'APPROVED',commit_id:'abc'}]).conclusion,'success');
});
test('stale, dismissed and superseded approvals cannot pass', () => {
  assert.ok(fs.existsSync(file), 'Tier-B policy missing');
  const {verdict} = require(file);
  const pr = {user:{login:'alex'},head:{sha:'abc'},labels:[{name:'tier-b'}]};
  for (const state of ['DISMISSED','CHANGES_REQUESTED']) {
    assert.equal(verdict(pr,[{id:1,user:{login:'fable'},state:'APPROVED',commit_id:'abc'},
      {id:2,user:{login:'fable'},state,commit_id:'abc'}]).conclusion,'failure');
  }
  assert.equal(verdict(pr,[{id:1,user:{login:'fable'},state:'APPROVED',commit_id:'old'}]).conclusion,'failure');
  assert.equal(verdict({...pr,labels:[]},[]).conclusion,'success');
});

test('a sweep groups an unlabeled PR with a failing Tier-B sibling on the same head', async () => {
  const {evaluate} = require(file);
  const prs = [
    {number:1,state:'open',user:{login:'alex'},head:{sha:'same'},labels:[{name:'tier-b'}]},
    {number:2,state:'open',user:{login:'alex'},head:{sha:'same'},labels:[]},
  ];
  const created=[];
  const github={rest:{pulls:{get:()=>{},list:()=>{},listReviews:()=>{},listFiles:()=>{}},checks:{listForRef:()=>{},create:async x=>created.push(x)}},
    paginate:async (fn,args)=>fn===github.rest.pulls.list ? prs : []};
  github.rest.pulls.get=async(args)=>({data:prs.find(pr=>pr.number===args.pull_number)});
  await evaluate(github,{repo:{owner:'alexander-bain',repo:'bainluck'},eventName:'schedule',payload:{}});
  assert.equal(created.length,1);
  assert.equal(created[0].conclusion,'failure');
});

test('refreshed Tier-B sibling joining a head cannot disappear from the group',async()=>{
  const {evaluate}=require(file);
  const old=[{number:1,state:'open',user:{login:'alex'},head:{sha:'old'},labels:[{name:'tier-b'}]},
    {number:2,state:'open',user:{login:'alex'},head:{sha:'same'},labels:[]}];
  const current=old.map(pr=>({...pr,head:{sha:'same'}}));const created=[];
  const github={rest:{pulls:{get:async args=>({data:current.find(p=>p.number===args.pull_number)}),list:()=>{},listReviews:()=>{},listFiles:()=>{}},checks:{listForRef:()=>{},create:async c=>created.push(c)}},
    paginate:async fn=>fn===github.rest.pulls.list?old:[]};
  await evaluate(github,{repo:{owner:'alexander-bain',repo:'bainluck'},eventName:'schedule',payload:{}});
  assert.equal(created.find(c=>c.head_sha==='same')?.conclusion,'failure');
});

test('the scheduled sweep reconciles a dismissed review on another head',async()=>{
  const {evaluate}=require(file);
  const prs=[{number:1,state:'open',user:{login:'alex'},head:{sha:'a'},labels:[{name:'tier-b'}]},
    {number:2,state:'open',user:{login:'alex'},head:{sha:'b'},labels:[]}];const created=[];
  const github={rest:{pulls:{get:async args=>({data:prs.find(p=>p.number===args.pull_number)}),list:()=>{},listReviews:()=>{},listFiles:()=>{}},checks:{listForRef:()=>{},create:async c=>created.push(c)}},
    paginate:async fn=>fn===github.rest.pulls.list?prs:[]};
  await evaluate(github,{repo:{owner:'alexander-bain',repo:'bainluck'},eventName:'schedule',payload:{}});
  assert.equal(created.find(c=>c.head_sha==='a')?.conclusion,'failure');
});

test('membership changes during the final check lookup force a fresh verdict',async()=>{
  const {evaluate}=require(file);
  let pr={number:1,state:'open',user:{login:'alex'},head:{sha:'same'},labels:[]};let changed=false;const created=[];
  const github={rest:{pulls:{get:async()=>({data:{...pr,labels:[...pr.labels]}}),list:()=>{},listReviews:()=>{},listFiles:()=>{}},checks:{listForRef:()=>{},create:async c=>created.push(c)}},
    paginate:async fn=>{
      if(fn===github.rest.pulls.list)return[{...pr,labels:[...pr.labels]}];
      if(fn===github.rest.checks.listForRef && !changed){changed=true;pr={...pr,labels:[{name:'tier-b'}]};}
      return[];
    }};
  await evaluate(github,{repo:{owner:'alexander-bain',repo:'bainluck'},payload:{pull_request:{number:1}}});
  assert.equal(created.at(-1)?.conclusion,'failure');
});


test('review policy changes reject bot approval and require Alex to merge', async () => {
  const {evaluate} = require(file);
  for (const changed of [
    {filename:'.github/workflows/tier-b-review.yml'},
    {filename:'docs/release-loop/tier-b-review-brief.md'},
    {filename:'moved-brief.md',previous_filename:'docs/release-loop/tier-b-review-brief.md'},
  ]) {
    const pr={number:1,state:'open',user:{login:'alex'},head:{sha:'head'},labels:[{name:'tier-b'}]};
    for (const user of [{login:'claude[bot]',type:'Bot'},{login:'github-actions[bot]'},{login:'reviewer',type:'User'}]) {
      const created=[];
      const github={rest:{pulls:{get:async()=>({data:pr}),list:()=>{},listReviews:()=>{},listFiles:()=>{}},
        checks:{listForRef:()=>{},create:async result=>created.push(result)}},
        paginate:async(fn,args)=>{
          if(fn===github.rest.pulls.list)return [pr];
          if(fn===github.rest.pulls.listFiles){assert.equal(args.per_page,100);return [changed];}
          if(fn===github.rest.pulls.listReviews)return [{id:1,user,state:'APPROVED',commit_id:'head'}];
          return [];
        }};
      await evaluate(github,{repo:{owner:'alexander-bain',repo:'bainluck'},payload:{pull_request:{number:1}}});
      assert.equal(created[0].conclusion,user.login==='reviewer'?'success':'failure');
      assert.match(created[0].output.summary,/Alex must merge/);
    }
  }
});

test('bot review works on ordinary changes but unknown file scope never publishes success', async () => {
  const {evaluate} = require(file);
  const pr={number:1,state:'open',user:{login:'alex'},head:{sha:'head'},labels:[{name:'tier-b'}]};
  const created=[];
  let unavailable=false;
  const github={rest:{pulls:{get:async()=>({data:pr}),list:()=>{},listReviews:()=>{},listFiles:()=>{}},
    checks:{listForRef:()=>{},create:async result=>created.push(result)}},
    paginate:async fn=>{
      if(fn===github.rest.pulls.list)return [pr];
      if(fn===github.rest.pulls.listFiles){if(unavailable)throw new Error('file API unavailable');return [{filename:'backend/app/example.py'}];}
      if(fn===github.rest.pulls.listReviews)return [{id:1,user:{login:'claude[bot]',type:'Bot'},state:'APPROVED',commit_id:'head'}];
      return [];
    }};
  await evaluate(github,{repo:{owner:'alexander-bain',repo:'bainluck'},payload:{pull_request:{number:1}}});
  assert.equal(created[0].conclusion,'success');
  unavailable=true;created.length=0;
  await assert.rejects(evaluate(github,{repo:{owner:'alexander-bain',repo:'bainluck'},eventName:'schedule',payload:{}}),/file API unavailable/);
  assert.equal(created.length,0);
});

// Count actual mock API requests, including publishes, on the population that
// exhausted the installation budget. No network or extra dependencies needed.
function policyClient(prs) {
  const calls=[],created=[];
  const clone=pr=>({...pr,head:{...pr.head},labels:pr.labels.map(label=>({...label}))});
  const request=(method,args)=>calls.push({method,...args});
  const github={rest:{pulls:{},checks:{}},paginate:async(fn,args)=>fn(args)};
  github.rest.pulls.list=async args=>{request('list',args);return prs.map(clone);};
  github.rest.pulls.get=async args=>{request('get',args);return {data:clone(prs.find(pr=>pr.number===args.pull_number))};};
  github.rest.pulls.listReviews=async args=>{request('reviews',args);return [];};
  github.rest.pulls.listFiles=async args=>{request('files',args);return [];};
  github.rest.checks.listForRef=async args=>{request('checks',args);return [];};
  github.rest.checks.create=async args=>{request('create',args);created.push(args);};
  return {github,calls,created};
}
const repo={owner:'alexander-bain',repo:'bainluck'};

async function alexApprovalCase({files=[{filename:'.github/workflows/tier-b-review.yml'}],
  labels=[{name:'tier-b'},{name:'alex-approved'}],events=[],reviews=[],eventError,commitError}={}) {
  const pr={number:1,state:'open',user:{login:'alexander-bain'},head:{sha:'head'},labels};
  const client=policyClient([pr]);
  client.pr=pr;
  client.headCommitDate='2026-11-02T00:00:00Z';
  client.github.rest.repos={getCommit:async args=>{
    client.calls.push({method:'commit',...args});assert.equal(args.ref,pr.head.sha);
    if(commitError)throw commitError;
    return {data:{commit:{committer:{date:client.headCommitDate}}}};
  }};
  client.github.rest.pulls.listFiles=async args=>{client.calls.push({method:'files',...args});return files;};
  client.github.rest.pulls.listReviews=async args=>{client.calls.push({method:'reviews',...args});return reviews;};
  client.github.rest.issues={listEvents:async args=>{
    client.calls.push({method:'events',...args});
    assert.equal(args.issue_number,1);assert.equal(args.per_page,100);
    if(eventError)throw eventError;
    return events;
  }};
  client.run=()=>require(file).evaluate(client.github,{repo,eventName:'pull_request_target',payload:{pull_request:{number:1}}});
  return client;
}

for(const files of [
  [{filename:'.github/workflows/tier-b-review.yml'}],
  [{filename:'docs/release-loop/tier-b-review-brief.md'}],
  [{filename:'moved.md',previous_filename:'docs/release-loop/tier-b-review-brief.md'}],
]) test(`Alex's own policy PR passes through his label: ${files[0].filename}`,async()=>{
  const client=await alexApprovalCase({files,events:[{id:2,event:'labeled',label:{name:'alex-approved'},actor:{login:'alexander-bain'},created_at:'2026-11-02T00:01:00Z'}]});
  await client.run();
  assert.equal(client.created[0].conclusion,'success');
  assert.match(client.created[0].output.summary,/Alex approved.*alex-approved/);
  assert.match(client.created[0].output.summary,/Alex must merge/);
  assert.equal(client.calls.filter(c=>c.method==='commit').length,1);
  assert.match(client.created[0].output.summary,/windows must never apply this label/);
});

for(const events of [
  [],
  [{id:2,event:'labeled',label:{name:'alex-approved'},actor:{login:'other'}}],
  [{id:2,event:'labeled',label:{name:'alex-approved'},actor:{login:'alexander-bain[bot]'}}],
  [{id:2,event:'labeled',label:{name:'alex-approved'}}],
  [{id:2,event:'labeled',label:{name:'alex-approved'},actor:{login:'alexander-bain'}},
   {id:3,event:'unlabeled',label:{name:'alex-approved'},actor:{login:'alexander-bain'}}],
  [{id:3,event:'labeled',label:{name:'alex-approved'},actor:{login:'other'}},
   {id:1,event:'labeled',label:{name:'alex-approved'},actor:{login:'alexander-bain'}},
   {id:2,event:'unlabeled',label:{name:'alex-approved'},actor:{login:'other'}}],
]) test(`an unverified or replaced alex-approved label cannot approve: ${JSON.stringify(events)}`,async()=>{
  const client=await alexApprovalCase({events});await client.run();
  assert.equal(client.created[0].conclusion,'failure');
  assert.match(client.created[0].output.summary,/label must be applied by Alex/);
  assert.equal(client.calls.filter(c=>c.method==='commit').length,0);
});

test('Alex can reapply the label after another actor; unrelated label events do not replace it',async()=>{
  const client=await alexApprovalCase({events:[
    {id:1,event:'labeled',label:{name:'alex-approved'},actor:{login:'other'}},
    {id:2,event:'unlabeled',label:{name:'alex-approved'},actor:{login:'other'}},
    {id:3,event:'labeled',label:{name:'alex-approved'},actor:{login:'alexander-bain'},created_at:'2026-11-02T00:01:00Z'},
    {id:4,event:'labeled',label:{name:'tier-b'},actor:{login:'other'}},
  ]});await client.run();assert.equal(client.created[0].conclusion,'success');
});

test('the exit requires the current label and policy file scope, and never audits Tier A',async()=>{
  for(const options of [
    {labels:[{name:'tier-b'}]},
    {files:[{filename:'tools/release/tier_b.cjs'}]},
    {labels:[{name:'alex-approved'}]},
  ]) {
    const client=await alexApprovalCase({...options,events:[{id:1,event:'labeled',label:{name:'alex-approved'},actor:{login:'alexander-bain'}}]});
    await client.run();
    assert.equal(client.created[0].conclusion,options.labels?.every(l=>l.name!=='tier-b')?'success':'failure');
    assert.equal(client.calls.filter(c=>c.method==='events').length,0);
    assert.equal(client.calls.filter(c=>c.method==='commit').length,0);
  }
});

test('unknown label attribution never publishes success',async()=>{
  const client=await alexApprovalCase({eventError:new Error('events unavailable')});
  await assert.rejects(client.run(),/events unavailable/);assert.equal(client.created.length,0);
});

test('a label approved on one head fails after a push until Alex reapplies it',async()=>{
  const events=[{id:1,event:'labeled',label:{name:'alex-approved'},actor:{login:'alexander-bain'},created_at:'2026-11-02T00:01:00Z'}];
  const client=await alexApprovalCase({events});
  await client.run();assert.equal(client.created.at(-1).conclusion,'success');
  client.pr.head.sha='new-head';client.headCommitDate='2026-11-02T00:02:00Z';
  await client.run();assert.equal(client.created.at(-1).conclusion,'failure');
  assert.match(client.created.at(-1).output.summary,/alex-approved predates the current head; re-apply after review/);
  events.push({id:2,event:'labeled',label:{name:'alex-approved'},actor:{login:'alexander-bain'},created_at:'2026-11-02T00:03:00Z'});
  await client.run();assert.equal(client.created.at(-1).conclusion,'success');
  assert.deepEqual(client.calls.filter(c=>c.method==='commit').map(c=>c.ref),['head','new-head','new-head']);
});

test('equal or unknown label/head dates cannot approve',async()=>{
  for(const [labeledAt,committedAt] of [
    ['2026-11-02T00:00:00Z','2026-11-02T00:00:00Z'],
    [undefined,'2026-11-02T00:00:00Z'],
    ['invalid','2026-11-02T00:00:00Z'],
    ['2026-11-02T00:01:00Z',undefined],
  ]) {
    const client=await alexApprovalCase({events:[{id:1,event:'labeled',label:{name:'alex-approved'},actor:{login:'alexander-bain'},created_at:labeledAt}]});
    client.headCommitDate=committedAt;await client.run();
    assert.equal(client.created.at(-1).conclusion,'failure');
    assert.match(client.created.at(-1).output.summary,/alex-approved predates the current head; re-apply after review/);
  }
});

test('an unavailable head commit never publishes success',async()=>{
  const client=await alexApprovalCase({commitError:new Error('commit unavailable'),events:[{id:1,event:'labeled',label:{name:'alex-approved'},actor:{login:'alexander-bain'},created_at:'2026-11-02T00:01:00Z'}]});
  await assert.rejects(client.run(),/commit unavailable/);assert.equal(client.created.length,0);
});
const openPRs=()=>Array.from({length:74},(_,i)=>({number:i+1,state:'open',user:{login:'author'},
  head:{sha:`head-${i+1}`},labels:i<6?[{name:'tier-b'}]:[]}));

for (const [eventName,payload] of [
  ['pull_request_target',{pull_request:{number:1}}],
  ['repository_dispatch',{client_payload:{pull_number:1}}],
  ['workflow_dispatch',{inputs:{pull_number:'1'}}],
]) test(`${eventName} evaluates only its PR, even with 74 open PRs`,async()=>{
  const {evaluate}=require(file);
  const {github,calls,created}=policyClient(openPRs());
  await evaluate(github,{repo,eventName,payload});
  assert.equal(calls.filter(c=>c.method==='list').length,0);
  assert.deepEqual(calls.filter(c=>c.pull_number).map(c=>c.pull_number),[1,1,1,1]);
  assert.equal(created.length,1);
  assert.equal(created[0].head_sha,'head-1');
  assert.equal(created[0].conclusion,'failure');
  assert.equal(calls.length,6);
});

test('a Tier-A event skips reviews and files and publishes success',async()=>{
  const {evaluate}=require(file);
  const {github,calls,created}=policyClient(openPRs());
  await evaluate(github,{repo,eventName:'pull_request_target',payload:{pull_request:{number:74}}});
  assert.equal(calls.filter(c=>['list','reviews','files'].includes(c.method)).length,0);
  assert.deepEqual(calls.filter(c=>c.method==='get').map(c=>c.pull_number),[74,74]);
  assert.equal(calls.length,4);
  assert.equal(created[0].conclusion,'success');
});

test('a 74-PR sweep stays linear and never refreshes or reads review scope for Tier A',async()=>{
  const {evaluate}=require(file);
  const {github,calls,created}=policyClient(openPRs());
  await evaluate(github,{repo,eventName:'schedule',payload:{}});
  assert.equal(calls.filter(c=>c.method==='list').length,2);
  assert.equal(calls.filter(c=>c.method==='get').length,12);
  assert.equal(calls.filter(c=>c.method==='reviews').length,6);
  assert.equal(calls.filter(c=>c.method==='files').length,6);
  assert.ok(calls.filter(c=>c.pull_number).every(c=>c.pull_number<=6));
  assert.equal(created.length,74);
  assert.equal(created.filter(c=>c.conclusion==='failure').length,6);
  assert.equal(created.filter(c=>c.conclusion==='success').length,68);
  assert.equal(calls.length,174);
});

test('an unscoped event cannot accidentally sweep every open PR',async()=>{
  const {evaluate}=require(file);
  for (const pull_number of [undefined,0,-1,'not-a-number']) {
    const {github,calls}=policyClient(openPRs());
    await assert.rejects(evaluate(github,{repo,eventName:'repository_dispatch',payload:{client_payload:{pull_number}}}),/number is required/);
    assert.equal(calls.length,0);
  }
});

test('membership churn retries once, then fails every observed head',async()=>{
  const {evaluate}=require(file);
  let version=1,changes=0,gets=0;const created=[];
  const current=()=>({number:1,state:'open',user:{login:'author'},head:{sha:`head-${version}`},labels:[]});
  const github={rest:{pulls:{get:async()=>{gets++;return {data:current()};},list:()=>{},listReviews:()=>{},listFiles:()=>{}},
    checks:{listForRef:()=>{},create:async result=>created.push(result)}},
    paginate:async fn=>{
      if(fn===github.rest.pulls.list)assert.fail('event must not list PRs');
      if(fn===github.rest.checks.listForRef && changes<2){changes++;version++;}
      return [];
    }};
  await evaluate(github,{repo,eventName:'pull_request_target',payload:{pull_request:{number:1}}});
  assert.equal(gets,4,'one initial and one final read per attempt, at most two attempts');
  const latest=new Map(created.map(check=>[check.head_sha,check]));
  assert.deepEqual([...latest.keys()].sort(),['head-1','head-2','head-3']);
  assert.ok([...latest.values()].every(check=>check.conclusion==='failure'));
});

test('the workflow uses a half-hour sweep and keeps per-PR events from coalescing each other',()=>{
  const workflow=fs.readFileSync(path.resolve(__dirname,'../../.github/workflows/tier-b.yml'),'utf8');
  assert.match(workflow,/cron: '\*\/30 \* \* \* \*'/);
  assert.match(workflow,/cancel-in-progress: false/);
  assert.ok(workflow.includes("github.event.pull_request.number || github.event.client_payload.pull_number || github.event.inputs.pull_number || 'sweep'"));
  assert.match(workflow,/pull_number:\s+description: Pull request to evaluate\s+required: true\s+type: number/);
});
