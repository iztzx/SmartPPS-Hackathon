#!/usr/bin/env python3
"""
Create JamAI action and knowledge tables (best-effort) and run a quick Add-Rows test.

This script uses the JamAI API endpoints to create two tables:
- emergency_routing (action table with completion columns)
- pps_knowledge (knowledge table)

It then posts a test Add-Rows insert to verify the Add-Rows endpoint.

Usage:
  export JAMAI_PAT=...
  export JAMAI_PROJECT_ID=...
  export JAMAI_API_URL=https://api.jamaibase.com
  python scripts/create_action_table_and_run.py

Note: API schemas vary between JamAI deployments. This script is defensive and prints responses.
"""
import os
import sys
import json
import time
import requests

JAMAI_PAT = os.getenv('JAMAI_PAT') or os.getenv('JAMAI_PAT')
JAMAI_PROJECT_ID = os.getenv('JAMAI_PROJECT_ID')
JAMAI_API_URL = os.getenv('JAMAI_API_URL', 'https://api.jamaibase.com')

HEADERS = {
    'Authorization': f'Bearer {JAMAI_PAT}' if JAMAI_PAT else '',
    'Content-Type': 'application/json'
}
if JAMAI_PROJECT_ID:
    HEADERS['X-PROJECT-ID'] = JAMAI_PROJECT_ID


def create_table_payloads():
    # The JamAI API expects 'id' and 'cols' (not 'columns').
    emergency = {
        "id": "emergency_routing",
        "name": "Emergency Routing",
        "type": "action",
        "cols": [
            {"id": "input", "name": "Input", "type": "text"},
            {"id": "decoded_tags", "name": "Decoded Tags", "type": "completion", "config": {"completion": {"system_instruction": "You are a structured data decoder. Use the 'input' field and return ONLY a comma-separated list of tags like '4 Pax, Warga Emas/Bedridden, Pet/Cat'."}}},
            {"id": "pps_data", "name": "PPS Data", "type": "json"},
            {"id": "selected_pps", "name": "Selected PPS", "type": "text"},
            {"id": "analysis_text", "name": "Analysis Text", "type": "completion", "config": {"completion": {"system_instruction": "You are an emergency routing assistant. Use decoded_tags and pps_data to output a brief analysis and a final line 'BEST MATCH: <PPS name>'."}}},
            {"id": "created_at", "name": "Created At", "type": "timestamp"}
        ]
    }

    pps_knowledge = {
        "id": "pps_knowledge",
        "name": "PPS Knowledge",
        "type": "knowledge",
        "cols": [
            {"id": "id", "name": "ID", "type": "text"},
            {"id": "name", "name": "Name", "type": "text"},
            {"id": "lat", "name": "Latitude", "type": "number"},
            {"id": "lon", "name": "Longitude", "type": "number"},
            {"id": "address", "name": "Address", "type": "text"},
            {"id": "features", "name": "Features", "type": "text"},
            {"id": "capacity", "name": "Capacity", "type": "number"},
            {"id": "tags", "name": "Tags", "type": "text"},
            {"id": "description", "name": "Description", "type": "text"}
        ]
    }
    return emergency, pps_knowledge


def create_table(payload):
    url = JAMAI_API_URL.rstrip('/') + '/api/v2/gen_tables/action'
    print(f'Creating table via POST {url} payload.table_id={payload.get("table_id")}')
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        print('Status:', r.status_code)
        print('Body:', r.text)
        return r
    except Exception as e:
        print('Create table request failed:', e)
        return None


def add_rows_test():
    # Post a test row to Add-Rows endpoint
    url = JAMAI_API_URL.rstrip('/') + '/api/v2/gen_tables/action/rows/add'
    payload = {
        "table_id": "emergency_routing",
        "data": [
            {
                "id": f"test-{int(time.time())}",
                "action": "decode_vulnerabilities",
                "input": "2 adults, 1 infant, small pet cat, no mobility issues",
                "pps_data": [],
                "created_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            }
        ],
        "stream": False,
        "concurrent": False
    }
    print('Posting Add-Rows test to', url)
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        print('Status:', r.status_code)
        try:
            print('JSON:', json.dumps(r.json(), indent=2))
        except Exception:
            print('Body:', r.text)
        return r
    except Exception as e:
        print('Add-Rows test failed:', e)
        return None


def main():
    if not JAMAI_PAT:
        print('ERROR: JAMAI_PAT not set in environment')
        sys.exit(1)
    print('Using JAMAI_API_URL=', JAMAI_API_URL)
    emergency, pps = create_table_payloads()

    print('\n-- Creating emergency action table (best-effort)')
    create_table(emergency)

    print('\n-- Creating pps_knowledge table (best-effort)')
    create_table(pps)

    print('\n-- Running Add-Rows test (will trigger completions if your table is configured)')
    add_rows_test()


if __name__ == '__main__':
    main()
