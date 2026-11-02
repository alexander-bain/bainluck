"""Record reviewed existing watcher PASS evidence before the first loop-controlled release."""
import argparse
import json
import pathlib
import sys

import arm
import discover
import health
import platforms


def seed(proof,master_current,reviewed,apply):
    if not apply:return {'activation':'held','flags_changed':False,'requires':'reviewed existing current-provider watcher PASS evidence'}
    if not master_current or not reviewed:raise ValueError('baseline seeding requires master-current and reviewed evidence')
    ready=[]
    for provider in ('heroku',):
        entry=proof.get(provider,{})
        live=platforms.current(provider)
        arm.validate_baseline(entry,live)
        evidence=entry.get('evidence',{})
        if any(not isinstance(evidence.get(key),str) or not (evidence[key]=='VERDICT PASS' or evidence[key].startswith('VERDICT PASS ')) for key in ('worker_check','guard2','guard3')):
            raise ValueError('bootstrap needs conclusive existing watcher evidence, not a probe-only PASS')
        rows=discover.receipt_rows(provider)
        if live['sha'] in discover.failed_sources(rows):raise ValueError('failed source cannot be seeded')
        health.probe(provider)
        ready.append((provider,live))
    # Validate the proof and current public health before writing a receipt.
    for provider,live in ready:
        if live['id'] not in discover.receipts(provider):discover.record(provider,live,'VERDICT PASS')
    return {'activation':'baselines seeded; fast lane remains off','flags_changed':False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--proof',type=pathlib.Path);parser.add_argument('--apply',action='store_true')
    parser.add_argument('--master-is-current',action='store_true');parser.add_argument('--proof-reviewed',action='store_true')
    args=parser.parse_args();proof=json.loads(args.proof.read_text()) if args.proof else {}
    print(json.dumps(seed(proof,args.master_is_current,args.proof_reviewed,args.apply),indent=2))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('Baseline seeding refused: '+type(exc).__name__,file=sys.stderr);sys.exit(2)
