import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';

// Pure filesystem/model fixtures only. No network, PostgreSQL, or timing claims.
// Run: node --test --test-concurrency=1 review/test_journal_security.mjs
// Optional SECURITY_ROOT points at tools/experiments in another candidate checkout.
const root=process.env.SECURITY_ROOT||fileURLToPath(new URL('../../',import.meta.url));
const labs=['fenced-display-authority','stream-backpressure','stream-reconnect'];
const fixture=t=>{const dir=fs.mkdtempSync(path.join(process.env.SECURITY_TMPDIR||os.tmpdir(),'journal-security-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));return dir;};
const fault=()=>Object.assign(Error('injected-EIO'),{code:'EIO'});
function trackedIO(overrides={}){
  const live=new Set(),events=[];
  const io={
    openSync(file,...args){const fd=fs.openSync(file,...args);live.add(fd);events.push({op:'open',fd,file,args});return fd;},
    closeSync(fd){fs.closeSync(fd);live.delete(fd);events.push({op:'close',fd});},
    fsyncSync(fd){fs.fsyncSync(fd);events.push({op:'fsync',fd});},
    ...overrides,
  };
  return {io,live,events};
}
for(const lab of labs){
  const {Journal,digest}=await import(pathToFileURL(path.join(root,lab,'src/journal.mjs')));
  const encoded=value=>JSON.stringify({value,hash:digest(value)})+'\n';
  await test(`${lab}: exclusive private create, durable inode then parent, one held descriptor`,t=>{
    const dir=fixture(t),file=path.join(dir,'literal % 雪.wal'),trace=trackedIO(),j=new Journal(file,{io:trace.io});t.after(()=>j.close());
    assert.equal(fs.statSync(file).mode&0o777,0o600);
    const fileOpens=trace.events.filter(e=>e.op==='open'&&e.file===file);assert.equal(fileOpens.length,1);
    const flags=fileOpens[0].args[0];for(const flag of ['O_RDWR','O_APPEND','O_CREAT','O_EXCL','O_NOFOLLOW'])assert.equal(flags&fs.constants[flag],fs.constants[flag]);
    const syncs=trace.events.filter(e=>e.op==='fsync');assert.equal(syncs.length,2);assert.equal(syncs[0].fd,j.fd);assert.notEqual(syncs[1].fd,j.fd);
    j.append({n:1});assert.deepEqual(j.read().records,[{n:1}]);assert.deepEqual(j.read().records,[{n:1}]);j.append({n:2});assert.deepEqual(j.read().records,[{n:1},{n:2}]);
    j.close();assert.equal(trace.live.size,0);j.close();
  });
  await test(`${lab}: existing reopen is no-follow, non-creating, and preserves permissions`,t=>{
    const dir=fixture(t),file=path.join(dir,'existing.wal');fs.writeFileSync(file,encoded({n:1}),{flag:'wx',mode:0o640});const mode=fs.statSync(file).mode;
    const trace=trackedIO(),j=new Journal(file,{io:trace.io});t.after(()=>j.close());
    const opened=trace.events.filter(e=>e.op==='open'&&e.file===file);assert.equal(opened.length,1);const flags=opened[0].args[0];
    assert.ok(flags&fs.constants.O_NOFOLLOW);assert.equal(flags&fs.constants.O_CREAT,0);assert.equal(trace.events.filter(e=>e.op==='fsync').length,2);
    assert.equal(fs.statSync(file).mode,mode);assert.deepEqual(j.records,[{n:1}]);
  });
  for(const kind of ['symlink','dangling-symlink','hardlink','directory'])await test(`${lab}: rejects preexisting ${kind} without modifying its target`,t=>{
    const dir=fixture(t),file=path.join(dir,'journal.wal'),target=path.join(dir,'target.wal');
    if(kind!=='dangling-symlink')fs.writeFileSync(target,encoded({target:true}),{flag:'wx',mode:0o600});
    if(kind==='hardlink')fs.linkSync(target,file);else if(kind==='directory')fs.mkdirSync(file);else fs.symlinkSync(target,file);
    const before=kind==='dangling-symlink'?null:fs.readFileSync(target),trace=trackedIO();
    assert.throws(()=>new Journal(file,{io:trace.io}));assert.equal(trace.live.size,0);
    if(before)assert.deepEqual(fs.readFileSync(target),before);else assert.equal(fs.existsSync(target),false);
  });
  for(const point of ['after-open','during-read'])await test(`${lab}: pathname replacement ${point} cannot separate recovery from append`,t=>{
    const dir=fixture(t),file=path.join(dir,'journal.wal'),held=path.join(dir,'original.wal');fs.writeFileSync(file,encoded({inode:'original'}),{flag:'wx',mode:0o600});
    let replaced=false;const swap=()=>{if(replaced)return;replaced=true;fs.renameSync(file,held);fs.writeFileSync(file,encoded({inode:'replacement'}),{flag:'wx',mode:0o600});};
    const io={openSync(p,...args){const fd=fs.openSync(p,...args);if(p===file&&point==='after-open')swap();return fd;},readSync(fd,...args){if(point==='during-read')swap();return fs.readSync(fd,...args);}};
    const j=new Journal(file,{io});t.after(()=>j.close());assert.deepEqual(j.records,[{inode:'original'}]);j.append({appended:true});
    assert.deepEqual(j.read().records,[{inode:'original'},{appended:true}]);assert.equal(fs.readFileSync(held,'utf8'),encoded({inode:'original'})+encoded({appended:true}));assert.equal(fs.readFileSync(file,'utf8'),encoded({inode:'replacement'}));
  });
  await test(`${lab}: replacement with a symlink between exclusive failure and reopen is refused`,t=>{
    const dir=fixture(t),file=path.join(dir,'journal.wal'),target=path.join(dir,'target.wal');fs.writeFileSync(file,encoded({n:1}));fs.writeFileSync(target,encoded({target:true}));
    const before=fs.readFileSync(target);let swapped=false;
    const trace=trackedIO();const open=trace.io.openSync;trace.io.openSync=(p,...args)=>{try{return open(p,...args);}catch(e){if(e.code==='EEXIST'&&!swapped){swapped=true;fs.renameSync(file,path.join(dir,'old.wal'));fs.symlinkSync(target,file);}throw e;}};
    assert.throws(()=>new Journal(file,{io:trace.io}));assert.equal(trace.live.size,0);assert.deepEqual(fs.readFileSync(target),before);
  });
  for(const unsupported of [undefined,0])await test(`${lab}: unavailable O_NOFOLLOW (${String(unsupported)}) fails before filesystem use`,t=>{
    const file=path.join(fixture(t),'no-create.wal');let opened=false;
    assert.throws(()=>new Journal(file,{io:{constants:{...fs.constants,O_NOFOLLOW:unsupported},openSync(){opened=true;throw fault();}}}),/journal-nofollow-unavailable/);assert.equal(opened,false);assert.equal(fs.existsSync(file),false);
  });
  for(const stage of ['create-open','existing-open','fstat','read','short-read','checksum','oversized','new-file-fsync','directory-open','directory-fsync'])await test(`${lab}: ${stage} constructor failure closes every acquired descriptor`,t=>{
    const dir=fixture(t),file=path.join(dir,'journal.wal'),existing=['existing-open','read','short-read','checksum','oversized'].includes(stage);
    if(existing)fs.writeFileSync(file,stage==='checksum'?'{"value":1,"hash":"bad"}\n':encoded({n:1}),{flag:'wx',mode:0o600});const before=existing?fs.readFileSync(file):null;
    const trace=trackedIO(),open=trace.io.openSync,sync=trace.io.fsyncSync;let syncCount=0;
    trace.io.openSync=(p,...args)=>{if(stage==='create-open'&&p===file)throw fault();if(stage==='existing-open'&&p===file&&!(args[0]&fs.constants.O_CREAT))throw fault();if(stage==='directory-open'&&p===dir)throw fault();return open(p,...args);};
    trace.io.fstatSync=fd=>{if(stage==='fstat')throw fault();return fs.fstatSync(fd);};
    trace.io.readSync=(...args)=>{if(stage==='read')throw fault();if(stage==='short-read')return 0;return fs.readSync(...args);};
    trace.io.fsyncSync=fd=>{syncCount++;if(stage==='new-file-fsync'&&syncCount===1||stage==='directory-fsync'&&syncCount===2)throw fault();return sync(fd);};
    assert.throws(()=>new Journal(file,{io:trace.io,maxBytes:stage==='oversized'?1:1024}));assert.equal(trace.live.size,0);if(before)assert.deepEqual(fs.readFileSync(file),before);
  });
  for(const failAt of [1,2])await test(`${lab}: failed creation sync ${failAt} cannot bypass inode/directory durability on reopen`,t=>{
    const file=path.join(fixture(t),'journal.wal'),failed=trackedIO();let count=0;
    failed.io.fsyncSync=fd=>{if(++count===failAt)throw fault();fs.fsyncSync(fd);};
    assert.throws(()=>new Journal(file,{io:failed.io}),/injected-EIO/);assert.equal(failed.live.size,0);assert.equal(fs.existsSync(file),true);
    const retry=trackedIO(),j=new Journal(file,{io:retry.io});t.after(()=>j.close());const syncs=retry.events.filter(e=>e.op==='fsync');
    assert.equal(syncs.length,2);assert.equal(syncs[0].fd,j.fd);assert.notEqual(syncs[1].fd,j.fd);j.append({retry:true});assert.deepEqual(j.read().records,[{retry:true}]);
  });
  await test(`${lab}: bounded positional reads tolerate short reads and preserve exact capacity`,t=>{
    const dir=fixture(t),file=path.join(dir,'journal.wal'),first={n:'雪'},second={n:2};fs.writeFileSync(file,encoded(first));
    const limit=Buffer.byteLength(encoded(first)+encoded(second)),positions=[];
    const j=new Journal(file,{maxBytes:limit,io:{readSync(fd,b,off,len,pos){positions.push(pos);return fs.readSync(fd,b,off,Math.min(3,len),pos);}}});t.after(()=>j.close());assert.equal(positions[0],0);
    j.append(second);assert.equal(fs.statSync(file).size,limit);assert.throws(()=>j.append({n:3}),/journal-capacity/);assert.equal(j.poisoned,false);assert.deepEqual(j.read().records,[first,second]);
  });
  await test(`${lab}: partial write failure poisons journal without claiming a record`,t=>{
    const file=path.join(fixture(t),'journal.wal'),j=new Journal(file);t.after(()=>j.close());let calls=0;
    j.io={writeSync(fd,b,off,len){if(calls++)throw fault();return fs.writeSync(fd,b,off,Math.min(3,len));},fsyncSync:fs.fsyncSync};
    assert.throws(()=>j.append({n:1}),/injected-EIO/);assert.equal(j.poisoned,true);assert.deepEqual(j.records,[]);assert.throws(()=>j.append({n:2}),/journal-unusable/);j.close();
    const reopened=new Journal(file);t.after(()=>reopened.close());assert.ok(reopened.read().tornBytes>0);assert.equal(reopened.poisoned,true);
  });
}
const schedule=path.join(root,'fenced-display-authority/src/schedule-matrix.mjs');
const runSchedule=(dir,out)=>{
  const env={...process.env,TMPDIR:dir,TMP:dir,TEMP:dir};if(out===undefined)delete env.OUT;else env.OUT=out;
  return spawnSync(process.execPath,[schedule],{env,encoding:'utf8',timeout:30000,maxBuffer:1024*1024});
};
await test('schedule report: default creates distinct private directories and exclusive 0600 reports',t=>{
  const dir=fixture(t);for(let n=0;n<2;n++){const r=runSchedule(dir);assert.equal(r.status,0,r.stderr);}
  const outputs=fs.readdirSync(dir);assert.equal(outputs.length,2);
  for(const name of outputs){const out=path.join(dir,name);assert.equal(fs.statSync(out).mode&0o777,0o700);assert.equal(fs.statSync(path.join(out,'schedule-matrix.json')).mode&0o777,0o600);const summary=JSON.parse(fs.readFileSync(path.join(out,'schedule-matrix.json'),'utf8'));assert.equal(summary.randomized.operations,30000);}
});
for(const kind of ['regular','symlink','dangling-symlink'])await test(`schedule report: refuses preexisting ${kind} and never changes parent permissions`,t=>{
  const dir=fixture(t),out=path.join(dir,'explicit-output');fs.mkdirSync(out,{mode:0o750});const mode=fs.statSync(out).mode,report=path.join(out,'schedule-matrix.json'),target=path.join(dir,'target.json');
  if(kind==='regular')fs.writeFileSync(report,'preserve-report',{flag:'wx',mode:0o600});else {if(kind==='symlink')fs.writeFileSync(target,'preserve-target',{flag:'wx',mode:0o600});fs.symlinkSync(target,report);}
  const r=runSchedule(dir,out);assert.notEqual(r.status,0);assert.match(r.stderr,/EEXIST/);assert.equal(fs.statSync(out).mode,mode);
  if(kind==='regular')assert.equal(fs.readFileSync(report,'utf8'),'preserve-report');else if(kind==='symlink')assert.equal(fs.readFileSync(target,'utf8'),'preserve-target');else assert.equal(fs.existsSync(target),false);
});
