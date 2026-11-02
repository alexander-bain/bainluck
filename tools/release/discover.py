"""Find production releases not yet recorded by this loop; reconcile external releases too."""
import argparse
import json
import os
import re
import sys

import platforms


def receipt_rows(provider):
    return platforms.github_pages('/deployments?environment=release-health-'+provider)


def receipt_index(rows):
    result={}
    for row in rows:
        payload=row.get('payload')
        if isinstance(payload,dict) and payload.get('candidate_id') and payload.get('verdict'):
            result.setdefault(payload['candidate_id'],payload)
    return result


def failed_sources(rows):
    return {row.get('payload',{}).get('candidate_sha') for row in rows
            if isinstance(row.get('payload'),dict) and row['payload'].get('verdict') in
            ('ROLLBACK REQUESTED','ROLLED BACK','VERDICT FAIL')}


def receipts(provider):
    return receipt_index(receipt_rows(provider))


def record(provider,candidate,verdict):
    row=platforms.github('/deployments','POST',{
        'ref':candidate['sha'],'auto_merge':False,'required_contexts':[],
        'environment':'release-health-'+provider,'production_environment':False,
        'payload':{'candidate_id':candidate['id'],'candidate_sha':candidate['sha'],'verdict':verdict,'reason':candidate.get('reason','')},
        'description':'Release loop: '+verdict[:80]})
    platforms.github('/deployments/'+str(row['id'])+'/statuses','POST',{
        'state':'success' if verdict=='VERDICT PASS' else 'failure',
        'description':verdict[:140],'auto_inactive':False})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--provider',choices=['heroku'],default='heroku')
    args=parser.parse_args()
    candidates=[]
    providers=[args.provider]
    for provider in providers:
        candidate=platforms.current(provider)
        # Replaying a terminal receipt repairs a lost NOW write. The observer
        # skips measurement for that receipt and report() upserts its one line.
        if not re.fullmatch(r'[0-9a-f]{40}',candidate.get('sha') or ''):
            raise ValueError('production source SHA unavailable')
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
