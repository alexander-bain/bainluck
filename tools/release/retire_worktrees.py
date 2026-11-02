#!/usr/bin/env python3
"""Inventory and retire clean merged personal worktrees, preserving live tmp trees."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOTS = (Path('/Users/bain/.codex-personal/worktrees'),
         Path('/Users/bain/.codex-personal/private-artifacts'))
REPO = Path(__file__).resolve().parents[2]


def git(*args, path=REPO, check=True):
    return subprocess.run(['git','-C',str(path),*args],text=True,capture_output=True,check=check)


def personal(path):
    resolved = Path(path).resolve()
    return any(root == resolved or root in resolved.parents for root in ROOTS)


def eligible(row):
    return personal(row['path']) and (row['merged'] or row.get('abandoned',False)) and row['valid'] and not row['locked']


def disk_worktrees(root, depth=0):
    # Only inspect the process directories, stopping at a repository boundary.
    # Never descend into source trees, node_modules or artifacts inside a tree.
    if depth > 5 or not root.is_dir() or root.is_symlink():
        return []
    if (root/'.git').exists():
        return [root]
    found=[]
    for entry in root.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            found.extend(disk_worktrees(entry,depth+1))
    return found


def inventory():
    master = git('rev-parse','master').stdout.strip()
    # One ancestry traversal, rather than hundreds of repeated graph reads.
    ancestors = set(git('rev-list',master).stdout.splitlines())
    raw = git('worktree','list','--porcelain').stdout
    records={}
    for block in raw.strip().split('\n\n'):
        fields = dict(line.partition(' ')[::2] for line in block.splitlines())
        path=fields.get('worktree','')
        if not personal(path):
            continue
        records[path]={'path':path,'branch':fields.get('branch','').removeprefix('refs/heads/'),
                       'head':fields.get('HEAD'),'locked':'locked' in fields,'valid':Path(path).is_dir(),
                       'merged':fields.get('HEAD') in ancestors,'registered':True}
    for root in ROOTS:
        for path in disk_worktrees(root):
            if str(path) in records:
                continue
            head = git('rev-parse','HEAD',path=path,check=False)
            branch = git('branch','--show-current',path=path,check=False)
            records[str(path)]={'path':str(path),'branch':branch.stdout.strip(),'head':head.stdout.strip(),
                                'locked':False,'valid':head.returncode==0,'merged':head.stdout.strip() in ancestors,
                                'registered':False}
    return {'master':master,'rows':sorted(records.values(),key=lambda row:row['path'])}



def inventory_markdown(manifest):
    fields=('path','branch','head','merged','valid','locked','abandoned')
    stable={'master':manifest['master'],'rows':[{key:row.get(key) for key in fields} for row in manifest['rows']]}
    digest=hashlib.sha256(json.dumps(stable,sort_keys=True).encode()).hexdigest()
    lines=[f'<!-- worktree-inventory:{digest} -->',f'Inventory against master `{manifest["master"]}`.',
           '', '| worktree | branch | merged into master |','|---|---|---|']
    for row in manifest['rows']:
        path=row['path'].replace('/Users/bain/','~/').replace('|',r'\|')
        branch=(row.get('branch') or 'detached').replace('|',r'\|')
        state='yes' if row['merged'] else 'no (Day 0 reset abandoned)' if row.get('abandoned') else 'no'
        lines.append(f'| {path} | {branch} | {state} |')
    text='\n'.join(lines)
    if len(text)>59000:raise ValueError('inventory exceeds one GitHub comment; publish a linked file before retirement')
    return text


def publication_matches(comments,manifest):
    expected=inventory_markdown(manifest).strip()
    return any(str(comment.get('body','')).strip()==expected for comment in comments)


def require_publication(pr,manifest):
    result=subprocess.run(['gh','api',f'repos/alexander-bain/bainluck/issues/{pr}/comments?per_page=100',
                           '--paginate','--slurp'],text=True,capture_output=True,check=True)
    comments=[comment for page in json.loads(result.stdout) for comment in page]
    if not publication_matches(comments,manifest):
        raise ValueError('hold: this exact inventory must be posted on its PR before removing worktrees')



def reset_abandoned(branch,head):
    if not branch:return False
    result=subprocess.run(['gh','pr','list','--repo','alexander-bain/bainluck','--head',branch,
                           '--state','all','--limit','30','--json','number,state,mergedAt,headRefOid'],
                          capture_output=True,text=True,check=True)
    pulls=json.loads(result.stdout)
    if not pulls or any(pr['state']=='OPEN' for pr in pulls):return False
    latest=max(pulls,key=lambda pr:pr['number'])
    if latest['state']!='CLOSED' or latest['mergedAt'] or latest['headRefOid']!=head:return False
    result=subprocess.run(['gh','api',f'repos/alexander-bain/bainluck/issues/{latest["number"]}/comments?per_page=100',
                           '--paginate','--slurp'],capture_output=True,text=True,check=True)
    return any(comment.get('body','').strip()=='superseded by the Day 0 reset; reopen if still wanted'
               for page in json.loads(result.stdout) for comment in page)


def active_directories():
    result = subprocess.run(['lsof','-a','-d','cwd','-F','n'],text=True,capture_output=True)
    if result.returncode not in (0,1):
        raise RuntimeError('cannot inspect active working directories')
    return [line[1:] for line in result.stdout.splitlines() if line.startswith('n/')]


def retire(manifest, delete_remote=False):
    active = active_directories()
    for row in manifest['rows']:
        row['action']='kept'
        if not eligible(row) or not row['registered']:
            continue
        path=Path(row['path'])
        if any(directory==str(path) or directory.startswith(str(path)+'/') for directory in active):
            row['action']='kept: active process'
            continue
        # No force removal: tracked/untracked user work makes this a refusal.
        status=git('status','--porcelain','--untracked-files=all',path=path)
        if status.stdout.strip():
            row['action']='kept: local changes'
            continue
        ignored=git('status','--porcelain','--ignored=matching','--untracked-files=normal',path=path).stdout.splitlines()
        expendable={'node_modules','.next','venv','.venv','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache','.DS_Store'}
        if any(not any(piece in expendable for piece in line[3:].strip('"').split('/')) for line in ignored):
            row['action']='kept: ignored local files'
            continue
        if git('rev-parse','HEAD',path=path).stdout.strip()!=row['head']:
            row['action']='kept: moved since inventory'
            continue
        if git('merge-base','--is-ancestor',row['head'],'master',check=False).returncode!=0 and not (row.get('abandoned') and reset_abandoned(row['branch'],row['head'])):
            row['action']='kept: no longer merged'
            continue
        removed=git('worktree','remove',str(path),check=False)
        if removed.returncode:
            row['action']='kept: removal refused'
            row['error']=removed.stderr.strip()
            continue
        row['action']='removed'
        branch=row['branch']
        if delete_remote and branch and branch!='master':
            # Delete only the exact remote head that was classified as merged.
            # A remote branch that advanced or has an open PR is preserved.
            remote=git('ls-remote','origin',f'refs/heads/{branch}').stdout.split()
            if not remote:
                row['remote_action']='already absent'
                continue
            if remote[0]!=row['head']:
                row['remote_action']='kept: remote advanced'
                continue
            prs=subprocess.run(['gh','pr','list','--repo','alexander-bain/bainluck',
                                '--head',branch,'--state','open','--json','number'],
                               capture_output=True,text=True,check=True)
            if json.loads(prs.stdout):
                row['remote_action']='kept: open PR'
                continue
            git('push',f'--force-with-lease=refs/heads/{branch}:{row["head"]}',
                'origin',f':refs/heads/{branch}')
            row['remote_action']='deleted'
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--delete-remote',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--inventory-pr',type=int)
    parser.add_argument('--publish-pr',type=int)
    parser.add_argument('--include-reset-abandoned',action='store_true')
    args=parser.parse_args()
    if args.apply and not args.inventory_pr:
        parser.error('--apply requires --inventory-pr NUMBER and a verified posted inventory')
    manifest=inventory()
    if args.include_reset_abandoned:
        for row in manifest['rows']:
            if not row['merged']:
                row['abandoned']=reset_abandoned(row['branch'],row['head'])
    args.output.write_text(json.dumps(manifest,indent=2)+'\n')
    if args.publish_pr:
        subprocess.run(['gh','api','--method','POST',f'repos/alexander-bain/bainluck/issues/{args.publish_pr}/comments','--input','-'],input=json.dumps({'body':inventory_markdown(manifest)}),text=True,capture_output=True,check=True)
    if args.apply:
        require_publication(args.inventory_pr,manifest)
        try:
            retire(manifest,args.delete_remote)
        finally:
            # Keep the receipt even if GitHub becomes unavailable mid-reset.
            args.output.write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'{len(manifest["rows"])} worktrees; {sum(r["merged"] for r in manifest["rows"])} merged; '
          f'{sum(r.get("action")=="removed" for r in manifest["rows"])} removed')


if __name__=='__main__':
    main()
