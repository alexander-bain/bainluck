import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
export const digest = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
// Single writer, existing surviving filesystem, complete-prefix recovery only.
// The caller must control/trust the parent directory and its ancestors. O_NOFOLLOW
// protects the final component, not directory traversal or the pathname's survival.
// Existing multi-link files are rejected; this is not a concurrent-writer lock.
// Recovery and append use one held descriptor, never a checked-and-reopened path.
// Every successful append fsyncs before return. No power-loss/host-loss guarantee.
export class Journal {
  constructor(file, {maxBytes=64*1024*1024, io=fs}={}) {
    this.file=file; this.io=io; this.maxBytes=maxBytes; this.poisoned=false;
    const ops={...fs,...io}, c=ops.constants;
    if(!Number.isInteger(c.O_NOFOLLOW)||c.O_NOFOLLOW===0)throw Error('journal-nofollow-unavailable');
    // O_NONBLOCK prevents a non-regular existing file (for example a FIFO) from
    // blocking the open before fstat can reject it. It has no effect on regular files.
    const flags=c.O_RDWR|c.O_APPEND|c.O_NOFOLLOW|(c.O_NONBLOCK??0);
    try {
      try {this.fd=ops.openSync(file,flags|c.O_CREAT|c.O_EXCL,0o600);}
      catch(error){if(error.code!=='EEXIST')throw error;this.fd=ops.openSync(file,flags);}
      const stat=ops.fstatSync(this.fd);
      if(!stat.isFile())throw Error('journal-not-regular');
      if(stat.nlink!==1)throw Error('journal-not-single-link');
      const r=this.read();
      // Sync on every admission, including reopening after a failed create/sync.
      // Make the held inode durable before its directory entry; do not reopen it.
      ops.fsyncSync(this.fd);
      const dir=ops.openSync(path.dirname(file),c.O_RDONLY|(c.O_DIRECTORY??0));
      try{ops.fsyncSync(dir);}finally{ops.closeSync(dir);}
      this.records=r.records;this.poisoned=r.tornBytes>0;
    } catch(error) {
      if(this.fd!==undefined){
        const fd=this.fd;this.fd=undefined;
        try{ops.closeSync(fd);}catch(closeError){throw new AggregateError([error,closeError],'journal-constructor-cleanup');}
      }
      throw error;
    }
  }
  read(){
    const ops={...fs,...this.io}, size=ops.fstatSync(this.fd).size;
    if(size>this.maxBytes)throw Error('journal-capacity');
    const bytes=Buffer.alloc(size);
    // Explicit positions leave the shared file offset unchanged, including after
    // appends, so repeated recovery reads always start from byte zero.
    for(let off=0;off<size;){const n=ops.readSync(this.fd,bytes,off,size-off,off);if(n<=0)throw Error('journal-short-read');off+=n;}
    const end=bytes.lastIndexOf(10)+1,records=[];
    for(const line of bytes.subarray(0,end).toString().split('\n').filter(Boolean)){const r=JSON.parse(line);if(digest(r.value)!==r.hash)throw Error('journal-checksum');records.push(r.value);}
    return {records,tornBytes:bytes.length-end};
  }
  append(value){if(this.poisoned)throw Error('journal-unusable');const b=Buffer.from(JSON.stringify({value,hash:digest(value)})+'\n'),ops={...fs,...this.io};
    if(ops.fstatSync(this.fd).size+b.length>this.maxBytes)throw Error('journal-capacity');
    try{let off=0;while(off<b.length){let n=ops.writeSync(this.fd,b,off,b.length-off);if(n<=0)throw Error('journal-zero-write');off+=n;}ops.fsyncSync(this.fd);this.records.push(structuredClone(value));}
    catch(e){this.poisoned=true;throw e;}}
  close(){if(this.fd!==undefined){const fd=this.fd;this.fd=undefined;(this.io.closeSync??fs.closeSync)(fd);}}
}
