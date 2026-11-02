"""One attended setup release after master-current, with full CI and already seeded baselines."""
import argparse
import datetime as dt
import os
import sys
import urllib.request

import discover
import health
import platforms
import rollback
import vercel_release


def verify_bootstrap_confirmation(master_current):
    if not master_current:raise ValueError('bootstrap is held until Alex confirms master is current')


def full_ci(run,jobs):
    if run.get('status')!='completed' or run.get('conclusion')!='success':return False
    if any(step.get('name')==vercel_release.FAST_STEP and step.get('conclusion')=='success' for job in jobs for step in job.get('steps',[])):
        return False
    full=[job for job in jobs if job.get('name','').startswith('backend-tests (') and job.get('conclusion')=='success' and
          any(step.get('name','').startswith('Run tests (shard ') and step.get('conclusion')=='success' for step in job.get('steps',[]))]
    return len(full)==4


def verify_full_master_ci(run_id,sha):
    run=platforms.github('/actions/runs/'+str(run_id))
    if run.get('event')!='push' or run.get('head_branch')!='master' or run.get('head_sha')!=sha:
        raise ValueError('bootstrap needs the exact master push CI run')
    if platforms.github('/branches/master')['commit']['sha']!=sha:raise ValueError('bootstrap source is not current master')
    attempt=run.get('run_attempt')
    if not isinstance(attempt,int) or attempt<1:raise ValueError('current CI attempt unknown')
    jobs=platforms.github('/actions/runs/'+str(run_id)+'/attempts/'+str(attempt)+'/jobs?per_page=100')['jobs']
    if not full_ci(run,jobs):raise ValueError('bootstrap needs executed full CI, never a fast-only or retained gate')


def validate_seeded(provider):
    live=platforms.current(provider);rows=discover.receipt_rows(provider)
    entry=discover.receipt_index(rows).get(live['id'])
    if not entry or entry.get('verdict')!='VERDICT PASS' or entry.get('candidate_sha')!=live.get('sha') or live['sha'] in discover.failed_sources(rows):
        raise ValueError('current exact provider baseline must be seeded before bootstrap')
    return live


def bootstrap(provider,sha,run_id,master_current):
    verify_bootstrap_confirmation(master_current)
    if os.environ.get('GITHUB_ACTIONS')!='true':raise ValueError('bootstrap must run in its serialized Actions writer job')
    verify_full_master_ci(run_id,sha)
    if provider=='vercel':original=validate_seeded(provider)
    else:
        original=platforms.current(provider)
        if not rollback.known_good_targets(discover.receipt_rows(provider),original.get('sha')):
            raise ValueError('Heroku bootstrap needs an already seeded rollback baseline')
    if sha in discover.failed_sources(discover.receipt_rows(provider)):raise ValueError('bootstrap source is vetoed')
    health.probe(provider)
    if provider=='vercel':
        try:
            identity=vercel_release.prepare(sha,bootstrap=True)
            if identity:vercel_release.promote(sha,identity,bootstrap=True)
            # Authenticated router-only batch proves the Vercel ingress is live
            # without forging worker startup or injecting health-check evidence.
            import base64
            raw=b'<158>1 2026-11-02T00:00:00.000Z host heroku router - - release-log-drain ingress probe'
            body=str(len(raw)).encode()+b' '+raw
            token=platforms.required('RELEASE_LOG_DRAIN_TOKEN')
            request=urllib.request.Request('https://bainluck.com/api/release-log-drain',data=body,method='POST',
                headers={'Authorization':'Basic '+base64.b64encode(('logplex:'+token).encode()).decode(),'Content-Type':'application/logplex-1'})
            with urllib.request.urlopen(request,timeout=20) as response:
                if response.status!=202:raise ValueError('authenticated drain ingress did not accept the probe')
            health.probe('vercel')
            return {'provider':provider,'candidate_id':platforms.current(provider)['id'],'bootstrap':'frontend routes deployed; warm durable history before Heroku bootstrap/arming'}
        except Exception:
            live=platforms.current('vercel')
            if live.get('sha')==sha and live['id']!=original['id']:
                rollback.rollback('vercel',sha,live['id'],original['id'])
            raise
    # Once the durable stream is warm, re-release the current exact master slug
    # under heroku-deploy. This creates a captured startup/A10 boundary while
    # the pre-bootstrap PASS remains available as a rollback target.
    health.capture(dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=30))
    if original.get('sha')!=sha:raise ValueError('Heroku bootstrap must re-release current exact master, not change its code')
    result=platforms.heroku('/releases','POST',{'slug':original['slug']['id']})
    return {'provider':provider,'candidate_id':result['id'],'bootstrap':'same binary released; existing health workflow now checks the durable window'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--provider',choices=['heroku','vercel'],required=True)
    parser.add_argument('--sha',required=True);parser.add_argument('--ci-run',required=True);parser.add_argument('--master-is-current',action='store_true')
    args=parser.parse_args()
    import json
    print(json.dumps(bootstrap(args.provider,args.sha,args.ci_run,args.master_is_current)))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('Bootstrap refused: '+type(exc).__name__,file=sys.stderr);sys.exit(2)
