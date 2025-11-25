#!/usr/bin/env python3
"""
Emergency routing workflow:
- Decode vulnerabilities via JamAI LLM (decode_vulnerabilities)
- Insert a row into `emergency_routing` table/action documenting the input and decoded tags
- Run route_optimal_pps via JamAI LLM (RAG with PPS + SOP)
- Insert a result row into `emergency_routing` table/action with selected PPS and full analysis

Usage (PowerShell):
$env:JAMAI_PAT = '...'
$env:JAMAI_PROJECT_ID = 'proj_xxx'
$env:JAMAI_API_URL = 'https://api.jamai.example'  # LLM endpoint base
python .\scripts\emergency_routing_workflow.py --text "4 people, one bedridden, one cat" --location "Segamat, Johor"

The script will attempt to POST rows to these candidate endpoints (in order):
- $JAMAI_TABLE_API_URL (if provided)
- $JAMAI_API_URL/v1/projects/{project_id}/tables/emergency_routing/rows
- $JAMAI_API_URL/v1/projects/{project_id}/tables/emergency_routing

Adjust the endpoint or provide JAMAI_TABLE_API_URL if your JamAI deployment uses a different path.
"""

import os
import sys
import json
import argparse
from datetime import datetime

try:
    import requests
except Exception:
    requests = None

PPS_DATA = [
    { 'id': 1, 'name': 'PPS North (Sekolah)', 'distance_km': 1.0, 'lat': 1.5000, 'lon': 103.7500, 'features': '2nd floor classrooms only, No lift, Limited parking', 'constraints': 'Cannot accommodate bedridden patients (stairs).'},
    { 'id': 2, 'name': 'PPS Central (Dewan)', 'distance_km': 2.0, 'lat': 1.4800, 'lon': 103.7300, 'features': 'Ground floor access, Ample parking, Strict pet policy', 'constraints': "Strict 'No Animals' policy."},
    { 'id': 3, 'name': 'PPS South (Kolej)', 'distance_km': 4.0, 'lat': 1.4500, 'lon': 103.7200, 'features': 'OKU toilets, Designated outdoor pet area, Ground floor halls', 'constraints': 'None relevant to standard needs.'}
]

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
    api_url = os.environ.get('JAMAI_API_URL') or ''
    table_api_url = os.environ.get('JAMAI_TABLE_API_URL') or ''
    return pat, project_id, api_url, table_api_url


def call_llm(api_url, pat, payload, timeout=30):
    if requests is None:
        raise RuntimeError('requests library required (pip install requests)')
    headers = {'Content-Type': 'application/json'}
    if pat:
        headers['Authorization'] = f'Bearer {pat}'
    resp = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=timeout)
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, resp.text


def decode_vulnerabilities(api_url, pat, text):
    system = { 'parts': [{ 'text': 'You are a data decoder using Qwen3-VL. Provide only a comma-separated list of standardized tags (e.g., "4 Pax, Bedridden, Pet/Cat").' }] }
    contents = [{ 'parts': [{ 'text': f'Action: decode_vulnerabilities\nUser Input: "{text}"' }] }]
    payload = { 'systemInstruction': system, 'contents': contents, 'model': 'qwen3-vl' }
    status, result = call_llm(api_url, pat, payload)
    decoded_text = ''
    if isinstance(result, dict):
        decoded_text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
    else:
        decoded_text = str(result)
    tags = [t.strip() for t in decoded_text.split(',') if t.strip()]
    return tags, decoded_text, status, result


def route_optimal_pps(api_url, pat, tags, location_str='Unknown'):
    system_prompt = (
        'You are an emergency management AI using Qwen3-VL with RAG. Query the pps_knowledge table to get available PPS. Select the best-suited PPS based on user needs and constraints. Provide reasoning and end with "BEST MATCH: <PPS name>".'
    )
    user_query = f"Action: route_optimal_pps\nUser Needs: {'; '.join(tags)}\nLocation: {location_str}\nSOP: {SOP_KNOWLEDGE}\n\nQuery pps_knowledge table for available PPS centers and select the best match."
    payload = { 'systemInstruction': { 'parts': [{ 'text': system_prompt }] }, 'contents': [{ 'parts': [{ 'text': user_query }] }], 'model': 'qwen3-vl' }
    status, result = call_llm(api_url, pat, payload)
    full_text = ''
    if isinstance(result, dict):
        full_text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
    else:
        full_text = str(result)
    best = None
    for line in full_text.splitlines()[::-1]:
        if line.strip().upper().startswith('BEST MATCH:'):
            best = line.split(':',1)[1].strip()
            break
    return best, full_text, status, result


def try_post_table_rows(url, pat, rows_payload, project_id=None):
    if requests is None:
        raise RuntimeError('requests library required (pip install requests)')
    headers = {'Content-Type': 'application/json'}
    if pat:
        headers['Authorization'] = f'Bearer {pat}'
    # add project header when provided (some JamAI deployments require project id header)
    if project_id:
        headers['X-PROJECT-ID'] = project_id
        headers['X-Project-Id'] = project_id
    try:
        resp = requests.post(url, headers=headers, data=json.dumps(rows_payload), timeout=30)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body
    except Exception as e:
        return None, str(e)


def build_candidate_table_urls(api_url, project_id, table_name='emergency_routing'):
    candidates = []
    # If api_url seems like a full generate endpoint, derive base
    base = api_url.rstrip('/') if api_url else ''
    if base:
        # Prefer JamAI Add Rows API for generative tables
        candidates.append(f"{base}/api/v2/gen_tables/action/rows/add")
        # Project-scoped variants
        if project_id:
            candidates.append(f"{base}/v1/projects/{project_id}/tables/{table_name}/rows")
            candidates.append(f"{base}/v1/projects/{project_id}/tables/{table_name}")
        # Other common variants
        candidates.append(f"{base}/v1/tables/{table_name}/rows")
    return candidates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--text', '-t', required=True, help='User free-text describing situation')
    parser.add_argument('--location', '-l', default='Unknown', help='Optional location string')
    args = parser.parse_args()

    pat, project_id, api_url, table_api_url = get_config()
    if not api_url:
        print('ERROR: JAMAI_API_URL must be set (LLM endpoint).', file=sys.stderr)
        sys.exit(2)
    if not pat:
        print('ERROR: JAMAI_PAT must be set.', file=sys.stderr)
        sys.exit(2)

    # 1) Decode vulnerabilities
    print('Decoding vulnerabilities...')
    tags, decoded_text, s1, r1 = decode_vulnerabilities(api_url, pat, args.text)
    print('Decoded tags:', tags)

    timestamp = datetime.utcnow().isoformat()

    # Build row payload for decode_vulnerabilities
    decode_row = {
        'id': f'decode-{int(datetime.utcnow().timestamp())}',
        'action': 'decode_vulnerabilities',
        'input': args.text,
        'decoded_tags': tags,
        'decoded_text_raw': decoded_text,
        'pps_data': PPS_DATA,
        'created_at': timestamp
    }

    # 2) Post decode row to table
    # Prepare both legacy and Add Rows payload shapes. JamAI Add Rows API expects {table_id, data: [..]}
    legacy_rows_payload = { 'rows': [decode_row] }
    add_rows_payload = { 'table_id': 'emergency_routing', 'data': [decode_row], 'stream': False, 'concurrent': False }

    candidate_urls = []
    if table_api_url:
        candidate_urls.append(table_api_url)
    candidate_urls.extend(build_candidate_table_urls(api_url, project_id))

    posted = False
    for url in candidate_urls:
        print('Trying to POST decode row to', url)
        # If URL looks like the Add Rows endpoint, send add_rows_payload, otherwise try legacy payload
        payload = add_rows_payload if '/api/v2/gen_tables/' in url or url.endswith('/rows/add') else legacy_rows_payload
        status, body = try_post_table_rows(url, pat, payload, project_id)
        print('Status:', status)
        print('Body:', json.dumps(body) if isinstance(body, (dict, list)) else body)
        if status and 200 <= status < 300:
            print('Posted decode row successfully to', url)
            posted = True
            break
    if not posted:
        print('Warning: Could not post decode row to any candidate table endpoint. Proceeding without table write.')

    # 3) Route optimal PPS
    print('\nRequesting route_optimal_pps from JamAI...')
    best, analysis_text, s2, r2 = route_optimal_pps(api_url, pat, tags, args.location)
    print('Best match:', best)

    # 4) Post routing result row
    route_row = {
        'id': f'route-{int(datetime.utcnow().timestamp())}',
        'action': 'route_optimal_pps',
        'input_tags': tags,
        'selected_pps': best,
        'analysis_text': analysis_text,
        'pps_data': PPS_DATA,
        'created_at': datetime.utcnow().isoformat()
    }
    legacy_rows_payload2 = { 'rows': [route_row] }
    add_rows_payload2 = { 'table_id': 'emergency_routing', 'data': [route_row], 'stream': False, 'concurrent': False }

    posted2 = False
    for url in candidate_urls:
        print('Trying to POST route row to', url)
        payload = add_rows_payload2 if '/api/v2/gen_tables/' in url or url.endswith('/rows/add') else legacy_rows_payload2
        status, body = try_post_table_rows(url, pat, payload, project_id)
        print('Status:', status)
        print('Body:', json.dumps(body) if isinstance(body, (dict, list)) else body)
        if status and 200 <= status < 300:
            print('Posted route row successfully to', url)
            posted2 = True
            break
    if not posted2:
        print('Warning: Could not post route row to any candidate table endpoint.')

    print('\nWorkflow finished.')

if __name__ == '__main__':
    main()
