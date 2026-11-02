"""Refuse retained scope outputs and re-read live-path eligibility at release gates."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from live_path import is_live_event


def verify_attempt(recorded, current):
    if not recorded or not current or recorded != current:
        raise ValueError('retained change-scope attempt is stale; rerun all jobs')


def active_policy(read):
    rows=[]
    for page in range(1,101):
        batch=read('/deployments?environment=release-loop-policy&per_page=100&page='+str(page))
        if not isinstance(batch,list):
            raise ValueError('release-loop policy response is invalid')
        rows.extend(batch)
        if len(batch)<100:
            break
    else:
        raise ValueError('release-loop policy pagination did not finish')
    if not rows or any(not isinstance(row,dict) or not isinstance(row.get('id'),int) for row in rows):
        raise ValueError('release-loop policy is missing or cannot be ordered')
    latest=max(rows,key=lambda row:row['id'])
    payload=latest.get('payload')
    if (not isinstance(payload,dict) or payload.get('authority')!='release-loop-policy-v1'
            or payload.get('fast_enabled') is not True
            or not re.fullmatch(r'[0-9a-f]{40}',payload.get('master_sha',''))):
        raise ValueError('latest trusted release-loop policy is disabled or invalid; rerun all jobs')
    # The trusted arming tool commits payload authority before changing coarse
    # flags. A disabled payload takes effect even if its status write fails.
    return payload


def verify_eligibility(event_name, event, head, read):
    active_policy(read)
    if event_name == 'pull_request':
        number = event.get('pull_request', {}).get('number')
        candidates = [read('/pulls/' + str(number))]
    else:
        candidates = read('/commits/' + head + '/pulls')
    if not is_live_event(event_name, event, candidates, head):
        raise ValueError('current PR head or live-path label no longer admits this gate; rerun all jobs')


def read(path):
    result = subprocess.run(['gh', 'api', 'repos/' + os.environ['GITHUB_REPOSITORY'] + path],
                            text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def main():
    verify_attempt(os.environ.get('SCOPE_ATTEMPT'), os.environ.get('GITHUB_RUN_ATTEMPT'))
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    verify_eligibility(os.environ['GITHUB_EVENT_NAME'], event, os.environ['SCOPE_HEAD'], read)
    print('Current attempt, source head, label and trusted policy receipt admit this gate.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Fast gate refused; rerun all jobs: ' + type(exc).__name__, file=sys.stderr)
        sys.exit(2)
