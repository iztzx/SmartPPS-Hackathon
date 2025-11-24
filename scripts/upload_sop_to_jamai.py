#!/usr/bin/env python3
"""
Upload SOP rows to JamAI Action/Table API.
Tries to use the `jamai` SDK if available, otherwise falls back to a plain HTTP POST using `requests`.

Usage:
  Set environment variables: JAMAI_PAT, JAMAI_PROJECT_ID, and either JAMAI_TABLE_API_URL or JAMAI_API_URL.

  python scripts/upload_sop_to_jamai.py

The script will POST a single SOP row containing a short Malaysian Flood SOP summary.
"""
import os
import json
import sys
from datetime import datetime

try:
    import requests
except Exception:
    requests = None

# SOP text (same summary used in the frontend)
SOP_KNOWLEDGE = (
    "Standard Operating Procedures for Malaysian Flood Mitigation (summary):\n"
    "1) Monitor official weather and agensi kerajaan updates; follow evacuation orders immediately.\n"
    "2) Prioritise evacuation of vulnerable persons: elderly, bedridden, infants, pregnant women, and persons with disabilities (OKU).\n"
    "3) Pets: declare animals at registration; some PPS allow pets in designated areas—bring carriers and food.\n"
    "4) Bring essential documents (ICs), medications, minimal bedding, drinking water, and basic food; label items with head of family name.\n"
    "5) Hygiene: bring face masks, soap, hand sanitizer, and maintain distancing where possible.\n"
    "6) Sanitation: use provided toilets; report sanitary issues to PPS officer.\n"
    "7) Electrical safety: avoid floodwaters, do not use electrical appliances in water; generators must be outdoors with safe ventilation.\n"
    "8) Medical emergencies: inform PPS medical teams immediately; register special needs on arrival for priority assistance.\n"
    "9) Registration: register at the PPS counter, obtain family token/QR, comply with volunteer instructions.\n"
    "10) Communication: keep phones charged, use designated family contact points, and do not re-enter flooded areas until declared safe."
)


def get_config():
    pat = os.environ.get('JAMAI_PAT') or ''
    project_id = os.environ.get('JAMAI_PROJECT_ID') or ''
    table_url = os.environ.get('JAMAI_TABLE_API_URL') or ''
    api_url = os.environ.get('JAMAI_API_URL') or ''
    return pat, project_id, table_url, api_url


def build_table_endpoint(project_id, api_url):
    # Conservative construction: many JamAI deployments expose a "tables" API under a project path.
    # If you have a custom endpoint, set JAMAI_TABLE_API_URL.
    if not api_url or not project_id:
        return None
    return f"{api_url.rstrip('/')}/v1/projects/{project_id}/tables"


def upload_via_requests(url, pat, payload, project_id=None):
    if requests is None:
        raise RuntimeError('The requests package is required for HTTP fallback. Install with `pip install requests`')
    headers = {'Content-Type': 'application/json'}
    if pat:
        headers['Authorization'] = f'Bearer {pat}'
    # Include project header when provided — some JamAI deployments require it
    if project_id:
        headers['X-PROJECT-ID'] = project_id
        headers['X-Project-Id'] = project_id
    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
        return resp.status_code, resp.text
    except Exception as e:
        return None, str(e)


def main():
    pat, project_id, table_url, api_url = get_config()

    if not table_url:
        table_url = build_table_endpoint(project_id, api_url)

    if not table_url:
        print('ERROR: Please set JAMAI_TABLE_API_URL or JAMAI_API_URL + JAMAI_PROJECT_ID in the environment.', file=sys.stderr)
        sys.exit(2)

    if not pat:
        print('ERROR: JAMAI_PAT is not set in environment (required).', file=sys.stderr)
        sys.exit(2)

    row = {
        'id': f'sop-{int(datetime.utcnow().timestamp())}',
        'data': {
            'title': 'Malaysian Flood SOP (summary)',
            'text': SOP_KNOWLEDGE
        }
    }

    # JamAI Add Rows API expects: { table_id: string, data: [ { col: value, ... } ], stream?: bool }
    payload = {
        'table_id': 'emergency_routing',
        'data': [
            {
                'action': 'sop_upload',
                'title': 'Malaysian Flood SOP (summary)',
                'text': SOP_KNOWLEDGE,
                'source': 'safe-route-ui',
                'created_at': datetime.utcnow().isoformat()
            }
        ],
        'stream': False,
        'concurrent': False
    }

    # Build candidate endpoints to try (prefer Add Rows API)
    candidates = []
    if table_url:
        candidates.append(table_url)
    base = api_url.rstrip('/') if api_url else ''
    if base:
        # JamAI Add Rows API (generative tables)
        candidates.append(f"{base}/api/v2/gen_tables/action/rows/add")
        # Legacy/project-scoped table endpoints (common variants)
        if project_id:
            candidates.append(f"{base}/v1/projects/{project_id}/tables/emergency_routing/rows")
            candidates.append(f"{base}/v1/projects/{project_id}/tables/emergency_routing")
        candidates.append(f"{base}/v1/tables/emergency_routing/rows")

    print('Uploading SOP row (trying candidate endpoints)')

    status = None
    body = None
    for url in candidates:
        print(f'Trying: {url}')
        status, body = upload_via_requests(url, pat, payload, project_id)
        if status is None:
            print('Network/client error:', body)
            continue
        print('HTTP status:', status)
        print('Response body:', body)
        if 200 <= status < 300:
            print('\nSOP upload appears successful to', url)
            break
    else:
        print('\nSOP upload failed to all candidate endpoints. Check JAMAI_TABLE_API_URL, JAMAI_API_URL, PAT and table schema expected by JamAI.')


if __name__ == '__main__':
    main()
