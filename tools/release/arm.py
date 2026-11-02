"""Preview the release loop's activation gates; enable it only with reviewed live proof."""
import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.error

import discover
import health
import platforms


def validate_baseline(proof,live):
    if proof.get('verdict')!='VERDICT PASS' or proof.get('provider') != 'heroku' or not re.fullmatch(r'[0-9a-f]{40}',proof.get('candidate_sha','')):
        raise ValueError('bootstrap requires a conclusive provider health PASS with a full source SHA')
    if proof.get('candidate_id')!=live.get('id') or proof['candidate_sha']!=live.get('sha'):
        raise ValueError('bootstrap proof is not the current exact provider release')


def publish_policy(master,enabled):
    row=platforms.github('/deployments','POST',{
        'ref':master,'auto_merge':False,'required_contexts':[],
        'environment':'release-loop-policy','production_environment':False,
        'payload':{'authority':'release-loop-policy-v1','fast_enabled':enabled,'master_sha':master},
    })
    platforms.github('/deployments/'+str(row['id'])+'/statuses','POST',{'state':'success','auto_inactive':False})


def set_flags(enabled):
    name = 'RELEASE_LOOP_FAST_ENABLED'
    value = 'true' if enabled else 'false'
    try:
        platforms.github('/actions/variables/'+name, 'PATCH', {'name':name, 'value':value})
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        platforms.github('/actions/variables', 'POST', {'name':name, 'value':value})


def arm(proof,master_current,control_verified,apply,disable=False):
    if not apply:
        return {'activation':'held','variables':['RELEASE_LOOP_FAST_ENABLED'],
                'requirements':['Alex master is current','known-good exact Heroku PASS receipt',
                                'CI deploy observation verified','complete worker logs available',
                                'Heroku rollback verified']}
    if disable:
        master=platforms.github('/branches/master')['commit']['sha']
        publish_policy(master,False)
        set_flags(False)
        return {'activation':'disabled','master_sha':master}
    if not master_current or not control_verified:
        raise ValueError('activation requires master-current confirmation and reviewed provider control proof')
    master=platforms.github('/branches/master')['commit']['sha']
    if proof.get('master_sha')!=master: raise ValueError('activation proof is for an older master')
    health.capture(dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=30))
    requirements={'heroku':['ci_deploy_observed','worker_logs_verified','rollback_verified']}
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
    publish_policy(master,True)
    set_flags(True)
    return {'activation':'enabled','master_sha':master}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true');parser.add_argument('--master-is-current',action='store_true')
    parser.add_argument('--provider-control-verified',action='store_true');parser.add_argument('--proof',type=pathlib.Path);parser.add_argument('--disable',action='store_true')
    args=parser.parse_args()
    proof=json.loads(args.proof.read_text()) if args.proof else {}
    print(json.dumps(arm(proof,args.master_is_current,args.provider_control_verified,args.apply,args.disable),indent=2))

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('Release loop activation refused: '+type(exc).__name__,file=sys.stderr);sys.exit(2)
