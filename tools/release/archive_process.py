#!/usr/bin/env python3
"""Prepare process-archive only after lanes pause and the settings-freeze PR merges."""
import argparse
import hashlib
import json
import os
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
    if any(piece.startswith('YOUR-TURN') and piece!='YOUR-TURN.md' for piece in pieces):
        return True
    return any(piece.startswith('LANE-') and piece.endswith('.lock') for piece in pieces)


def git(*args, input=None, env=None, check=True):
    return subprocess.run(['git','-C',str(REPO),*args],input=input,text=True,
                          capture_output=True,check=check,env=env)


def files(source):
    found=[]
    targets=[source/'.claude/handoff',source/'artifacts']
    targets.extend(p for p in source.iterdir() if p.name.startswith('YOUR-TURN') and p.name!='YOUR-TURN.md')
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
        for path in candidates:
            relative=path.relative_to(source).as_posix()
            if not archive_path(relative):continue
            if path.stat(follow_symlinks=False).st_size>95*1024*1024:
                raise ValueError('archive includes a file requiring Git LFS; no source is removed')
            digest=fingerprint(path)
            if path.is_symlink():
                oid=git('hash-object','-w','--stdin',input=os.readlink(path)).stdout.strip()
                mode='120000'
            else:
                oid=git('hash-object','-w','--',str(path)).stdout.strip()
                mode='100755' if path.stat().st_mode & stat.S_IXUSR else '100644'
            git('update-index','--add','--cacheinfo',mode,oid,relative,env=env)
            receipt.append({'path':relative,'sha256':digest,'oid':oid})
        tree=git('write-tree',env=env).stdout.strip()
        commit=git('commit-tree',tree,'-p','origin/master',input='Archive retired Day 0 process files\n').stdout.strip()
        git('update-ref','refs/heads/process-archive',commit,'0'*40)
    git('push','origin','process-archive:refs/heads/process-archive')
    remote=git('ls-remote','origin','refs/heads/process-archive').stdout.split()[0]
    if remote!=commit:raise RuntimeError('archive push was not verified; no source removed')
    # Revalidate the complete snapshot before any removal, then only remove
    # retired process paths. Current YOUR-TURN.md and source code never qualify.
    for row in receipt:
        if fingerprint(source/row['path'])!=row['sha256']:
            raise RuntimeError('archive source changed after snapshot; no source removed')
    for row in receipt:
        (source/row['path']).unlink()
    for target in (source/'.claude/handoff',source/'artifacts'):
        if target.is_dir():
            for parent,dirs,names in os.walk(target,topdown=False):
                if not dirs and not names:
                    Path(parent).rmdir()
    # Tracked removals are proposed in this isolated PR branch. They do not
    # mutate the shared master index or branch.
    tracked=git('ls-files','-z').stdout.split('\0')
    to_remove=[path for path in tracked if path and archive_path(path)]
    if to_remove:git('rm','-r','--',*to_remove)
    ignore=REPO/'.gitignore'
    with ignore.open('a') as stream:
        stream.write('\n# Retired process data lives on process-archive\n.claude/handoff/\nartifacts/\nYOUR-TURN*.bak*\nLANE-*.lock\n')
    (REPO/'docs/release-loop/process-archive-receipt.json').write_text(json.dumps({'archive_commit':commit,'files':receipt},indent=2)+'\n')
    print(f'Archive verified on process-archive at {commit}; {len(receipt)} retired files removed; review isolated PR deletions before merge.')


if __name__=='__main__':
    main()
