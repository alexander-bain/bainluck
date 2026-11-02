"""Shared health/full-suite rollback. Run in the provider's deployment concurrency group."""
import argparse
import json
import re
import sys
import time

import platforms
import discover


def rollback_if_current(provider, candidate_sha, candidate_id, live, previous_id, write):
    if not re.fullmatch(r'[0-9a-f]{40}', candidate_sha or ''):
        raise ValueError('rollback requires a full candidate SHA')
    if not live.get('sha') or not live.get('id') or not previous_id or previous_id == candidate_id:
        raise ValueError('rollback identity or prior release is unknown')
    if live['sha'] != candidate_sha or (candidate_id and live['id'] != candidate_id):
        return False
    write({'release':previous_id} if provider == 'heroku' else {'deploymentId':previous_id})
    return True


def rollback(provider, candidate_sha, candidate_id=None, previous_id=None):
    # Read only after the Actions job owns heroku-deploy/vercel-production.
    # Re-read immediately before POST to exclude an intervening out-of-band release.
    live = platforms.current(provider)
    if live.get('sha') != candidate_sha or (candidate_id and live['id'] != candidate_id):
        return False
    candidate_id = candidate_id or live['id']
    if not previous_id:
        rows = platforms.deployments(provider)
        candidate_index = next(i for i,row in enumerate(rows) if row['id'] == candidate_id)
        previous_id = next(row['id'] for row in rows[candidate_index+1:] if row.get('sha') != candidate_sha)
    if provider == 'heroku':
        target_sha=platforms.release_sha(platforms.heroku('/releases/'+previous_id))
        write = lambda body: platforms.heroku('/releases', 'POST', body)
    else:
        target=platforms.vercel('/v13/deployments/'+previous_id)
        target_sha=target.get('meta',{}).get('githubCommitSha') or target.get('gitSource',{}).get('sha')
        write = lambda body: platforms.vercel('/v1/projects/' + platforms.required('VERCEL_PROJECT_ID') + '/rollback', 'POST', body)
    if not re.fullmatch(r'[0-9a-f]{40}',target_sha or ''):
        raise ValueError('prior release source is unknown')
    changed=rollback_if_current(provider, candidate_sha, candidate_id, platforms.current(provider), previous_id, write)
    if changed: verify_rollback(provider,target_sha)
    return changed


def verify_rollback(provider, target_sha, read=None, sleep=time.sleep, now=time.monotonic):
    read=read or (lambda: platforms.current(provider))
    deadline=now()+90
    while now()<deadline:
        if read().get('sha')==target_sha: return
        sleep(2)
    raise RuntimeError('provider did not confirm the rollback target')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--provider', choices=['heroku','vercel'], required=True)
    parser.add_argument('--candidate-sha', required=True)
    parser.add_argument('--candidate-id')
    parser.add_argument('--previous-id')
    parser.add_argument('--reason', required=True)
    args=parser.parse_args()
    changed=rollback(args.provider,args.candidate_sha,args.candidate_id,args.previous_id)
    if changed:
        discover.record(args.provider,{'id':args.candidate_id or args.candidate_sha,'sha':args.candidate_sha},'ROLLED BACK')
    platforms.report('%s %s %s: %s — %s' % (args.provider,args.candidate_id or '',args.candidate_sha[:8],
                     'ROLLED BACK' if changed else 'superseded; no rollback',args.reason))
    print('ROLLED BACK' if changed else 'SUPERSEDED')
    return 1 if changed else 0

if __name__ == '__main__':
    try: sys.exit(main())
    except Exception as exc:
        print('Rollback refused: ' + type(exc).__name__, file=sys.stderr)
        sys.exit(2)
