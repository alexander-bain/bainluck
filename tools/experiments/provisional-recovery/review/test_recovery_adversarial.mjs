import {fileURLToPath} from 'node:url';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {WAL, Owner, Client, frame, hash} from '../src/candidate.mjs';

const root = process.env.REVIEW_TMP || fileURLToPath(new URL('../runtime/independent-review/', import.meta.url));
fs.mkdirSync(root, {recursive:true});
const token = {stream:'independent-review', epoch:'review-epoch', generation:1};
const job = seq => ({...token, seq, payload:frame(seq), hash:hash(frame(seq))});
const fake = {persist:async j=>({hash:j.hash,receipt:'synthetic-receipt'})};

await test('a torn old WAL suffix cannot corrupt a newly accepted fsynced record', () => {
  const file = path.join(fs.mkdtempSync(path.join(root,'torn-append-')),'log.wal');
  const initial = new WAL(file);
  initial.append(job(1));
  initial.close();
  fs.appendFileSync(file, '{"job":');
  let next;
  try { next = new WAL(file); }
  catch (e) {
    assert.match(String(e), /torn|repair|corrupt|quarantine|unusable/);
    return; // Refusing a damaged WAL is a safe alternative to explicit repair.
  }
  let accepted = false;
  try { next.append(job(2)); accepted = true; }
  catch (e) { assert.match(String(e), /torn|repair|corrupt|quarantine|unusable/); }
  try {
    const recovered = next.read();
    assert.deepEqual(recovered.jobs.map(j=>j.seq), accepted ? [1,2] : [1]);
  } finally { next.close(); }
});

await test('new publications must name the exact synthetic instrument, not just string fields', async () => {
  for (const instrument of [{}, {provider:'x',market:'x',token:'x',outcome:'x'}, {...frame(1).instrument,outcome:'no'}]) {
    const messages=[];
    const owner=new Owner({token,store:fake,publish:m=>messages.push(m)});
    const result=owner.offer({...frame(1),instrument});
    await owner.drain();
    assert.equal(result.error,'invalid');
    assert.equal(messages.length,0);
  }
});

await test('copied payload hash cannot bless a changed source identity on the client', () => {
  const client=new Client();
  client.connect({...token,terminal:false},{...token,available:true,revision:0,entries:[]});
  const original=frame(1);
  const changed=structuredClone(original);
  changed.instrument.outcome='no';
  const result=client.accept({kind:'publication',...token,seq:1,payload:changed,hash:hash(original),state:'pending',revision:1});
  assert.ok(result.error);
  assert.equal(client.current,null);
});

await test('client refuses unknown persistence states without a chart/status mutation', () => {
  const client=new Client();
  client.connect({...token,terminal:false},{...token,available:true,revision:0,entries:[]});
  const message={kind:'publication',...token,seq:1,payload:frame(1),hash:hash(frame(1)),state:'pending',revision:1};
  assert.equal(client.accept(message).displayed,true);
  const before=JSON.stringify(client.current);
  const result=client.accept({...message,kind:'persistence',state:'invented-state',revision:2});
  assert.ok(result.error);
  assert.equal(JSON.stringify(client.current),before);
  assert.equal(client.points.length,1);
});

await test('rejected or irrelevant high-revision messages cannot poison the client cursor', () => {
  for (const mutation of ['invalid-state','changed-payload','unmatched-ack','older-publication']) {
    const client=new Client();
    client.connect({...token,terminal:false},{...token,available:true,revision:0,entries:[]});
    const base={kind:'publication',...token,seq:1,payload:frame(1),hash:hash(frame(1)),state:'pending',revision:1};
    assert.equal(client.accept(base).displayed,true);
    const bad={...base,revision:999999};
    if (mutation==='invalid-state') bad.state='made-up';
    if (mutation==='changed-payload') bad.payload={...base.payload,p:.9};
    if (mutation==='unmatched-ack') {bad.kind='persistence';bad.seq=999;}
    client.accept(bad);
    assert.equal(client.revision,1,mutation);
    const next={...base,seq:2,payload:frame(2,.6),hash:hash(frame(2,.6)),revision:2};
    assert.equal(client.accept(next).displayed,true,mutation);
    assert.equal(client.current.seq,2);
    assert.equal(client.current.p,.6);
  }
});
