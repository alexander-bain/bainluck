// Execute only the exact output-directory initializer, never benchmark/model work.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
const experiments=fileURLToPath(new URL('../../',import.meta.url));
for(const relative of [
 'fenced-display-authority/src/test.mjs',
 'fenced-display-authority/src/crash-matrix.mjs',
 'fenced-display-authority/src/benchmark.mjs',
 'stream-reconnect/tests/inherited-model.mjs',
 'stream-backpressure/tests/inherited-model.mjs'
]) test(relative+' uses private defaults without changing explicit OUT',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'output-default-review-'));
 try{
  const source=fs.readFileSync(path.join(experiments,relative),'utf8');
  const initializer=source.match(/const out=process\.env\.OUT\|\|fs\.mkdtempSync\(path\.join\(os\.tmpdir\(\),'[^']+'\)\);fs\.mkdirSync\(out,\{recursive:true,mode:0o700\}\);if\(!process\.env\.OUT\)console\.error\('Private experiment output: '\+out\);/);
  assert.ok(initializer,'expected auditable path-only initializer');
  const run=env=>{const logs=[];const out=vm.runInNewContext(initializer[0]+'out;',{fs,path,os:{tmpdir:()=>root},process:{env},console:{error:value=>logs.push(value)}});return {out,logs};};
  const a=run({}),b=run({});assert.notEqual(a.out,b.out);assert.equal(path.dirname(a.out),root);assert.equal(path.dirname(b.out),root);
  for(const x of [a,b]){assert.equal(fs.statSync(x.out).mode&0o777,0o700);assert.deepEqual(x.logs,['Private experiment output: '+x.out]);}
  const explicit=path.join(root,'caller-owned');fs.mkdirSync(explicit,{mode:0o705});fs.writeFileSync(path.join(explicit,'sentinel'),'unchanged');
  const mode=fs.statSync(explicit).mode;const c=run({OUT:explicit});assert.equal(c.out,explicit);assert.deepEqual(c.logs,[]);assert.equal(fs.statSync(explicit).mode,mode);assert.equal(fs.readFileSync(path.join(explicit,'sentinel'),'utf8'),'unchanged');
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});
