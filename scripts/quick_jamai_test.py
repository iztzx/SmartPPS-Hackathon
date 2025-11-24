#!/usr/bin/env python3
"""
Quick JamAI Add Rows endpoint tester.

Usage (PowerShell):
  $env:JAMAI_PAT = '...'
  $env:JAMAI_PROJECT_ID = 'proj_xxx'
  $env:JAMAI_API_URL = 'https://api.jamaibase.com'
  python .\scripts\quick_jamai_test.py

This script attempts a minimal Add Rows write using environment variables.
"""
import os, sys, json
try:
    import requests
except Exception:
    print('Please install requests: python -m pip install requests')
    sys.exit(2)

pat = os.environ.get('JAMAI_PAT') or ''
proj = os.environ.get('JAMAI_PROJECT_ID') or ''
api = os.environ.get('JAMAI_API_URL') or ''
table_url = os.environ.get('JAMAI_TABLE_API_URL') or ''

if not pat:
    print('ERROR: Set JAMAI_PAT in environment')
    sys.exit(2)

if not table_url:
    if not api:
        print('ERROR: Set JAMAI_TABLE_API_URL or JAMAI_API_URL in environment')
        sys.exit(2)
    table_url = api.rstrip('/') + '/api/v2/gen_tables/action/rows/add'

payload = {
    'table_id': 'emergency_routing',
    'data': [ { 'action': 'ping', 'text': 'quick test' } ],
    'stream': False,
    'concurrent': False
}

headers = {
    'Authorization': f'Bearer {pat}',
    'Content-Type': 'application/json'
}
if proj:
    headers['X-PROJECT-ID'] = proj

print('Testing Add Rows POST to:', table_url)
try:
    r = requests.post(table_url, json=payload, headers=headers, timeout=15)
    try:
        body = r.json()
    except Exception:
        body = r.text
    print('Status:', r.status_code)
    print('Body:', json.dumps(body, indent=2) if isinstance(body, (dict, list)) else body)
except Exception as e:
    print('Network error:', e)
    sys.exit(1)
