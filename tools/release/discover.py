"""Find production releases not yet recorded by this loop; reconcile external releases too."""
import argparse
import json
import os
import sys

import platforms


def receipts(provider):
    rows=platforms.github('/deployments?environment=release-health-'+provider+'&per_page=100')
    return {row.get('payload',{}).get('candidate_id') for row in rows
            if isinstance(row.get('payload'),dict) and row['payload'].get('verdict')}


def record(provider,candidate,verdict):
    row=platforms.github('/deployments','POST',{
        'ref':candidate['sha'],'auto_merge':False,'required_contexts':[],
        'environment':'release-health-'+provider,'production_environment':False,
        'payload':{'candidate_id':candidate['id'],'verdict':verdict},
        'description':'Release loop: '+verdict[:80]})
    platforms.github('/deployments/'+str(row['id'])+'/statuses','POST',{
        'state':'success' if verdict=='VERDICT PASS' else 'failure',
        'description':verdict[:140],'auto_inactive':False})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--provider',choices=['heroku','vercel','both'],default='both')
    args=parser.parse_args()
    candidates=[]
    for provider in (['heroku','vercel'] if args.provider=='both' else [args.provider]):
        seen=receipts(provider)
        candidate=platforms.current(provider)
        if candidate['id'] not in seen:
            if not candidate.get('sha'): raise ValueError('production source SHA unavailable')
            candidates.append({'provider':provider,'id':candidate['id'],'sha':candidate['sha']})
    value=json.dumps({'include':candidates})
    print(value)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as stream:
            stream.write('matrix='+value+'\n')
            stream.write('any='+('true' if candidates else 'false')+'\n')

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('Discovery failed: '+type(exc).__name__,file=sys.stderr);sys.exit(2)
