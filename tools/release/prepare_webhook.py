"""Preview activation by default; no provider writes until Alex confirms master is current."""
import argparse
import json
import sys

import platforms


def prepare(apply,master_current,send=None):
    plan={'url':'https://bainluck.com/api/release-webhook','resource':'api:release',
          'vercel_server_settings':['HEROKU_RELEASE_WEBHOOK_SECRET','RELEASE_DISPATCH_TOKEN'],
          'activation':'held until Alex writes master is current; relay PR must deploy before delivery works'}
    if not apply: return plan
    if not master_current: raise ValueError('activation requires Alex master-is-current confirmation')
    secret=platforms.required('HEROKU_RELEASE_WEBHOOK_SECRET')
    dispatch=platforms.required('RELEASE_DISPATCH_TOKEN')
    if len(secret)<32: raise ValueError('webhook signing secret must have at least 32 characters')
    send=send or platforms.vercel
    project=platforms.required('VERCEL_PROJECT_ID')
    # Token stays in encrypted server-only Vercel env, never NEXT_PUBLIC_*.
    send('/v10/projects/'+project+'/env?upsert=true','POST',[
        {'key':'HEROKU_RELEASE_WEBHOOK_SECRET','value':secret,'type':'encrypted','target':['production']},
        {'key':'RELEASE_DISPATCH_TOKEN','value':dispatch,'type':'encrypted','target':['production']},
    ])
    rows=platforms.heroku('/webhooks')
    body={'url':plan['url'],'include':['api:release'],'level':'sync','secret':secret}
    existing=next((row for row in rows if row.get('url')==plan['url']),None)
    if existing:
        platforms.heroku('/webhooks/'+existing['id'],'PATCH',body)
    else:
        platforms.heroku('/webhooks','POST',body)
    return {**plan,'activation':'configured; merge/deploy the relay PR, then verify a signed delivery reaches Actions'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--master-is-current',action='store_true')
    args=parser.parse_args()
    print(json.dumps(prepare(args.apply,args.master_is_current),indent=2))

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('Webhook activation refused: '+type(exc).__name__,file=sys.stderr);sys.exit(2)
