#!/usr/bin/env python3
"""Open the nine independent review PRs. Default is a local preview; never merges."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

REPO='alexander-bain/bainluck'
PACKETS=[
 (8,'live-path','/tmp/bainluck-wt-live-path','Live-path Python 3.11 gate and full-suite watchdog',True),
 (1,'release-loop','/tmp/bainluck-wt-loop','Prepare master protection and repository auto-merge',True),
 (2,'tier-b','/tmp/bainluck-wt-tier-b','Independent Tier-B review requirement',False),
 (3,'post-deploy-health','/tmp/bainluck-wt-health','Automatic post-deploy health and guarded rollback',True),
 (4,'slim-instructions','/tmp/bainluck-wt-docs','Slim shared agent instructions below 15 KB',True),
 (5,'day-zero-reset','/tmp/bainluck-wt-reset','Day 0 PR and issue reset with one weekly browser summary',False),
 (6,'archive-process','/tmp/bainluck-wt-archive','Prepare process archive after pause and settings freeze',False),
 (7,'testflight','/tmp/bainluck-wt-testflight','Tuesday TestFlight delivery for every iOS merge',False),
 (9,'retire-worktrees','/tmp/bainluck-wt-retire','Retire old worktrees after posting their inventory',False),
]


def run(args,**kwargs):
    return subprocess.run(args,text=True,capture_output=True,check=True,**kwargs).stdout.strip()


def packet(number,suffix,path,title,tier_b):
    branch='loop/'+suffix
    actual=run(['git','-C',path,'branch','--show-current'])
    if actual!=branch or actual=='master':raise ValueError('PR path is on an unexpected branch')
    if run(['git','-C',path,'status','--porcelain']):raise ValueError('commit the review work before publishing: '+path)
    raw=(Path(path)/f'docs/release-loop/pr-{number:02d}.md').read_text()
    paragraphs=[part.strip() for part in raw.split('\n\n') if part.strip() and not part.lstrip().startswith(('#','Labels:'))]
    if len(paragraphs)!=1:raise ValueError('PR description must be one plain-English paragraph')
    return {'number':number,'branch':branch,'path':path,'title':f'Release loop ({number}): {title}',
            'body':paragraphs[0],'labels':['tier-b'] if tier_b else [],
            'sha':run(['git','-C',path,'rev-parse','HEAD'])}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish',action='store_true')
    parser.add_argument('--output',type=Path,default=Path('/tmp/release-loop-published-prs.json'))
    args=parser.parse_args()
    packets=[packet(*row) for row in PACKETS]
    if not args.publish:
        print(json.dumps(packets,indent=2))
        return
    # User authorized these PRs and tier-b label, never a merge or master push.
    run(['gh','label','create','tier-b','--repo',REPO,'--color','B60205',
         '--description','Requires approval from someone other than the PR author','--force'])
    opened=[]
    try:
        for item in packets:
            run(['git','-C',item['path'],'push','origin',f'{item["branch"]}:refs/heads/{item["branch"]}'])
            existing=json.loads(run(['gh','pr','list','--repo',REPO,'--head',item['branch'],'--base','master',
                                     '--state','open','--json','url,number']))
            with tempfile.TemporaryDirectory(prefix='release-pr-body-') as temp:
                body=Path(temp)/'body.md';body.write_text(item['body']+'\n')
                if existing:
                    if len(existing)!=1:raise ValueError('multiple PRs for this branch')
                    run(['gh','pr','edit',str(existing[0]['number']),'--repo',REPO,'--body-file',str(body)])
                    url=existing[0]['url']
                else:
                    command=['gh','pr','create','--repo',REPO,'--base','master','--head',item['branch'],
                             '--title',item['title'],'--body-file',str(body),'--draft']
                    for label in item['labels']:command.extend(['--label',label])
                    url=run(command)
            opened.append({'item':item['number'],'branch':item['branch'],'sha':item['sha'],'url':url})
            args.output.write_text(json.dumps(opened,indent=2)+'\n')
            print(url)
    finally:
        args.output.write_text(json.dumps(opened,indent=2)+'\n')


if __name__=='__main__':main()
