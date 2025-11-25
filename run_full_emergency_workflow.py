#!/usr/bin/env python3
"""
Full Emergency Routing Workflow Utility (Optimized):
1. Skip PPS upload (relies on pre-configured 'pps_knowledge' table).
2. Upload SOP text to 'emergency_routing' table (RAG knowledge/logging).
3. Decode user's free-text input into standardized tags (LLM call 1).
4. Route to the optimal PPS using RAG (SOP + pps_knowledge) (LLM call 2).
5. Log both decode and route results to 'emergency_routing' action table.

Usage:
  # Set environment variables (replace ... with your actual values)
  $env:JAMAI_PAT = '...'
  $env:JAMAI_PROJECT_ID = 'proj_xxx'
  $env:JAMAI_API_URL = 'https://api.jamai.example'
  
  python run_full_emergency_workflow.py --text "4 people, one bedridden, one cat" --location "Segamat, Johor"
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
    print('ERROR: requests library required (pip install requests)', file=sys.stderr)
    sys.exit(2)

# --- Shared Data (PPS data REMOVED - relies on RAG) ---
# NOTE: The client-side (index.html) will still display a static list
# for demonstration, but the core routing logic below relies on RAG.
STATIC_PPS_FOR_DISPLAY = [
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
# --- Configuration & Utility Functions ---

def get_config():
    pat = os.environ.get('JAMAI_PAT') or ''
    project_id = os.environ.get('JAMAI_PROJECT_ID') or ''
    api_url = os.environ.get('JAMAI_API_URL') or ''
    table_api_url = os.environ.get('JAMAI_TABLE_API_URL') or ''
    return pat, project_id, api_url, table_api_url

def build_candidate_table_urls(api_url, project_id, table_name):
    # Prefer JamAI Add Rows API for generative tables
    base = api_url.rstrip('/') if api_url else ''
    candidates = [f"{base}/api/v2/gen_tables/action/rows/add"]
    if project_id:
        candidates.append(f"{base}/v1/projects/{project_id}/tables/{table_name}/rows")
        candidates.append(f"{base}/v1/projects/{project_id}/tables/{table_name}")
    return candidates

def try_post_table_rows(url, pat, rows_payload, project_id=None):
    headers = {'Content-Type': 'application/json'}
    if pat: headers['Authorization'] = f'Bearer {pat}'
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
        
def call_llm(api_url, pat, payload, timeout=30):
    headers = {'Content-Type': 'application/json'}
    if pat: headers['Authorization'] = f'Bearer {pat}'
    resp = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=timeout)
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, resp.text


# --- Step 1: Upload SOP Knowledge (emergency_routing table) ---

# PPS Upload function REMOVED

def upload_sop_knowledge(pat, project_id, api_url, table_api_url):
    print('\n--- Uploading SOP Knowledge (emergency_routing table) ---')

    # Row for the emergency_routing table (action: sop_upload)
    sop_row = {
        'id': f'sop-{int(datetime.utcnow().timestamp())}',
        'action': 'sop_upload',
        'title': 'Malaysian Flood SOP (summary)',
        'text': SOP_KNOWLEDGE,
        'source': 'safe-route-workflow',
        'created_at': datetime.utcnow().isoformat()
    }
    
    payload = {
        'table_id': 'emergency_routing',
        'data': [sop_row],
        'stream': False,
        'concurrent': False
    }

    candidate_urls = [table_api_url] if table_api_url else []
    candidate_urls.extend(build_candidate_table_urls(api_url, project_id, 'emergency_routing'))

    for url in candidate_urls:
        print(f'Trying to POST SOP row to: {url}')
        status, body = try_post_table_rows(url, pat, payload, project_id)
        if status and 200 <= status < 300:
            print(f'✅ SOP upload successful to {url}')
            return True
        elif status is not None:
            print(f'   Upload failed (Status {status}). Body: {json.dumps(body) if isinstance(body, dict) else body[:100]}...')

    print('❌ Failed to upload SOP knowledge to any candidate endpoint.')
    return False

# --- Step 2 & 3: LLM Analysis & Routing (RAG relies on pps_knowledge) ---

def decode_vulnerabilities(api_url, pat, text):
    system = { 'parts': [{ 'text': 'You are a data decoder using Qwen3-VL. Provide only a comma-separated list of standardized tags (e.g., "4 Pax, Bedridden, Pet/Cat").' }] }
    contents = [{ 'parts': [{ 'text': f'Action: decode_vulnerabilities\nUser Input: "{text}"' }] }]
    payload = { 'systemInstruction': system, 'contents': contents, 'model': 'qwen3-vl' }
    
    status, result = call_llm(api_url, pat, payload)
    decoded_text = ''
    if isinstance(result, dict):
        decoded_text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
    tags = [t.strip() for t in decoded_text.split(',') if t.strip()]
    return tags, decoded_text, status, result


def route_optimal_pps(api_url, pat, tags, location_str='Unknown'):
    system_prompt = (
        'You are an emergency management AI using Qwen3-VL with RAG. Query the pps_knowledge table and the SOP knowledge to get available PPS and rules. Select the best-suited PPS based on user needs and constraints. Provide reasoning and end with "BEST MATCH: <PPS name>".'
    )
    # The crucial change: Removed PPS_DATA from the prompt. We rely on JamAI RAG using pps_knowledge table.
    user_query = f"Action: route_optimal_pps\nUser Needs: {'; '.join(tags)}\nLocation: {location_str}\n\nQuery pps_knowledge table and SOP knowledge for available PPS centers and select the best match."
    
    payload = { 'systemInstruction': { 'parts': [{ 'text': system_prompt }] }, 'contents': [{ 'parts': [{ 'text': user_query }] }], 'model': 'qwen3-vl' }
    
    status, result = call_llm(api_url, pat, payload)
    full_text = ''
    if isinstance(result, dict):
        full_text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
    
    best = None
    for line in full_text.splitlines()[::-1]:
        if line.strip().upper().startswith('BEST MATCH:'):
            best = line.split(':',1)[1].strip()
            break
            
    return best, full_text, status, result

# --- Step 4: Log Results to Table ---

def log_workflow_results(pat, project_id, api_url, table_api_url, decode_row, route_row):
    print('\n--- Logging Workflow Results (emergency_routing table) ---')

    rows_to_log = [decode_row, route_row]
    payload = {
        'table_id': 'emergency_routing',
        'data': rows_to_log,
        'stream': False,
        'concurrent': False
    }

    candidate_urls = [table_api_url] if table_api_url else []
    candidate_urls.extend(build_candidate_table_urls(api_url, project_id, 'emergency_routing'))

    for url in candidate_urls:
        print(f'Trying to POST results to: {url}')
        status, body = try_post_table_rows(url, pat, payload, project_id)
        if status and 200 <= status < 300:
            print(f'✅ Workflow results logged successfully to {url}')
            return True
        elif status is not None:
            print(f'   Logging failed (Status {status}). Body: {json.dumps(body) if isinstance(body, dict) else body[:100]}...')

    print('❌ Failed to log workflow results to any candidate endpoint.')
    return False

# --- Main Execution ---

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--text', '-t', required=True, help='User free-text describing situation')
    parser.add_argument('--location', '-l', default='Unknown', help='Optional location string')
    args = parser.parse_args()

    pat, project_id, api_url, table_api_url = get_config()
    
    if not all([pat, project_id, api_url]):
        print('ERROR: JAMAI_PAT, JAMAI_PROJECT_ID, and JAMAI_API_URL must be set in the environment.', file=sys.stderr)
        sys.exit(2)

    # 1. Setup Knowledge Base (Only SOP upload remains)
    upload_sop_knowledge(pat, project_id, api_url, table_api_url)

    # 2. Decode vulnerabilities
    print('\n--- Step 2: Decoding Vulnerabilities ---')
    tags, decoded_text, s1, r1 = decode_vulnerabilities(api_url, pat, args.text)
    print(f'Decoded tags: {tags}')

    timestamp1 = datetime.utcnow().isoformat()
    decode_row = {
        'id': f'decode-{int(datetime.utcnow().timestamp())}',
        'action': 'decode_vulnerabilities',
        'input': args.text,
        'location': args.location,
        'decoded_tags': tags,
        'pps_data': STATIC_PPS_FOR_DISPLAY, # Retain this in log for auditing context
        'created_at': timestamp1
    }

    # 3. Route optimal PPS (LLM RAG call)
    print('\n--- Step 3: Routing Optimal PPS ---')
    best, analysis_text, s2, r2 = route_optimal_pps(api_url, pat, tags, args.location)
    print(f'Best match: {best}')

    timestamp2 = datetime.utcnow().isoformat()
    route_row = {
        'id': f'route-{int(datetime.utcnow().timestamp())}',
        'action': 'route_optimal_pps',
        'input_tags': tags,
        'location': args.location,
        'selected_pps': best,
        'analysis_text': analysis_text,
        'pps_data': STATIC_PPS_FOR_DISPLAY, # Retain this in log for auditing context
        'created_at': timestamp2
    }

    # 4. Log all results (Decode + Route)
    log_workflow_results(pat, project_id, api_url, table_api_url, decode_row, route_row)
    
    print('\n--- Workflow Finished ---')
    if best:
        print(f'SUCCESS: Recommended PPS is {best}')
    else:
        print('WARNING: Could not determine the best match.')


if __name__ == '__main__':
    main()