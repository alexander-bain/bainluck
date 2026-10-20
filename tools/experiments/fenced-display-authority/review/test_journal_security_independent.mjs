// Pure local filesystem contracts. All writes stay in newly created private
// test directories; no network, PostgreSQL, browser, or production paths.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL,fileURLToPath} from 'node:url';

// Portable location: fenced-display-authority/review/test_journal_security_independent.mjs.
const root=process.env.SECURITY_ROOT||path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const modules=['fenced-display-authority','stream-backpressure','stream-reconnect'];
const digest=value=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
const line=value=>Buffer.from(JSON.stringify({value,hash:digest(value)})+'\n');
// Independent byte comparison through the same held descriptor, using explicit
// positions because append writes can leave the descriptor's shared offset at EOF.
const readBytes=fd=>{
  const bytes=Buffer.alloc(fs.fstatSync(fd).size);
  for(let offset=0;offset<bytes.length;){
    const n=fs.readSync(fd,bytes,offset,bytes.length-offset,offset);
    assert.ok(n>0,'complete positional byte read');
    offset+=n;
  }
  return bytes;
};
const readFileBytes=file=>{
  const fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);
  try{return readBytes(fd);}finally{fs.closeSync(fd);}
};
const trackedIo=()=>{
  const live=new Set();
  return {live,io:{
    openSync:(...args)=>{const fd=fs.openSync(...args);live.add(fd);return fd;},
    closeSync:fd=>{fs.closeSync(fd);live.delete(fd);},
  }};
};
const withDir=fn=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'journal-independent-'));
  try{return fn(dir);}finally{fs.rmSync(dir,{recursive:true,force:true});}
};
for(const name of modules){
  const {Journal}=await import(pathToFileURL(path.join(root,name,'src/journal.mjs')));
  const {Broker,frame}=await import(pathToFileURL(path.join(root,name,'src/broker.mjs')));
  test(`${name}: literal Unicode/space/percent path, private create, repeated positional recovery`,()=>withDir(dir=>{
    const f=path.join(dir,'Δ literal % journal.wal'),j=new Journal(f);
    try{
      assert.equal(fs.fstatSync(j.fd).mode&0o777,0o600);
      const first={kind:'first',text:'é漢字'},second={kind:'second',n:2};
      j.append(first);
      assert.deepEqual(j.read(),{records:[first],tornBytes:0});
      assert.deepEqual(j.read(),{records:[first],tornBytes:0});
      j.append(second);
      assert.deepEqual(j.read(),{records:[first,second],tornBytes:0});
      assert.deepEqual(readBytes(j.fd),Buffer.concat([line(first),line(second)]));
    }finally{j.close();}
    const reopened=new Journal(f);
    try{assert.equal(reopened.records.length,2);}finally{reopened.close();}
  }));
  test(`${name}: exact UTF-8 byte limit succeeds, next append and oversized reopen refuse unchanged`,()=>withDir(dir=>{
    const f=path.join(dir,'limit.wal'),value={kind:'x',text:'é漢'},bytes=line(value);
    const j=new Journal(f,{maxBytes:bytes.length});
    try{
      j.append(value);
      assert.equal(fs.fstatSync(j.fd).size,bytes.length);
      assert.throws(()=>j.append(value));
      assert.deepEqual(j.records,[value]);
    }finally{j.close();}
    const reopened=new Journal(f,{maxBytes:bytes.length});
    try{assert.deepEqual(reopened.records,[value]);}finally{reopened.close();}
    const tracker=trackedIo();
    assert.throws(()=>new Journal(f,{maxBytes:bytes.length-1,io:tracker.io}));
    assert.equal(tracker.live.size,0);
    assert.deepEqual(readFileBytes(f),bytes);
  }));
  test(`${name}: torn suffix poisons replay and append without truncating evidence`,()=>withDir(dir=>{
    const f=path.join(dir,'torn.wal'),value={kind:'x',n:1};
    const j=new Journal(f);j.append(value);j.close();
    fs.appendFileSync(f,'{"unfinished":"é');
    const original=readFileBytes(f),r=new Journal(f);
    try{
      assert.deepEqual(r.records,[value]);
      assert.equal(r.poisoned,true);
      assert.throws(()=>r.append({kind:'y'}));
      assert.deepEqual(readBytes(r.fd),original);
    }finally{r.close();}
  }));
  test(`${name}: corrupt recovery never leaks a descriptor or rewrites the file`,()=>withDir(dir=>{
    const f=path.join(dir,'bad.wal'),bytes=Buffer.from('{"value":{"kind":"x"},"hash":"bad"}\n');
    fs.writeFileSync(f,bytes,{flag:'wx',mode:0o600});
    const tracker=trackedIo();
    for(let n=0;n<3;n++)assert.throws(()=>new Journal(f,{io:tracker.io}));
    assert.equal(tracker.live.size,0);
    assert.deepEqual(readFileBytes(f),bytes);
  }));
  test(`${name}: reopening after failed creation directory fsync requires a successful directory sync`,()=>withDir(dir=>{
    const f=path.join(dir,'creation-retry.wal'),tracker=trackedIo();
    assert.throws(()=>new Journal(f,{io:{...tracker.io,fsyncSync:fd=>{
      if(fs.fstatSync(fd).isDirectory())throw Error('synthetic-directory-fsync-EIO');
      fs.fsyncSync(fd);
    }}}),/synthetic-directory-fsync-EIO/);
    assert.equal(tracker.live.size,0);
    let parentSyncs=0;
    const reopened=new Journal(f,{io:{fsyncSync:fd=>{
      if(fs.fstatSync(fd).isDirectory())parentSyncs++;
      fs.fsyncSync(fd);
    }}});
    try{
      assert.ok(parentSyncs>0,'a prior failed create must not bypass directory durability on reopen');
      reopened.append({kind:'recovered-create'});
      assert.equal(reopened.records.length,1);
    }finally{reopened.close();}
  }));
  test(`${name}: terminal survives restart with historical rows but no current or reseed`,()=>withDir(dir=>{
    const f=path.join(dir,'terminal.wal'),j=new Journal(f),b=new Broker({journal:j});
    const t=b.claim('owner');
    assert.equal(b.offer(t,frame(1,.6)).accepted,true);
    assert.equal(b.terminal(t).terminal,true);
    j.close();
    const rj=new Journal(f);
    try{
      const r=new Broker({journal:rj});
      assert.equal(r.status,'terminal');
      assert.equal(r.history.length,1);
      assert.equal(r.latest,null);
      assert.notEqual(r.boot,t.boot);
      assert.equal(r.claim('new').error,'terminal');
      assert.equal(r.offer(t,frame(2,.7)).error,'fenced-or-terminal');
    }finally{rj.close();}
  }));
  test(`${name}: partial writes complete exactly; fsync failure remains poisoned before publication`,()=>withDir(dir=>{
    const f=path.join(dir,'partial.wal'),j=new Journal(f);
    j.io={writeSync:(fd,bytes,offset,length)=>fs.writeSync(fd,bytes,offset,Math.min(length,3)),fsyncSync:fs.fsyncSync};
    const value={kind:'partial',text:'é漢字'};j.append(value);
    assert.deepEqual(readBytes(j.fd),line(value));
    j.close();
    const g=new Journal(path.join(dir,'eio.wal')),b=new Broker({journal:g}),t=b.claim('owner');
    try{
      g.io={writeSync:fs.writeSync,fsyncSync:()=>{throw Error('synthetic-fsync-EIO');}};
      assert.equal(b.offer(t,frame(1,.6)).error,'synthetic-fsync-EIO');
      assert.equal(b.stats.accepted,0);
      assert.equal(b.history.length,0);
      assert.equal(b.latest,null);
      assert.equal(b.status,'fatal');
      assert.equal(g.poisoned,true);
      assert.throws(()=>g.append({kind:'later'}));
    }finally{g.close();}
  }));
}
