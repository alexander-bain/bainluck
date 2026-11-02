#!/usr/bin/env python3
"""Prepare process-archive only after lanes pause and the settings-freeze PR merges."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]
SOURCE = Path('/Users/bain/bainluck')
GITHUB = 'alexander-bain/bainluck'


def authorized(paused, freeze_merged):
    if paused != 'lanes are paused' or not freeze_merged:
        raise ValueError('hold: Alex must confirm lanes are paused and Builder A settings-freeze PR must be merged')


def archive_path(path):
    pieces=Path(path).parts
    if path.startswith(('.claude/handoff/','artifacts/')):
        return True
    if any(re.fullmatch(r'YOUR-TURN(?:-REPAIR-STEPS)?-ARCHIVE-[0-9][A-Za-z0-9_.-]*|YOUR-TURN-[0-9]{8}\.md|YOUR-TURN\.md\.(?:bak|backup)(?:[-.].*)?',piece) for piece in pieces):
        return True
    return any(piece.startswith('LANE-') and piece.endswith('.lock') for piece in pieces)


def git(*args, input=None, env=None, check=True):
    return subprocess.run(['git','-C',str(REPO),*args],input=input,text=True,
                          capture_output=True,check=check,env=env)


def files(source):
    found=[]
    targets=[source/'.claude/handoff',source/'artifacts']
    targets.extend(p for p in source.iterdir() if p.name.startswith('YOUR-TURN') and archive_path(p.name))
    targets.extend(source.glob('LANE-*.lock'))
    for target in targets:
        if target.is_file() or target.is_symlink():
            found.append(target)
        elif target.is_dir():
            for parent,dirs,names in os.walk(target,followlinks=False):
                for directory in list(dirs):
                    p=Path(parent)/directory
                    if p.is_symlink():found.append(p);dirs.remove(directory)
                found.extend(Path(parent)/name for name in names)
    return sorted(set(found))


def fingerprint(path):
    data=os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
    return hashlib.sha256(data).hexdigest()



def snapshot_rows(candidates,source,scan):
    rows=[]
    for index,path in enumerate(candidates):
        relative=path.relative_to(source).as_posix()
        if not archive_path(relative):continue
        if path.stat(follow_symlinks=False).st_size>95*1024*1024:
            raise ValueError('archive includes a file requiring Git LFS; no source is removed')
        snapshot=scan/(str(index)+path.suffix)
        if path.is_symlink():
            snapshot.write_bytes(os.readlink(path).encode())
            mode='120000'
        else:
            shutil.copyfile(path,snapshot)
            mode='100755' if path.stat().st_mode & stat.S_IXUSR else '100644'
        rows.append({'path':relative,'snapshot':snapshot,'sha256':fingerprint(snapshot),'mode':mode})
    return rows


def verify_sources(rows,source):
    for row in rows:
        if fingerprint(source/row['path'])!=row['sha256']:
            raise RuntimeError('archive source changed after snapshot; no source removed')


def scan_archive(candidates,source,scan=None):
    scanner=shutil.which('gitleaks')
    if not scanner:raise ValueError('gitleaks is required before publishing ignored archive bytes')
    if scan is None:
        with tempfile.TemporaryDirectory(prefix='release-archive-scan-') as temp:
            return scan_archive(candidates,source,Path(temp))
    scan.mkdir(mode=0o700,exist_ok=True)
    rows=snapshot_rows(candidates,source,scan)
    result=subprocess.run([scanner,'dir',str(scan),'--redact','--no-banner','--exit-code','1',
                           '--report-format','json','--report-path',str(scan.parent/'redacted-scan.json')],
                          text=True,capture_output=True)
    if result.returncode!=0:
        raise ValueError('gitleaks did not pass the archive; no ref is published and no source removed')
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--lanes-paused-confirmation',default='')
    parser.add_argument('--settings-freeze-pr',type=int)
    parser.add_argument('--source-root',type=Path,default=SOURCE)
    args=parser.parse_args()
    if not args.apply:
        print('HELD: no archive branch, source file, lock or inbox is changed. After both confirmations, run --apply with --settings-freeze-pr NUMBER and --lanes-paused-confirmation "lanes are paused".')
        return
    if args.lanes_paused_confirmation != 'lanes are paused' or not args.settings_freeze_pr:
        parser.error('both the lanes-paused confirmation and settings-freeze PR number are required')
    # Verify the actual PR merge and ancestry, rather than trust an arbitrary flag.
    result=subprocess.run(['gh','pr','view',str(args.settings_freeze_pr),'--repo',GITHUB,
                           '--json','state,mergedAt,mergeCommit,title'],text=True,capture_output=True,check=True)
    pr=json.loads(result.stdout)
    authorized(args.lanes_paused_confirmation,pr['state']=='MERGED' and bool(pr['mergedAt']))
    if 'settings' not in pr['title'].lower() or 'freeze' not in pr['title'].lower():
        raise ValueError('specified PR is not the settings-freeze PR')
    git('fetch','origin','master')
    git('merge-base','--is-ancestor',pr['mergeCommit']['oid'],'origin/master')
    if git('show-ref','--verify','--quiet','refs/heads/process-archive',check=False).returncode==0:
        raise ValueError('process-archive already exists; refusing to overwrite it')
    # Snapshot ignored files straight into git objects. Never copy or write an
    # artifacts/ file or runner inbox. Source files stay put until the archive is pushed.
    source=args.source_root.resolve()
    if source != SOURCE.resolve():
        raise ValueError('source root must be the paused primary checkout')
    candidates=files(source)
    if not candidates:raise ValueError('archive source is empty')
    receipt=[]
    with tempfile.TemporaryDirectory(prefix='release-process-index-') as temp:
        env={**os.environ,'GIT_INDEX_FILE':str(Path(temp)/'index')}
        git('read-tree','origin/master',env=env)
        rows=scan_archive(candidates,source,Path(temp)/'scan')
        for row in rows:
            # Hash the exact private bytes Gitleaks scanned, never a fresh read
            # of an original process file that could have changed meanwhile.
            oid=git('hash-object','-w','--',str(row['snapshot'])).stdout.strip()
            git('update-index','--add','--cacheinfo',row['mode'],oid,row['path'],env=env)
            receipt.append({'path':row['path'],'sha256':row['sha256'],'oid':oid})
        verify_sources(receipt,source)
        tree=git('write-tree',env=env).stdout.strip()
        commit=git('commit-tree',tree,'-p','origin/master',input='Archive retired Day 0 process files\n').stdout.strip()
        git('update-ref','refs/heads/process-archive',commit,'0'*40)
    git('push','origin','process-archive:refs/heads/process-archive')
    remote=git('ls-remote','origin','refs/heads/process-archive').stdout.split()[0]
    if remote!=commit:raise RuntimeError('archive push was not verified; no source removed')
    # Revalidate the complete snapshot before any removal, then only remove
    # retired process paths. Current YOUR-TURN.md and source code never qualify.
    verify_sources(receipt,source)
    for row in receipt:
        (source/row['path']).unlink()
    for target in (source/'.claude/handoff',source/'artifacts'):
        if target.is_dir():
            for parent,dirs,names in os.walk(target,topdown=False):
                try:Path(parent).rmdir()
                except OSError:
                    if any(Path(parent).iterdir()):continue
                    raise
    # Tracked removals are proposed in this isolated PR branch. They do not
    # mutate the shared master index or branch.
    tracked=git('ls-files','-z').stdout.split('\0')
    archived={row['path'] for row in receipt}
    to_remove=[path for path in tracked if path in archived]
    if to_remove:git('rm','-r','--',*to_remove)
    ignore=REPO/'.gitignore'
    with ignore.open('a') as stream:
        stream.write('\n# Retired process data lives on process-archive\n.claude/handoff/\nartifacts/\nYOUR-TURN*.bak*\nLANE-*.lock\n')
    (REPO/'docs/release-loop/process-archive-receipt.json').write_text(json.dumps({'archive_commit':commit,'files':receipt},indent=2)+'\n')
    print(f'Archive verified on process-archive at {commit}; {len(receipt)} retired files removed; review isolated PR deletions before merge.')


if __name__=='__main__':
    main()
