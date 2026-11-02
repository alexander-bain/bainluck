"""Build without assigning domains, then promote inside the Vercel Actions writer lock."""
import argparse
import os
import re
import subprocess
import sys
import time

import discover
import platforms
import rollback

FAST_STEP='Python 3.11 syntax, smoke test and change-scope selected tests'


def ci_ready(run,jobs):
    if run.get('status')=='completed': return run.get('conclusion')=='success'
    return any(job.get('name')=='fast-gate' and job.get('conclusion')=='success' and
               any(step.get('name')==FAST_STEP and step.get('conclusion')=='success' for step in job.get('steps',[]))
               for job in jobs)


def await_ci(run_id,sha):
    deadline=time.monotonic()+2400
    while time.monotonic()<deadline:
        run=platforms.github('/actions/runs/'+str(run_id))
        if run.get('head_branch')!='master' or run.get('event')!='push' or run.get('head_sha')!=sha:
            raise ValueError('only an exact master push CI run may deploy')
        jobs=platforms.github('/actions/runs/'+str(run_id)+'/jobs?per_page=100')['jobs']
        if ci_ready(run,jobs): return
        if run.get('status')=='completed': raise ValueError('CI failed; production promotion refused')
        time.sleep(15)
    raise TimeoutError('CI did not establish its release gate')


def ensure_ancestor(older,newer):
    return subprocess.run(['git','merge-base','--is-ancestor',older,newer],capture_output=True).returncode==0


def prepare(sha):
    if not re.fullmatch(r'[0-9a-f]{40}',sha): raise ValueError('full master source SHA required')
    live=platforms.current('vercel')
    rows=discover.receipt_rows('vercel')
    if sha in discover.failed_sources(rows): raise ValueError('failed source veto refuses the production draft')
    if live.get('sha')==sha or ensure_ancestor(sha,live.get('sha','')): return None
    if not ensure_ancestor(live.get('sha',''),sha): raise ValueError('current source ancestry is unknown')
    if not rollback.known_good_targets(rows,sha): raise ValueError('Vercel baseline must be bootstrapped')
    draft=platforms.vercel('/v13/deployments','POST',{
        'name':'bainluck','project':platforms.required('VERCEL_PROJECT_ID'),'target':'production',
        'autoAssignCustomDomains':False,
        'gitSource':{'type':'github','repoId':int(platforms.required('GITHUB_REPOSITORY_ID')),'ref':sha},
    })
    identity=draft['id'];deadline=time.monotonic()+1200
    while time.monotonic()<deadline:
        state=platforms.vercel('/v13/deployments/'+identity)
        if state.get('readyState')=='READY': return identity
        if state.get('readyState') in ('ERROR','CANCELED'): raise ValueError('production draft failed')
        time.sleep(10)
    raise TimeoutError('production draft did not complete')


def promote(sha,identity):
    # This function runs under vercel-production. The watchdog writes its SHA
    # veto in a separate job BEFORE waiting for this writer lock, so a failure
    # found during the draft build cannot be promoted later on a stale CI green.
    rows=discover.receipt_rows('vercel')
    if sha in discover.failed_sources(rows): raise ValueError('failed source veto refuses promotion')
    draft=platforms.candidate('vercel',identity)
    if draft.get('sha')!=sha: raise ValueError('production draft source does not match its gate')
    live=platforms.current('vercel')
    if live.get('sha')==sha or ensure_ancestor(sha,live.get('sha','')): return None
    if not ensure_ancestor(live.get('sha',''),sha): raise ValueError('promotion would rewind or has unknown ancestry')
    if not rollback.known_good_targets(rows,sha): raise ValueError('no verified non-failed rollback baseline')
    # Check the durable veto again immediately before the only domain mutation.
    if sha in discover.failed_sources(discover.receipt_rows('vercel')):
        raise ValueError('watchdog veto arrived before promotion')
    platforms.vercel('/v10/projects/'+platforms.required('VERCEL_PROJECT_ID')+'/promote/'+identity,'POST')
    rollback.verify_rollback('vercel',sha)
    if platforms.current('vercel')['id']!=identity: raise ValueError('production identity not confirmed')
    event=platforms.github('/deployments','POST',{
        'ref':sha,'auto_merge':False,'required_contexts':[],
        'environment':'Production-Vercel','production_environment':True,
        'payload':{'provider':'vercel','candidate_id':identity},
    })
    platforms.github('/deployments/'+str(event['id'])+'/statuses','POST',{
        'state':'success','environment_url':'https://bainluck.com','auto_inactive':False,
    })
    return identity


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sha',required=True);parser.add_argument('--ci-run');parser.add_argument('--candidate-id')
    parser.add_argument('--mode',choices=['gate','build','promote'],required=True)
    args=parser.parse_args();identity=None
    if args.mode=='gate':
        if not args.ci_run: raise ValueError('gate requires its CI run')
        await_ci(args.ci_run,args.sha)
    elif args.mode=='build': identity=prepare(args.sha)
    else:
        if not args.candidate_id: raise ValueError('promotion requires a prepared deployment ID')
        identity=promote(args.sha,args.candidate_id)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as out:
            out.write('deployed='+('true' if identity else 'false')+'\n')
            out.write('candidate_id='+(identity or '')+'\n')
    print('CI gate established' if args.mode=='gate' else ('Deployment '+identity if identity else 'Already live or superseded; no production change'))

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('Vercel release refused: '+type(exc).__name__,file=sys.stderr);sys.exit(2)
