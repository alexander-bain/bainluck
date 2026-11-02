"""Fresh release authority readable by a workflow token without Variables permission."""
import re

import platforms


def enabled():
    rows=platforms.github_pages('/deployments?environment=release-loop-policy')
    if not rows:return False
    latest=max(rows,key=lambda row:int(row['id']))
    payload=latest.get('payload')
    return isinstance(payload,dict) and payload.get('authority')=='release-loop-policy-v1' and payload.get('fast_enabled') is True and bool(re.fullmatch(r'[0-9a-f]{40}',payload.get('master_sha','')))


def require_enabled():
    if not enabled():raise ValueError('fresh release policy is disabled or unknown')
