"""Refuse retained scope outputs and re-read live-path eligibility at release gates."""
import json
import os
import subprocess
import sys
from pathlib import Path

from live_path import is_live_event


def verify_attempt(recorded, current):
    if not recorded or not current or recorded != current:
        raise ValueError('retained change-scope attempt is stale; rerun all jobs')


def verify_eligibility(event_name, event, head, read):
    if read('/actions/variables/RELEASE_LOOP_FAST_ENABLED').get('value') != 'true':
        raise ValueError('fast lane is no longer enabled; rerun all jobs')
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
    print('Current attempt, source head, label and fast-lane setting admit this gate.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Fast gate refused; rerun all jobs: ' + type(exc).__name__, file=sys.stderr)
        sys.exit(2)
