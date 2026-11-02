"""Preview the release loop's activation gates; enable it only with reviewed live proof."""
import argparse
import base64
import json
import pathlib
import re
import sys
import urllib.error

import discover
import health
import platforms


def validate_baseline(proof,live):
    if proof.get('verdict')!='VERDICT PASS' or proof.get('provider') not in ('heroku','vercel') or not re.fullmatch(r'[0-9a-f]{40}',proof.get('candidate_sha','')):
        raise ValueError('bootstrap requires a conclusive provider health PASS with a full source SHA')
    if proof.get('candidate_id')!=live.get('id') or proof['candidate_sha']!=live.get('sha'):
        raise ValueError('bootstrap proof is not the current exact provider release')


def arm(proof,master_current,control_verified,apply):
    if not apply:
        return {'activation':'held','variables':['RELEASE_LOOP_VERCEL_ENABLED','RELEASE_LOOP_FAST_ENABLED'],
                'requirements':['Alex master is current','known-good exact provider PASS receipts',
                                'signed Heroku delivery seen in Actions','durable worker startup logs available',
                                'Vercel Git master auto deployment disabled','production draft does not move domains',
                                'Actions promotion and rollback APIs verified on the live project']}
    if not master_current or not control_verified:
        raise ValueError('activation requires master-current confirmation and reviewed provider control proof')
    master=platforms.github('/branches/master')['commit']['sha']
    if proof.get('master_sha')!=master: raise ValueError('activation proof is for an older master')
    config=platforms.github('/contents/frontend/vercel.json?ref=master')
    config=json.loads(base64.b64decode(config['content']))
    if config.get('git',{}).get('deploymentEnabled',{}).get('master') is not False:
        raise ValueError('master Vercel Git auto-deployment has not been disabled')
    project=platforms.vercel('/v9/projects/'+platforms.required('VERCEL_PROJECT_ID'))
    if project.get('rootDirectory')!='frontend': raise ValueError('Vercel root does not match the controlled config')
    requirements={'heroku':['signed_event_seen','durable_worker_logs_verified','rollback_verified'],
                  'vercel':['git_auto_deploy_disabled_verified','draft_domains_unchanged_verified','actions_promotion_verified','rollback_verified']}
    for provider,checks in requirements.items():
        block=proof.get(provider,{})
        if any(block.get(check) is not True for check in checks):
            raise ValueError('provider control proof is incomplete: '+provider)
        baseline=block.get('baseline',{});live=platforms.current(provider)
        validate_baseline(baseline,live)
        health.probe(provider)
        rows=discover.receipt_rows(provider)
        if any(isinstance(row.get('payload'),dict) and row['payload'].get('candidate_sha')==live['sha'] and row['payload'].get('verdict') in ('ROLLBACK REQUESTED','ROLLED BACK','VERDICT FAIL') for row in rows):
            raise ValueError('failed source cannot be bootstrapped from another release ID')
        existing=discover.receipt_index(rows).get(live['id'])
        if existing and existing['verdict'] in ('ROLLBACK REQUESTED','ROLLED BACK','VERDICT FAIL'):
            raise ValueError('failed source cannot be bootstrapped as healthy')
        if not existing or existing.get('candidate_sha')!=live['sha']: discover.record(provider,live,'VERDICT PASS')
    webhooks=platforms.heroku('/webhooks')
    if not any(row.get('url')=='https://bainluck.com/api/release-webhook' and 'api:release' in row.get('include',[]) for row in webhooks):
        raise ValueError('Heroku release webhook is not configured')
    runs=platforms.github('/actions/workflows/post-deploy-health.yml/runs?event=repository_dispatch&status=success&per_page=20')['workflow_runs']
    if not runs: raise ValueError('signed Heroku event has not produced a successful health workflow')
    for name in ('RELEASE_LOOP_VERCEL_ENABLED','RELEASE_LOOP_FAST_ENABLED'):
        try: platforms.github('/actions/variables/'+name,'PATCH',{'name':name,'value':'true'})
        except urllib.error.HTTPError as exc:
            if exc.code!=404: raise
            platforms.github('/actions/variables','POST',{'name':name,'value':'true'})
    return {'activation':'enabled','master_sha':master}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true');parser.add_argument('--master-is-current',action='store_true')
    parser.add_argument('--provider-control-verified',action='store_true');parser.add_argument('--proof',type=pathlib.Path)
    args=parser.parse_args()
    proof=json.loads(args.proof.read_text()) if args.proof else {}
    print(json.dumps(arm(proof,args.master_is_current,args.provider_control_verified,args.apply),indent=2))

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('Release loop activation refused: '+type(exc).__name__,file=sys.stderr);sys.exit(2)
