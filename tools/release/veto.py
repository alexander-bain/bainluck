"""Persist failed source SHAs before waiting for any production rollback writer lock."""
import argparse
import re
import sys

import discover


def mark_failed(sha,reason,record=None):
    if not re.fullmatch(r'[0-9a-f]{40}',sha or ''): raise ValueError('source veto requires a full SHA')
    record=record or discover.record
    for provider in ('heroku','vercel'):
        record(provider,{'id':'failed-source:'+sha,'sha':sha,'reason':reason},'VERDICT FAIL')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--candidate-sha',required=True);parser.add_argument('--reason',required=True)
    args=parser.parse_args();mark_failed(args.candidate_sha,args.reason);print('Failed source veto recorded for both production providers')

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('Source veto failed: '+type(exc).__name__,file=sys.stderr);sys.exit(2)
