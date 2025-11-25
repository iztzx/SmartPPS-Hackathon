#!/usr/bin/env python3
"""
JamAI Full Emergency Workflow with Diagnostics.

This script performs 5 steps:
1. CREATE the 'emergency_routing' Action Table (using Management API URL derived from JAMAI_API_URL).
2. Upload SOP knowledge to the table (RAG setup).
3. Decode user input (LLM Call 1).
4. Route optimal PPS using RAG grounded on 'pps_knowledge' and SOPs (LLM Call 2).
5. Log all results to the 'emergency_routing' table.

CRITICAL: If table creation or decoding fails, it means the URL derivation or the PAT is invalid.

Usage (If using environment variables, these will override the script's defaults):
  $env:JAMAI_PAT = '...'
  $env:JAMAI_PROJECT_ID = 'proj_xxx'
  $env:JAMAI_API_URL = 'https://api.jamaibase.com/v1/generate/content'
  
  python full_workflow_diagnostics.py --text "4 people, one bedridden, one cat"
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

# --- Configuration Defaults (From user's config.js) ---
# NOTE: These can be overridden by environment variables (JAMAI_PAT, JAMAI_PROJECT_ID, JAMAI_API_URL)
DEFAULT_JAMAI_PAT = "jamai_pat_2e78e7a9f44d66ca4726d3520eb04477d7c02260745203df"
DEFAULT_JAMAI_PROJECT_ID = "myid"
DEFAULT_JAMAI_API_URL = 'https://api.jamaibase.com/v1/generate/content'

# --- Shared Data ---
STATIC_PPS_FOR_DISPLAY = [
    { 'id': 1, 'name': 'PPS North (Sekolah)', 'distance_km': 1.0, 'features': '2nd floor classrooms only, No lift', 'constraints': 'Cannot accommodate bedridden patients (stairs).'},
    { 'id': 2, 'name': 'PPS Central (Dewan)', 'distance_km': 2.0, 'features': 'Ground floor access, Ample parking', 'constraints': "Strict 'No Animals' policy."},
    { 'id': 3, 'name': 'PPS South (Kolej)', 'distance_km': 4.0, 'features': 'OKU toilets, Designated outdoor pet area, Ground floor halls', 'constraints': 'None relevant to standard needs.'}
]

SOP_KNOWLEDGE = (
    "Standard Operating Procedures for Malaysian Flood Mitigation (summary):\n"
    "1) Monitor official weather and agensi kerajaan updates; follow evacuation orders immediately.\n"
    "2) Prioritise evacuation of vulnerable persons: elderly, bedridden, infants, pregnant women, and persons with disabilities (OKU).\n"
    "3) Pets: declare animals at registration; some PPS allow pets in designated areas—bring carriers and food.\n"
    "4) Bring essential documents (ICs), medications, minimal bedding, drinking water, and basic food.\n"
)

# --- Configuration & Utility Functions ---

def get_config():
    """Reads configuration from environment variables, falling back to defaults."""
    pat = os.environ.get('JAMAI_PAT') or DEFAULT_JAMAI_PAT
    project_id = os.environ.get('JAMAI_PROJECT_ID') or DEFAULT_JAMAI_PROJECT_ID
    api_url = os.environ.get('JAMAI_API_URL') or DEFAULT_JAMAI_API_URL
    return pat, project_id, api_url

def make_headers(pat, project_id=None, content_type='application/json'):
    """Creates standard headers for JamAI requests."""
    headers = {'Content-Type': content_type}
    if pat:
        headers['Authorization'] = f'Bearer {pat}'
    if project_id:
        headers['X-PROJECT-ID'] = project_id
        headers['X-Project-Id'] = project_id
    return headers

def call_jamai_api(url, pat, payload, project_id=None, method='POST', timeout=30):
    """Generic function to call JamAI API endpoints."""
    headers = make_headers(pat, project_id)
    try:
        resp = requests.request(method, url, headers=headers, data=json.dumps(payload), timeout=timeout)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return resp.status_code, body
    except Exception as e:
        return None, str(e)

# --- Step 1: Action Table Creation ---

def create_emergency_routing_table(pat, project_id, llm_api_url, table_name='emergency_routing'):
    """
    Attempts to create the Action Table using the JamAI Management API.
    Derives the Management URL from the LLM API URL to ensure consistency.
    """
    print(f'\n--- Step 1: Creating Action Table: {table_name} ---')
    
    # Derivation: Split off the LLM model path (/v1/generate/content) to get the base
    # NOTE: This ensures the Management URL is on the same base domain as the LLM URL.
    base_url_parts = llm_api_url.split('/v1')[0].rstrip('/')
    management_url = f"{base_url_parts}/v1/projects/{project_id}/tables"
    
    # 2. Define the exact Action Table Schema
    # Syntax follows the JamAI SDK Documentation's t.ActionTableSchemaCreate structure translated to JSON.
    schema_payload = {
        'id': table_name,
        'title': 'Emergency Routing Workflow Log',
        'is_action_table': True,
        'cols': [
            {'id': 'id', 'dtype': 'str', 'column_type': 'input'},
            {'id': 'action', 'dtype': 'str', 'column_type': 'input'}, # decode_vulnerabilities, route_optimal_pps, sop_upload
            {'id': 'created_at', 'dtype': 'date-time', 'column_type': 'input'},
            {'id': 'input', 'dtype': 'str', 'column_type': 'input'}, # User's initial free-text
            {'id': 'location', 'dtype': 'str', 'column_type': 'input'},
            {'id': 'input_tags', 'dtype': 'list', 'column_type': 'input'},
            
            # LLM Outputs
            {'id': 'decoded_tags', 'dtype': 'list', 'column_type': 'LLM Output'},
            {'id': 'selected_pps', 'dtype': 'str', 'column_type': 'LLM Output'},
            {'id': 'analysis_text', 'dtype': 'str', 'column_type': 'LLM Output'},
            
            # Python Outputs (For Auditing/SOP content)
            {'id': 'pps_data', 'dtype': 'json', 'column_type': 'Python Output'},
            {'id': 'text', 'dtype': 'str', 'column_type': 'Python Output'} # Used for SOP content
        ]
    }
    
    print(f'Attempting POST table schema to Management URL: {management_url}')
    status, body = call_jamai_api(management_url, pat, schema_payload, project_id, method='POST')
    
    if status in [200, 201]:
        print(f'✅ Action Table "{table_name}" created successfully.')
        return True
    elif status == 409: # Conflict: Table already exists
        print(f'⚠️ Action Table "{table_name}" already exists (Status 409). Skipping creation.')
        return True
    else:
        print(f'❌ CRITICAL TABLE CREATION FAILED. Status: {status}. Check PAT and Management URL.')
        print(f'   Target URL: {management_url}')
        print(f'   Raw Response: {body}')
        sys.exit(1)

# --- Step 2, 3, 4, 5: Workflow and Logging ---

def upload_sop_knowledge(pat, project_id, llm_api_url):
    """Uploads SOP as a RAG source into the emergency_routing table."""
    print('\n--- Step 2: Uploading SOP Knowledge (RAG Source) ---')

    # Derive Add Rows URL
    base_url_parts = llm_api_url.split('/v1')[0].rstrip('/')
    add_rows_url = f"{base_url_parts}/api/v2/gen_tables/action/rows/add"
    
    sop_row = {
        'id': f'sop-{int(datetime.utcnow().timestamp())}',
        'action': 'sop_upload',
        'title': 'Malaysian Flood SOP (summary)',
        'text': SOP_KNOWLEDGE, # This 'text' field is the RAG source
        'source': 'safe-route-workflow',
        'created_at': datetime.utcnow().isoformat()
    }
    
    payload = {
        'table_id': 'emergency_routing',
        'data': [sop_row],
        'stream': False,
        'concurrent': False
    }

    print(f'Attempting POST SOP row to Add Rows URL: {add_rows_url}')
    status, body = call_jamai_api(add_rows_url, pat, payload, project_id, method='POST')
    
    if status and 200 <= status < 300:
        print(f'✅ SOP upload successful.')
        return True
    else:
        print(f'❌ SOP upload failed. Status: {status}. Raw Response: {body}')
        return False

def decode_vulnerabilities(api_url, pat, text):
    """LLM Call 1: Decodes user text into tags."""
    print('\n--- Step 3: Decoding Vulnerabilities (LLM Call) ---')
    system = { 'parts': [{ 'text': 'You are a data decoder using Qwen3-VL. Provide only a comma-separated list of standardized tags (e.g., "4 Pax, Bedridden, Pet/Cat").' }] }
    contents = [{ 'parts': [{ 'text': f'Action: decode_vulnerabilities\nUser Input: "{text}"' }] }]
    payload = { 'systemInstruction': system, 'contents': contents, 'model': 'qwen3-vl' }
    
    status, result = call_jamai_api(api_url, pat, payload)
    decoded_text = ''
    if status and 200 <= status < 300 and isinstance(result, dict):
        decoded_text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
    
    tags = [t.strip() for t in decoded_text.split(',') if t.strip()]
    
    if not tags:
        print(f"Decoding failed or returned empty result. Status: {status}. Raw: {result}")
        tags = ['Decoding Failed'] 
        
    return tags, decoded_text, status, result

def route_optimal_pps(api_url, pat, tags, location_str='Unknown'):
    """LLM Call 2: Routes PPS using RAG grounded on 'pps_knowledge' and SOPs."""
    print('\n--- Step 4: Routing Optimal PPS (LLM RAG Call) ---')
    system_prompt = (
        'You are an emergency management AI using Qwen3-VL with RAG. '
        '**Query the pps_knowledge table** and the SOP knowledge (from emergency_routing table) to ground your recommendations. '
        'Analyze user needs and constraints from the RAG sources. Select the best-suited PPS. '
        'Provide reasoning and end with "BEST MATCH: <PPS name>".'
    )
    user_query = f"User Needs: {'; '.join(tags)}. Location: {location_str}. Query pps_knowledge table and SOP knowledge for available PPS centers and select the best match."
    
    payload = { 'systemInstruction': { 'parts': [{ 'text': system_prompt }] }, 'contents': [{ 'parts': [{ 'text': user_query }] }], 'model': 'qwen3-vl' }
    
    status, result = call_jamai_api(api_url, pat, payload)
    full_text = ''
    best = None
    
    if status and 200 <= status < 300 and isinstance(result, dict):
        full_text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        
        for line in full_text.splitlines()[::-1]:
            if line.strip().upper().startswith('BEST MATCH:'):
                best = line.split(':',1)[1].strip()
                break
    
    if not best:
        print(f"Routing failed or best match not parsed. Status: {status}")

    return best, full_text, status, result

def log_workflow_results(pat, project_id, llm_api_url, decode_row, route_row):
    """Logs the results of the decode and route actions."""
    print('\n--- Step 5: Logging Workflow Results ---')
    
    base_url_parts = llm_api_url.split('/v1')[0].rstrip('/')
    add_rows_url = f"{base_url_parts}/api/v2/gen_tables/action/rows/add"

    rows_to_log = [decode_row, route_row]
    payload = {
        'table_id': 'emergency_routing',
        'data': rows_to_log,
        'stream': False,
        'concurrent': False
    }
    
    print(f'Attempting POST results to: {add_rows_url}')
    status, body = call_jamai_api(add_rows_url, pat, payload, project_id, method='POST')

    if status and 200 <= status < 300:
        print(f'✅ Workflow results logged successfully.')
        return True
    else:
        print(f'❌ Failed to log workflow results. Status: {status}. Raw Response: {body}')
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--text', '-t', required=True, help='User free-text describing situation')
    parser.add_argument('--location', '-l', default='Unknown', help='Optional location string')
    args = parser.parse_args()

    pat, project_id, api_url = get_config()
    
    if not all([pat, project_id, api_url]):
        print('CRITICAL ERROR: Set JAMAI_PAT, JAMAI_PROJECT_ID, and JAMAI_API_URL environment variables or ensure they are set as defaults in the script.', file=sys.stderr)
        sys.exit(2)

    # 1. Create Action Table (will exit if failure is detected)
    create_emergency_routing_table(pat, project_id, api_url)
         
    # 2. Upload SOP knowledge (RAG setup)
    upload_sop_knowledge(pat, project_id, api_url)

    # 3. Decode vulnerabilities (LLM Call 1)
    tags, _, s1, _ = decode_vulnerabilities(api_url, pat, args.text)

    timestamp1 = datetime.utcnow().isoformat()
    decode_row = {
        'id': f'decode-{int(datetime.utcnow().timestamp())}-1',
        'action': 'decode_vulnerabilities',
        'input': args.text,
        'location': args.location,
        'decoded_tags': tags,
        'pps_data': STATIC_PPS_FOR_DISPLAY,
        'created_at': timestamp1
    }

    # 4. Route optimal PPS (LLM Call 2 - RAG)
    best, analysis_text, s2, _ = route_optimal_pps(api_url, pat, tags, args.location)

    timestamp2 = datetime.utcnow().isoformat()
    route_row = {
        'id': f'route-{int(datetime.utcnow().timestamp())}-2',
        'action': 'route_optimal_pps',
        'input_tags': tags,
        'location': args.location,
        'selected_pps': best,
        'analysis_text': analysis_text,
        'pps_data': STATIC_PPS_FOR_DISPLAY,
        'created_at': timestamp2
    }

    # 5. Log all results
    log_workflow_results(pat, project_id, api_url, decode_row, route_row)
    
    print('\n--- Workflow Finished ---')


if __name__ == '__main__':
    main()