import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
export const digest = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
// Single writer, existing surviving filesystem, complete-prefix recovery only.
// Every successful append fsyncs before return. No power-loss/host-loss guarantee.
export class Journal {
  constructor(file, {maxBytes=64*1024*1024, io=fs}={}) {
    this.file=file; this.io=io; this.maxBytes=maxBytes; this.poisoned=false;
    if(!fs.existsSync(file)){const f=fs.openSync(file,'wx',0o600);fs.closeSync(f);const d=fs.openSync(path.dirname(file),'r');fs.fsyncSync(d);fs.closeSync(d);}
    const r=this.read();this.records=r.records;this.poisoned=r.tornBytes>0;this.fd=fs.openSync(file,'a');
  }
  read(){const bytes=fs.readFileSync(this.file);const end=bytes.lastIndexOf(10)+1;const records=[];
    for(const line of bytes.subarray(0,end).toString().split('\n').filter(Boolean)){const r=JSON.parse(line);if(digest(r.value)!==r.hash)throw Error('journal-checksum');records.push(r.value);}
    return {records,tornBytes:bytes.length-end};}
  append(value){if(this.poisoned)throw Error('journal-unusable');const b=Buffer.from(JSON.stringify({value,hash:digest(value)})+'\n');
    if(fs.fstatSync(this.fd).size+b.length>this.maxBytes)throw Error('journal-capacity');
    try{let off=0;while(off<b.length){let n=this.io.writeSync(this.fd,b,off,b.length-off);if(n<=0)throw Error('journal-zero-write');off+=n;}this.io.fsyncSync(this.fd);this.records.push(structuredClone(value));}
    catch(e){this.poisoned=true;throw e;}}
  close(){if(this.fd!==undefined){fs.closeSync(this.fd);this.fd=undefined;}}
}
