#!/usr/bin/env python3
"""
Upload PPS (Pusat Pemulihan Sementara) data to JamAI knowledge table for RAG grounding.

Usage (PowerShell):
  $env:JAMAI_PAT = '...'
  $env:JAMAI_PROJECT_ID = 'proj_xxx'
  $env:JAMAI_API_URL = 'https://api.jamaibase.com'
  python .\scripts\upload_pps_knowledge.py

This will POST PPS data rows to the 'pps_knowledge' knowledge table for RAG.
"""
import os
import sys
import json
from datetime import datetime

try:
    import requests
except Exception:
    print('Please install requests: python -m pip install requests')
    sys.exit(2)

# PPS Data (same as frontend)
PPS_DATA = [
    {
        'id': 1,
        'name': 'PPS North (Sekolah)',
        'distance_km': 1.0,
        'lat': 1.5000,
        'lon': 103.7500,
        'features': '2nd floor classrooms only, No lift, Limited parking',
        'constraints': 'Cannot accommodate bedridden patients (stairs).'
    },
    {
        'id': 2,
        'name': 'PPS Central (Dewan)',
        'distance_km': 2.0,
        'lat': 1.4800,
        'lon': 103.7300,
        'features': 'Ground floor access, Ample parking, Strict pet policy',
        'constraints': "Strict 'No Animals' policy."
    },
    {
        'id': 3,
        'name': 'PPS South (Kolej)',
        'distance_km': 4.0,
        'lat': 1.4500,
        'lon': 103.7200,
        'features': 'OKU toilets, Designated outdoor pet area, Ground floor halls',
        'constraints': 'None relevant to standard needs.'
    }
]

def get_config():
    pat = os.environ.get('JAMAI_PAT') or ''
    project_id = os.environ.get('JAMAI_PROJECT_ID') or ''
    api_url = os.environ.get('JAMAI_API_URL') or ''
    table_url = os.environ.get('JAMAI_TABLE_API_URL') or ''
    return pat, project_id, api_url, table_url

def upload_pps_knowledge():
    pat, project_id, api_url, table_url = get_config()

    if not pat:
        print('ERROR: Set JAMAI_PAT in environment')
        sys.exit(2)

    if not table_url:
        if not api_url:
            print('ERROR: Set JAMAI_TABLE_API_URL or JAMAI_API_URL in environment')
            sys.exit(2)
        table_url = api_url.rstrip('/') + '/api/v2/gen_tables/action/rows/add'

    headers = {
        'Authorization': f'Bearer {pat}',
        'Content-Type': 'application/json'
    }
    if project_id:
        headers['X-PROJECT-ID'] = project_id
        headers['X-Project-Id'] = project_id

    # Build Add Rows payload
    # Convert each PPS to a row for the 'pps_knowledge' table
    rows = []
    for pps in PPS_DATA:
        row = {
            'id': f"pps-{pps['id']}",
            'pps_name': pps['name'],
            'distance_km': pps['distance_km'],
            'latitude': pps['lat'],
            'longitude': pps['lon'],
            'features': pps['features'],
            'constraints': pps['constraints'],
            'description': f"PPS: {pps['name']}. Features: {pps['features']}. Constraints: {pps['constraints']}",
            'created_at': datetime.utcnow().isoformat()
        }
        rows.append(row)

    payload = {
        'table_id': 'pps_knowledge',
        'data': rows,
        'stream': False,
        'concurrent': False
    }

    print(f'Uploading {len(rows)} PPS rows to knowledge table at: {table_url}')
    try:
        r = requests.post(table_url, json=payload, headers=headers, timeout=30)
        try:
            body = r.json()
        except Exception:
            body = r.text
        
        print('Status:', r.status_code)
        print('Body:', json.dumps(body, indent=2) if isinstance(body, (dict, list)) else body)
        
        if 200 <= r.status_code < 300:
            print('\n✅ PPS knowledge table upload successful!')
            return True
        else:
            print('\n❌ Upload failed. Check JAMAI_TABLE_API_URL, PAT, and project ID.')
            return False
    except Exception as e:
        print('Network error:', e)
        sys.exit(1)

if __name__ == '__main__':
    upload_pps_knowledge()
