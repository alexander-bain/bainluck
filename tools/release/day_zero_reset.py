#!/usr/bin/env python3
"""One-time Day 0 reset. Default prints candidates; --apply executes Alex's reset."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import subprocess

REPO = 'alexander-bain/bainluck'
COMMENT = 'superseded by the Day 0 reset; reopen if still wanted'


def timestamp(text):
    return datetime.fromisoformat(text.replace('Z','+00:00'))


def old_pr(pr, now):
    return pr['state'] == 'open' and timestamp(pr['created_at']) < now - timedelta(days=14)


def stale_issue(issue, now):
    labels = {label['name'].lower() for label in issue['labels']}
    return ('pull_request' not in issue and issue['state'] == 'open' and
            'enhancement' not in labels and 'parked' not in labels and
            timestamp(issue['updated_at']) < now - timedelta(days=90))


def gh(*args, body=None):
    command = ['gh', *args]
    if body is not None:
        command.extend(['--input','-'])
    return subprocess.run(command,input=json.dumps(body) if body is not None else None,
                          text=True,capture_output=True,check=True).stdout


def pages(resource):
    result = json.loads(gh('api',f'repos/{REPO}/{resource}?state=open&per_page=100','--paginate','--slurp'))
    return [item for page in result for item in page]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    pulls = [pr for pr in pages('pulls') if old_pr(pr,now)]
    issues = [issue for issue in pages('issues') if stale_issue(issue,now)]
    print(json.dumps({'as_of':now.isoformat(),'close_prs':[p['number'] for p in pulls],
                      'park_issues':[i['number'] for i in issues]},indent=2))
    if not args.apply:
        return
    if issues:
        try:
            gh('api',f'repos/{REPO}/labels/parked')
        except subprocess.CalledProcessError as error:
            if '(HTTP 404)' not in error.stderr:
                raise
            gh('api','--method','POST',f'repos/{REPO}/labels',body={
                'name':'parked','color':'C5DEF5','description':'Untouched for 90 days at the Day 0 reset'})
    for pr in pulls:
        endpoint = f'repos/{REPO}/pulls/{pr["number"]}'
        current = json.loads(gh('api',endpoint))
        # Avoid closing anything the Delivery window just picked up.
        if not old_pr(current,now) or current['updated_at'] != pr['updated_at']:
            print(f'SKIP PR {pr["number"]}: changed since inventory')
            continue
        gh('pr','close',str(pr['number']),'--repo',REPO,'--comment',COMMENT)
        print(f'CLOSED PR {pr["number"]}')
    for issue in issues:
        endpoint = f'repos/{REPO}/issues/{issue["number"]}'
        current = json.loads(gh('api',endpoint))
        if not stale_issue(current,now) or current['updated_at'] != issue['updated_at']:
            print(f'SKIP issue {issue["number"]}: changed since inventory')
            continue
        gh('api','--method','POST',endpoint+'/labels',body={'labels':['parked']})
        print(f'PARKED issue {issue["number"]}')


if __name__ == '__main__':
    main()
